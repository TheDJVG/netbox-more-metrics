from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers

from netbox_more_metrics.models import Metric, MetricCollection


class MetricCollectionSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_more_metrics-api:metriccollection-detail"
    )

    class Meta:
        model = MetricCollection
        fields = ("id", "name", "display", "enabled", "url")


class NestedMetricCollectionSerializer(WritableNestedSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_more_metrics-api:metriccollection-detail"
    )

    class Meta:
        model = MetricCollection
        fields = ("id", "display", "url")


class MetricSerializer(NetBoxModelSerializer):
    class Meta:
        model = Metric
        fields = ("id", "name")


class MetricValueOptionSerializer(serializers.Serializer):
    id = (
        serializers.CharField()
    )  # We 'abuse' the id field here so that the normal APISelect widget/js works.
    display = serializers.CharField()
