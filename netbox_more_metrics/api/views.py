from netbox.api.viewsets import NetBoxModelViewSet

from netbox_more_metrics.api.serializers import MetricCollectionSerializer
from netbox_more_metrics.models import MetricCollection


class MetricCollectionViewSet(NetBoxModelViewSet):
    queryset = MetricCollection.objects.all()
    serializer_class = MetricCollectionSerializer
