from prometheus_client.metrics_core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    InfoMetricFamily,
)
from utilities.choices import ChoiceSet


class MetricTypeChoices(ChoiceSet):
    TYPE_GAUGE = "gauge"
    TYPE_COUNTER = "counter"
    TYPE_INFO = "info"

    CHOICES = ((TYPE_COUNTER, "Counter"), (TYPE_INFO, "Info"), (TYPE_GAUGE, "Gauge"))

    TYPES = {
        TYPE_INFO: InfoMetricFamily,
        TYPE_COUNTER: CounterMetricFamily,
        TYPE_GAUGE: GaugeMetricFamily,
    }
