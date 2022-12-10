from inspect import CO_VARARGS
from inspect import CO_VARKEYWORDS
from itertools import islice
from types import FrameType
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import TYPE_CHECKING
from typing import Tuple
from typing import Type

from ddtrace.internal.compat import BUILTIN_CONTAINER_TYPES
from ddtrace.internal.compat import BUILTIN_SIMPLE_TYPES
from ddtrace.internal.compat import CALLABLE_TYPES
from ddtrace.internal.compat import ExcInfoType
from ddtrace.internal.compat import NoneType
from ddtrace.internal.compat import stringify
from ddtrace.internal.safety import _isinstance
from ddtrace.internal.safety import get_slots
from ddtrace.internal.utils.cache import cached


if TYPE_CHECKING:  # pragma: no cover
    from ddtrace.internal.compat import Collection

GetSetDescriptor = type(type.__dict__["__dict__"])  # type: ignore[index]

EXCLUDED_FIELDS = frozenset(["__class__", "__dict__", "__weakref__", "__doc__", "__module__", "__hash__"])


MAXLEVEL = 2
MAXSIZE = 100
MAXLEN = 255
MAXFIELDS = 20


def get_args(frame):
    # type: (FrameType) -> Iterator[Tuple[str, Any]]
    code = frame.f_code
    nargs = code.co_argcount + bool(code.co_flags & CO_VARARGS) + bool(code.co_flags & CO_VARKEYWORDS)
    arg_names = code.co_varnames[:nargs]
    arg_values = (frame.f_locals[name] for name in arg_names)

    return zip(arg_names, arg_values)


def get_locals(frame):
    # type: (FrameType) -> Iterator[Tuple[str, Any]]
    code = frame.f_code
    nargs = code.co_argcount + bool(code.co_flags & CO_VARARGS) + bool(code.co_flags & CO_VARKEYWORDS)
    names = code.co_varnames[nargs:]
    values = (frame.f_locals.get(name) for name in names)

    return zip(names, values)


def get_globals(frame):
    # type: (FrameType) -> Iterator[Tuple[str, Any]]
    nonlocal_names = frame.f_code.co_names
    _globals = globals()

    return ((name, _globals[name]) for name in nonlocal_names if name in _globals)


def safe_getattr(obj, name):
    # type: (Any, str) -> Any
    try:
        return object.__getattribute__(obj, name)
    except Exception as e:
        return e


@cached()
def _has_safe_dict(_type):
    # type: (Type) -> bool
    try:
        return type(object.__getattribute__(_type, "__dict__").get("__dict__")) is GetSetDescriptor
    except AttributeError:
        return False


def _safe_dict(o):
    # type: (Any) -> Dict[str, Any]
    if _has_safe_dict(type(o)):
        return object.__getattribute__(o, "__dict__")
    raise AttributeError("No safe __dict__ attribute")


@cached()
def qualname(_type):
    # type: (Type) -> str
    try:
        return stringify(_type.__qualname__)
    except AttributeError:
        # The logic for implementing qualname in Python 2 is complex, so if we
        # don't have it, we just return the name of the type.
        try:
            return _type.__name__
        except AttributeError:
            return repr(_type)


def _serialize_collection(value, brackets, level, maxsize, maxlen, maxfields):
    # type: (Collection, str, int, int, int, int) -> str
    o, c = brackets[0], brackets[1]
    ellipsis = ", ..." if len(value) > maxsize else ""
    return "".join(
        (o, ", ".join(serialize(_, level - 1, maxsize, maxlen, maxfields) for _ in islice(value, maxsize)), ellipsis, c)
    )


def serialize(value, level=MAXLEVEL, maxsize=MAXSIZE, maxlen=MAXLEN, maxfields=MAXFIELDS):
    # type: (Any, int, int, int, int) -> str
    """Python object serializer.

    We provide our own serializer to avoid any potential side effects of calling
    ``str`` directly on arbitrary objects.
    """

    if _isinstance(value, CALLABLE_TYPES):
        return object.__repr__(value)

    if type(value) in BUILTIN_SIMPLE_TYPES:
        r = repr(value)
        return "".join((r[:maxlen], "..." + ("'" if r[0] == "'" else "") if len(r) > maxlen else ""))

    if not level:
        return repr(type(value))

    if type(value) not in BUILTIN_CONTAINER_TYPES:
        return (
            type(value).__name__
            + "("
            + ", ".join(
                [
                    "=".join((k, serialize(v, level - 1, maxsize, maxlen, maxfields)))
                    for k, v in list(get_fields(value).items())[:maxfields]
                ]
            )
            + ")"
        )

    if type(value) is dict:
        return (
            "{"
            + ", ".join(
                [
                    ": ".join((serialize(k, level - 1, maxsize, maxlen, maxfields), serialize(v, level - 1)))
                    for k, v in value.items()
                ]
            )
            + "}"
        )
    elif type(value) is list:
        return _serialize_collection(value, "[]", level, maxsize, maxlen, maxfields)
    elif type(value) is tuple:
        return _serialize_collection(value, "()", level, maxsize, maxlen, maxfields)
    elif type(value) is set:
        return _serialize_collection(value, r"{}", level, maxsize, maxlen, maxfields) if value else "set()"

    raise TypeError("Unhandled type: %s", type(value))


def get_fields(obj):
    # type: (Any) -> Dict[str, Any]
    try:
        return _safe_dict(obj)
    except AttributeError:
        # Check for slots
        return {s: safe_getattr(obj, s) for s in get_slots(obj)}


def capture_stack(top_frame, max_height=4096):
    # type: (FrameType, int) -> List[dict]
    frame = top_frame  # type: Optional[FrameType]
    stack = []
    h = 0
    while frame and h < max_height:
        code = frame.f_code
        stack.append(
            {
                "fileName": code.co_filename,
                "function": code.co_name,
                "lineNumber": frame.f_lineno,
            }
        )
        frame = frame.f_back
        h += 1
    return stack


def capture_exc_info(exc_info):
    # type: (ExcInfoType) -> Optional[Dict[str, Any]]
    _type, value, tb = exc_info
    if _type is None or value is None:
        return None

    top_tb = tb
    if top_tb is not None:
        while top_tb.tb_next is not None:
            top_tb = top_tb.tb_next

    return {
        "type": _type.__name__,
        "message": ", ".join([serialize(v) for v in value.args]),
        "stacktrace": capture_stack(top_tb.tb_frame) if top_tb is not None else None,
    }


def capture_value(value, level=MAXLEVEL, maxlen=MAXLEN, maxsize=MAXSIZE, maxfields=MAXFIELDS):
    # type: (Any, int, int, int, int) -> Dict[str, Any]
    _type = type(value)

    if _type in BUILTIN_SIMPLE_TYPES:
        if _type is NoneType:
            return {"type": "NoneType", "isNull": True}

        value_repr = repr(value)
        value_repr_len = len(value_repr)
        return (
            {
                "type": qualname(_type),
                "value": value_repr,
            }
            if value_repr_len <= maxlen
            else {
                "type": qualname(_type),
                "value": value_repr[:maxlen],
                "truncated": True,
                "size": value_repr_len,
            }
        )

    if _type in BUILTIN_CONTAINER_TYPES:
        if level < 0:
            return {
                "type": qualname(_type),
                "notCapturedReason": "depth",
                "size": len(value),
            }

        if _type is dict:
            # Mapping
            data = {
                "type": "dict",
                "entries": [
                    (
                        capture_value(k, level=level - 1, maxlen=maxlen, maxsize=maxsize, maxfields=maxfields),
                        capture_value(v, level=level - 1, maxlen=maxlen, maxsize=maxsize, maxfields=maxfields),
                    )
                    for _, (k, v) in zip(range(maxsize), value.items())
                ],
                "size": len(value),
            }

        else:
            # Sequence
            data = {
                "type": qualname(_type),
                "elements": [
                    capture_value(v, level=level - 1, maxlen=maxlen, maxsize=maxsize, maxfields=maxfields)
                    for _, v in zip(range(maxsize), value)
                ],
                "size": len(value),
            }

        if len(value) > maxsize:
            data["notCapturedReason"] = "collectionSize"

        return data

    # Arbitrary object
    if level < 0:
        return {
            "type": qualname(_type),
            "notCapturedReason": "depth",
        }

    fields = get_fields(value)
    data = {
        "type": qualname(_type),
        "fields": {
            n: capture_value(v, level=level - 1, maxlen=maxlen, maxsize=maxsize, maxfields=maxfields)
            for _, (n, v) in zip(range(maxfields), fields.items())
        },
    }

    if len(fields) > maxfields:
        data["notCapturedReason"] = "fieldCount"

    return data
