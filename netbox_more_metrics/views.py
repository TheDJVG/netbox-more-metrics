from django.db.models import F, Func, TextField, Value
from django.http import HttpResponse
from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

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
    actions = {"add": {"add"}}
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


class MetricCollectionExportView(ObjectView):
    queryset = MetricCollection.objects.all()
    http_method_names = ("get",)

    def get(self, request, **kwargs):
        instance = self.get_object(**kwargs)

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
    actions = {"add": {"add"}}
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


class MetricExportView(ObjectView):
    queryset = Metric.objects.all()
    http_method_names = ("get",)

    def get(self, request, **kwargs):
        instance = self.get_object(**kwargs)

        registry = CollectorRegistry()
        DynamicMetricCollector(registry=registry, metric=instance)

        metrics_page = generate_latest(registry)

        return HttpResponse(metrics_page, content_type=CONTENT_TYPE_LATEST)


class MetricEditView(ObjectEditView):
    queryset = Metric.objects.all()
    form = MetricForm


class MetricDeleteView(ObjectDeleteView):
    queryset = Metric.objects.all()
