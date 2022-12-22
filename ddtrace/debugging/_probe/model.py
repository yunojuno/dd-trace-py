import abc
from os.path import abspath
from os.path import isfile
from os.path import normcase
from os.path import normpath
from os.path import sep
from os.path import splitdrive
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import attr
import six

from ddtrace.debugging._capture.safe_getter import MAXFIELDS
from ddtrace.debugging._capture.safe_getter import MAXLEN
from ddtrace.debugging._capture.safe_getter import MAXLEVEL
from ddtrace.debugging._capture.safe_getter import MAXSIZE
from ddtrace.internal.logger import get_logger
from ddtrace.internal.module import _resolve
from ddtrace.internal.rate_limiter import BudgetRateLimiterWithJitter as RateLimiter
from ddtrace.internal.utils.cache import cached


log = get_logger(__name__)


def _with_defaults(f, **defaults):
    def _wrapper(*args, **kwargs):
        return f(*args, **defaults, **kwargs)

    return _wrapper


@cached()
def _resolve_source_file(path):
    # type: (str) -> Optional[str]
    """Resolve the source path for the given path.

    This recursively strips parent directories until it finds a file that
    exists according to sys.path.
    """
    npath = abspath(normpath(normcase(path)))
    if isfile(npath):
        return npath

    _, relpath = splitdrive(npath)
    while relpath:
        resolved_path = _resolve(relpath)
        if resolved_path is not None:
            return abspath(resolved_path)
        _, _, relpath = relpath.partition(sep)

    return None


class ExpressionEvaluationError(Exception):
    """Thrown when an error occurs while evaluating a dsl expression."""

    def __init__(self, dsl, e):
        super().__init__('failed to execture expression "' + dsl + '" due: ' + str(e))
        self.dsl = dsl
        self.error = str(e)


@attr.s
class CaptureLimits(object):
    max_level = attr.ib(type=int, default=MAXLEVEL)  # type: int
    max_size = attr.ib(type=int, default=MAXSIZE)  # type: int
    max_len = attr.ib(type=int, default=MAXLEN)  # type: int
    max_fields = attr.ib(type=int, default=MAXFIELDS)  # type: int


@attr.s
class DslExpression(object):
    dsl = attr.ib(type=str, default=None)  # type: str
    callable = attr.ib(type=Callable[[Dict[str, Any]], Any], default=None)  # type: Callable[[Dict[str, Any]], Any]

    def eval(self, _locals):
        try:
            return self.callable(_locals)
        except Exception as e:
            raise ExpressionEvaluationError(self.dsl, e)


@attr.s(hash=True)
class Probe(six.with_metaclass(abc.ABCMeta)):
    probe_id = attr.ib(type=str)
    tags = attr.ib(type=dict, eq=False)
    active = attr.ib(type=bool, eq=False)
    rate = attr.ib(type=float, eq=False)
    limiter = attr.ib(type=RateLimiter, init=False, repr=False, eq=False)  # type: RateLimiter

    def __attrs_post_init__(self):
        self.limiter = RateLimiter(
            limit_rate=self.rate,
            tau=1.0 / self.rate if self.rate else 1.0,
            on_exceed=lambda: log.warning("Rate limit exceeeded for %r", self),
            call_once=True,
            raise_on_exceed=False,
        )

    def activate(self):
        # type: () -> None
        """Activate the probe."""
        self.active = True

    def deactivate(self):
        # type: () -> None
        """Deactivate the probe."""
        self.active = False


def create_probe_defaults(f):
    def _wrapper(*args, **kwargs):
        kwargs.setdefault("tags", dict())
        kwargs.setdefault("active", True)
        kwargs.setdefault("rate", 1.0)
        return f(*args, **kwargs)

    return _wrapper


@attr.s
class ProbeConditionDetails(six.with_metaclass(abc.ABCMeta)):
    """Conditional probe.

    If the condition is ``None``, then this is equivalent to a non-conditional
    probe.
    """

    condition = attr.ib(type=Optional[DslExpression])  # type: Optional[DslExpression]


def probe_conditional_defaults(f):
    def _wrapper(*args, **kwargs):
        kwargs.setdefault("condition", None)
        return f(*args, **kwargs)

    return _wrapper


@attr.s
class LineLocationDetails(six.with_metaclass(abc.ABCMeta)):
    source_file = attr.ib(type=Optional[str], converter=_resolve_source_file)  # type: ignore[misc]
    line = attr.ib(type=Optional[int])


# TODO: make this an Enum once Python 2 support is dropped.
class ProbeEvaluateTimingForMethod(object):
    DEFAULT = "DEFAULT"
    ENTER = "ENTER"
    EXIT = "EXIT"


@attr.s
class FunctionLocationDetails(six.with_metaclass(abc.ABCMeta)):
    module = attr.ib(type=Optional[str])
    func_qname = attr.ib(type=Optional[str])
    evaluate_at = attr.ib(type=Optional[ProbeEvaluateTimingForMethod])


def function_location_defaults(f):
    def _wrapper(*args, **kwargs):
        kwargs.setdefault("evaluate_at", ProbeEvaluateTimingForMethod.DEFAULT)
        return f(*args, **kwargs)

    return _wrapper


# TODO: make this an Enum once Python 2 support is dropped.
class MetricProbeKind(object):
    COUNTER = "COUNT"
    GAUGE = "GAUGE"
    HISTOGRAM = "HISTOGRAM"
    DISTRIBUTION = "DISTRIBUTION"


@attr.s
class MetricProbeDetails(six.with_metaclass(abc.ABCMeta)):
    kind = attr.ib(type=Optional[str])
    name = attr.ib(type=Optional[str])
    value = attr.ib(type=Optional[Callable[[Dict[str, Any]], Any]])


def metric_probe_defaults(f):
    def _wrapper(*args, **kwargs):
        kwargs.setdefault("value", None)
        return f(*args, **kwargs)

    return _wrapper


@attr.s
class MetricLineProbe(Probe, ProbeConditionDetails, LineLocationDetails, MetricProbeDetails):
    @classmethod
    @create_probe_defaults
    @probe_conditional_defaults
    @metric_probe_defaults
    def create(cls, **kwargs):
        return MetricLineProbe(**kwargs)


@attr.s
class MetricFunctionProbe(Probe, ProbeConditionDetails, FunctionLocationDetails, MetricProbeDetails):
    @classmethod
    @create_probe_defaults
    @probe_conditional_defaults
    @function_location_defaults
    @metric_probe_defaults
    def create(cls, **kwargs):
        return MetricLineProbe(**kwargs)


@attr.s
class TemplateSegment(six.with_metaclass(abc.ABCMeta)):
    @abc.abstractmethod
    def eval(self, _locals):
        # type: (Dict[str,Any]) -> str
        pass


@attr.s
class ConstTemplateSegment(TemplateSegment):
    str_value = attr.ib(type=str, default=None)

    def eval(self, _locals):
        # type: (Dict[str,Any]) -> Any
        return self.str_value


@attr.s
class ExpressionTemplateSegment(TemplateSegment):
    expr = attr.ib(type=DslExpression, default=None)  # type: DslExpression

    def eval(self, _locals):
        # type: (Dict[str,Any]) -> Any
        return self.expr.eval(_locals)


@attr.s
class SnapshotProbeDetails(six.with_metaclass(abc.ABCMeta)):
    capture = attr.ib(type=CaptureLimits, eq=False)  # type: CaptureLimits


def snapshot_probe_defaults(f):
    def _wrapper(*args, **kwargs):
        kwargs.setdefault("capture", CaptureLimits())
        return f(*args, **kwargs)

    return _wrapper


@attr.s
class SnapshotLineProbe(Probe, ProbeConditionDetails, LineLocationDetails, SnapshotProbeDetails):
    @classmethod
    @create_probe_defaults
    @probe_conditional_defaults
    @snapshot_probe_defaults
    def create(cls, **kwargs):
        return SnapshotLineProbe(**kwargs)


@attr.s
class SnapshotFunctionProbe(Probe, ProbeConditionDetails, FunctionLocationDetails, SnapshotProbeDetails):
    @classmethod
    @create_probe_defaults
    @probe_conditional_defaults
    @function_location_defaults
    @snapshot_probe_defaults
    def create(cls, **kwargs):
        return SnapshotFunctionProbe(**kwargs)


@attr.s
class LogProbeDetails(six.with_metaclass(abc.ABCMeta)):
    template = attr.ib(type=Optional[str])
    segments = attr.ib(type=Optional[List[TemplateSegment]])


@attr.s
class LogLineProbe(Probe, ProbeConditionDetails, LineLocationDetails, LogProbeDetails, SnapshotProbeDetails):
    @classmethod
    @create_probe_defaults
    @probe_conditional_defaults
    @snapshot_probe_defaults
    def create(cls, **kwargs):
        return LogLineProbe(**kwargs)


@attr.s
class LogFunctionProbe(Probe, ProbeConditionDetails, FunctionLocationDetails, LogProbeDetails, SnapshotProbeDetails):
    @classmethod
    @create_probe_defaults
    @probe_conditional_defaults
    @function_location_defaults
    @snapshot_probe_defaults
    def create(cls, **kwargs):
        return LogFunctionProbe(**kwargs)


LineProbes = Union[SnapshotLineProbe, LogLineProbe, MetricLineProbe]
FunctionProbes = Union[SnapshotFunctionProbe, LogFunctionProbe, MetricFunctionProbe]
