from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import cast

import attr

from ddtrace.debugging._capture import safe_getter
from ddtrace.debugging._capture.model import CaptureState
from ddtrace.debugging._capture.model import CapturedEvent
from ddtrace.debugging._probe.model import CaptureLimits
from ddtrace.debugging._probe.model import ProbeEvaluateTimingForMethod
from ddtrace.debugging._probe.model import SnapshotFunctionProbe
from ddtrace.debugging._probe.model import SnapshotLineProbe
from ddtrace.internal.compat import ExcInfoType
from ddtrace.internal.rate_limiter import RateLimitExceeded


def _captured_context(
    arguments,  # type: List[Tuple[str, Any]]
    _locals,  # type: List[Tuple[str, Any]]
    throwable,  # type: ExcInfoType
    limits=CaptureLimits(),  # type: CaptureLimits
):
    # type: (...) -> Dict[str, Any]
    return {
        "arguments": {
            n: safe_getter.capture_value(v, limits.max_level, limits.max_len, limits.max_size, limits.max_fields)
            for n, v in arguments
        }
        if arguments is not None
        else {},
        "locals": {
            n: safe_getter.capture_value(v, limits.max_level, limits.max_len, limits.max_size, limits.max_fields)
            for n, v in _locals
        }
        if _locals is not None
        else {},
        "throwable": safe_getter.capture_exc_info(throwable),
    }


@attr.s
class Snapshot(CapturedEvent):
    """Raw snapshot.

    Used to collect the minimum amount of information from a firing probe.
    """

    entry_capture = attr.ib(type=Optional[dict], default=None)
    return_capture = attr.ib(type=Optional[dict], default=None)
    line_capture = attr.ib(type=Optional[dict], default=None)

    duration = attr.ib(type=Optional[int], default=None)  # nanoseconds

    def enter(self):
        frame = self.frame
        probe = cast(SnapshotFunctionProbe, self.probe)
        _args = list(self.args or safe_getter.get_args(frame))

        if probe.evaluate_at == ProbeEvaluateTimingForMethod.EXIT:
            return

        if not self._evalCondition(dict(_args)):
            return

        if probe.limiter.limit() is RateLimitExceeded:
            self.state = CaptureState.SKIP_RATE
            return

        self.entry_capture = _captured_context(
            _args,
            [],
            (None, None, None),
            limits=probe.limits,
        )

    def exit(self, retval, exc_info, duration):
        probe = cast(SnapshotFunctionProbe, self.probe)
        _args = self._enrich_args(retval, exc_info, duration)

        if probe.evaluate_at == ProbeEvaluateTimingForMethod.EXIT:
            if not self._evalCondition(_args):
                return
            if probe.limiter.limit() is RateLimitExceeded:
                self.state = CaptureState.SKIP_RATE
                return
        elif self.state != CaptureState.NONE:
            return

        _locals = []
        if exc_info[1] is None:
            _locals.append(("@return", retval))

        self.return_capture = _captured_context(
            self.args or safe_getter.get_args(self.frame), _locals, exc_info, limits=probe.limits
        )
        self.duration = duration
        self.state = CaptureState.DONE_AND_COMMIT

    def line(self, _locals=None, exc_info=(None, None, None)):
        frame = self.frame
        probe = cast(SnapshotLineProbe, self.probe)

        if not self._evalCondition(frame.f_locals):
            return

        if probe.limiter.limit() is RateLimitExceeded:
            self.state = CaptureState.SKIP_RATE
            return

        self.line_capture = _captured_context(
            self.args or safe_getter.get_args(frame),
            _locals or safe_getter.get_locals(frame),
            exc_info,
            limits=probe.limits,
        )
        self.state = CaptureState.DONE_AND_COMMIT
