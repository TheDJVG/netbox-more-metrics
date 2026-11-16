from netbox.api.fields import (
    ContentTypeField,
    RelatedObjectCountField,
    SerializedPKRelatedField,
)
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers

from netbox_more_metrics.models import (
    SENSITIVE_APP_LABELS,
    SENSITIVE_MODEL_NAMES,
    Metric,
    MetricCollection,
    get_allowed_object_types,
)

_HAS_DISPLAY_URL = "display_url" in NetBoxModelSerializer._declared_fields


class NestedMetricSerializer(WritableNestedSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_more_metrics-api:metric-detail")
    if not _HAS_DISPLAY_URL:
        display_url = serializers.HyperlinkedIdentityField(view_name="plugins:netbox_more_metrics:metric")

    class Meta:
        model = Metric
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "name",
            "metric_name",
            "metric_description",
        )


class NestedMetricCollectionSerializer(WritableNestedSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_more_metrics-api:metriccollection-detail")
    if not _HAS_DISPLAY_URL:
        display_url = serializers.HyperlinkedIdentityField(view_name="plugins:netbox_more_metrics:metriccollection")

    class Meta:
        model = MetricCollection
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "name",
            "description",
        )


class MetricCollectionSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_more_metrics-api:metriccollection-detail")
    if not _HAS_DISPLAY_URL:
        display_url = serializers.HyperlinkedIdentityField(view_name="plugins:netbox_more_metrics:metriccollection")
    export_url = serializers.HyperlinkedIdentityField(view_name="plugins:netbox_more_metrics:metriccollection_metrics")
    metrics = NestedMetricSerializer(many=True, read_only=True)
    metric_count = RelatedObjectCountField("metrics")

    class Meta:
        model = MetricCollection
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "name",
            "description",
            "enabled",
            "include_in_default",
            "export_url",
            "metrics",
            "metric_count",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "name",
            "description",
        )


class MetricSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_more_metrics-api:metric-detail")
    if not _HAS_DISPLAY_URL:
        display_url = serializers.HyperlinkedIdentityField(view_name="plugins:netbox_more_metrics:metric")
    export_url = serializers.HyperlinkedIdentityField(view_name="plugins:netbox_more_metrics:metric_metrics")
    content_type = ContentTypeField(queryset=get_allowed_object_types())
    collections = SerializedPKRelatedField(
        queryset=MetricCollection.objects.all(),
        serializer=NestedMetricCollectionSerializer,
        nested=True,
        many=True,
        required=True,
    )

    class Meta:
        model = Metric
        fields = (
            "id",
            "url",
            "display_url",
            "display",
            "name",
            "enabled",
            "metric_name",
            "metric_description",
            "metric_type",
            "metric_labels",
            "metric_value",
            "content_type",
            "filter",
            "exclude",
            "label_renames",
            "collections",
            "export_url",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "name",
            "metric_name",
            "metric_description",
        )

    def validate_content_type(self, value):
        from core.models import ObjectType

        if (
            value.app_label in SENSITIVE_APP_LABELS
            or f"{value.app_label}.{value.model}".lower() in SENSITIVE_MODEL_NAMES
        ):
            raise serializers.ValidationError(f"Access to sensitive model '{value}' is forbidden.")
        try:
            return ObjectType.objects.get(pk=value.pk)
        except ObjectType.DoesNotExist:
            raise serializers.ValidationError(f"ObjectType for '{value}' not found.")


class MetricValueOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    display = serializers.CharField()
