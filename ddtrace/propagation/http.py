from typing import Dict
from typing import FrozenSet
from typing import Optional

from ddtrace import config

from ..constants import AUTO_KEEP
from ..constants import AUTO_REJECT
from ..constants import PROPAGATION_STYLE_B3
from ..constants import PROPAGATION_STYLE_B3_SINGLE_HEADER
from ..constants import PROPAGATION_STYLE_DATADOG
from ..constants import USER_KEEP
from ..context import Context
from ..internal.logger import get_logger
from ._utils import get_wsgi_header


log = get_logger(__name__)

# HTTP headers one should set for distributed tracing.
# These are cross-language (eg: Python, Go and other implementations should honor these)
HTTP_HEADER_TRACE_ID = "x-datadog-trace-id"
HTTP_HEADER_PARENT_ID = "x-datadog-parent-id"
HTTP_HEADER_SAMPLING_PRIORITY = "x-datadog-sampling-priority"
HTTP_HEADER_ORIGIN = "x-datadog-origin"
HTTP_HEADER_B3_SINGLE = "b3"
HTTP_HEADER_B3_TRACE_ID = "x-b3-traceid"
HTTP_HEADER_B3_SPAN_ID = "x-b3-spanid"
HTTP_HEADER_B3_SAMPLED = "x-b3-sampled"
HTTP_HEADER_B3_FLAGS = "x-b3-flags"


def _possible_header(header):
    # type: (str) -> frozenset[str]
    return frozenset([header, get_wsgi_header(header).lower()])


# Note that due to WSGI spec we have to also check for uppercased and prefixed
# versions of these headers
POSSIBLE_HTTP_HEADER_TRACE_IDS = _possible_header(HTTP_HEADER_TRACE_ID)
POSSIBLE_HTTP_HEADER_PARENT_IDS = _possible_header(HTTP_HEADER_PARENT_ID)
POSSIBLE_HTTP_HEADER_SAMPLING_PRIORITIES = _possible_header(HTTP_HEADER_SAMPLING_PRIORITY)
POSSIBLE_HTTP_HEADER_ORIGIN = _possible_header(HTTP_HEADER_ORIGIN)
POSSIBLE_HTTP_HEADER_B3_SINGLE_HEADER = _possible_header(HTTP_HEADER_B3_SINGLE)
POSSIBLE_HTTP_HEADER_B3_TRACE_IDS = _possible_header(HTTP_HEADER_B3_TRACE_ID)
POSSIBLE_HTTP_HEADER_B3_SPAN_IDS = _possible_header(HTTP_HEADER_B3_SPAN_ID)
POSSIBLE_HTTP_HEADER_B3_SAMPLEDS = _possible_header(HTTP_HEADER_B3_SAMPLED)
POSSIBLE_HTTP_HEADER_B3_FLAGS = _possible_header(HTTP_HEADER_B3_FLAGS)


def _extract_header_value(possible_header_names, headers, default=None):
    # type: (FrozenSet[str], Dict[str, str], Optional[str]) -> Optional[str]
    for header in possible_header_names:
        try:
            return headers[header]
        except KeyError:
            pass

    return default


def _normalize_headers(headers):
    # type: (Dict[str, str]) -> Dict[str, str]
    return {name.lower(): v for name, v in headers.items()}


def _b3_id_to_dd_id(b3_id):
    # type: (str) -> int
    """Helper to convert B3 trace/span hex ids into Datadog compatible ints

    If the id is > 64 bit then truncate the trailing 64 bit.

    "463ac35c9f6413ad48485a3953bb6124" -> "48485a3953bb6124" -> 5208512171318403364
    """
    if len(b3_id) > 16:
        return int(b3_id[-16:], 16)
    return int(b3_id, 16)


def _dd_id_to_b3_id(dd_id):
    # type: (int) -> str
    """Helper to convert Datadog trace/span int ids into B3 compatible hex ids"""
    # DEV: `hex(dd_id)` will give us `0xDEADBEEF`
    # DEV: this gives us lowercase hex, which is what we want
    return "{:x}".format(dd_id)


def _inject_datadog(span_context, headers):
    # type: (Context, Dict[str, str]) -> None
    headers[HTTP_HEADER_TRACE_ID] = str(span_context.trace_id)
    headers[HTTP_HEADER_PARENT_ID] = str(span_context.span_id)
    sampling_priority = span_context.sampling_priority
    # Propagate priority only if defined
    if sampling_priority is not None:
        headers[HTTP_HEADER_SAMPLING_PRIORITY] = str(span_context.sampling_priority)
    # Propagate origin only if defined
    if span_context.dd_origin is not None:
        headers[HTTP_HEADER_ORIGIN] = str(span_context.dd_origin)


def _extract_datadog(headers):
    # type: (Dict[str, str]) -> Optional[Context]
    # TODO: Fix variable type changing (mypy)
    trace_id = _extract_header_value(
        POSSIBLE_HTTP_HEADER_TRACE_IDS,
        headers,
    )
    if trace_id is None:
        return None

    parent_span_id = _extract_header_value(
        POSSIBLE_HTTP_HEADER_PARENT_IDS,
        headers,
        default="0",
    )
    sampling_priority = _extract_header_value(
        POSSIBLE_HTTP_HEADER_SAMPLING_PRIORITIES,
        headers,
    )
    origin = _extract_header_value(
        POSSIBLE_HTTP_HEADER_ORIGIN,
        headers,
    )

    # Try to parse values into their expected types
    try:
        if sampling_priority is not None:
            sampling_priority = int(sampling_priority)  # type: ignore[assignment]
        else:
            sampling_priority = sampling_priority

        return Context(
            # DEV: Do not allow `0` for trace id or span id, use None instead
            trace_id=int(trace_id) or None,
            span_id=int(parent_span_id) or None,  # type: ignore[arg-type]
            sampling_priority=sampling_priority,  # type: ignore[arg-type]
            dd_origin=origin,
        )
    # If headers are invalid and cannot be parsed, return a new context and log the issue.
    except (TypeError, ValueError):
        log.debug(
            "received invalid x-datadog-* headers, " "trace-id: %r, parent-id: %r, priority: %r, origin: %r",
            trace_id,
            parent_span_id,
            sampling_priority,
            origin,
        )
    return None


def _inject_b3(span_context, headers):
    # type: (Context, Dict[str, str]) -> None
    # We are allowed to propagate only the sampling priority
    if span_context.trace_id is not None and span_context.span_id is not None:
        headers[HTTP_HEADER_B3_TRACE_ID] = _dd_id_to_b3_id(span_context.trace_id)
        headers[HTTP_HEADER_B3_SPAN_ID] = _dd_id_to_b3_id(span_context.span_id)
    sampling_priority = span_context.sampling_priority
    # Propagate priority only if defined
    if sampling_priority is not None:
        if sampling_priority == 0:
            headers[HTTP_HEADER_B3_SAMPLED] = "0"
        elif sampling_priority == 1:
            headers[HTTP_HEADER_B3_SAMPLED] = "1"
        elif sampling_priority > 1:
            headers[HTTP_HEADER_B3_FLAGS] = "1"


def _extract_b3(headers):
    # type: (Dict[str, str]) -> Optional[Context]
    trace_id_val = _extract_header_value(
        POSSIBLE_HTTP_HEADER_B3_TRACE_IDS,
        headers,
    )
    span_id_val = _extract_header_value(
        POSSIBLE_HTTP_HEADER_B3_SPAN_IDS,
        headers,
    )
    sampled = _extract_header_value(
        POSSIBLE_HTTP_HEADER_B3_SAMPLEDS,
        headers,
    )
    flags = _extract_header_value(
        POSSIBLE_HTTP_HEADER_B3_FLAGS,
        headers,
    )

    # Try to parse values into their expected types
    try:
        # DEV: We are allowed to have only x-b3-sampled/flags
        trace_id = None
        span_id = None
        if trace_id_val is not None:
            trace_id = _b3_id_to_dd_id(trace_id_val) or None
        if span_id_val is not None:
            span_id = _b3_id_to_dd_id(span_id_val) or None

        if sampled is not None:
            if sampled == "0":
                sampling_priority = AUTO_REJECT
            elif sampled == "1":
                sampling_priority = AUTO_KEEP
        if flags == "1":
            sampling_priority = USER_KEEP

        return Context(
            # DEV: Do not allow `0` for trace id or span id, use None instead
            trace_id=trace_id,
            span_id=span_id,
            sampling_priority=sampling_priority,
        )
    # If headers are invalid and cannot be parsed, return a new context and log the issue.
    except (TypeError, ValueError):
        log.debug(
            "received invalid x-b3-* headers, " "trace-id: %r, span-id: %r, sampled: %r, flags: %r",
            trace_id_val,
            span_id_val,
            sampled,
            flags,
        )
    return None


def _inject_b3_single_header(span_context, headers):
    # type: (Context, Dict[str, str]) -> None
    single_header = "{}-{}".format(span_context.trace_id, span_context.span_id)
    sampling_priority = span_context.sampling_priority
    if sampling_priority is not None:
        if sampling_priority == 0 or sampling_priority == 1:
            single_header += "-{}".format(sampling_priority)
        elif sampling_priority > 1:
            single_header += "-d"
    headers[HTTP_HEADER_B3_SINGLE] = single_header


def _extract_b3_single_header(headers):
    # type: (Dict[str, str]) -> Optional[Context]
    single_header = _extract_header_value(POSSIBLE_HTTP_HEADER_B3_SINGLE_HEADER, headers)
    if not single_header:
        return None

    trace_id = None
    span_id = None
    sampled = None

    parts = single_header.split("-")
    trace_id_val = None
    span_id_val = None
    if len(parts) == 1:
        sampled = parts[0]
    elif len(parts) == 2:
        trace_id_val, span_id_val = parts
    elif len(parts) >= 3:
        trace_id_val, span_id_val, sampled = parts[:3]

    # Try to parse values into their expected types
    try:
        # DEV: We are allowed to have only x-b3-sampled/flags
        if trace_id_val is not None:
            trace_id = _b3_id_to_dd_id(trace_id_val) or None
        if span_id_val is not None:
            span_id = _b3_id_to_dd_id(span_id_val) or None

        if sampled is not None:
            if sampled == "0":
                sampling_priority = AUTO_REJECT
            elif sampled == "1":
                sampling_priority = AUTO_KEEP
            if sampled == "d":
                sampling_priority = USER_KEEP

        return Context(
            # DEV: Do not allow `0` for trace id or span id, use None instead
            trace_id=trace_id,
            span_id=span_id,
            sampling_priority=sampling_priority,
        )
    # If headers are invalid and cannot be parsed, return a new context and log the issue.
    except (TypeError, ValueError):
        log.debug(
            "received invalid b3 header, b3: %r",
            single_header,
        )
    return None


class HTTPPropagator(object):
    """A HTTP Propagator using HTTP headers as carrier."""

    @staticmethod
    def inject(span_context, headers):
        # type: (Context, Dict[str, str]) -> None
        """Inject Context attributes that have to be propagated as HTTP headers.

        Here is an example using `requests`::

            import requests
            from ddtrace.propagation.http import HTTPPropagator

            def parent_call():
                with tracer.trace('parent_span') as span:
                    headers = {}
                    HTTPPropagator.inject(span.context, headers)
                    url = '<some RPC endpoint>'
                    r = requests.get(url, headers=headers)

        :param Context span_context: Span context to propagate.
        :param dict headers: HTTP headers to extend with tracing attributes.
        """
        if PROPAGATION_STYLE_DATADOG in config.propagation_style_inject:
            _inject_datadog(span_context, headers)
        if PROPAGATION_STYLE_B3 in config.propagation_style_inject:
            _inject_b3(span_context, headers)
        if PROPAGATION_STYLE_B3_SINGLE_HEADER in config.propagation_style_inject:
            _inject_b3_single_header(span_context, headers)

    @staticmethod
    def extract(headers):
        # type: (Dict[str,str]) -> Context
        """Extract a Context from HTTP headers into a new Context.

        Here is an example from a web endpoint::

            from ddtrace.propagation.http import HTTPPropagator

            def my_controller(url, headers):
                context = HTTPPropagator.extract(headers)
                if context:
                    tracer.context_provider.activate(context)

                with tracer.trace('my_controller') as span:
                    span.set_tag('http.url', url)

        :param dict headers: HTTP headers to extract tracing attributes.
        :return: New `Context` with propagated attributes.
        """
        if not headers:
            return Context()

        try:
            normalized_headers = _normalize_headers(headers)
            if PROPAGATION_STYLE_DATADOG in config.propagation_style_extract:
                context = _extract_datadog(normalized_headers)
                if context is not None:
                    return context
            if PROPAGATION_STYLE_B3 in config.propagation_style_extract:
                context = _extract_b3(normalized_headers)
                if context is not None:
                    return context
            if PROPAGATION_STYLE_B3_SINGLE_HEADER in config.propagation_style_extract:
                context = _extract_b3_single_header(normalized_headers)
                if context is not None:
                    return context
        except Exception:
            log.debug("error while extracting context propagation headers", exc_info=True)
        return Context()
