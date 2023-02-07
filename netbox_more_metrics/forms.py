from django import forms
from django.contrib.contenttypes.models import ContentType
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import (
    ContentTypeChoiceField,
    DynamicModelMultipleChoiceField,
)

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

    fieldsets = (
        ("", ("name", "metric_description", "enabled", "tags")),
        ("Metric configuration", ("metric_name", "metric_labels", "metric_type")),
        ("Metric source", ("content_type", "filter")),
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
            "filter",
            "content_type",
            "collections",
        )
