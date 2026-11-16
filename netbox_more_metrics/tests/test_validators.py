from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from netbox_more_metrics.validators import (
    validate_label_name,
    validate_label_renames,
    validate_labels,
    validate_metric_name,
)


class PrometheusValidatorsTier1TestCase(SimpleTestCase):
    """Tier 1: Feature coverage for Prometheus metric and label name validators."""

    def test_validate_metric_name_valid(self):
        valid_names = [
            "c",
            "netbox:device:count",
            "device_status_total",
            "cpu0_usage",
            "NetBox_Metric_123",
            ":root:metric",
            "_internal_metric",
        ]
        for name in valid_names:
            try:
                validate_metric_name(name)
            except ValidationError as e:
                self.fail(f"validate_metric_name raised ValidationError unexpectedly for '{name}': {e}")

    def test_validate_metric_name_invalid(self):
        invalid_names = [
            "",
            "9device",
            "metric-name",
            "my metric",
            "device.count",
            "metric@name",
            "metric$name",
        ]
        for name in invalid_names:
            with self.assertRaises(ValidationError, msg=f"Expected ValidationError for metric name '{name}'"):
                validate_metric_name(name)

    def test_validate_label_name_valid(self):
        valid_labels = [
            "name",
            "site_id",
            "_role",
            "device_type_1",
            "Status",
        ]
        for label in valid_labels:
            try:
                validate_label_name(label)
            except ValidationError as e:
                self.fail(f"validate_label_name raised ValidationError unexpectedly for '{label}': {e}")

    def test_validate_label_name_reserved_prefix(self):
        reserved_labels = [
            "__reserved",
            "__metric_label",
            "__name__",
            "___triple",
        ]
        for label in reserved_labels:
            with self.assertRaises(ValidationError) as ctx:
                validate_label_name(label)
            self.assertEqual(ctx.exception.code, "reserved")

    def test_validate_label_name_invalid_regex(self):
        invalid_labels = [
            "",
            "1label",
            "site:name",  # Colons are valid in metric names, but FORBIDDEN in label names
            "my-label",
            "label.name",
            "label name",
        ]
        for label in invalid_labels:
            with self.assertRaises(ValidationError, msg=f"Expected ValidationError for label '{label}'"):
                validate_label_name(label)


class PrometheusValidatorsTier2TestCase(SimpleTestCase):
    """Tier 2: Boundary & Corner Cases for Prometheus validators."""

    def test_validate_metric_name_single_character(self):
        # 1-character valid names
        validate_metric_name("a")
        validate_metric_name("Z")
        validate_metric_name("_")
        validate_metric_name(":")

        # 1-character invalid names
        with self.assertRaises(ValidationError):
            validate_metric_name("0")
        with self.assertRaises(ValidationError):
            validate_metric_name("-")

    def test_validate_label_name_single_character(self):
        # 1-character valid label names
        validate_label_name("a")
        validate_label_name("Z")
        validate_label_name("_")

        # 1-character invalid label names
        with self.assertRaises(ValidationError):
            validate_label_name(":")
        with self.assertRaises(ValidationError):
            validate_label_name("0")

    def test_validate_labels_duplicate_and_type(self):
        # Valid list
        validate_labels(["label1", "label2", "label3"])
        validate_labels([])

        # Duplicate items in list
        with self.assertRaises(ValidationError):
            validate_labels(["label1", "label1"])

        # Non-list type
        with self.assertRaises(ValidationError):
            validate_labels("not_a_list")
        with self.assertRaises(ValidationError):
            validate_labels({"label1": "val1"})

    def test_validate_label_renames_types_and_nested(self):
        # Valid mapping
        validate_label_renames({"old_name": "new_name", "site__name": "site"})

        # Non-dict input
        with self.assertRaises(ValidationError):
            validate_label_renames(["not", "a", "dict"])

        # Non-string key
        with self.assertRaises(ValidationError):
            validate_label_renames({123: "new_name"})

        # Non-string value
        with self.assertRaises(ValidationError):
            validate_label_renames({"old_name": 123})

        # Nested dict value
        with self.assertRaises(ValidationError):
            validate_label_renames({"old_name": {"nested": "value"}})

        # Duplicate target values
        with self.assertRaises(ValidationError):
            validate_label_renames({"key1": "duplicate_target", "key2": "duplicate_target"})

    def test_validate_label_renames_reserved_target(self):
        # Target label cannot start with __
        with self.assertRaises(ValidationError):
            validate_label_renames({"old_name": "__reserved_target"})
