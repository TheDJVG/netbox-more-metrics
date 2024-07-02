import logging
from time import time
from typing import Iterable

from django.core.exceptions import FieldError
from django.db.models import CharField, Count, F, Value
from django.db.models.functions import Cast, Coalesce
from prometheus_client import metrics_core
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    InfoMetricFamily,
)
from prometheus_client.registry import REGISTRY, Collector, CollectorRegistry

from netbox_more_metrics.metrics import dynamic_metric_collectors
from netbox_more_metrics.models import Metric, MetricCollection

logger = logging.getLogger(__name__)


class DynamicMetricCollectionCollector(Collector):
    def __init__(
        self,
        registry: CollectorRegistry = REGISTRY,
        collection: MetricCollection = None,
    ):
        self._is_default_registry = registry is REGISTRY
        self.registry = registry

        self.base_queryset = (
            collection.metrics.all() if collection else Metric.objects.all()
        )

        filter = dict(enabled=True, collections__enabled=True)

        if self._is_default_registry:
            filter.update(dict(collections__include_in_default=True))

        self.queryset = self.base_queryset.filter(**filter)

        if self._is_default_registry:
            logger.debug("Collector %r for default registry.", self)

        # Start the collectors.
        self._refresh_collectors()

        # We only register ourselves so that we can check for metrics that need to be added.
        # The actual metrics are emitted from their own instance and unregister themselves if needed.
        self.registry.register(self)

    def _get_enabled_metrics(self):
        metrics = self.queryset.all().distinct()
        return metrics

    def _refresh_collectors(self):
        for metric in self._get_enabled_metrics():
            if metric.metric_name not in self.registry._names_to_collectors:
                logger.debug(
                    "Adding dynamic metric collector for Metric '%s' (%d).",
                    metric.metric_name,
                    metric.pk,
                )
                DynamicMetricCollector(metric=metric, registry=self.registry)

    def collect(self) -> Iterable[metrics_core.Metric]:
        logger.debug("Refreshing dynamic metric collectors...")
        self._refresh_collectors()
        return

        # We have to yield some metric otherwise this will fail in the registry .collect() method.
        yield InfoMetricFamily()


class DynamicMetricCollector(Collector):
    def __init__(
        self,
        metric: Metric,
        registry: CollectorRegistry = REGISTRY,
        force_enable: bool = False,
    ):
        self._is_default_registry = registry is REGISTRY
        self._metric = metric
        self._registry = registry
        self.force_enable = force_enable

        self.pk = metric.pk
        self.name = metric.metric_name
        self.description = metric.metric_description
        self.metric_family = self._metric.metric_family
        self.metric_value = self._metric.metric_value or "count"
        self.model = self._metric.content_type.model_class()
        self.queryset = self.model.objects.all()

        # FIXME would be nice if we can put this in the choices someway.
        self.metric_value_is_method = not self.metric_value == "count"

        self.filter = self._metric.filter
        self.labels = self._metric.metric_labels
        self.created = time()

        self._internal_labels = (str(self.pk), self.name)

        logger.debug(
            "Dynamic metric collector for Metric '%s' (%d).",
            self._metric.metric_name,
            self._metric.pk,
        )

        # If the filter/labels are not valid we should not start this collector.
        if (self.filter and not self.test_filter()) or not self.test_labels():
            return

        registry.register(self)

        # Add an info metric of known dynamic collectors if it's attached to the global registry.
        if self._is_default_registry:
            dynamic_metric_collectors.labels(*self._internal_labels)

    def test_filter(self):
        # Test the filter to make sure it's valid.
        try:
            self.queryset.filter(**self.filter)
        except FieldError:
            logger.exception(
                "Metric '%s' (%d) filter is not valid.", self.name, self.pk
            )
            return False

        return True

    def test_labels(self):
        # Test the labels make sure they're valid.
        try:
            self.queryset.values(*self.labels)
        except FieldError:
            logger.exception("Metric '%s' (%d) labels are invalid.", self.name, self.pk)
            return False

        return True

    def unregister(self):
        logger.debug(
            "Unregistering dynamic metric collector '%s' (%d).", self.name, self.pk
        )
        self._registry.unregister(self)
        dynamic_metric_collectors.remove(*self._internal_labels)

    def renew(self):
        self.unregister()
        return self.__class__(registry=self._registry, metric=self._metric)

    def get_queryset(self):
        qs = self.queryset
        if self.filter:
            qs = qs.filter(**self.filter)

        return qs

    def get_label_annotations(self):
        return {
            f"__metric_label_{field}": Coalesce(
                Cast(F(field), output_field=CharField()), Value("null")
            )
            for field in self.labels
        }

    def get_metric_result(self):
        label_annotations = self.get_label_annotations()
        values = label_annotations.keys()

        if self.metric_value_is_method:
            return self.get_queryset().annotate(count=Count("*"), **label_annotations)

        base_qs = (
            self.get_queryset()
            .values(*self.labels)
            .annotate(count=Count("*"), **label_annotations)
            .values("count", *values)
        )

        return base_qs

    def is_metric_enabled(self):
        if not self._metric.enabled:
            return False

        if self._is_default_registry:
            return bool(
                self._metric.collections.filter(enabled=True, include_in_default=True)
            )

        return bool(self._metric.collections.filter(enabled=True))

    def collect(self) -> Iterable[metrics_core.Metric]:
        logger.debug("Collecting for Metric '%s' (%d).", self.name, self.pk)

        # Run some basic checks if this metric is still healthy.
        if self._is_default_registry:
            try:
                self._metric.refresh_from_db()
            except Metric.DoesNotExist:
                # If the object has disappeared we unregister ourselves.
                self.unregister()
                return

        # Check if the metric has changed, and if that's the case renew the metric.
        # Yield the metrics from the new instance.
        if self.created < self._metric.last_updated.timestamp():
            yield from self.renew().collect()
            return

        # Metric has been disabled, unregister.
        if not self.force_enable and not self.is_metric_enabled():
            if self._is_default_registry:
                self.unregister()
            return

        # Create the metric
        metric: GaugeMetricFamily | CounterMetricFamily | InfoMetricFamily = (
            self.metric_family(self.name, self.description, labels=self.labels)
        )

        # Get the data for the metric.
        results = self.get_metric_result()

        for result in results:
            if isinstance(result, dict):
                labels = {
                    field: result.get(f"__metric_label_{field}")
                    for field in self.labels
                }
                value = result.pop(self.metric_value)
            else:
                labels = {
                    field: getattr(result, f"__metric_label_{field}")
                    for field in self.labels
                }
                value = (
                    getattr(result, self.metric_value)
                    if not self.metric_value_is_method
                    else getattr(result, self.metric_value)()
                )

            if self.metric_family is InfoMetricFamily:
                metric.add_metric(labels="", value=result)
            else:
                metric.add_metric(labels.values(), value)

        yield metric

        if self._is_default_registry:
            dynamic_metric_collectors.labels(*self._internal_labels).inc()

    def describe(self):
        yield self.metric_family(self.name, self.description)
