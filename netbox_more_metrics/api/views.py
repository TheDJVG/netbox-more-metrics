from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import viewsets
from rest_framework.response import Response

from netbox_more_metrics.api.serializers import (
    MetricCollectionSerializer,
    MetricValueOptionSerializer,
)
from netbox_more_metrics.choices import MetricValueChoices
from netbox_more_metrics.models import MetricCollection


class MetricCollectionViewSet(NetBoxModelViewSet):
    queryset = MetricCollection.objects.all()
    serializer_class = MetricCollectionSerializer


class MetricValueTypeOptionsViewSet(viewsets.ViewSet):
    """
    Return valid Metric Value Type for an Object Type.
    """

    permission_classes = []

    def list(self, request):
        content_type = request.query_params.get("object_type")
        choices = MetricValueChoices.DEFAULT_CHOICES
        if content_type:
            choices = MetricValueChoices.choices_for_contenttype(content_type)

        options = list()
        for option in choices:
            value, name = option
            options.append({"id": value, "display": name})

        serializer = MetricValueOptionSerializer(options, many=True)

        return Response(
            {
                "count": len(options),
                "next": None,
                "previous": None,
                "results": serializer.data,
            }
        )
