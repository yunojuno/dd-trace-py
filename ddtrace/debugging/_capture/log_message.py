from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import cast

import attr

from ddtrace.debugging._capture.model import CaptureState
from ddtrace.debugging._capture.model import CapturedEvent
from ddtrace.debugging._capture.model import EvaluationError
from ddtrace.debugging._capture.safe_getter import serialize
from ddtrace.debugging._probe.model import ConstTemplateSegment
from ddtrace.debugging._probe.model import ExpressionEvaluationError
from ddtrace.debugging._probe.model import FunctionLocationDetails
from ddtrace.debugging._probe.model import ProbeEvaluateTimingForMethod
from ddtrace.debugging._probe.model import SnapshotProbeDetails
from ddtrace.debugging._probe.model import TemplateSegment


@attr.s
class LogMessage(CapturedEvent):
    """Raw dynamic log message.

    Used to collect the minimum amount of information from a firing probe.
    """

    segments = attr.ib(type=List[TemplateSegment], default=[])
    message = attr.ib(type=Optional[str], default=None)
    duration = attr.ib(type=Optional[int], default=None)  # nanoseconds

    def _eval_segment(self, segment, _locals):
        # type: (TemplateSegment, Dict[str, Any]) -> str
        probe = cast(SnapshotProbeDetails, self.probe)
        capture = probe.capture
        try:
            if isinstance(segment, ConstTemplateSegment):
                return segment.eval(_locals)
            return serialize(
                segment.eval(_locals),
                level=capture.max_level,
                maxsize=capture.max_size,
                maxlen=capture.max_len,
                maxfields=capture.max_fields,
            )
        except ExpressionEvaluationError as e:
            self.errors.append(EvaluationError(expr=e.dsl, message=e.error))
            return "ERROR"

    def enter(self):
        probe = cast(FunctionLocationDetails, self.probe)

        if probe.evaluate_at == ProbeEvaluateTimingForMethod.EXIT:
            return

        _args = dict(self.args) if self.args else {}
        if not self._evalCondition(_args):
            return

        self.message = "".join([self._eval_segment(s, _args) for s in self.segments])
        self.state = CaptureState.DONE_AND_COMMIT

    def exit(self, retval, exc_info, duration):
        probe = cast(FunctionLocationDetails, self.probe)
        _args = self._enrich_args(retval, exc_info, duration)

        if probe.evaluate_at != ProbeEvaluateTimingForMethod.EXIT:
            return
        if not self._evalCondition(_args):
            return

        self.message = "".join([self._eval_segment(s, _args) for s in self.segments])
        self.duration = duration
        self.state = CaptureState.DONE_AND_COMMIT

    def line(self, _locals=None, exc_info=(None, None, None)):
        frame = self.frame

        if not self._evalCondition(_locals or frame.f_locals):
            return

        self.message = "".join([self._eval_segment(s, _locals or frame.f_locals) for s in self.segments])
        self.state = CaptureState.DONE_AND_COMMIT
