from unittest.mock import patch

from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test.client import Client
from django.urls import reverse
from utilities.testing.base import TestCase

from netbox_more_metrics.models import Metric, MetricCollection

User = get_user_model()


class ExportAuthBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)

        cls.site = Site.objects.create(name="ViewSite", slug="viewsite")
        cls.manufacturer = Manufacturer.objects.create(name="ViewMan", slug="viewman")
        cls.device_type = DeviceType.objects.create(manufacturer=cls.manufacturer, model="ViewModel", slug="viewmodel")
        cls.device_role = DeviceRole.objects.create(name="ViewRole", slug="viewrole")
        cls.device = Device.objects.create(
            name="view-device",
            site=cls.site,
            device_type=cls.device_type,
            role=cls.device_role,
        )

        cls.collection = MetricCollection.objects.create(name="ViewCollection", enabled=True)
        cls.metric = Metric.objects.create(
            name="ViewMetric",
            metric_name="view_metric_total",
            metric_description="View metric description",
            metric_type="counter",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name"],
        )
        cls.collection.metrics.add(cls.metric)

        # Users
        cls.user_with_perm = User.objects.create_user(username="user_with_perm", password="password123")
        cls.user_no_perm = User.objects.create_user(username="user_no_perm", password="password123")
        cls.superuser = User.objects.create_superuser(
            username="admin_user", password="password123", email="admin@example.com"
        )
        cls.inactive_user = User.objects.create_user(username="inactive_user", password="password123", is_active=False)


# =====================================================================
# Feature 5: Metrics Export Authentication & Exemption (M2 / R3)
# =====================================================================


class MetricsExportAuthTier1TestCase(ExportAuthBaseTestCase):
    """Tier 1: Feature coverage for export authentication and permission bypass."""

    def test_anonymous_export_with_bypass_enabled(self):
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=True,
        ):
            client = Client()
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(
                response["Content-Type"].startswith("text/plain"),
                f"Unexpected content type: {response['Content-Type']}",
            )

    def test_anonymous_export_with_bypass_disabled_forbidden(self):
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=False,
        ):
            client = Client()
            response = client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_authenticated_export_with_permission_allowed(self):
        self.add_permissions("netbox_more_metrics.view_metriccollection")
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=False,
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    @override_settings(EXEMPT_VIEW_PERMISSIONS=[])
    def test_authenticated_export_without_permission_forbidden(self):
        # self.client is logged in as self.user, who has NO permissions by default
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=False,
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_metric_export_view_auth_bypass(self):
        url = reverse(
            "plugins:netbox_more_metrics:metric_metrics",
            kwargs={"pk": self.metric.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=True,
        ):
            client = Client()
            response = client.get(url)
            self.assertEqual(response.status_code, 200)


class MetricsExportAuthTier2TestCase(ExportAuthBaseTestCase):
    """Tier 2: Boundary & Corner Cases for export authentication and permissions."""

    @override_settings(LOGIN_REQUIRED=True, EXEMPT_VIEW_PERMISSIONS=[])
    def test_login_required_middleware_does_not_redirect(self):
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=True,
        ):
            client = Client()
            response = client.get(url)
            # Must NOT redirect to /login/ (302)
            self.assertNotEqual(response.status_code, 302)
            self.assertEqual(response.status_code, 200)

    def test_nonexistent_pk_returns_404_not_500(self):
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": 999999},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=True,
        ):
            client = Client()
            response = client.get(url)
            self.assertEqual(response.status_code, 404)

    def test_non_get_http_methods_return_405(self):
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=True,
        ):
            client = Client()
            response_post = client.post(url)
            self.assertEqual(response_post.status_code, 405)

            response_put = client.put(url)
            self.assertEqual(response_put.status_code, 405)

            response_delete = client.delete(url)
            self.assertEqual(response_delete.status_code, 405)

    def test_inactive_user_with_permission_denied(self):
        client = Client()
        client.force_login(self.inactive_user)
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=False,
        ):
            response = client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_superuser_access_when_auth_required(self):
        client = Client()
        client.force_login(self.superuser)
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": self.collection.pk},
        )
        with patch(
            "netbox_more_metrics.views.get_plugin_config",
            return_value=False,
        ):
            response = client.get(url)
            self.assertEqual(response.status_code, 200)


# =====================================================================
# Feature 19: UI Views, Export Context & Polish (M3 / R3)
# =====================================================================


class UIViewAndContextTier1TestCase(ExportAuthBaseTestCase):
    """Tier 1: Feature coverage for NetBox UI views and context rendering."""

    def test_metric_collection_list_view_authenticated(self):
        self.add_permissions("netbox_more_metrics.view_metriccollection")
        url = reverse("plugins:netbox_more_metrics:metriccollection_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_metric_collection_view_authenticated(self):
        self.add_permissions(
            "netbox_more_metrics.view_metriccollection",
            "netbox_more_metrics.view_metric",
        )
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection",
            kwargs={"pk": self.collection.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_metric_list_view_authenticated(self):
        self.add_permissions("netbox_more_metrics.view_metric")
        url = reverse("plugins:netbox_more_metrics:metric_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_metric_view_authenticated(self):
        self.add_permissions(
            "netbox_more_metrics.view_metric",
            "netbox_more_metrics.view_metriccollection",
        )
        url = reverse(
            "plugins:netbox_more_metrics:metric",
            kwargs={"pk": self.metric.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_metric_view_extra_context(self):
        self.add_permissions(
            "netbox_more_metrics.view_metric",
            "netbox_more_metrics.view_metriccollection",
        )
        url = reverse(
            "plugins:netbox_more_metrics:metric",
            kwargs={"pk": self.metric.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("metrics", response.context)
        self.assertIn("collections_table", response.context)


class UIViewAndContextTier2TestCase(ExportAuthBaseTestCase):
    """Tier 2: Boundary & Corner Cases for NetBox UI views."""

    @override_settings(LOGIN_REQUIRED=True, EXEMPT_VIEW_PERMISSIONS=[])
    def test_ui_views_anonymous_redirect_or_forbidden(self):
        client = Client()
        url = reverse("plugins:netbox_more_metrics:metriccollection_list")
        response = client.get(url)
        # Without permissions, NetBox ObjectView redirects to login or denies
        self.assertIn(response.status_code, (302, 403))

    @override_settings(EXEMPT_VIEW_PERMISSIONS=[])
    def test_ui_views_without_permission_forbidden(self):
        # Authenticated user without view permission receives 403
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection",
            kwargs={"pk": self.collection.pk},
        )
        response = self.client.get(url)
        self.assertIn(response.status_code, (403, 404))

    def test_metric_collection_view_extra_context(self):
        self.add_permissions(
            "netbox_more_metrics.view_metriccollection",
            "netbox_more_metrics.view_metric",
        )
        url = reverse(
            "plugins:netbox_more_metrics:metriccollection",
            kwargs={"pk": self.collection.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("metrics_table", response.context)

    def test_ui_views_nonexistent_pk_returns_404(self):
        self.add_permissions("netbox_more_metrics.view_metric")
        url = reverse("plugins:netbox_more_metrics:metric", kwargs={"pk": 999999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_metric_view_with_multiple_collections(self):
        col2 = MetricCollection.objects.create(name="SecondCol", enabled=True)
        self.metric.collections.add(col2)
        self.add_permissions(
            "netbox_more_metrics.view_metric",
            "netbox_more_metrics.view_metriccollection",
        )
        url = reverse(
            "plugins:netbox_more_metrics:metric",
            kwargs={"pk": self.metric.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        table = response.context["collections_table"]
        self.assertGreaterEqual(len(table.data), 2)
