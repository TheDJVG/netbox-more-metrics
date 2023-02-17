from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import viewsets
from rest_framework.response import Response

from netbox_more_metrics import querysets
from netbox_more_metrics.api.serializers import (
    MetricCollectionSerializer,
    MetricValueOptionSerializer,
)
from netbox_more_metrics.models import MetricCollection


class MetricCollectionViewSet(NetBoxModelViewSet):
    queryset = MetricCollection.objects.all()
    serializer_class = MetricCollectionSerializer


class MetricValueTypeOptionsViewSet(viewsets.ViewSet):
    permission_classes = []

    def list(self, request):
        content_type = request.query_params.get("object_type")
        qs = querysets.DefaultExtendedQuerySet
        if content_type:
            qs = querysets.get_extended_queryset_for_model(content_type)

        options = list()
        for option in qs.CHOICES:
            value, name = option
            options.append({"id": value, "display": name})

        serializer = MetricValueOptionSerializer(options, many=True)

        return Response(
            {
                "results": serializer.data,
                "count": len(options),
                "next": None,
                "previous": None,
            }
        )
