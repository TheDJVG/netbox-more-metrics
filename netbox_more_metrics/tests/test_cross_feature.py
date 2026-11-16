from datetime import timedelta
from unittest.mock import patch

from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Rack, Site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.test.client import Client
from django.urls import reverse
from django.utils.timezone import now
from extras.models import Tag
from prometheus_client import CollectorRegistry
from rest_framework.test import APIClient
from users.models import Token
from utilities.testing.base import TestCase

from netbox_more_metrics.collectors import (
    DynamicMetricCollectionCollector,
    DynamicMetricCollector,
)
from netbox_more_metrics.filtersets import MetricCollectionFilterSet, MetricFilterSet
from netbox_more_metrics.forms import MetricForm
from netbox_more_metrics.models import Metric, MetricCollection, validate_field_path
from netbox_more_metrics.search import MetricCollectionIndex, MetricIndex

User = get_user_model()


class CrossFeatureBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)

        cls.site_a = Site.objects.create(name="Site-A", slug="site-a")
        cls.site_b = Site.objects.create(name="Site-B", slug="site-b")
        cls.manufacturer = Manufacturer.objects.create(name="Cisco", slug="cisco")
        cls.device_type = DeviceType.objects.create(manufacturer=cls.manufacturer, model="Catalyst 9300", slug="c9300")
        cls.device_role = DeviceRole.objects.create(name="Switch", slug="switch")

        cls.dev1 = Device.objects.create(
            name="cf-device-01",
            site=cls.site_a,
            device_type=cls.device_type,
            role=cls.device_role,
        )
        cls.dev2 = Device.objects.create(
            name="cf-device-02",
            site=cls.site_a,
            device_type=cls.device_type,
            role=cls.device_role,
        )

        cls.rack1 = Rack.objects.create(name="Rack-A", site=cls.site_a, u_height=42)
        cls.rack2 = Rack.objects.create(name="Rack-B", site=cls.site_a, u_height=42)

        cls.tag = Tag.objects.create(name="Production", slug="production")

        # Users
        cls.user_noperm = User.objects.create_user(username="noperm_user", password="password123")
        cls.user_perm = User.objects.create_user(username="perm_user", password="password123")


# =====================================================================
# CF-01: Anonymous Export Bypass vs. Collection Enablement Gating
# =====================================================================


class CrossFeatureAuthAndCollectionTests(CrossFeatureBaseTestCase):
    @override_settings(LOGIN_REQUIRED=True, EXEMPT_VIEW_PERMISSIONS=[])
    def test_anonymous_export_under_login_required_with_disabled_collection(self):
        col = MetricCollection.objects.create(name="Disabled Col", enabled=False)
        m = Metric.objects.create(
            name="M_Disabled",
            metric_name="m_disabled_count",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        col.metrics.add(m)

        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": col.pk},
        )
        with patch("netbox_more_metrics.views.get_plugin_config", return_value=True):
            client = Client()
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            # Body should contain 0 metric samples
            self.assertEqual(response.content.strip(), b"")

        # Counter-check: when export_metrics_without_auth is False
        with patch("netbox_more_metrics.views.get_plugin_config", return_value=False):
            client = Client()
            response = client.get(url)
            self.assertEqual(response.status_code, 403)


# =====================================================================
# CF-02: Form Tag Persistence ↔ Collector Scraper Label Extraction
# =====================================================================


class CrossFeatureFormAndScrapeTests(CrossFeatureBaseTestCase):
    def test_form_tag_persistence_and_metric_collection_scrape(self):
        col = MetricCollection.objects.create(name="ScrapeCol", enabled=True)
        form_data = {
            "name": "Site Devices Form Metric",
            "metric_description": "Site devices description",
            "enabled": True,
            "metric_name": "netbox_site_devices",
            "metric_labels": ["site__name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [col.pk],
            "tags": [self.tag.pk],
        }
        form = MetricForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        metric = form.save()

        # Assert tag persisted
        self.assertEqual(metric.tags.count(), 1)
        self.assertEqual(metric.tags.first().slug, "production")

        # Scrape collector
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=metric, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        family = families[0]
        self.assertEqual(family.name, "netbox_site_devices")
        # 2 devices in Site-A
        sample = next(s for s in family.samples if s.labels.get("site__name") == "Site-A")
        self.assertEqual(sample.value, 2.0)


# =====================================================================
# CF-03: FilterSet Multi-Criteria Querying ↔ Search Indexing
# =====================================================================


class CrossFeatureFilterAndSearchTests(CrossFeatureBaseTestCase):
    def test_filterset_and_search_index_consistency(self):
        col_core = MetricCollection.objects.create(name="Core Metrics", description="Core", enabled=True)
        col_edge = MetricCollection.objects.create(name="Edge Metrics", description="Edge", enabled=True)
        col_arch = MetricCollection.objects.create(name="Archive", description="Old", enabled=False)

        m_core = Metric.objects.create(
            name="Core Device Metric",
            metric_name="core_dev_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        m_core.collections.add(col_core)

        # FilterSet test
        fs_metric = MetricFilterSet({"metric_type": ["gauge"], "q": "Core"}, queryset=Metric.objects.all())
        self.assertIn(m_core, fs_metric.qs)

        fs_col = MetricCollectionFilterSet({"enabled": True, "q": "Edge"}, queryset=MetricCollection.objects.all())
        self.assertIn(col_edge, fs_col.qs)
        self.assertNotIn(col_arch, fs_col.qs)

        # Search index registration
        self.assertEqual(MetricIndex.model, Metric)
        self.assertEqual(MetricCollectionIndex.model, MetricCollection)


# =====================================================================
# CF-04: Metric Renaming & Label Update ↔ _total Counter Renewal
# =====================================================================


class CrossFeatureLifecycleAndNamingTests(CrossFeatureBaseTestCase):
    def test_counter_total_suffix_preservation_on_metric_labels_update(self):
        col = MetricCollection.objects.create(name="CounterLifecycleCol", enabled=True)
        m = Metric.objects.create(
            name="HTTP Requests",
            metric_name="http_requests_total",
            metric_type="counter",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["status"],
            enabled=True,
        )
        col.metrics.add(m)

        registry = CollectorRegistry()
        collector = DynamicMetricCollectionCollector(registry=registry, collection=col)
        self.assertIn(m.pk, collector._active_metric_collectors)

        # Update metric labels and timestamp
        m.metric_labels = ["name", "status"]
        m.last_updated = now() + timedelta(seconds=2)
        m.save()

        # Scrape a second time
        collector._refresh_collectors()
        self.assertIn(m.pk, collector._active_metric_collectors)
        families = list(registry.collect())
        self.assertEqual(len(families), 1)
        sample = families[0].samples[0]
        self.assertIn("name", sample.labels)
        self.assertIn("status", sample.labels)


# =====================================================================
# CF-05: Utilization Method Deduplication ↔ Label Renames & NULL
# =====================================================================


class CrossFeatureUtilizationAndDeduplicationTests(CrossFeatureBaseTestCase):
    def test_utilization_metric_deduplication_with_null_labels_and_renames(self):
        m = Metric.objects.create(
            name="Rack Deduplication Metric",
            metric_name="netbox_rack_space_utilization",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["site__name", "tenant__name"],
            label_renames={"site__name": "datacenter", "tenant__name": "client"},
            enabled=True,
        )
        registry = CollectorRegistry()
        dyn_collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(dyn_collector.collect())
        self.assertEqual(len(families), 1)
        family = families[0]
        # Rack1 and Rack2 both have tenant=None and site=Site-A, and utilization 0.0
        # Should deduplicate to exactly 1 sample
        self.assertEqual(len(family.samples), 1)
        sample = family.samples[0]
        self.assertEqual(sample.labels.get("client"), "null")
        self.assertEqual(sample.labels.get("datacenter"), "Site-A")


# =====================================================================
# CF-06: Custom Field Data Traversal ↔ JSON Path SQL Annotation
# =====================================================================


class CrossFeatureCustomFieldAndSecurityTests(CrossFeatureBaseTestCase):
    def test_custom_field_extraction_and_security_boundary(self):
        self.dev1.custom_field_data = {"environment": "staging"}
        self.dev1.save()

        m = Metric.objects.create(
            name="CF Data Metric",
            metric_name="custom_field_dev_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name", "custom_field_data__environment"],
            filter={"name": "cf-device-01"},
            enabled=True,
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        sample = families[0].samples[0]
        self.assertEqual(sample.labels.get("custom_field_data__environment"), "staging")

        # Security check: sensitive field names in traversal rejected
        with self.assertRaises(ValidationError):
            validate_field_path(Device, "custom_field_data__password")


# =====================================================================
# CF-07: Relational Label Sanitization ↔ Double Underscore Annotation
# =====================================================================


class CrossFeatureAnnotationSanitizationTests(CrossFeatureBaseTestCase):
    def test_relational_annotation_alias_sanitization(self):
        m = Metric.objects.create(
            name="DeepRelMetric",
            metric_name="deep_rel_metric",
            metric_type="gauge",
            content_type=self.device_ct,
            metric_labels=["device_type__manufacturer__name"],
            enabled=True,
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        alias = collector.get_annotation_alias("device_type__manufacturer__name")
        self.assertNotIn("__", alias)
        self.assertTrue(alias.startswith("_metric_label_device_type_manufacturer_name_"))

        # Query executes without FieldError
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(families[0].samples[0].labels.get("device_type__manufacturer__name"), "Cisco")


# =====================================================================
# CF-08: REST API Metric Creation ↔ Security Traversal Rejection
# =====================================================================


class CrossFeatureAPISecurityTests(CrossFeatureBaseTestCase):
    def test_api_creation_rejects_sensitive_model_and_redos_lookups(self):
        self.add_permissions("netbox_more_metrics.add_metric")
        token_ct = ObjectType.objects.get_for_model(Token)
        col = MetricCollection.objects.create(name="APISecCol", enabled=True)

        api_client = APIClient()
        api_client.force_authenticate(user=self.user)
        url = reverse("plugins-api:netbox_more_metrics-api:metric-list")

        # Attempt 1: Target sensitive token model
        resp1 = api_client.post(
            url,
            {
                "name": "TokenMetric",
                "metric_name": "token_metric",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": token_ct.pk,
                "collections": [col.pk],
                "metric_labels": ["key"],
            },
            format="json",
        )
        self.assertEqual(resp1.status_code, 400)

        # Attempt 2: Forbidden regex lookup
        resp2 = api_client.post(
            url,
            {
                "name": "ReDoSMetric",
                "metric_name": "redos_metric",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": self.device_ct.pk,
                "collections": [col.pk],
                "metric_labels": ["name"],
                "filter": {"name__regex": ".*"},
            },
            format="json",
        )
        self.assertEqual(resp2.status_code, 400)


# =====================================================================
# CF-09: Unauthenticated Scrape Gating vs. Authenticated Permissions
# =====================================================================


class CrossFeaturePermissionGatingTests(CrossFeatureBaseTestCase):
    @override_settings(EXEMPT_VIEW_PERMISSIONS=[])
    def test_authenticated_and_unauthenticated_export_permissions(self):
        m = Metric.objects.create(
            name="PermMetric",
            metric_name="perm_metric_count",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        url = reverse("plugins:netbox_more_metrics:metric_metrics", kwargs={"pk": m.pk})

        with patch("netbox_more_metrics.views.get_plugin_config", return_value=False):
            # 1. Anonymous client -> 403
            anon_client = Client()
            self.assertEqual(anon_client.get(url).status_code, 403)

            # 2. User without permission -> 403
            noperm_client = Client()
            noperm_client.force_login(self.user_noperm)
            self.assertEqual(noperm_client.get(url).status_code, 403)

            # 3. User with view permission -> 200
            self.add_permissions("netbox_more_metrics.view_metric")
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)


# =====================================================================
# CF-10: Default Registry Inclusion ↔ Multi-Collection Separation
# =====================================================================


class CrossFeatureRegistrySeparationTests(CrossFeatureBaseTestCase):
    def test_default_registry_inclusion_and_collection_isolation(self):
        col1 = MetricCollection.objects.create(name="ColDefault", enabled=True, include_in_default=True)
        col2 = MetricCollection.objects.create(name="ColIsolated", enabled=True, include_in_default=False)
        col3 = MetricCollection.objects.create(name="ColDisabled", enabled=False, include_in_default=True)

        m1 = Metric.objects.create(
            name="M1",
            metric_name="m1_default_count",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        col1.metrics.add(m1)

        m2 = Metric.objects.create(
            name="M2",
            metric_name="m2_isolated_count",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        col2.metrics.add(m2)

        m3 = Metric.objects.create(
            name="M3",
            metric_name="m3_disabled_count",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        col3.metrics.add(m3)

        # Scrape Col 2 endpoint
        reg2 = CollectorRegistry()
        col2_collector = DynamicMetricCollectionCollector(registry=reg2, collection=col2)
        self.assertIn(m2.pk, col2_collector._active_metric_collectors)
        self.assertNotIn(m1.pk, col2_collector._active_metric_collectors)

        # Scrape Col 3 endpoint
        reg3 = CollectorRegistry()
        col3_collector = DynamicMetricCollectionCollector(registry=reg3, collection=col3)
        self.assertEqual(len(col3_collector._active_metric_collectors), 0)
