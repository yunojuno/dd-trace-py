from functools import partial
from typing import TYPE_CHECKING

from opentelemetry.context.context import Context as OtelContext
from opentelemetry.trace import NonRecordingSpan as OtelNonRecordingSpan
from opentelemetry.trace import Span as OtelSpan
from opentelemetry.trace import SpanContext as OtelSpanContext
import opentelemetry.version

from ddtrace.internal.utils.version import parse_version


if TYPE_CHECKING:
    from ddtrace import Tracer as DDTracer


if parse_version(opentelemetry.version.__version__) < (1, 4):
    # In opentelemetry.trace.use_span() SPAN_KEY is used to add Spans to a Context Dictionary.
    # This context dictionary is then used to activate and get the current span.
    # To fully support the otel api we must use SPAN_KEY to add otel spans to otel context objects.
    # https://github.com/open-telemetry/opentelemetry-python/blob/v1.15.0/opentelemetry-api/src/opentelemetry/trace/__init__.py#L571
    from opentelemetry.trace.propagation import SPAN_KEY as _DDOTEL_SPAN_KEY
else:
    # opentelemetry-api>=1.4 uses _SPAN_KEY to store spans in the Context Dictionary
    from opentelemetry.trace.propagation import _SPAN_KEY as _DDOTEL_SPAN_KEY

from ddtrace.context import Context as DDContext
from ddtrace.internal.utils import get_argument_value
from ddtrace.opentelemetry.span import Span
from ddtrace.vendor.wrapt import wrap_function_wrapper as _w


def _dd_runtime_context_attach(ddtracer, wrapped, instance, args, kwargs):
    # type: (...) -> object
    """Gets an otel span from the context object, and activates the corresponding
    datadog span or datadog context object.
    """
    otel_context = get_argument_value(args, kwargs, 0, "context")  # type: OtelContext
    # Get Otel Span from the context object. Otelspan can be none if the context
    # only contains baggage or some other propagated object.
    # Note - _DDOTEL_SPAN_KEY is used by
    otel_span = otel_context.get(_DDOTEL_SPAN_KEY, None)

    if otel_span:
        if isinstance(otel_span, Span):
            ddtracer.context_provider.activate(otel_span._ddspan)
        elif isinstance(otel_span, OtelSpan):
            trace_id, span_id, *_ = otel_span.get_span_context()
            ddcontext = DDContext(trace_id, span_id)
            ddtracer.context_provider.activate(ddcontext)
        else:
            # Update this codeblock to support baggage
            raise ValueError("The following span is not compatible with ddtrace: %s" % (otel_context,))

    return object()


def _dd_runtime_context_get_current(ddtracer, wrapped, instance, args, kwargs):
    # type: (...) -> OtelContext
    """Converts the active datadog span to an Opentelemetry Span and then stores it an OtelContext
    in a format that can be parsed bu the OpenTelemetry API
    """
    ddactive = ddtracer.context_provider.active()
    if ddactive is None:
        return OtelContext()
    elif isinstance(ddactive, DDContext):
        otel_span_context = OtelSpanContext(ddactive.trace_id, ddactive.span_id, True)
        return OtelContext({_DDOTEL_SPAN_KEY: OtelNonRecordingSpan(otel_span_context)})
    else:
        # ddactive is a datadog span, create a new otel span using the active datadog span
        return OtelContext({_DDOTEL_SPAN_KEY: Span(ddactive)})


def _dd_runtime_context_detach(wrapped, instance, args, kwargs):
    # type: (...) -> None
    """NOOP, datadog context provider does not support manual deactivation"""
    pass


def wrap_otel_context(tracer):
    # type: (DDTracer) -> None
    """wraps the default Otel Context Manager. Warning ContextVarsRuntimeContext can be overridden by setting"""
    _w(
        "opentelemetry.context.contextvars_context",
        "ContextVarsRuntimeContext.attach",
        partial(_dd_runtime_context_attach, tracer),
    )
    _w(
        "opentelemetry.context.contextvars_context",
        "ContextVarsRuntimeContext.get_current",
        partial(_dd_runtime_context_get_current, tracer),
    )
    _w("opentelemetry.context.contextvars_context", "ContextVarsRuntimeContext.detach", _dd_runtime_context_detach)
