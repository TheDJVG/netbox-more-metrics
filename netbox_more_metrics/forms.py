from core.models import ObjectType
from django import forms
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import (
    ContentTypeChoiceField,
    DynamicModelMultipleChoiceField,
)
from utilities.forms.rendering import FieldSet

from netbox_more_metrics.choices import MetricValueChoices
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
        label="Object Type", queryset=ObjectType.objects.all()
    )
    metric_description = forms.CharField(label="Description")

    metric_value = DynamicMetricValueOptionField(
        query_params={"object_type": "$content_type"},
        object_type_field="content_type",
        help_text="Select the value used for the metric. This might ignore aggregation done by labels.",
    )

    fieldsets = (
        FieldSet("name", "metric_description", "enabled", "tags"),
        FieldSet("content_type", "filter", name="Metric source"),
        FieldSet(
            "metric_name",
            "metric_labels",
            "metric_type",
            "metric_value",
            name="Metric configuration",
        ),
        FieldSet("collections", name="Metric exposition"),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set the choices for the content_type field.
        if self.data:
            content_type = self.data.get("content_type")
            if content_type:
                self.fields["metric_value"].choices = (
                    MetricValueChoices.choices_for_contenttype(content_type)
                )
        elif self.instance.pk:
            content_type = self.instance.content_type.model_class()
            self.fields["metric_value"].choices = (
                MetricValueChoices.choices_for_contenttype(content_type)
            )
