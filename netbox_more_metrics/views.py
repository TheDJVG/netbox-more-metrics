from typing import ClassVar

from django.core.exceptions import PermissionDenied
from django.db.models import F, Func, TextField, Value
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View
from netbox.plugins import get_plugin_config
from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from netbox_more_metrics import filtersets
from netbox_more_metrics.collectors import (
    DynamicMetricCollectionCollector,
    DynamicMetricCollector,
)
from netbox_more_metrics.forms import MetricCollectionForm, MetricForm
from netbox_more_metrics.models import Metric, MetricCollection
from netbox_more_metrics.tables import MetricCollectionTable, MetricTable

#
# MetricCollection
#


class MetricCollectionListView(ObjectListView):
    queryset = MetricCollection.objects.all()
    filterset = filtersets.MetricCollectionFilterSet
    actions: ClassVar[dict] = {"add": {"add"}}
    table = MetricCollectionTable


class MetricCollectionView(ObjectView):
    queryset = MetricCollection.objects.all()

    def get_extra_context(self, request, instance):
        metrics_table = MetricTable(
            data=instance.metrics.restrict(request.user, "view").annotate(
                labels=Func(
                    F("metric_labels"),
                    Value(", "),
                    function="array_to_string",
                    output_field=TextField(),
                )
            ),
            orderable=False,
            exclude=("actions", "labels"),
        )

        return {"metrics_table": metrics_table}


class MetricCollectionExportView(View):
    http_method_names = ("get",)

    def has_permission(self, request=None):
        req = request or getattr(self, "request", None)
        if get_plugin_config("netbox_more_metrics", "export_metrics_without_auth"):
            return True
        if req is None or not req.user.is_authenticated:
            return False
        return req.user.has_perm("netbox_more_metrics.view_metriccollection")

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.has_permission(request):
            raise PermissionDenied("Authentication and view permission required to export metrics.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, **kwargs):
        if get_plugin_config("netbox_more_metrics", "export_metrics_without_auth"):
            instance = get_object_or_404(MetricCollection, pk=kwargs["pk"])
        else:
            instance = get_object_or_404(
                MetricCollection.objects.restrict(request.user, "view"),
                pk=kwargs["pk"],
            )

        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=instance)

        metrics_page = generate_latest(registry)

        return HttpResponse(metrics_page, content_type=CONTENT_TYPE_LATEST)


class MetricCollectionEditView(ObjectEditView):
    queryset = MetricCollection.objects.all()
    form = MetricCollectionForm


class MetricCollectionDeleteView(ObjectDeleteView):
    queryset = MetricCollection.objects.all()


#
# Metric
#


class MetricListView(ObjectListView):
    queryset = Metric.objects.all().annotate(
        labels=Func(
            F("metric_labels"),
            Value(", "),
            function="array_to_string",
            output_field=TextField(),
        )
    )
    filterset = filtersets.MetricFilterSet
    actions: ClassVar[dict] = {"add": {"add"}}
    table = MetricTable


class MetricView(ObjectView):
    queryset = Metric.objects.all()

    def get_extra_context(self, request, instance):
        # Generate metrics to be shown on page.
        registry = CollectorRegistry()
        DynamicMetricCollector(registry=registry, metric=instance, force_enable=True)

        # Collections table
        collections_table = MetricCollectionTable(
            data=instance.collections.restrict(request.user, "view"),
            orderable=False,
            exclude=("actions",),
        )

        return {
            "metrics": generate_latest(registry).decode(),
            "collections_table": collections_table,
        }


class MetricExportView(View):
    http_method_names = ("get",)

    def has_permission(self, request=None):
        req = request or getattr(self, "request", None)
        if get_plugin_config("netbox_more_metrics", "export_metrics_without_auth"):
            return True
        if req is None or not req.user.is_authenticated:
            return False
        return req.user.has_perm("netbox_more_metrics.view_metric")

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.has_permission(request):
            raise PermissionDenied("Authentication and view permission required to export metrics.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, **kwargs):
        if get_plugin_config("netbox_more_metrics", "export_metrics_without_auth"):
            instance = get_object_or_404(Metric, pk=kwargs["pk"])
        else:
            instance = get_object_or_404(
                Metric.objects.restrict(request.user, "view"),
                pk=kwargs["pk"],
            )

        registry = CollectorRegistry()
        DynamicMetricCollector(registry=registry, metric=instance)

        metrics_page = generate_latest(registry)

        return HttpResponse(metrics_page, content_type=CONTENT_TYPE_LATEST)


class MetricEditView(ObjectEditView):
    queryset = Metric.objects.all()
    form = MetricForm


class MetricDeleteView(ObjectDeleteView):
    queryset = Metric.objects.all()
