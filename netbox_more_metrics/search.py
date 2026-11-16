from netbox.search import SearchIndex, register_search

from netbox_more_metrics.models import Metric, MetricCollection


@register_search
class MetricCollectionIndex(SearchIndex):
    model = MetricCollection
    fields = (
        ("name", 100),
        ("description", 500),
    )
    display_attrs = (
        "description",
        "enabled",
    )


@register_search
class MetricIndex(SearchIndex):
    model = Metric
    fields = (
        ("name", 100),
        ("metric_name", 100),
        ("metric_description", 500),
    )
    display_attrs = (
        "metric_name",
        "metric_description",
        "metric_type",
        "metric_value",
        "enabled",
    )


indexes = (
    MetricCollectionIndex,
    MetricIndex,
)
