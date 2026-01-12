from core.models import ObjectType
from netbox.api.fields import ContentTypeField, SerializedPKRelatedField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers

from netbox_more_metrics.models import Metric, MetricCollection


class NestedMetricSerializer(WritableNestedSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_more_metrics-api:metric-detail"
    )

    class Meta:
        model = Metric
        fields = (
            "id",
            "display",
            "name",
            "metric_name",
            "url",
        )


class MetricCollectionSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_more_metrics-api:metriccollection-detail"
    )
    export_url = serializers.HyperlinkedIdentityField(
        view_name="plugins:netbox_more_metrics:metriccollection_metrics"
    )
    metrics = NestedMetricSerializer(many=True, read_only=True)

    class Meta:
        model = MetricCollection
        fields = (
            "id",
            "name",
            "display",
            "enabled",
            "include_in_default",
            "url",
            "export_url",
            "metrics",
        )


class NestedMetricCollectionSerializer(WritableNestedSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_more_metrics-api:metriccollection-detail"
    )

    class Meta:
        model = MetricCollection
        fields = ("id", "display", "url")


class MetricSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_more_metrics-api:metric-detail"
    )
    export_url = serializers.HyperlinkedIdentityField(
        view_name="plugins:netbox_more_metrics:metric_metrics"
    )
    content_type = ContentTypeField(queryset=ObjectType.objects.all())
    collections = SerializedPKRelatedField(
        queryset=MetricCollection.objects.all(),
        serializer=NestedMetricCollectionSerializer,
        many=True,
        required=True,
    )

    class Meta:
        model = Metric
        fields = (
            "id",
            "display",
            "name",
            "url",
            "export_url",
            "enabled",
            "metric_name",
            "metric_description",
            "metric_type",
            "metric_labels",
            "metric_value",
            "content_type",
            "filter",
            "label_renames",
            "collections",
        )


class MetricValueOptionSerializer(serializers.Serializer):
    id = (
        serializers.CharField()
    )  # We 'abuse' the id field here so that the normal APISelect widget/js works.
    display = serializers.CharField()
