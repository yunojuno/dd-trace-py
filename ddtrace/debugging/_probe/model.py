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
    tags = attr.ib(type=dict, factory=dict, eq=False)
    active = attr.ib(type=bool, default=True, eq=False)
    rate = attr.ib(type=float, default=1.0, eq=False)
    limiter = attr.ib(type=RateLimiter, init=False, repr=False, eq=False)  # type: RateLimiter
    capture = attr.ib(type=CaptureLimits, default=CaptureLimits(), eq=False)  # type: CaptureLimits

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


@attr.s
class ConditionalProbe(Probe):
    """Conditional probe.

    If the condition is ``None``, then this is equivalent to a non-conditional
    probe.
    """

    condition = attr.ib(type=Optional[DslExpression], default=None)  # type: Optional[DslExpression]


@attr.s
class LineProbe(ConditionalProbe):
    source_file = attr.ib(type=Optional[str], default=None, converter=_resolve_source_file)  # type: ignore[misc]
    line = attr.ib(type=Optional[int], default=None)


# TODO: make this an Enum once Python 2 support is dropped.
class MethodLocation(object):
    DEFAULT = "DEFAULT"
    ENTER = "ENTER"
    EXIT = "EXIT"


@attr.s
class FunctionProbe(ConditionalProbe):
    module = attr.ib(type=Optional[str], default=None)
    func_qname = attr.ib(type=Optional[str], default=None)
    evaluate_at = attr.ib(type=Optional[MethodLocation], default=MethodLocation.DEFAULT)


# TODO: make this an Enum once Python 2 support is dropped.
class MetricProbeKind(object):
    COUNTER = "COUNT"
    GAUGE = "GAUGE"
    HISTOGRAM = "HISTOGRAM"
    DISTRIBUTION = "DISTRIBUTION"


@attr.s
class MetricLineProbe(LineProbe):
    kind = attr.ib(type=Optional[str], default=None)
    name = attr.ib(type=Optional[str], default=None)
    value = attr.ib(type=Optional[Callable[[Dict[str, Any]], Any]], default=None)


@attr.s
class TemplateSegment(object):
    str_value = attr.ib(type=Optional[str], default=None)
    expr = attr.ib(type=Optional[str], default=None)
    parsed_expr = attr.ib(type=Optional[Callable[[Dict[str, Any]], Any]], default=None)


@attr.s
class LogLineProbe(LineProbe):
    template = attr.ib(type=Optional[str], default=None)
    segments = attr.ib(type=Optional[List[TemplateSegment]], default=None)


@attr.s
class MetricFunctionProbe(FunctionProbe):
    kind = attr.ib(type=Optional[str], default=None)
    name = attr.ib(type=Optional[str], default=None)


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
class LogLineProbe(LineProbe):
    template = attr.ib(type=Optional[str], default=None)
    segments = attr.ib(type=Optional[List[TemplateSegment]], default=None)


@attr.s
class LogFunctionProbe(FunctionProbe):
    template = attr.ib(type=Optional[str], default=None)
    segments = attr.ib(type=Optional[List[TemplateSegment]], default=None)
