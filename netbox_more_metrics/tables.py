import django_tables2 as tables
from netbox.tables import NetBoxTable, columns

from netbox_more_metrics.models import Metric, MetricCollection


class MetricCollectionTable(NetBoxTable):
    name = tables.Column(linkify=True)
    include_in_default = tables.BooleanColumn(verbose_name="Exported globally")

    class Meta(NetBoxTable.Meta):
        model = MetricCollection
        fields = ("id", "name", "enabled", "include_in_default", "description")
        default_columns = ("pk", "name", "enabled", "include_in_default", "description")


class MetricTable(NetBoxTable):
    name = tables.Column(linkify=True)
    metric_name = tables.Column(verbose_name="Metric")
    content_type = columns.ContentTypeColumn(verbose_name="Object type")
    metric_description = tables.Column(verbose_name="Description")
    metric_type = columns.ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = Metric
        fields = (
            "id",
            "name",
            "enabled",
            "metric_name",
            "labels",
            "metric_type",
            "content_type",
            "metric_description",
        )
        default_columns = (
            "pk",
            "name",
            "enabled",
            "metric_name",
            "labels",
            "metric_type",
            "content_type",
            "metric_description",
        )
