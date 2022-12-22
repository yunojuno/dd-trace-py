import inspect
import threading
from typing import Optional
from uuid import uuid4

import attr
import mock

from ddtrace.debugging._capture.collector import CapturedEventCollector
from ddtrace.debugging._capture.model import CaptureState
from ddtrace.debugging._capture.snapshot import Snapshot
from ddtrace.debugging._probe.model import CaptureLimits
from ddtrace.debugging._probe.model import DslExpression


class MockLimiter:
    def limit(self):
        return


@attr.s
class MockProbe(object):
    probe_id = attr.ib(type=str)
    condition = attr.ib(type=Optional[DslExpression])
    limiter = attr.ib(factory=MockLimiter)
    limits = CaptureLimits()


@attr.s
class MockFrame(object):
    f_locals = attr.ib(type=dict)


@attr.s
class MockThread(object):
    ident = attr.ib(type=int)
    name = attr.ib(type=str)


def mock_encoder(wraps=None):
    encoder = mock.Mock(wraps=wraps)
    snapshot_encoder = mock.Mock()
    encoder._encoders = {Snapshot: snapshot_encoder}

    return encoder, snapshot_encoder


def test_collector_cond():
    encoder, _ = mock_encoder()

    collector = CapturedEventCollector(encoder=encoder)

    snapshot1 = Snapshot(
        probe=MockProbe(uuid4(), DslExpression("a not null", lambda _: _["a"] is not None)),
        frame=MockFrame(dict(a=42)),
        args=[("a", 42)],
        thread=MockThread(-1, "MainThread"),
    )
    snapshot1.line([("c", True)])
    collector.push(snapshot1)

    snapshot2 = Snapshot(
        probe=MockProbe(uuid4(), DslExpression("b not null", lambda _: _["b"] is not None)),
        frame=MockFrame(dict(b=None)),
        args=[("b", None)],
        thread=MockThread(-2, "WorkerThread"),
    )
    snapshot2.line([("c", True)])
    collector.push(snapshot2)

    encoder.put.assert_called_once()


def test_collector_collect_enqueue_only_commit_state():
    encoder, _ = mock_encoder()

    collector = CapturedEventCollector(encoder=encoder)
    for i in range(10):
        mockedEvent = mock.Mock()
        with collector.attach(mockedEvent):
            mockedEvent.enter.assert_called_once()
            mockedEvent.state = CaptureState.DONE_AND_COMMIT if i % 2 == 0 else CaptureState.SKIP_COND
        mockedEvent.exit.assert_called_once()

    assert len(encoder.put.mock_calls) == 5


def test_collector_push_enqueue():
    encoder, _ = mock_encoder()

    collector = CapturedEventCollector(encoder=encoder)
    for _ in range(10):
        snapshot = Snapshot(
            probe=MockProbe(uuid4(), None),
            frame=inspect.currentframe(),
            thread=threading.current_thread(),
        )
        snapshot.line()
        collector.push(snapshot)

    assert len(encoder.put.mock_calls) == 10
