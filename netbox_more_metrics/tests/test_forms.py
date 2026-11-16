from core.models import ObjectType
from dcim.models import Device, Rack
from extras.models import Tag
from users.models import Token
from utilities.testing.base import TestCase

from netbox_more_metrics.forms import MetricCollectionForm, MetricForm
from netbox_more_metrics.models import SENSITIVE_APP_LABELS, Metric, MetricCollection


class FormBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)
        cls.token_ct = ObjectType.objects.get_for_model(Token)

        cls.tag1 = Tag.objects.create(name="Production", slug="production")
        cls.tag2 = Tag.objects.create(name="Staging", slug="staging")

        cls.collection = MetricCollection.objects.create(name="FormTestCollection", enabled=True)


# =====================================================================
# Feature 9: MetricForm Tag Support (M2 / R3)
# =====================================================================


class MetricFormTagTier1TestCase(FormBaseTestCase):
    """Tier 1: Feature coverage for MetricForm tag support."""

    def test_tags_in_meta_fields(self):
        self.assertIn("tags", MetricForm.Meta.fields)

    def test_tags_in_fieldsets(self):
        found = False
        for fieldset in MetricForm.fieldsets:
            if "tags" in fieldset.items:
                found = True
                break
        self.assertTrue(found, "tags field not found in MetricForm.fieldsets")

    def test_create_metric_with_tags_persists(self):
        form_data = {
            "name": "TaggedMetric",
            "metric_description": "Metric with tags",
            "enabled": True,
            "metric_name": "tagged_metric_count",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [self.tag1.pk, self.tag2.pk],
        }
        form = MetricForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form validation failed: {form.errors}")
        metric = form.save()
        self.assertEqual(metric.tags.count(), 2)
        tag_slugs = set(metric.tags.values_list("slug", flat=True))
        self.assertEqual(tag_slugs, {"production", "staging"})

    def test_update_metric_tags(self):
        metric = Metric.objects.create(
            name="UpdateTagMetric",
            metric_name="update_tag_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        metric.tags.add(self.tag1)

        form_data = {
            "name": metric.name,
            "metric_description": "Updated tags",
            "enabled": True,
            "metric_name": metric.metric_name,
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [self.tag2.pk],
        }
        form = MetricForm(data=form_data, instance=metric)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        form.save()
        metric.refresh_from_db()
        self.assertEqual(list(metric.tags.values_list("slug", flat=True)), ["staging"])

    def test_empty_tags_allowed(self):
        form_data = {
            "name": "NoTagMetric",
            "metric_description": "Metric without tags",
            "enabled": True,
            "metric_name": "no_tag_metric_count",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [],
        }
        form = MetricForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        metric = form.save()
        self.assertEqual(metric.tags.count(), 0)


class MetricFormTagTier2TestCase(FormBaseTestCase):
    """Tier 2: Boundary & Corner Cases for MetricForm tags."""

    def test_clear_existing_tags(self):
        metric = Metric.objects.create(
            name="ClearTagsMetric",
            metric_name="clear_tags_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        metric.tags.add(self.tag1, self.tag2)

        form_data = {
            "name": metric.name,
            "metric_description": "Cleared tags",
            "enabled": True,
            "metric_name": metric.metric_name,
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [],
        }
        form = MetricForm(data=form_data, instance=metric)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        form.save()
        metric.refresh_from_db()
        self.assertEqual(metric.tags.count(), 0)

    def test_duplicate_tags_deduplicated(self):
        form_data = {
            "name": "DupTagsMetric",
            "metric_description": "Duplicate tags",
            "enabled": True,
            "metric_name": "dup_tags_metric",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [self.tag1.pk, self.tag1.pk],
        }
        form = MetricForm(data=form_data)
        self.assertTrue(form.is_valid())
        metric = form.save()
        self.assertEqual(metric.tags.count(), 1)

    def test_tags_preserved_on_unrelated_edit(self):
        metric = Metric.objects.create(
            name="PreserveTagsMetric",
            metric_name="preserve_tags_metric",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
        )
        metric.tags.add(self.tag1)

        form_data = {
            "name": "Renamed Metric",
            "metric_description": "New description",
            "enabled": True,
            "metric_name": metric.metric_name,
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [self.tag1.pk],
        }
        form = MetricForm(data=form_data, instance=metric)
        self.assertTrue(form.is_valid())
        form.save()
        metric.refresh_from_db()
        self.assertEqual(metric.name, "Renamed Metric")
        self.assertEqual(list(metric.tags.values_list("slug", flat=True)), ["production"])

    def test_metric_collection_form_tags(self):
        self.assertIn("tags", MetricCollectionForm.Meta.fields)
        col_data = {
            "name": "TaggedCol",
            "description": "Col with tags",
            "enabled": True,
            "include_in_default": False,
            "tags": [self.tag1.pk],
        }
        form = MetricCollectionForm(data=col_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        col = form.save()
        self.assertEqual(list(col.tags.values_list("slug", flat=True)), ["production"])

    def test_special_characters_in_tags(self):
        tag_special = Tag.objects.create(name="NetBox-4-Metrics:v1", slug="netbox-4-metrics-v1")
        form_data = {
            "name": "SpecialTagCol",
            "description": "Special tag col",
            "enabled": True,
            "tags": [tag_special.pk],
        }
        form = MetricCollectionForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        col = form.save()
        self.assertIn(tag_special, col.tags.all())


# =====================================================================
# Features 12 & 19: ObjectType Choices & Dynamic Form Options (M2/M3)
# =====================================================================


class FormObjectTypeAndDynamicOptionsTier1TestCase(FormBaseTestCase):
    """Tier 1: Feature coverage for ObjectType restrictions and dynamic options."""

    def test_content_type_queryset_excludes_sensitive_models(self):
        form = MetricForm()
        ct_queryset = form.fields["content_type"].queryset
        for ct in ct_queryset:
            self.assertNotIn(ct.app_label, SENSITIVE_APP_LABELS)

    def test_dynamic_choices_for_rack_in_data(self):
        form = MetricForm(data={"content_type": self.rack_ct.pk})
        choices = dict(form.fields["metric_value"].choices)
        self.assertIn("get_utilization", choices)
        self.assertIn("get_power_utilization", choices)
        self.assertIn("count", choices)

    def test_dynamic_choices_for_device_in_data(self):
        form = MetricForm(data={"content_type": self.device_ct.pk})
        choices = dict(form.fields["metric_value"].choices)
        self.assertNotIn("get_utilization", choices)
        self.assertIn("count", choices)

    def test_dynamic_choices_populated_from_instance(self):
        metric = Metric.objects.create(
            name="InstMetric",
            metric_name="inst_metric",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["name"],
        )
        form = MetricForm(instance=metric)
        choices = dict(form.fields["metric_value"].choices)
        self.assertIn("get_utilization", choices)

    def test_invalid_content_type_choice_rejected(self):
        form_data = {
            "name": "InvalidCTMetric",
            "metric_description": "Invalid CT",
            "enabled": True,
            "metric_name": "invalid_ct_metric",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.token_ct.pk,  # Sensitive token model
            "collections": [self.collection.pk],
        }
        form = MetricForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("content_type", form.errors)


class FormObjectTypeAndDynamicOptionsTier2TestCase(FormBaseTestCase):
    """Tier 2: Boundary & Corner Cases for Form validation and serialization."""

    def test_metric_value_invalid_for_content_type_error(self):
        form_data = {
            "name": "MismatchValueMetric",
            "metric_description": "Mismatch value",
            "enabled": True,
            "metric_name": "mismatch_value_metric",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "get_utilization",  # Invalid on Device
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
        }
        form = MetricForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("metric_value", form.errors)

    def test_form_with_label_renames_valid(self):
        form_data = {
            "name": "RenameFormMetric",
            "metric_description": "Label renames",
            "enabled": True,
            "metric_name": "rename_form_metric",
            "metric_labels": ["name"],
            "label_renames": '{"name": "hostname"}',
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
        }
        form = MetricForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        metric = form.save()
        self.assertEqual(metric.label_renames, {"name": "hostname"})

    def test_metric_collection_form_valid_and_save(self):
        form_data = {
            "name": "SaveCol",
            "description": "Save collection description",
            "enabled": True,
            "include_in_default": True,
        }
        form = MetricCollectionForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        col = form.save()
        self.assertEqual(col.name, "SaveCol")
        self.assertTrue(col.include_in_default)

    def test_metric_collection_form_defaults(self):
        form = MetricCollectionForm()
        # Default initial value for enabled is True
        self.assertTrue(form.fields["enabled"].initial)
        self.assertFalse(form.fields["include_in_default"].initial)

    def test_form_init_with_empty_data_does_not_crash(self):
        form = MetricForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
