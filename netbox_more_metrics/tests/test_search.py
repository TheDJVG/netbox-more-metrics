from core.models import ObjectType
from dcim.models import Device
from netbox.search import SearchIndex
from netbox.search.backends import search_backend
from utilities.testing.base import TestCase

from netbox_more_metrics.models import Metric, MetricCollection
from netbox_more_metrics.search import MetricCollectionIndex, MetricIndex, indexes


class SearchIndexBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)

        cls.collection = MetricCollection.objects.create(
            name="Searchable Collection",
            description="A special cluster monitoring collection",
            enabled=True,
        )
        cls.metric = Metric.objects.create(
            name="Searchable Metric",
            metric_name="searchable_metric_count",
            metric_description="Metrics for testing full text search",
            metric_type="gauge",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        # NetBox 4.7+ defers search indexing via transaction.on_commit; populate cache explicitly in setUpTestData.
        search_backend.cache([cls.collection])
        search_backend.cache([cls.metric])


# =====================================================================
# Feature 17: NetBox 4.x Search Indexing (M3 / R3)
# =====================================================================


class SearchIndexTier1TestCase(SearchIndexBaseTestCase):
    """Tier 1: Feature coverage for NetBox 4.x SearchIndex registration and configuration."""

    def test_search_index_registration(self):
        self.assertTrue(issubclass(MetricCollectionIndex, SearchIndex))
        self.assertTrue(issubclass(MetricIndex, SearchIndex))

    def test_metric_collection_index_fields(self):
        field_dict = dict(MetricCollectionIndex.fields)
        self.assertIn("name", field_dict)
        self.assertIn("description", field_dict)
        self.assertEqual(field_dict["name"], 100)
        self.assertEqual(field_dict["description"], 500)

    def test_metric_collection_index_display_attrs(self):
        self.assertIn("description", MetricCollectionIndex.display_attrs)
        self.assertIn("enabled", MetricCollectionIndex.display_attrs)

    def test_metric_index_fields(self):
        field_dict = dict(MetricIndex.fields)
        self.assertIn("name", field_dict)
        self.assertIn("metric_name", field_dict)
        self.assertIn("metric_description", field_dict)
        self.assertEqual(field_dict["name"], 100)
        self.assertEqual(field_dict["metric_name"], 100)
        self.assertEqual(field_dict["metric_description"], 500)

    def test_metric_index_display_attrs(self):
        attrs = MetricIndex.display_attrs
        self.assertIn("metric_name", attrs)
        self.assertIn("metric_description", attrs)
        self.assertIn("metric_type", attrs)
        self.assertIn("metric_value", attrs)
        self.assertIn("enabled", attrs)


class SearchIndexTier2TestCase(SearchIndexBaseTestCase):
    """Tier 2: Boundary & Corner Cases for SearchIndex backend queries."""

    def test_search_index_model_binding(self):
        self.assertEqual(MetricCollectionIndex.model, MetricCollection)
        self.assertEqual(MetricIndex.model, Metric)

    def test_search_indexes_tuple(self):
        self.assertIn(MetricCollectionIndex, indexes)
        self.assertIn(MetricIndex, indexes)

    def test_search_backend_query_metric_collection(self):
        results = search_backend.search("Searchable Collection", user=self.user)
        # Search backend returns search entries
        matching = [r for r in results if r.object == self.collection]
        self.assertEqual(len(matching), 1)

    def test_search_backend_query_metric(self):
        results = search_backend.search("searchable_metric_count", user=self.user)
        matching = [r for r in results if r.object == self.metric]
        self.assertEqual(len(matching), 1)

    def test_search_index_weight_ordering(self):
        # Weight 100 takes precedence over 500 in NetBox ranking
        fields = dict(MetricIndex.fields)
        self.assertLess(fields["name"], fields["metric_description"])
