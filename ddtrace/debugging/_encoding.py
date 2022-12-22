import abc
import json
import os
import sys
from threading import Thread
from types import FrameType
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Type
from typing import Union
from typing import cast

import six

from ddtrace.debugging._capture import safe_getter
from ddtrace.debugging._capture.log_message import LogMessage
from ddtrace.debugging._capture.snapshot import Snapshot
from ddtrace.debugging._capture.snapshot import _captured_context
from ddtrace.debugging._config import config
from ddtrace.debugging._probe.model import FunctionLocationDetails
from ddtrace.debugging._probe.model import LineLocationDetails
from ddtrace.internal import forksafe
from ddtrace.internal._encoding import BufferFull
from ddtrace.internal.logger import get_logger


log = get_logger(__name__)


MAXLEVEL = 2
MAXSIZE = 100
MAXLEN = 255
MAXFIELDS = 20


class JsonBuffer(object):
    def __init__(self, max_size=None):
        self.max_size = max_size
        self._reset()

    def put(self, item):
        # type: (bytes) -> int
        if self._flushed:
            self._reset()

        size = len(item)
        if self.size + size > self.max_size:
            raise BufferFull(self.size, size)

        if self.size > 2:
            self.size += 1
            self._buffer += b","
        self._buffer += item
        self.size += size
        return size

    def _reset(self):
        self.size = 2
        self._buffer = bytearray(b"[")
        self._flushed = False

    def flush(self):
        self._buffer += b"]"
        try:
            return self._buffer
        finally:
            self._flushed = True


class Encoder(six.with_metaclass(abc.ABCMeta)):
    @abc.abstractmethod
    def encode(self, item):
        # type: (Any) -> bytes
        """Encode the given snapshot."""


class BufferedEncoder(six.with_metaclass(abc.ABCMeta)):
    count = 0

    @abc.abstractmethod
    def put(self, item):
        # type: (Any) -> int
        """Enqueue the given item and returns its encoded size."""

    @abc.abstractmethod
    def encode(self):
        # type: () -> Optional[bytes]
        """Encode the given item."""


_EMPTY_CAPTURED_CONTEXT = _captured_context([], [], (None, None, None))


def _snapshot_v2(snapshot):
    # type (Snapshot) -> Dict[str, Any]
    frame = snapshot.frame
    probe = snapshot.probe

    captures = {
        "entry": snapshot.entry_capture or _EMPTY_CAPTURED_CONTEXT,
        "return": snapshot.return_capture or _EMPTY_CAPTURED_CONTEXT,
    }
    if isinstance(probe, LineLocationDetails):
        captures["lines"] = {
            probe.line: snapshot.line_capture or _EMPTY_CAPTURED_CONTEXT,
        }
        location = {
            "file": probe.source_file,
            "lines": [probe.line],
        }
    elif isinstance(probe, FunctionLocationDetails):
        location = {
            "type": probe.module,
            "method": probe.func_qname,
        }
    return {
        "id": snapshot.event_id,
        "timestamp": int(snapshot.timestamp * 1e3),  # milliseconds
        "duration": snapshot.duration,  # nanoseconds
        "stack": safe_getter.capture_stack(frame),
        "captures": captures,
        "probe": {
            "id": probe.probe_id,
            "location": location,
        },
        "language": "python",
    }


def _logger_v2(thread, frame):
    # type: (Thread, FrameType) -> Dict[str, Any]
    code = frame.f_code

    return {
        "name": code.co_filename,
        "method": code.co_name,
        "thread_name": "%s;pid:%d" % (thread.name, os.getpid()),
        "thread_id": thread.ident,
        "version": 2,
    }


def add_tags(payload):
    if not config._tags_in_qs and config.tags:
        payload["ddtags"] = config.tags


def format_captured_value(value):
    # type: (Any) -> str
    v = value.get("value")
    if v is not None:
        return v
    elif value.get("isNull"):
        return "None"

    es = value.get("elements")
    if es is not None:
        return "%s(%s)" % (value["type"], ", ".join(format_captured_value(e) for e in es))

    es = value.get("entries")
    if es is not None:
        return "{%s}" % ", ".join(format_captured_value(k) + ": " + format_captured_value(v) for k, v in es)

    fs = value.get("fields")
    if fs is not None:
        return "%s(%s)" % (value["type"], ", ".join("%s=%s" % (k, format_captured_value(v)) for k, v in fs.items()))

    return "%s()" % value["type"]


def format_message(function, args, retval=None):
    # type: (str, Dict[str, Any], Optional[Any]) -> str
    message = "%s(%s)" % (
        function,
        ", ".join(("=".join((n, format_captured_value(a))) for n, a in args.items())),
    )

    if retval is not None:
        return "\n".join((message, "=".join(("@return", format_captured_value(retval)))))

    return message


def logs_track_upload_snapshot_request_v2(
    service,  # type: str
    snapshot,  # type: Snapshot
    host,  # type: Optional[str]
):
    # type: (...) -> Dict[str, Any]
    snapshot_data = _snapshot_v2(snapshot)
    top_frame = snapshot_data["stack"][0]
    if isinstance(snapshot.probe, LineLocationDetails):
        arguments = list(snapshot_data["captures"]["lines"].values())[0]["arguments"]
        message = format_message(top_frame["function"], arguments)
    elif isinstance(snapshot.probe, FunctionLocationDetails):
        arguments = snapshot_data["captures"]["entry"]["arguments"]
        retval = snapshot.return_capture["locals"].get("@return") if snapshot.return_capture else None
        message = format_message(cast(str, snapshot.probe.func_qname), arguments, retval)
    else:
        message = "snapshot event"

    context = snapshot.context
    payload = {
        "service": service,
        "debugger.snapshot": snapshot_data,
        "host": host,
        "logger": _logger_v2(snapshot.thread, snapshot.frame),
        "dd.trace_id": context.trace_id if context else None,
        "dd.span_id": context.span_id if context else None,
        "ddsource": "dd_debugger",
        "message": message,
        "timestamp": snapshot_data["timestamp"],
    }
    add_tags(payload)

    return payload


def log_track_upload_log_message_request_v2(
    service,  # type: str
    log_msg,  # type: LogMessage
    host,  # type: Optional[str]
):
    probe = log_msg.probe
    if isinstance(probe, LineLocationDetails):
        location = {
            "file": probe.source_file,
            "lines": [probe.line],
        }  # type: Dict
    elif isinstance(probe, FunctionLocationDetails):
        location = {
            "type": probe.module,
            "method": probe.func_qname,
        }
    else:
        location = {}

    snapshot_data = {
        "id": log_msg.event_id,
        "probe": {
            "id": probe.probe_id,
            "location": location,
        },
        "evaluationErrors": [{"expr": e.expr, "message": e.message} for e in log_msg.errors],
        "timestamp": int(log_msg.timestamp * 1e3),  # milliseconds
        "language": "python",
    }

    context = log_msg.context
    payload = {
        "service": service,
        "debugger.snapshot": snapshot_data,
        "host": host,
        "logger": _logger_v2(log_msg.thread, log_msg.frame),
        "dd.trace_id": context.trace_id if context else None,
        "dd.span_id": context.span_id if context else None,
        "ddsource": "dd_debugger",
        "message": log_msg.message,
        "timestamp": snapshot_data["timestamp"],
    }
    add_tags(payload)

    return payload


class SnapshotJsonEncoder(Encoder):
    def __init__(self, service, host=None):
        # type: (str, Optional[str]) -> None
        self._service = service
        self._host = host

    def encode(self, snapshot):
        # type: (Snapshot) -> bytes
        return json.dumps(
            logs_track_upload_snapshot_request_v2(
                service=self._service,
                snapshot=snapshot,
                host=self._host,
            )
        ).encode("utf-8")


class LogMessageJsonEncoder(Encoder):
    def __init__(self, service, host=None):
        # type: (str, Optional[str]) -> None
        self._service = service
        self._host = host

    def encode(self, log_msg):
        # type: (LogMessage) -> bytes
        return json.dumps(
            log_track_upload_log_message_request_v2(
                service=self._service,
                log_msg=log_msg,
                host=self._host,
            )
        ).encode("utf-8")


class BatchJsonEncoder(BufferedEncoder):
    def __init__(self, item_encoders, buffer_size=4 * (1 << 20), on_full=None):
        # type: (Dict[Type, Union[Encoder, Type]], int, Optional[Callable[[Any, bytes], None]]) -> None
        self._encoders = item_encoders
        self._buffer = JsonBuffer(buffer_size)
        self._lock = forksafe.Lock()
        self._on_full = on_full
        self.count = 0
        self.max_size = buffer_size - self._buffer.size

    def put(self, item):
        # type: (Union[Snapshot, str]) -> int
        encoder = self._encoders.get(type(item))
        if encoder is None:
            raise ValueError("No encoder for item type: %r" % type(item))

        return self.put_encoded(item, encoder.encode(item))

    def put_encoded(self, item, encoded):
        # type: (Union[Snapshot, str], bytes) -> int
        try:
            with self._lock:
                size = self._buffer.put(encoded)
                self.count += 1
                return size
        except BufferFull:
            if self._on_full is not None:
                self._on_full(item, encoded)
            six.reraise(*sys.exc_info())

    def encode(self):
        # type: () -> Optional[bytes]
        with self._lock:
            if self.count == 0:
                # Reclaim memory
                self._buffer._reset()
                return None

            encoded = self._buffer.flush()
            self.count = 0
            return encoded
