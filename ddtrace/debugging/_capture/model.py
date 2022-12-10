import abc
from threading import Thread
import time
from types import FrameType
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from uuid import uuid4

import attr
import six

from ddtrace.context import Context
from ddtrace.debugging._capture import safe_getter
from ddtrace.debugging._probe.model import ConditionalProbe
from ddtrace.debugging._probe.model import ExpressionEvaluationError


@attr.s
class EvaluationError(object):
    expr = attr.ib(type=str)
    message = attr.ib(type=str)


# TODO: make this an Enum once Python 2 support is dropped.
class CaptureState(object):
    NONE = "NONE"
    SKIP_COND = "SKIP_COND"
    SKIP_COND_ERROR = "SKIP_COND_ERROR"
    SKIP_RATE = "SKIP_RATE"
    COMMIT = "COMMIT"


@attr.s
class CapturedEvent(six.with_metaclass(abc.ABCMeta)):
    """Capture Event baseclass.

    Used to store collected when a probe is triggered.
    """

    probe = attr.ib(type=ConditionalProbe)  # type: ConditionalProbe
    frame = attr.ib(type=FrameType)  # type: FrameType
    thread = attr.ib(type=Thread)

    context = attr.ib(type=Optional[Context], default=None)
    args = attr.ib(type=Optional[List[Tuple[str, Any]]], default=None)
    state = attr.ib(type=str, default=CaptureState.NONE)
    errors = attr.ib(type=List[EvaluationError], factory=lambda: list())
    timestamp = attr.ib(type=float, factory=time.time)
    event_id = attr.ib(type=str, init=False, factory=lambda: str(uuid4()))

    def _evalCondition(self, _locals=None):
        # type: (Optional[Dict[str, Any]]) -> bool
        """Evaluate the probe condition against the collected frame."""
        condition = self.probe.condition
        if condition is None:
            return True

        try:
            if bool(condition.eval(_locals or self.frame.f_locals)):
                return True
        except ExpressionEvaluationError as e:
            self.errors.append(EvaluationError(expr=e.dsl, message=e.error))
            self.state = CaptureState.SKIP_COND_ERROR
        else:
            self.state = CaptureState.SKIP_COND

        return False

    def _enrich_args(self, retval, exc_info, duration):
        _locals = list(self.args or safe_getter.get_args(self.frame))
        _locals.append(("@duration", duration))
        if exc_info[1] is None:
            _locals.append(("@return", retval))
        return dict(_locals)

    @abc.abstractmethod
    def enter(self):
        pass

    @abc.abstractmethod
    def exit(self, retval, exc_info, duration):
        pass

    @abc.abstractmethod
    def line(self, _locals=None, exc_info=(None, None, None)):
        pass
