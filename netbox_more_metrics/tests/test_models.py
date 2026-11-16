from core.models import ObjectType
from dcim.models import Device, Rack
from django.core.exceptions import ValidationError
from users.models import Token, User
from utilities.testing.base import TestCase

from netbox_more_metrics.models import (
    ALLOWED_LOOKUP_TYPES,
    SENSITIVE_APP_LABELS,
    Metric,
    MetricCollection,
    get_allowed_object_types,
    validate_field_path,
)


class OrmAccessControlTier1TestCase(TestCase):
    """Tier 1: Feature coverage for ORM access control and ReDoS prevention (Feature 12)."""

    def setUp(self):
        super().setUp()
        self.device_ct = ObjectType.objects.get_for_model(Device)
        self.token_ct = ObjectType.objects.get_for_model(Token)
        self.user_ct = ObjectType.objects.get_for_model(User)

    def test_reject_sensitive_base_content_type(self):
        metric = Metric(
            name="SensitiveTokenMetric",
            metric_name="token_count",
            metric_description="Count tokens",
            metric_type="gauge",
            metric_value="count",
            content_type=self.token_ct,
            metric_labels=["key"],
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("content_type", ctx.exception.message_dict)

    def test_reject_relational_traversal_to_user_token(self):
        from extras.models import JournalEntry

        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(Device, "owner__name")
        self.assertIn("Traversal to sensitive model", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(JournalEntry, "created_by__username")
        self.assertIn("Traversal to sensitive model", str(ctx.exception))

    def test_reject_sensitive_field_password(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(Device, "site__password")
        self.assertIn("Access to sensitive field", str(ctx.exception))

    def test_reject_regex_lookup_in_filter(self):
        metric = Metric(
            name="RegexMetric",
            metric_name="regex_device_count",
            metric_description="Count devices by regex",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            filter={"name__regex": "^[a-z]+$"},
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("filter", ctx.exception.message_dict)
        self.assertIn("Lookup 'regex' is not permitted", str(ctx.exception.message_dict["filter"]))

    def test_reject_iregex_lookup_in_exclude(self):
        metric = Metric(
            name="IregexMetric",
            metric_name="iregex_device_count",
            metric_description="Exclude devices by iregex",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            exclude={"name__iregex": "^test.*$"},
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("exclude", ctx.exception.message_dict)
        self.assertIn("Lookup 'iregex' is not permitted", str(ctx.exception.message_dict["exclude"]))


class OrmAccessControlTier2TestCase(TestCase):
    """Tier 2: Boundary & Corner Cases for ORM access control and ReDoS prevention (Feature 12)."""

    def setUp(self):
        super().setUp()
        self.device_ct = ObjectType.objects.get_for_model(Device)

    def test_deep_traversal_across_legitimate_models(self):
        # rack -> site -> region -> name on Device
        validate_field_path(Device, "rack__site__region__name")

    def test_mixed_case_sensitive_field(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(Device, "site__SECRET")
        self.assertIn("Access to sensitive field", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(Device, "site__TOKEN")
        self.assertIn("Access to sensitive field", str(ctx.exception))

    def test_whitelisted_lookups_all_allowed(self):
        for lookup in ALLOWED_LOOKUP_TYPES:
            filter_path = f"name__{lookup}"
            validate_field_path(Device, filter_path, is_filter=True)

    def test_custom_field_data_traversal(self):
        # Should not raise validation error on custom_field_data JSON traversal
        validate_field_path(Device, "custom_field_data__asset_id")

    def test_get_allowed_object_types_excludes_auth_apps(self):
        allowed_cts = get_allowed_object_types()
        for ct in allowed_cts:
            self.assertNotIn(
                ct.app_label,
                SENSITIVE_APP_LABELS,
                f"Sensitive app_label {ct.app_label} found in allowed object types",
            )


class ModelCleanAndDisplayTier1TestCase(TestCase):
    """Tier 1: Feature coverage for clean(), __str__(), and display helpers (Feature 19)."""

    def setUp(self):
        super().setUp()
        self.device_ct = ObjectType.objects.get_for_model(Device)

    def test_metric_collection_str(self):
        col = MetricCollection(name="Core Infrastructure")
        self.assertEqual(str(col), "Core Infrastructure")

    def test_metric_str(self):
        metric = Metric(name="Active Devices")
        self.assertEqual(str(metric), "Active Devices")

    def test_clean_requires_valid_content_type(self):
        metric = Metric(
            name="NoCTMetric",
            metric_name="no_ct_count",
            metric_description="No content type",
            metric_type="gauge",
            metric_value="count",
            content_type=None,
            metric_labels=["name"],
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("content_type", ctx.exception.message_dict)

    def test_clean_rejects_non_dict_filter_and_exclude(self):
        metric_list_filter = Metric(
            name="ListFilterMetric",
            metric_name="list_filter_count",
            metric_description="List filter",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            filter=["not", "a", "dict"],
        )
        with self.assertRaises(ValidationError) as ctx:
            metric_list_filter.clean()
        self.assertIn("filter", ctx.exception.message_dict)

        metric_str_exclude = Metric(
            name="StrExcludeMetric",
            metric_name="str_exclude_count",
            metric_description="Str exclude",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            exclude="not a dict",
        )
        with self.assertRaises(ValidationError) as ctx:
            metric_str_exclude.clean()
        self.assertIn("exclude", ctx.exception.message_dict)

    def test_clean_handles_invalid_filter_types_safely(self):
        # Invalid integer conversion for id filter converts safely to ValidationError
        metric = Metric(
            name="InvalidFilterValMetric",
            metric_name="invalid_filter_val_count",
            metric_description="Invalid filter val",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            filter={"id": "non_integer_id_string"},
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("filter", ctx.exception.message_dict)


class ModelCleanAndDisplayTier2TestCase(TestCase):
    """Tier 2: Boundary & Corner Cases for model validation and display methods (Feature 19)."""

    def setUp(self):
        super().setUp()
        self.device_ct = ObjectType.objects.get_for_model(Device)
        self.rack_ct = ObjectType.objects.get_for_model(Rack)

    def test_get_metric_value_display(self):
        metric_count = Metric(content_type=self.device_ct, metric_value="count")
        self.assertEqual(metric_count.get_metric_value_display(), "Count")

        metric_util = Metric(content_type=self.rack_ct, metric_value="get_utilization")
        self.assertEqual(metric_util.get_metric_value_display(), "Percentage Utilized")

        # Fallback when content_type is None
        metric_none = Metric(content_type=None, metric_value="count")
        self.assertEqual(metric_none.get_metric_value_display(), "count")

    def test_metric_value_choices_validation(self):
        # 'get_utilization' is valid for Rack but NOT valid for Device
        metric = Metric(
            name="InvalidChoiceMetric",
            metric_name="device_utilization",
            metric_description="Device utilization is invalid",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("metric_value", ctx.exception.message_dict)

    def test_shadow_rename_prevention(self):
        # Renaming label 'name' to 'site__name' when 'site__name' is also in metric_labels
        metric = Metric(
            name="ShadowMetric",
            metric_name="shadow_metric",
            metric_description="Shadow test",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name", "site__name"],
            label_renames={"name": "site__name"},
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("label_renames", ctx.exception.message_dict)

    def test_missing_metric_labels_rejected(self):
        metric = Metric(
            name="NoLabelsMetric",
            metric_name="no_labels_metric",
            metric_description="No labels",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("metric_labels", ctx.exception.message_dict)

    def test_label_renames_not_in_metric_labels_rejected(self):
        metric = Metric(
            name="UnknownRenameMetric",
            metric_name="unknown_rename_metric",
            metric_description="Unknown rename",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            label_renames={"nonexistent_label": "target_name"},
        )
        with self.assertRaises(ValidationError) as ctx:
            metric.clean()
        self.assertIn("label_renames", ctx.exception.message_dict)
