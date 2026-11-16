import hashlib
import logging
import re
from collections.abc import Iterable
from time import time

from django.core.exceptions import FieldError
from django.db.models import CharField, Count, F, Func, Value
from django.db.models.functions import Cast, Coalesce
from prometheus_client import metrics_core
from prometheus_client.core import InfoMetricFamily
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
        self.collection = collection
        self._active_metric_collectors: dict[int, DynamicMetricCollector] = {}

        self.base_queryset = (
            self.collection.metrics.filter(enabled=True)
            if self.collection
            else Metric.objects.filter(enabled=True, collections__enabled=True)
        )
        filter_kwargs = {}
        if not self.collection and self._is_default_registry:
            filter_kwargs["collections__include_in_default"] = True
        self.queryset = self.base_queryset.filter(**filter_kwargs) if filter_kwargs else self.base_queryset

        if self.collection and not self.collection.enabled:
            return

        if self._is_default_registry:
            logger.debug("Collector %r for default registry.", self)

        # Start the collectors.
        self._refresh_collectors()

        # We only register ourselves so that we can check for metrics that need to be added.
        # The actual metrics are emitted from their own instance and unregister themselves if needed.
        self.registry.register(self)

    def _get_enabled_metrics(self):
        if self.collection and not self.collection.enabled:
            return []
        return self.queryset.prefetch_related("collections").distinct()

    def _refresh_collectors(self):
        if self.collection and not self.collection.enabled:
            for pk in list(self._active_metric_collectors.keys()):
                collector = self._active_metric_collectors.pop(pk)
                collector.unregister()
            return

        enabled_metrics = {m.pk: m for m in self._get_enabled_metrics()}

        # Remove collectors for metrics that are no longer enabled or were deleted
        for pk in list(self._active_metric_collectors.keys()):
            if pk not in enabled_metrics:
                collector = self._active_metric_collectors.pop(pk)
                collector.unregister()

        for pk, metric in enabled_metrics.items():
            if pk not in self._active_metric_collectors:
                logger.debug(
                    "Adding dynamic metric collector for Metric '%s' (%s).",
                    metric.metric_name,
                    metric.pk,
                )
                collector = DynamicMetricCollector(metric=metric, registry=self.registry)
                if collector.is_valid:
                    self._active_metric_collectors[pk] = collector
            else:
                active_collector = self._active_metric_collectors[pk]
                if metric.last_updated and (
                    active_collector._metric.last_updated is None
                    or metric.last_updated > active_collector._metric.last_updated
                ):
                    active_collector._metric = metric
                    renewed = active_collector.renew()
                    if renewed.is_valid:
                        self._active_metric_collectors[pk] = renewed
                    else:
                        self._active_metric_collectors.pop(pk, None)

    def collect(self) -> Iterable[metrics_core.Metric]:
        logger.debug("Refreshing dynamic metric collectors...")
        self._refresh_collectors()
        return []


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
        self.is_valid = False

        self.pk = metric.pk
        self.name = metric.metric_name
        self.description = metric.metric_description
        self.metric_family = self._metric.metric_family
        self.metric_value = self._metric.metric_value or "count"
        content_type = (
            getattr(self._metric, "content_type", None) if getattr(self._metric, "content_type_id", None) else None
        )
        self.model = content_type.model_class() if content_type else None
        if self.model is None:
            return

        self.queryset = self.model.objects.all()
        self.metric_value_is_method = self.metric_value != "count"

        self.filter = self._metric.filter
        self.exclude = self._metric.exclude
        self.labels = {
            field: self._metric.label_renames.get(field, field) for field in (self._metric.metric_labels or [])
        }
        self.created = time()

        self._internal_labels = (str(self.pk), self.name)

        logger.debug(
            "Dynamic metric collector for Metric '%s' (%s).",
            self._metric.metric_name,
            self._metric.pk,
        )

        # If the filter/exclude/labels are not valid we should not start this collector.
        if (
            (self.filter and not self.test_filter())
            or (self.exclude and not self.test_exclude())
            or not self.test_labels()
        ):
            return

        registry.register(self)
        self.is_valid = True

        # Add an info metric of known dynamic collectors if it's attached to the global registry.
        if self._is_default_registry:
            dynamic_metric_collectors.labels(*self._internal_labels)

    def test_filter(self):
        # Test the filter to make sure it's valid.
        try:
            self.queryset.filter(**self.filter)
        except (FieldError, ValueError, TypeError):
            logger.exception("Metric '%s' (%s) filter is not valid.", self.name, self.pk)
            return False

        return True

    def test_exclude(self):
        # Test the exclude filter to make sure it's valid.
        try:
            self.queryset.filter(**self.exclude)
        except (FieldError, ValueError, TypeError):
            logger.exception("Metric '%s' (%s) exclude is not valid.", self.name, self.pk)
            return False

        return True

    def test_labels(self):
        # Test the labels make sure they're valid.
        try:
            self.queryset.values(*self.labels.keys())
        except (FieldError, ValueError, TypeError):
            logger.exception("Metric '%s' (%s) labels are invalid.", self.name, self.pk)
            return False

        return True

    def unregister(self):
        logger.debug("Unregistering dynamic metric collector '%s' (%s).", self.name, self.pk)
        try:
            self._registry.unregister(self)
        except KeyError:
            pass
        if self._is_default_registry:
            try:
                dynamic_metric_collectors.remove(*self._internal_labels)
            except KeyError:
                pass
        self.is_valid = False

    def renew(self):
        self.unregister()
        return self.__class__(
            registry=self._registry,
            metric=self._metric,
            force_enable=self.force_enable,
        )

    def get_queryset(self):
        qs = self.queryset
        if self.filter:
            qs = qs.filter(**self.filter)
        if self.exclude:
            qs = qs.exclude(**self.exclude)

        return qs

    def get_annotation_alias(self, label_name: str) -> str:
        clean_name = re.sub(r"_+", "_", label_name).strip("_")
        if clean_name != label_name or not clean_name:
            digest = hashlib.sha256(label_name.encode("utf-8")).hexdigest()[:8]
            prefix = f"_metric_label_{clean_name}" if clean_name else "_metric_label"
            return f"{prefix}_{digest}"
        return f"_metric_label_{clean_name}"

    def get_label_annotations(self):
        annotations = {}
        for field, label_name in self.labels.items():
            field_name = self.get_annotation_alias(label_name)
            if field.startswith("custom_field_data__"):
                keys = [Value(key) for key in field.split("__")[1:]]
                annotations[field_name] = Coalesce(
                    Func(
                        F("custom_field_data"),
                        *keys,
                        function="jsonb_extract_path_text",
                        output_field=CharField(),
                    ),
                    Value("null"),
                )
            else:
                annotations[field_name] = Coalesce(Cast(F(field), output_field=CharField()), Value("null"))
        return annotations

    def get_metric_result(self):
        label_annotations = self.get_label_annotations()
        values = label_annotations.keys()

        if self.metric_value_is_method:
            return self.get_queryset().annotate(**label_annotations)

        if not self.labels:
            total_count = self.get_queryset().count()
            return [{"count": total_count}]

        base_qs = (
            self.get_queryset()
            .order_by()
            .values(*self.labels.keys())
            .annotate(count=Count("*"), **label_annotations)
            .values("count", *values)
        )

        return base_qs

    def is_metric_enabled(self):
        if not self._metric.enabled:
            return False

        if (
            hasattr(self._metric, "_prefetched_objects_cache")
            and "collections" in self._metric._prefetched_objects_cache
        ):
            collections = self._metric.collections.all()
            if self._is_default_registry:
                return any(c.enabled and getattr(c, "include_in_default", True) for c in collections)
            return any(c.enabled for c in collections)

        if self._is_default_registry:
            return self._metric.collections.filter(enabled=True, include_in_default=True).exists()

        return self._metric.collections.filter(enabled=True).exists()

    def collect(self) -> Iterable[metrics_core.Metric]:
        if not self.is_valid:
            return []

        logger.debug("Collecting for Metric '%s' (%s).", self.name, self.pk)

        # Metric has been disabled, unregister.
        if not self.force_enable and not self.is_metric_enabled():
            if self._is_default_registry:
                self.unregister()
            return

        # Create the metric
        if self.metric_family is InfoMetricFamily:
            metric = self.metric_family(self.name, self.description, labels=())
        else:
            metric = self.metric_family(self.name, self.description, labels=self.labels.values())

        # Get the data for the metric.
        results = self.get_metric_result()
        seen_labelsets = set()

        for result in results:
            if isinstance(result, dict):
                labels = {
                    label_name: str(result.get(self.get_annotation_alias(label_name), ""))
                    for label_name in self.labels.values()
                }
                value = result.pop(self.metric_value)
            else:
                labels = {
                    label_name: str(getattr(result, self.get_annotation_alias(label_name), ""))
                    for label_name in self.labels.values()
                }
                raw_val = getattr(result, self.metric_value)
                try:
                    value = raw_val() if callable(raw_val) else raw_val
                except (ZeroDivisionError, ValueError, TypeError, AttributeError) as e:
                    logger.warning("Failed to evaluate %s on %r: %s", self.metric_value, result, e)
                    value = 0.0

            # Deduplicate series by labelset for utilization/method metrics or identical rows
            labelset_key = tuple(sorted(labels.items()))
            if labelset_key in seen_labelsets:
                continue
            seen_labelsets.add(labelset_key)

            if self.metric_family is InfoMetricFamily:
                metric.add_metric(labels=(), value=labels)
            else:
                metric.add_metric(labels.values(), value)

        yield metric

        if self._is_default_registry:
            dynamic_metric_collectors.labels(*self._internal_labels).inc()

    def describe(self):
        yield self.metric_family(self.name, self.description)
