import abc
from typing import Optional

from ..context import Context


class MetadataName:
    def __init__(self, name):
        # type: (str) -> None
        self._raw = name.strip("_- ")
        self._upper_case = self._raw.upper()
        self._lower_case = self._raw.lower()
        self._snake_case = self._raw.replace("-", "_").replace(" ", "_")
        self._upper_snake_case = self._snake_case.upper()
        self._lower_snake_case = self._snake_case.lower()
        self._wsgi = "HTTP_{}".format(self._upper_snake_case)
        self._lower_wsgi = "http_{}".format(self._lower_snake_case)

    @property
    def raw(self):
        # type: () -> str
        return self._raw

    @property
    def upper_case(self):
        # type: () -> str
        return self._upper_case

    @property
    def lower_case(self):
        # type: () -> str
        return self._lower_case

    @property
    def snake_case(self):
        # type: () -> str
        return self._snake_case

    @property
    def upper_snake_case(self):
        # type: () -> str
        return self._upper_snake_case

    @property
    def lower_snake_case(self):
        # type: () -> str
        return self._lower_snake_case

    @property
    def wsgi(self):
        # type: () -> str
        return self._wsgi

    @property
    def lower_wsgi(self):
        # type: () -> str
        return self._lower_wsgi


class Metadata(abc.ABC):
    def __init__(self, data):
        # type: (dict[str, str]) -> None
        self._data = data

    def get(self, name):
        # type: (MetadataName) -> Optional[str]
        return self._data.get(name.raw)

    def set(self, name, value):
        # type: (MetadataName, str) -> None
        self._data[name.raw] = value


class NormalizedMetadata(Metadata):
    def __init__(self, data):
        # type: (dict[str, str]) -> None
        super(NormalizedMetadata, self).__init__({name.lower(): value for name, value in data.items()})
        self._original_data = data

    def get(self, name):
        # type: (MetadataName) -> Optional[str]
        return self._data.get(name.lower_case, self._data.get(name.lower_wsgi))

    def set(self, name, value):
        # type: (MetadataName, str) -> None
        self._original_data[name.lower_case] = value


class WSGIHeaders(Metadata):
    def get(self, name):
        # type: (MetadataName) -> Optional[str]
        return self._data.get(name.wsgi)


class PropagationFormat(abc.ABC):
    @abc.abstractmethod
    def inject(self, context, metadata):
        # type: (Context, Metadata) -> None
        pass

    @abc.abstractmethod
    def extract(self, metadata):
        # type: (Metadata) -> Context
        pass


class DatadogPropagationFormat(PropagationFormat):
    TRACE_ID = MetadataName("x-datadog-trace-id")
    PARENT_ID = MetadataName("x-datadog-parent-id")
    SAMPLING_PRIORITY = MetadataName("x-datadog-sampling-priority")
    ORIGIN = MetadataName("x-datadog-origin")

    def inject(self, context, metadata):
        # type: (Context, Metadata) -> None
        metadata.set(self.TRACE_ID, str(context.trace_id))
        metadata.set(self.PARENT_ID, str(context.span_id))
        sampling_priority = context.sampling_priority
        if sampling_priority is not None:
            metadata.set(self.SAMPLING_PRIORITY, str(sampling_priority))

        dd_origin = context.dd_origin
        if dd_origin is not None:
            metadata.set(self.ORIGIN, dd_origin)

    def extract(self, metadata):
        # type: (Metadata) -> Context
        # TODO: Fix variable type changing (mypy)
        trace_id = metadata.get(self.TRACE_ID)
        if trace_id is None:
            return Context()

        parent_span_id = metadata.get(self.PARENT_ID) or "0"
        sampling_priority = metadata.get(self.SAMPLING_PRIORITY)
        origin = metadata.get(self.ORIGIN)

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
            # log.debug(
            #     "received invalid x-datadog-* headers, " "trace-id: %r, parent-id: %r, priority: %r, origin: %r",
            #     trace_id,
            #     parent_span_id,
            #     sampling_priority,
            #     origin,
            # )
            pass
        return Context()


# Existing API
class HTTPPropagator:
    @staticmethod
    def inject(context, headers):
        # type: (Context, dict[str, str]) -> None
        propagation_format = DatadogPropagationFormat()
        propagation_format.inject(context, Metadata(headers))

    @staticmethod
    def extract(headers):
        # type: (dict[str, str]) -> Context
        metadata = NormalizedMetadata(headers)
        propagation_format = DatadogPropagationFormat()  # TODO: Can we define this once?

        try:
            return propagation_format.extract(metadata)
        except Exception:
            return Context()
