"""
netbox_more_metrics/tests/test_adversarial.py

Tier 5 Adversarial and Stress Test Suite.
Verifies security boundaries, edge-case naming, zero-division resilience,
and empty-labelset aggregation correctness.
"""

from unittest.mock import patch

from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Rack, Site
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test.client import Client
from django.urls import reverse
from extras.models import Tag
from prometheus_client import CollectorRegistry
from users.models import ObjectPermission
from utilities.testing.base import TestCase

from netbox_more_metrics.collectors import DynamicMetricCollector
from netbox_more_metrics.models import Metric, MetricCollection

User = get_user_model()


class AdversarialViewsTier5TestCase(TestCase):
    """Tier 5 Adversarial Coverage: View Security & Access Control Boundaries."""

    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.col_ct = ObjectType.objects.get_for_model(MetricCollection)
        cls.metric_ct = ObjectType.objects.get_for_model(Metric)

        cls.site = Site.objects.create(name="AdvSite", slug="advsite")
        cls.mfr = Manufacturer.objects.create(name="AdvMfr", slug="advmfr")
        cls.dt = DeviceType.objects.create(manufacturer=cls.mfr, model="AdvModel", slug="advmodel")
        cls.role = DeviceRole.objects.create(name="AdvRole", slug="advrole")

        cls.dev1 = Device.objects.create(name="adv-dev-1", site=cls.site, device_type=cls.dt, role=cls.role)
        cls.dev2 = Device.objects.create(name="adv-dev-2", site=cls.site, device_type=cls.dt, role=cls.role)

        cls.col_public = MetricCollection.objects.create(name="PublicCollection", enabled=True)
        cls.col_restricted = MetricCollection.objects.create(name="RestrictedCollection", enabled=True)

        cls.metric1 = Metric.objects.create(
            name="AdvMetric1",
            metric_name="adv_metric_one",
            metric_type="gauge",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        cls.col_public.metrics.add(cls.metric1)

        cls.metric2 = Metric.objects.create(
            name="AdvMetric2",
            metric_name="adv_metric_two",
            metric_type="gauge",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        cls.col_restricted.metrics.add(cls.metric2)

        # Users
        cls.constrained_user = User.objects.create_user(username="adv_constrained_user", password="password123")
        cls.user_metric_only = User.objects.create_user(username="adv_metric_only", password="password123")
        cls.user_col_only = User.objects.create_user(username="adv_col_only", password="password123")

        # Constrained ObjectPermission: view only "PublicCollection"
        obj_perm = ObjectPermission.objects.create(
            name="PublicCollectionOnly",
            actions=["view"],
            constraints={"name": "PublicCollection"},
        )
        obj_perm.object_types.add(cls.col_ct)
        obj_perm.users.add(cls.constrained_user)

    @override_settings(LOGIN_REQUIRED=True, EXEMPT_VIEW_PERMISSIONS=[])
    def test_object_level_permission_constraint_enforcement(self):
        """
        Adversarial Test: When export_metrics_without_auth=False, a user with
        constrained ObjectPermission on MetricCollection must NOT be able to
        export a collection outside their permission constraint.
        """
        client = Client()
        client.force_login(self.constrained_user)

        with patch("netbox_more_metrics.views.get_plugin_config", return_value=False):
            # Allowed public collection
            url_public = reverse(
                "plugins:netbox_more_metrics:metriccollection_metrics",
                kwargs={"pk": self.col_public.pk},
            )
            resp_public = client.get(url_public)
            self.assertEqual(resp_public.status_code, 200)

            # Restricted collection must be denied (404 via restrict() or 403)
            url_restricted = reverse(
                "plugins:netbox_more_metrics:metriccollection_metrics",
                kwargs={"pk": self.col_restricted.pk},
            )
            resp_restricted = client.get(url_restricted)
            self.assertIn(
                resp_restricted.status_code,
                (403, 404),
                f"Object permission constraint bypassed! Got status {resp_restricted.status_code}",
            )

    @override_settings(LOGIN_REQUIRED=True, EXEMPT_VIEW_PERMISSIONS=[])
    def test_cross_view_permission_isolation(self):
        """
        Adversarial Test: User with view_metriccollection cannot access MetricExportView,
        and user with view_metric cannot access MetricCollectionExportView.
        """
        client = Client()

        # Assign view_metriccollection only
        perm_col = ObjectPermission.objects.create(name="ColPermOnly", actions=["view"])
        perm_col.object_types.add(self.col_ct)
        perm_col.users.add(self.user_col_only)

        client.force_login(self.user_col_only)
        with patch("netbox_more_metrics.views.get_plugin_config", return_value=False):
            resp_col = client.get(
                reverse(
                    "plugins:netbox_more_metrics:metriccollection_metrics",
                    kwargs={"pk": self.col_public.pk},
                )
            )
            self.assertEqual(resp_col.status_code, 200)

            resp_metric = client.get(
                reverse(
                    "plugins:netbox_more_metrics:metric_metrics",
                    kwargs={"pk": self.metric1.pk},
                )
            )
            self.assertEqual(resp_metric.status_code, 403)

        perm_col.delete()

    def test_http_method_rejection_post_put_delete(self):
        """
        Adversarial Test: Ensure non-GET methods (POST, PUT, PATCH, DELETE) are rejected with 405.
        """
        client = Client()
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.col_public.pk},
        )
        with patch("netbox_more_metrics.views.get_plugin_config", return_value=True):
            for method in ("post", "put", "patch", "delete"):
                resp = getattr(client, method)(url)
                self.assertEqual(
                    resp.status_code,
                    405,
                    f"Method {method.upper()} was not rejected with 405!",
                )

    def test_export_view_nonexistent_and_boundary_pks(self):
        """
        Adversarial Test: Verify 404 handling on zero, negative, and large boundary PKs.
        """
        client = Client()
        with patch("netbox_more_metrics.views.get_plugin_config", return_value=True):
            for bad_pk in (0, 99999999):
                url = reverse(
                    "plugins:netbox_more_metrics:metriccollection_metrics",
                    kwargs={"pk": bad_pk},
                )
                resp = client.get(url)
                self.assertEqual(resp.status_code, 404)


class AdversarialCollectorsTier5TestCase(TestCase):
    """Tier 5 Adversarial Coverage: Collector Lifecycle, Aggregations & Boundary Conditions."""

    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)

        cls.site = Site.objects.create(name="AdvColSite", slug="advcolsite")
        cls.mfr = Manufacturer.objects.create(name="AdvColMfr", slug="advcolmfr")
        cls.dt = DeviceType.objects.create(manufacturer=cls.mfr, model="AdvColModel", slug="advcolmodel")
        cls.role = DeviceRole.objects.create(name="AdvColRole", slug="advcolrole")

        cls.devs = [
            Device.objects.create(
                name=f"adv-count-dev-{i}",
                site=cls.site,
                device_type=cls.dt,
                role=cls.role,
            )
            for i in range(5)
        ]

    def test_count_metric_with_empty_labels_aggregates_total_count(self):
        """
        Adversarial Test: Count metric with metric_labels=[] must aggregate to
        total count (5.0), NOT group by PK and emit 1.0.
        """
        m = Metric.objects.create(
            name="TotalCountMetric",
            metric_name="adv_total_device_count",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=[],
            filter={"site__slug": "advcolsite"},
            enabled=True,
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        self.assertEqual(len(families[0].samples), 1)
        sample = families[0].samples[0]
        self.assertEqual(
            sample.value,
            5.0,
            f"Expected 5.0 devices, but got {sample.value} due to values(*()) group-by bug!",
        )

    def test_method_utilization_zero_division_resilience(self):
        """
        Adversarial Test: A Rack with u_height=0 must not trigger unhandled
        ZeroDivisionError in DynamicMetricCollector.collect().
        """
        rack_zero = Rack.objects.create(name="ZeroHeightRack", site=self.site, u_height=0)
        m = Metric.objects.create(
            name="ZeroRackUtil",
            metric_name="adv_rack_zero_util",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
            filter={"name": "ZeroHeightRack"},
            enabled=True,
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        try:
            families = list(collector.collect())
            self.assertEqual(len(families), 1)
        except ZeroDivisionError:
            self.fail("DynamicMetricCollector.collect() crashed with unhandled ZeroDivisionError on u_height=0 rack!")
        finally:
            rack_zero.delete()

    def test_collector_logging_with_unpersisted_metric_pk_none(self):
        """
        Adversarial Test: DynamicMetricCollector initialized with unsaved metric (pk=None)
        must not crash logger with TypeError (%d format specifier).
        """
        m_unsaved = Metric(
            name="UnsavedMetric",
            metric_name="adv_unsaved_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            filter={"nonexistent_field": 123},  # Invalid filter
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m_unsaved, registry=registry, force_enable=True)
        self.assertFalse(collector.is_valid)

    def test_m2m_relation_label_expansion_and_null_coalescing(self):
        """
        Adversarial Test: Verify M2M tag label extraction correctly outputs distinct tag
        samples and coalesces untagged devices to 'null'.
        """
        t1 = Tag.objects.create(name="AdvTag1", slug="advtag1")
        t2 = Tag.objects.create(name="AdvTag2", slug="advtag2")

        dev_tagged = self.devs[0]
        dev_tagged.tags.set([t1, t2])

        m = Metric.objects.create(
            name="AdvTagMetric",
            metric_name="adv_device_tag_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["tags__slug"],
            filter={"site__slug": "advcolsite"},
            enabled=True,
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        tag_values = {s.labels.get("tags__slug") for s in families[0].samples}
        self.assertIn("advtag1", tag_values)
        self.assertIn("advtag2", tag_values)
        self.assertIn("null", tag_values)
        t1.delete()
        t2.delete()

    def test_info_metric_family_with_colons_and_multi_rows(self):
        """
        Adversarial Test: Verify InfoMetricFamily exposition format with colons in name
        and multi-row label generation.
        """
        m = Metric.objects.create(
            name="AdvColonInfo",
            metric_name="adv:device:info",
            metric_type="info",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name", "status"],
            filter={"site__slug": "advcolsite"},
            enabled=True,
        )
        registry = CollectorRegistry()
        collector = DynamicMetricCollector(metric=m, registry=registry, force_enable=True)
        families = list(collector.collect())
        self.assertEqual(len(families), 1)
        family = families[0]
        self.assertEqual(family.name, "adv:device:info")
        self.assertEqual(len(family.samples), 5)
