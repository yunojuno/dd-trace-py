from typing import FrozenSet


PROPAGATION_STYLE_DATADOG = "datadog"
PROPAGATION_STYLE_B3 = "b3"
PROPAGATION_STYLE_B3_SINGLE_HEADER = "b3 single header"
PROPAGATION_STYLE_ALL = frozenset(
    [PROPAGATION_STYLE_DATADOG, PROPAGATION_STYLE_B3, PROPAGATION_STYLE_B3_SINGLE_HEADER]
)  # type: FrozenSet[str]


DEFAULT_SERVICE_NAME = "unnamed_python_service"
