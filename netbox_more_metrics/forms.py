from django import forms
from django.contrib.contenttypes.models import ContentType
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import (
    ContentTypeChoiceField,
    DynamicModelMultipleChoiceField,
)

from netbox_more_metrics.fields import DynamicMetricValueOptionField
from netbox_more_metrics.models import Metric, MetricCollection


class MetricCollectionForm(NetBoxModelForm):
    include_in_default = forms.BooleanField(label="Exported globally", required=False)

    class Meta:
        model = MetricCollection
        fields = ("name", "description", "enabled", "include_in_default", "tags")


class MetricForm(NetBoxModelForm):
    collections = DynamicModelMultipleChoiceField(
        queryset=MetricCollection.objects.all()
    )
    content_type = ContentTypeChoiceField(
        label="Object Type", queryset=ContentType.objects.all()
    )
    metric_description = forms.CharField(label="Description")

    metric_value = DynamicMetricValueOptionField(
        query_params={"object_type": "$content_type"},
        object_type_field="content_type",
        help_text="Select the value used for the metric. This might ignore aggregation done by labels.",
    )

    fieldsets = (
        ("", ("name", "metric_description", "enabled", "tags")),
        ("Metric source", ("content_type", "filter")),
        (
            "Metric configuration",
            ("metric_name", "metric_labels", "metric_type", "metric_value"),
        ),
        ("Metric exposition", ("collections",)),
    )

    class Meta:
        model = Metric
        fields = (
            "name",
            "metric_description",
            "enabled",
            "metric_name",
            "metric_labels",
            "metric_type",
            "metric_value",
            "filter",
            "content_type",
            "collections",
        )
