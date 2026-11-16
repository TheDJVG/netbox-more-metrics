from core.models import ObjectType
from dcim.models import Device, Rack
from django.urls import reverse
from rest_framework import serializers
from rest_framework.test import APIClient, APIRequestFactory
from users.models import Token
from utilities.testing.base import TestCase

from netbox_more_metrics.api.serializers import (
    MetricCollectionSerializer,
    MetricSerializer,
)
from netbox_more_metrics.api.views import MetricValueTypeOptionsViewSet
from netbox_more_metrics.models import Metric, MetricCollection


class ApiBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)
        cls.token_ct = ObjectType.objects.get_for_model(Token)

        cls.collection = MetricCollection.objects.create(
            name="APICollection", description="API Collection description", enabled=True
        )
        cls.metric = Metric.objects.create(
            name="APIMetric",
            metric_name="api_metric_count",
            metric_description="API Metric description",
            metric_type="gauge",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name"],
            enabled=True,
        )
        cls.metric.collections.add(cls.collection)

    def setUp(self):
        super().setUp()
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.user)
        self.anon_client = APIClient()
        self.factory = APIRequestFactory()
        self.req = self.factory.get("/")


# =====================================================================
# Feature 11: API Endpoint Authentication Hardening (M2 / R3)
# =====================================================================


class ApiAuthHardeningTier1TestCase(ApiBaseTestCase):
    """Tier 1: Feature coverage for API endpoint authentication hardening."""

    def test_anonymous_request_denied(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.anon_client.get(url)
        self.assertIn(response.status_code, (401, 403))

    def test_authenticated_request_allowed(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_default_choices_without_param(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"], [{"id": "count", "display": "Count"}])

    def test_model_specific_choices(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(f"{url}?object_type=dcim.rack")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        choice_ids = [opt["id"] for opt in data["results"]]
        self.assertIn("get_utilization", choice_ids)
        self.assertIn("get_power_utilization", choice_ids)
        self.assertIn("count", choice_ids)

    def test_permission_classes_attribute(self):
        from rest_framework.permissions import IsAuthenticated

        self.assertIn(IsAuthenticated, MetricValueTypeOptionsViewSet.permission_classes)


class ApiAuthHardeningTier2TestCase(ApiBaseTestCase):
    """Tier 2: Boundary & Corner Cases for options API endpoint."""

    def test_invalid_object_type_param_fallback(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(f"{url}?object_type=invalid.nonexistent")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"], [{"id": "count", "display": "Count"}])

    def test_sensitive_object_type_param(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(f"{url}?object_type=users.token")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should not expose any sensitive methods, only default choices
        self.assertEqual(data["results"], [{"id": "count", "display": "Count"}])

    def test_post_method_returns_405(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.post(url, {})
        self.assertEqual(response.status_code, 405)

    def test_object_type_as_integer(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(f"{url}?object_type=999999")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["results"], [{"id": "count", "display": "Count"}])

    def test_response_envelope_structure(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        response = self.api_client.get(url)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)


# =====================================================================
# Feature 18: API Serializers Enhancement (M3 / R3)
# =====================================================================


class ApiSerializerTier1TestCase(ApiBaseTestCase):
    """Tier 1: Feature coverage for API serializers enhancement."""

    def test_metric_collection_serializer_fields(self):
        serializer = MetricCollectionSerializer(instance=self.collection, context={"request": self.req})
        fields = serializer.data
        expected_fields = [
            "id",
            "name",
            "description",
            "enabled",
            "include_in_default",
            "export_url",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        ]
        for field in expected_fields:
            self.assertIn(field, fields, f"Field '{field}' missing from MetricCollectionSerializer")

    def test_metric_serializer_fields(self):
        serializer = MetricSerializer(instance=self.metric, context={"request": self.req})
        fields = serializer.data
        expected_fields = [
            "id",
            "name",
            "metric_name",
            "metric_description",
            "metric_type",
            "metric_labels",
            "metric_value",
            "content_type",
            "filter",
            "exclude",
            "label_renames",
            "collections",
            "export_url",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        ]
        for field in expected_fields:
            self.assertIn(field, fields, f"Field '{field}' missing from MetricSerializer")

    def test_metric_collection_api_list(self):
        self.add_permissions("netbox_more_metrics.view_metriccollection")
        url = reverse("plugins-api:netbox_more_metrics-api:metriccollection-list")
        response = self.api_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)

    def test_metric_api_list(self):
        self.add_permissions("netbox_more_metrics.view_metric")
        url = reverse("plugins-api:netbox_more_metrics-api:metric-list")
        response = self.api_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["count"], 1)

    def test_serializer_validate_content_type_blocks_sensitive_model(self):
        serializer = MetricSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_content_type(self.token_ct)


class ApiSerializerTier2TestCase(ApiBaseTestCase):
    """Tier 2: Boundary & Corner Cases for API serializers."""

    def test_brief_fields_metric_collection(self):
        brief_fields = MetricCollectionSerializer.Meta.brief_fields
        for field in ("id", "url", "display", "name", "description"):
            self.assertIn(field, brief_fields)

    def test_brief_fields_metric(self):
        brief_fields = MetricSerializer.Meta.brief_fields
        for field in ("id", "url", "display", "name", "metric_name", "metric_description"):
            self.assertIn(field, brief_fields)

    def test_metric_serializer_export_url_format(self):
        serializer = MetricSerializer(instance=self.metric, context={"request": self.req})
        export_url = serializer.data.get("export_url")
        self.assertTrue(
            export_url.endswith(f"/plugins/more-metrics/metrics/{self.metric.pk}/metrics/"),
            f"Unexpected export_url: {export_url}",
        )

    def test_metric_collection_serializer_export_url_format(self):
        serializer = MetricCollectionSerializer(instance=self.collection, context={"request": self.req})
        export_url = serializer.data.get("export_url")
        self.assertTrue(
            export_url.endswith(f"/plugins/more-metrics/collections/{self.collection.pk}/metrics/"),
            f"Unexpected export_url: {export_url}",
        )

    def test_metric_serializer_nested_collections(self):
        serializer = MetricSerializer(instance=self.metric, context={"request": self.req})
        collections = serializer.data.get("collections", [])
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0]["id"], self.collection.pk)
        self.assertEqual(collections[0]["name"], self.collection.name)
