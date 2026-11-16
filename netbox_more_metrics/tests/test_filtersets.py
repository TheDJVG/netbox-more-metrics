from core.models import ObjectType
from dcim.models import Device, Rack
from netbox.filtersets import NetBoxModelFilterSet
from utilities.testing.base import TestCase

from netbox_more_metrics.filtersets import MetricCollectionFilterSet, MetricFilterSet
from netbox_more_metrics.models import Metric, MetricCollection


class FilterSetBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)

        cls.col1 = MetricCollection.objects.create(
            name="Alpha Collection", description="Alpha description", enabled=True, include_in_default=True
        )
        cls.col2 = MetricCollection.objects.create(
            name="Beta Collection", description="Beta description", enabled=False, include_in_default=False
        )
        cls.col3 = MetricCollection.objects.create(
            name="Gamma Collection", description="Gamma description", enabled=True, include_in_default=False
        )

        cls.m1 = Metric.objects.create(
            name="Device Count Alpha",
            metric_name="dev_count_alpha",
            metric_description="Count devices in Alpha",
            metric_type="gauge",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name", "status"],
            enabled=True,
        )
        cls.m1.collections.add(cls.col1)

        cls.m2 = Metric.objects.create(
            name="Rack Util Beta",
            metric_name="rack_util_beta",
            metric_description="Rack utilization",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=cls.rack_ct,
            metric_labels=["site__name"],
            enabled=False,
        )
        cls.m2.collections.add(cls.col2)

        cls.m3 = Metric.objects.create(
            name="Packets Total Gamma",
            metric_name="packets_total_gamma",
            metric_description="Total packets",
            metric_type="counter",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["status"],
            enabled=True,
        )
        cls.m3.collections.add(cls.col3)


# =====================================================================
# Feature 16: NetBox 4.x FilterSets (M3 / R3)
# =====================================================================


class FilterSetTier1TestCase(FilterSetBaseTestCase):
    """Tier 1: Feature coverage for NetBox 4.x FilterSets."""

    def test_filterset_inheritance(self):
        self.assertTrue(issubclass(MetricCollectionFilterSet, NetBoxModelFilterSet))
        self.assertTrue(issubclass(MetricFilterSet, NetBoxModelFilterSet))

    def test_filter_collection_by_name(self):
        params = {"name": ["Alpha Collection"]}
        fs = MetricCollectionFilterSet(params, queryset=MetricCollection.objects.all())
        self.assertEqual(fs.qs.count(), 1)
        self.assertEqual(fs.qs.first(), self.col1)

    def test_filter_collection_by_enabled(self):
        params = {"enabled": True}
        fs = MetricCollectionFilterSet(params, queryset=MetricCollection.objects.all())
        self.assertEqual(fs.qs.count(), 2)
        self.assertNotIn(self.col2, fs.qs)

    def test_filter_collection_by_include_in_default(self):
        params = {"include_in_default": True}
        fs = MetricCollectionFilterSet(params, queryset=MetricCollection.objects.all())
        self.assertEqual(fs.qs.count(), 1)
        self.assertEqual(fs.qs.first(), self.col1)

    def test_filter_metric_by_metric_type(self):
        params = {"metric_type": ["counter"]}
        fs = MetricFilterSet(params, queryset=Metric.objects.all())
        self.assertEqual(fs.qs.count(), 1)
        self.assertEqual(fs.qs.first(), self.m3)


class FilterSetTier2TestCase(FilterSetBaseTestCase):
    """Tier 2: Boundary & Corner Cases for NetBox 4.x FilterSets."""

    def test_filter_metric_by_content_type(self):
        params = {"content_type_id": [self.rack_ct.pk]}
        fs = MetricFilterSet(params, queryset=Metric.objects.all())
        self.assertEqual(fs.qs.count(), 1)
        self.assertEqual(fs.qs.first(), self.m2)

    def test_filter_metric_by_collection(self):
        params = {"collection_id": [self.col1.pk]}
        fs = MetricFilterSet(params, queryset=Metric.objects.all())
        self.assertEqual(fs.qs.count(), 1)
        self.assertEqual(fs.qs.first(), self.m1)

        params_name = {"collection": [self.col3.name]}
        fs_name = MetricFilterSet(params_name, queryset=Metric.objects.all())
        self.assertEqual(fs_name.qs.count(), 1)
        self.assertEqual(fs_name.qs.first(), self.m3)

    def test_filter_metric_labels_array(self):
        params = {"metric_labels": ["status"]}
        fs = MetricFilterSet(params, queryset=Metric.objects.all())
        # Both m1 (labels: name, status) and m3 (labels: status) contain "status"
        self.assertEqual(fs.qs.count(), 2)
        self.assertNotIn(self.m2, fs.qs)

    def test_filterset_search_method(self):
        # Search by q in MetricFilterSet
        params = {"q": "utilization"}
        fs = MetricFilterSet(params, queryset=Metric.objects.all())
        self.assertEqual(fs.qs.count(), 1)
        self.assertEqual(fs.qs.first(), self.m2)

        # Search by q in MetricCollectionFilterSet
        params_col = {"q": "Beta"}
        fs_col = MetricCollectionFilterSet(params_col, queryset=MetricCollection.objects.all())
        self.assertEqual(fs_col.qs.count(), 1)
        self.assertEqual(fs_col.qs.first(), self.col2)

    def test_filterset_empty_search(self):
        params = {"q": "   "}
        fs = MetricFilterSet(params, queryset=Metric.objects.all())
        self.assertEqual(fs.qs.count(), Metric.objects.count())
