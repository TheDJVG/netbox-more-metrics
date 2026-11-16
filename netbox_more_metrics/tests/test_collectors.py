from datetime import timedelta
from unittest.mock import patch

from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Rack, Site
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import now
from ipam.models import RIR, Aggregate, Prefix
from prometheus_client import CollectorRegistry
from prometheus_client.core import InfoMetricFamily
from prometheus_client.registry import REGISTRY
from utilities.testing.base import TestCase

from netbox_more_metrics.collectors import (
    DynamicMetricCollectionCollector,
    DynamicMetricCollector,
)
from netbox_more_metrics.models import Metric, MetricCollection


class CollectorBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)
        cls.prefix_ct = ObjectType.objects.get_for_model(Prefix)

        cls.site = Site.objects.create(name="Site Alpha", slug="site-alpha")
        cls.manufacturer = Manufacturer.objects.create(name="Cisco", slug="cisco")
        cls.device_type = DeviceType.objects.create(manufacturer=cls.manufacturer, model="Catalyst 9300", slug="c9300")
        cls.device_role = DeviceRole.objects.create(name="Switch", slug="switch")

        cls.device1 = Device.objects.create(
            name="switch-01",
            site=cls.site,
            device_type=cls.device_type,
            role=cls.device_role,
        )
        cls.device2 = Device.objects.create(
            name="switch-02",
            site=cls.site,
            device_type=cls.device_type,
            role=cls.device_role,
        )

        cls.rack1 = Rack.objects.create(name="Rack 1", site=cls.site, u_height=42)
        cls.rack2 = Rack.objects.create(name="Rack 2", site=cls.site, u_height=42)

        cls.rir = RIR.objects.create(name="RFC 1918", slug="rfc-1918")
        cls.aggregate = Aggregate.objects.create(prefix="10.0.0.0/8", rir=cls.rir)
        prefix_site_kwarg = {"scope": cls.site} if hasattr(Prefix, "scope") else {"site": cls.site}
        cls.prefix1 = Prefix.objects.create(prefix="10.1.0.0/24", **prefix_site_kwarg)
        cls.prefix2 = Prefix.objects.create(prefix="10.2.0.0/24", **prefix_site_kwarg)


# ---------------------------------------------------------------------
# Feature 6: Prometheus Suffix Collision Elimination (M2 / R3)
# ---------------------------------------------------------------------


class SuffixCollisionTier1TestCase(CollectorBaseTestCase):
    """Tier 1: Feature coverage for suffix collisions (_total, _info)."""

    def test_counter_ending_in_total_registers(self):
        col = MetricCollection.objects.create(name="TotalCol", enabled=True)
        m = Metric.objects.create(
            name="Packets Total",
            metric_name="device_packets_total",
            metric_description="Packets",
            metric_type="counter",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["status"],
        )
        col.metrics.add(m)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m.pk, collector._active_metric_collectors)

    def test_repeated_scrapes_of_total_counter_no_collision(self):
        col = MetricCollection.objects.create(name="TotalCol2", enabled=True)
        m = Metric.objects.create(
            name="Requests Total",
            metric_name="http_requests_total",
            metric_description="Requests",
            metric_type="counter",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["status"],
        )
        col.metrics.add(m)

        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=col)

        # Scrape 5 consecutive times
        for _ in range(5):
            metrics = list(registry.collect())
            self.assertTrue(len(metrics) > 0)

    def test_info_metric_ending_in_info_registers(self):
        col = MetricCollection.objects.create(name="InfoCol", enabled=True)
        m = Metric.objects.create(
            name="System Info",
            metric_name="system_build_info",
            metric_description="Build info",
            metric_type="info",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m.pk, collector._active_metric_collectors)

    def test_repeated_scrapes_of_info_metric_no_collision(self):
        col = MetricCollection.objects.create(name="InfoCol2", enabled=True)
        m = Metric.objects.create(
            name="Device Info",
            metric_name="device_hardware_info",
            metric_description="Hardware info",
            metric_type="info",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)

        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=col)
        for _ in range(5):
            metrics = list(registry.collect())
            self.assertTrue(len(metrics) > 0)

    def test_pk_tracking_integrity(self):
        col = MetricCollection.objects.create(name="MultiCol", enabled=True)
        m1 = Metric.objects.create(
            name="M1",
            metric_name="net_packets_total",
            metric_type="counter",
            content_type=self.device_ct,
            metric_labels=["status"],
        )
        m2 = Metric.objects.create(
            name="M2",
            metric_name="net_device_info",
            metric_type="info",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m1, m2)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(set(collector._active_metric_collectors.keys()), {m1.pk, m2.pk})


class SuffixCollisionTier2TestCase(CollectorBaseTestCase):
    """Tier 2: Boundary & Corner Cases for suffix collisions."""

    def test_metric_name_with_multiple_total_suffixes(self):
        col = MetricCollection.objects.create(name="DoubleTotalCol", enabled=True)
        m = Metric.objects.create(
            name="Double Total",
            metric_name="packets_total_total",
            metric_type="counter",
            content_type=self.device_ct,
            metric_labels=["status"],
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=col)
        for _ in range(3):
            list(registry.collect())

    def test_metric_name_stem_sharing(self):
        col = MetricCollection.objects.create(name="StemSharingCol", enabled=True)
        m1 = Metric.objects.create(
            name="Stem Gauge",
            metric_name="cpu_load_percent",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        m2 = Metric.objects.create(
            name="Stem Counter",
            metric_name="cpu_load_total",
            metric_type="counter",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m1, m2)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m1.pk, collector._active_metric_collectors)
        self.assertIn(m2.pk, collector._active_metric_collectors)
        metrics = list(registry.collect())
        self.assertEqual(len(metrics), 2)

    def test_metric_name_exactly_total_or_info(self):
        m = Metric(
            name="Bare Total",
            metric_name="_total",
            metric_type="counter",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        m.clean()
        self.assertEqual(m.metric_name, "_total")

    def test_reregistration_after_unregister(self):
        m = Metric.objects.create(
            name="Reregister Metric",
            metric_name="rereg_total",
            metric_type="counter",
            content_type=self.device_ct,
            metric_labels=["status"],
        )
        registry = CollectorRegistry()
        dyn_collector = DynamicMetricCollector(metric=m, registry=registry)
        self.assertTrue(dyn_collector.is_valid)
        dyn_collector.unregister()
        self.assertFalse(dyn_collector.is_valid)

        # Re-register
        dyn_collector2 = DynamicMetricCollector(metric=m, registry=registry)
        self.assertTrue(dyn_collector2.is_valid)

    def test_disabled_total_metric_removed_from_active_tracking(self):
        col = MetricCollection.objects.create(name="DisableTrackingCol", enabled=True)
        m = Metric.objects.create(
            name="Tracking Metric",
            metric_name="track_packets_total",
            metric_type="counter",
            content_type=self.device_ct,
            metric_labels=["status"],
            enabled=True,
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m.pk, collector._active_metric_collectors)

        m.enabled = False
        m.save()
        collector._refresh_collectors()
        self.assertNotIn(m.pk, collector._active_metric_collectors)


# ---------------------------------------------------------------------
# Feature 7: Disabled Collection Export Gating (M2 / R3)
# ---------------------------------------------------------------------


class DisabledCollectionGatingTier1TestCase(CollectorBaseTestCase):
    """Tier 1: Feature coverage for disabled collection gating."""

    def test_disabled_collection_init_returns_empty(self):
        col = MetricCollection.objects.create(name="DisabledCol", enabled=False)
        m = Metric.objects.create(
            name="DisMetric",
            metric_name="dis_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(collector._active_metric_collectors, {})
        self.assertEqual(list(collector.collect()), [])

    def test_disabled_collection_export_empty_samples(self):
        col = MetricCollection.objects.create(name="DisabledCol2", enabled=False)
        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=col)
        metrics = list(registry.collect())
        self.assertEqual(metrics, [])

    def test_enabling_collection_resumes_emission(self):
        col = MetricCollection.objects.create(name="ToggleCol", enabled=False)
        m = Metric.objects.create(
            name="ToggleMetric",
            metric_name="toggle_device_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(collector._active_metric_collectors, {})

        # Enable collection
        col.enabled = True
        col.save()
        collector.collection = col
        collector._refresh_collectors()
        self.assertIn(m.pk, collector._active_metric_collectors)

    def test_global_collector_excludes_disabled_collections(self):
        col_dis = MetricCollection.objects.create(name="GlobalDisCol", enabled=False)
        m_dis = Metric.objects.create(
            name="DisMetricGlobal",
            metric_name="global_dis_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col_dis.metrics.add(m_dis)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=None)
        self.assertNotIn(m_dis.pk, collector._active_metric_collectors)

    def test_no_redundant_m2m_join_in_query(self):
        col = MetricCollection.objects.create(name="NoRedundantJoinCol", enabled=True)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        sql = str(collector.base_queryset.query)
        self.assertEqual(sql.count("JOIN"), 1)


class DisabledCollectionGatingTier2TestCase(CollectorBaseTestCase):
    """Tier 2: Boundary & Corner Cases for disabled collection gating."""

    def test_metric_enabled_in_disabled_collection(self):
        col = MetricCollection.objects.create(name="DisColM", enabled=False)
        m = Metric.objects.create(
            name="M1",
            metric_name="m1_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(len(list(registry.collect())), 0)

    def test_metric_disabled_in_enabled_collection(self):
        col = MetricCollection.objects.create(name="EnColM", enabled=True)
        m = Metric.objects.create(
            name="M2",
            metric_name="m2_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=False,
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(len(list(registry.collect())), 0)

    def test_metric_in_mixed_enabled_disabled_collections(self):
        col_a = MetricCollection.objects.create(name="ColA", enabled=True)
        col_b = MetricCollection.objects.create(name="ColB", enabled=False)
        m = Metric.objects.create(
            name="MixedMetric",
            metric_name="mixed_device_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        col_a.metrics.add(m)
        col_b.metrics.add(m)

        reg_a = CollectorRegistry()
        col_collector_a = DynamicMetricCollectionCollector(registry=reg_a, collection=col_a)
        self.assertIn(m.pk, col_collector_a._active_metric_collectors)

        reg_b = CollectorRegistry()
        col_collector_b = DynamicMetricCollectionCollector(registry=reg_b, collection=col_b)
        self.assertNotIn(m.pk, col_collector_b._active_metric_collectors)

    def test_dynamic_disabling_during_process_lifetime(self):
        col = MetricCollection.objects.create(name="DynDisCol", enabled=True)
        m = Metric.objects.create(
            name="DynMetric",
            metric_name="dyn_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m.pk, collector._active_metric_collectors)

        col.enabled = False
        col.save()
        collector.collect()
        self.assertEqual(collector._active_metric_collectors, {})

    def test_collection_with_zero_metrics(self):
        col = MetricCollection.objects.create(name="EmptyCol", enabled=True)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(list(collector.collect()), [])


# ---------------------------------------------------------------------
# Feature 8: Collector Lifecycle Resilience (M2 / R3)
# ---------------------------------------------------------------------


class CollectorLifecycleTier1TestCase(CollectorBaseTestCase):
    """Tier 1: Feature coverage for collector lifecycle resilience."""

    def test_unregister_non_default_registry_safe(self):
        m = Metric.objects.create(
            name="UnregM",
            metric_name="unreg_test_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        self.assertTrue(collector.is_valid)

        # Unregister twice; should not raise KeyError
        collector.unregister()
        self.assertFalse(collector.is_valid)
        collector.unregister()

    def test_renew_unvalidated_collector_returns_invalid(self):
        m = Metric.objects.create(
            name="InvalidFilterM",
            metric_name="invalid_filter_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)

        # Corrupt the filter
        m.filter = {"nonexistent_column": "bad"}
        renewed = collector.renew()
        self.assertFalse(renewed.is_valid)
        self.assertEqual(list(renewed.collect()), [])

    def test_metric_with_null_last_updated(self):
        col = MetricCollection.objects.create(name="NullUpdateCol", enabled=True)
        m = Metric.objects.create(
            name="NullUpdateM",
            metric_name="null_update_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        Metric.objects.filter(pk=m.pk).update(last_updated=None)
        m.refresh_from_db()

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        # Should not raise TypeError or AttributeError
        collector._refresh_collectors()

    def test_info_metric_family_format(self):
        m = Metric.objects.create(
            name="InfoFormatM",
            metric_name="info_format_test",
            metric_type="info",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        family = families[0]
        self.assertIsInstance(family, InfoMetricFamily)

    def test_collect_generator_semantics_no_dead_code(self):
        col = MetricCollection.objects.create(name="GenSemanticsCol", enabled=True)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        result = list(collector.collect())
        self.assertEqual(result, [])


class CollectorLifecycleTier2TestCase(CollectorBaseTestCase):
    """Tier 2: Boundary & Corner Cases for collector lifecycle."""

    def test_collector_when_model_is_none(self):
        m = Metric(
            name="BadModelM",
            metric_name="bad_model_metric",
            metric_type="gauge",
            content_type=None,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        self.assertFalse(collector.is_valid)

    def test_collector_describe_method(self):
        m = Metric.objects.create(
            name="DescribeM",
            metric_name="describe_test_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        desc = list(collector.describe())
        self.assertEqual(len(desc), 1)
        self.assertEqual(desc[0].name, "describe_test_metric")

    def test_renew_when_metric_filter_corrupted(self):
        col = MetricCollection.objects.create(name="CorruptCol", enabled=True)
        m = Metric.objects.create(
            name="CorruptM",
            metric_name="corrupt_test_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m.pk, collector._active_metric_collectors)

        # Update metric to invalid filter and advance timestamp
        m.filter = {"nonexistent_field__exact": 123}
        m.last_updated = now() + timedelta(seconds=5)
        m.save()
        collector._refresh_collectors()
        self.assertNotIn(m.pk, collector._active_metric_collectors)

    def test_timestamp_comparison_equal_timestamps(self):
        m = Metric.objects.create(
            name="EqualTimeM",
            metric_name="equal_time_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col = MetricCollection.objects.create(name="EqualTimeCol", enabled=True)
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)

        with patch.object(DynamicMetricCollector, "renew") as mock_renew:
            collector._refresh_collectors()
            mock_renew.assert_not_called()

    def test_default_registry_counter_cleanup(self):
        m = Metric.objects.create(
            name="DefaultRegCleanupM",
            metric_name="default_reg_cleanup_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        collector = DynamicMetricCollector(metric=m, registry=REGISTRY)
        collector.unregister()
        self.assertFalse(collector.is_valid)


# ---------------------------------------------------------------------
# Feature 10: Utilization Metric Series Deduplication (M2 / R3)
# ---------------------------------------------------------------------


class UtilizationDeduplicationTier1TestCase(CollectorBaseTestCase):
    """Tier 1: Feature coverage for utilization metric deduplication."""

    def test_rack_utilization_unique_series(self):
        m = Metric.objects.create(
            name="RackUtilization",
            metric_name="netbox_rack_utilization",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["site__slug"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        # Both racks are in site Alpha; with label site__slug only, deduplicates to 1 sample
        self.assertEqual(len(families[0].samples), 1)

    def test_rack_power_utilization_unique_series(self):
        m = Metric.objects.create(
            name="RackPowerUtilization",
            metric_name="netbox_rack_power_utilization",
            metric_type="gauge",
            metric_value="get_power_utilization",
            content_type=self.rack_ct,
            metric_labels=["site__slug"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(len(families[0].samples), 1)

    def test_prefix_utilization_unique_series(self):
        m = Metric.objects.create(
            name="PrefixUtilization",
            metric_name="netbox_prefix_utilization",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.prefix_ct,
            metric_labels=["status"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(len(families[0].samples), 1)

    def test_no_count_star_in_method_result(self):
        m = Metric.objects.create(
            name="NoCountStarM",
            metric_name="no_count_star_util",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        qs = collector.get_metric_result()
        # Method query does not have .values("count", ...) aggregation
        self.assertNotIn("count", qs.query.annotations)

    def test_method_metric_value_evaluation(self):
        m = Metric.objects.create(
            name="EvalMethodM",
            metric_name="eval_method_util",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        # Racks have 0 devices, utilization is 0.0
        self.assertAlmostEqual(families[0].samples[0].value, 0.0)


class UtilizationDeduplicationTier2TestCase(CollectorBaseTestCase):
    """Tier 2: Boundary & Corner Cases for utilization deduplication."""

    def test_multiple_rows_empty_labels(self):
        m = Metric.objects.create(
            name="EmptyLabelsUtil",
            metric_name="empty_labels_util",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=[],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(len(families[0].samples), 1)

    def test_zero_utilization_value(self):
        m = Metric.objects.create(
            name="ZeroUtilM",
            metric_name="zero_util_metric",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertTrue(any(s.value == 0.0 for s in families[0].samples))

    def test_empty_queryset_utilization(self):
        m = Metric.objects.create(
            name="EmptyQsUtil",
            metric_name="empty_qs_util",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
            filter={"name": "nonexistent_rack_999"},
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(len(families[0].samples), 0)

    def test_method_returning_none(self):
        m = Metric.objects.create(
            name="NoneMethodM",
            metric_name="none_method_metric",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        with patch.object(Rack, "get_utilization", return_value=None):
            # Safe handling of None
            try:
                list(collector.collect())
            except Exception as e:
                self.fail(f"collect() crashed on None method return: {e}")

    def test_distinct_labelsets_preserved(self):
        m = Metric.objects.create(
            name="DistinctRackUtil",
            metric_name="distinct_rack_util",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        # Rack 1 and Rack 2 have distinct names, both emitted
        self.assertEqual(len(families[0].samples), 2)


# ---------------------------------------------------------------------
# Feature 13: 2N+1 Scrape Query Optimization (M2 / R3)
# ---------------------------------------------------------------------


class QueryOptimizationTier1TestCase(CollectorBaseTestCase):
    """Tier 1: Feature coverage for 2N+1 scrape query optimization."""

    def test_no_refresh_from_db_in_collect(self):
        col = MetricCollection.objects.create(name="OptCol", enabled=True)
        m = Metric.objects.create(
            name="OptM",
            metric_name="opt_metric_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)

        with patch.object(Metric, "refresh_from_db") as mock_refresh:
            collector.collect()
            mock_refresh.assert_not_called()

    def test_prefetch_related_collections(self):
        col = MetricCollection.objects.create(name="PrefetchCol", enabled=True)
        m = Metric.objects.create(
            name="PrefetchM",
            metric_name="prefetch_metric_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        qs = collector._get_enabled_metrics()
        self.assertIn("collections", qs._prefetch_related_lookups)

    def test_is_metric_enabled_uses_prefetched_cache(self):
        col = MetricCollection.objects.create(name="PrefetchCacheCol", enabled=True)
        m = Metric.objects.create(
            name="CacheM",
            metric_name="cache_metric_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        # Fetch with prefetch
        m_prefetched = Metric.objects.prefetch_related("collections").get(pk=m.pk)
        registry = CollectorRegistry()
        dyn_collector = DynamicMetricCollector(metric=m_prefetched, registry=registry)

        with CaptureQueriesContext(connection) as queries:
            enabled = dyn_collector.is_metric_enabled()
            self.assertTrue(enabled)
            # Should not issue SQL queries
            self.assertEqual(len(queries), 0)

    def test_query_count_scales_linearly(self):
        col = MetricCollection.objects.create(name="LinearCol", enabled=True)
        for i in range(3):
            m = Metric.objects.create(
                name=f"LinearM{i}",
                metric_name=f"linear_metric_{i}",
                metric_type="gauge",
                content_type=self.device_ct,
                metric_labels=["name"],
            )
            col.metrics.add(m)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        with CaptureQueriesContext(connection) as queries:
            collector._refresh_collectors()
            # Must be a fixed small number of queries (metrics query + prefetch query), not 2N+1
            self.assertLessEqual(len(queries), 4)

    def test_distinct_on_metrics_queryset(self):
        col = MetricCollection.objects.create(name="DistinctCol", enabled=True)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        qs = collector._get_enabled_metrics()
        self.assertTrue(qs.query.distinct)


class QueryOptimizationTier2TestCase(CollectorBaseTestCase):
    """Tier 2: Boundary & Corner Cases for query optimization."""

    def test_fallback_when_cache_not_populated(self):
        col = MetricCollection.objects.create(name="FallbackCol", enabled=True)
        m = Metric.objects.create(
            name="FallbackM",
            metric_name="fallback_metric_count",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col.metrics.add(m)
        m_bare = Metric.objects.get(pk=m.pk)
        registry = CollectorRegistry()
        dyn_collector = DynamicMetricCollector(metric=m_bare, registry=registry)
        # Should cleanly query DB and return True
        self.assertTrue(dyn_collector.is_metric_enabled())

    def test_default_registry_prefetch_logic(self):
        col1 = MetricCollection.objects.create(name="DefaultCol1", enabled=True, include_in_default=True)
        col2 = MetricCollection.objects.create(name="DefaultCol2", enabled=True, include_in_default=False)
        m1 = Metric.objects.create(
            name="DefM1",
            metric_name="def_m1",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col1.metrics.add(m1)
        m2 = Metric.objects.create(
            name="DefM2",
            metric_name="def_m2",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        col2.metrics.add(m2)

        m1_pref = Metric.objects.prefetch_related("collections").get(pk=m1.pk)
        m2_pref = Metric.objects.prefetch_related("collections").get(pk=m2.pk)

        c1 = DynamicMetricCollector(metric=m1_pref, registry=REGISTRY)
        self.addCleanup(c1.unregister)
        c2 = DynamicMetricCollector(metric=m2_pref, registry=REGISTRY)
        self.addCleanup(c2.unregister)

        self.assertTrue(c1.is_metric_enabled())
        self.assertFalse(c2.is_metric_enabled())

    def test_queryset_evaluation_efficiency(self):
        col = MetricCollection.objects.create(name="EffCol", enabled=True)
        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        # Empty collection should not execute heavy queries
        metrics = list(collector._get_enabled_metrics())
        self.assertEqual(metrics, [])

    def test_metrics_without_collections_ignored(self):
        m = Metric.objects.create(
            name="NoColM",
            metric_name="no_col_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        dyn = DynamicMetricCollector(metric=m, registry=registry)
        self.assertFalse(dyn.is_metric_enabled())

    def test_bulk_metric_refresh_behavior(self):
        col = MetricCollection.objects.create(name="BulkCol", enabled=True)
        for i in range(5):
            m = Metric.objects.create(
                name=f"BulkM{i}",
                metric_name=f"bulk_metric_{i}",
                metric_type="gauge",
                content_type=self.device_ct,
                metric_labels=["name"],
            )
            col.metrics.add(m)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertEqual(len(collector._active_metric_collectors), 5)


# ---------------------------------------------------------------------
# Feature 15: Relational Label Annotation Alias Fix (M2 / R3)
# ---------------------------------------------------------------------


class RelationalLabelAliasTier1TestCase(CollectorBaseTestCase):
    """Tier 1: Feature coverage for relational label annotation alias sanitization."""

    def test_get_annotation_alias_simple(self):
        m = Metric.objects.create(
            name="SimpleAliasM",
            metric_name="simple_alias_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        alias = collector.get_annotation_alias("name")
        self.assertEqual(alias, "_metric_label_name")

    def test_get_annotation_alias_multi_hop(self):
        m = Metric.objects.create(
            name="MultiHopAliasM",
            metric_name="multi_hop_alias_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["site__name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        alias = collector.get_annotation_alias("site__name")
        self.assertNotIn("__", alias)
        self.assertTrue(alias.startswith("_metric_label_site_name_"))

    def test_get_annotation_alias_sha256_hash(self):
        m = Metric.objects.create(
            name="HashAliasM",
            metric_name="hash_alias_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["rack__site__name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        alias = collector.get_annotation_alias("rack__site__name")
        # Suffix should be 8 hex chars
        parts = alias.split("_")
        self.assertEqual(len(parts[-1]), 8)

    def test_relational_annotation_query_executes(self):
        m = Metric.objects.create(
            name="RelExecM",
            metric_name="rel_exec_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["site__name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertTrue(any(s.labels.get("site__name") == "Site Alpha" for s in families[0].samples))

    def test_custom_field_annotation_jsonb(self):
        m = Metric.objects.create(
            name="CustomFieldM",
            metric_name="custom_field_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["custom_field_data__env"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)


class RelationalLabelAliasTier2TestCase(CollectorBaseTestCase):
    """Tier 2: Boundary & Corner Cases for relational label annotation alias."""

    def test_annotation_alias_collision_resistance(self):
        m = Metric.objects.create(
            name="ColResistM",
            metric_name="col_resist_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["site__name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        alias1 = collector.get_annotation_alias("site__name")
        alias2 = collector.get_annotation_alias("site_name")
        self.assertNotEqual(alias1, alias2)

    def test_leading_and_trailing_underscores_stripped(self):
        m = Metric.objects.create(
            name="UnderStripM",
            metric_name="under_strip_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        alias = collector.get_annotation_alias("__label__")
        self.assertNotIn("____", alias)

    def test_null_coalescence_in_annotations(self):
        Device.objects.create(
            name="no-rack-dev",
            site=self.site,
            device_type=self.device_type,
            role=self.device_role,
            rack=None,
        )
        m = Metric.objects.create(
            name="NullRackM",
            metric_name="null_rack_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name", "rack__name"],
            filter={"name": "no-rack-dev"},
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(families[0].samples[0].labels.get("rack__name"), "null")

    def test_custom_field_null_coalescence(self):
        m = Metric.objects.create(
            name="NullCustomFieldM",
            metric_name="null_custom_field_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["name", "custom_field_data__nonexistent_field"],
            filter={"name": "switch-01"},
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(families[0].samples[0].labels.get("custom_field_data__nonexistent_field"), "null")

    def test_deep_multi_hop_annotation_alias(self):
        m = Metric.objects.create(
            name="DeepHopM",
            metric_name="deep_hop_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["device_type__manufacturer__name"],
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry)
        alias = collector.get_annotation_alias("device_type__manufacturer__name")
        self.assertNotIn("__", alias)
        self.assertTrue(alias.startswith("_metric_label_device_type_manufacturer_name_"))
