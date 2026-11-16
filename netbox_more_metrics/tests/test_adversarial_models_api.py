"""
netbox_more_metrics/tests/test_adversarial_models_api.py

Tier 5 Adversarial and Stress Test Suite:
Models, Forms, Validators, FilterSets, Search Index & REST API.
"""

import re

from core.models import ObjectType
from dcim.models import Device, Rack, Site
from django.core.exceptions import ValidationError
from django.urls import reverse
from extras.models import JournalEntry, Tag
from netbox.search.backends import search_backend
from rest_framework.test import APIClient, APIRequestFactory
from users.models import Token, User
from utilities.testing.base import TestCase

from netbox_more_metrics.collectors import DynamicMetricCollector
from netbox_more_metrics.filtersets import MetricCollectionFilterSet, MetricFilterSet
from netbox_more_metrics.forms import MetricCollectionForm, MetricForm
from netbox_more_metrics.models import (
    SENSITIVE_APP_LABELS,
    Metric,
    MetricCollection,
    validate_field_path,
)
from netbox_more_metrics.search import MetricCollectionIndex, MetricIndex
from netbox_more_metrics.validators import (
    validate_label_name,
    validate_label_renames,
    validate_labels,
    validate_metric_name,
)


class Tier5ModelValidationAdversarialTestCase(TestCase):
    """
    Tier 5: Adversarial and stress testing for Metric.clean() and field path traversal.
    Covers ReDoS injections, sensitive model traversal, ContentType bypass attempts,
    invalid filter/exclude types, and relational annotation alias safety.
    """

    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)
        cls.site_ct = ObjectType.objects.get_for_model(Site)
        cls.token_ct = ObjectType.objects.get_for_model(Token)
        cls.user_ct = ObjectType.objects.get_for_model(User)

        cls.collection = MetricCollection.objects.create(name="Tier5ModelCol", enabled=True)

    def test_redos_injection_regex_lookup_rejected(self):
        """Verify that __regex and __iregex are rejected across filters and excludes."""
        for lookup in ("name__regex", "name__iregex", "rack__site__name__regex", "rack__site__name__iregex"):
            metric = Metric(
                name="ReDoSMetric",
                metric_name=f"redos_{re.sub(r'[^a-zA-Z0-9_]', '_', lookup)}",
                metric_description="ReDoS probe",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                filter={lookup: "^(a+)+$"},
            )
            with self.assertRaises(ValidationError) as ctx:
                metric.clean()
            self.assertIn("filter", ctx.exception.message_dict)

    def test_redos_injection_case_variations(self):
        """Verify uppercase or mixed-case regex lookups (e.g. REGEX, IREGEX) are rejected."""
        for lookup in ("name__REGEX", "name__IREGEX", "name__Regex"):
            metric = Metric(
                name="ReDoSMetricUpper",
                metric_name=f"redos_upper_{re.sub(r'[^a-zA-Z0-9_]', '_', lookup)}",
                metric_description="Upper ReDoS probe",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                filter={lookup: "^(a+)+$"},
            )
            with self.assertRaises(ValidationError) as ctx:
                metric.clean()
            self.assertIn("filter", ctx.exception.message_dict)

    def test_content_type_whitelist_bypass_sensitive_apps(self):
        """Verify that all sensitive app labels and models cannot be used as Metric.content_type."""
        for app in SENSITIVE_APP_LABELS:
            cts = ObjectType.objects.filter(app_label=app)
            for ct in cts:
                metric = Metric(
                    name="SensitiveAppMetric",
                    metric_name=f"sens_{ct.app_label}_{ct.model}",
                    metric_description="Sensitive probe",
                    metric_type="gauge",
                    metric_value="count",
                    content_type=ct,
                    metric_labels=["id"],
                )
                with self.assertRaises(ValidationError) as ctx:
                    metric.clean()
                self.assertIn("content_type", ctx.exception.message_dict)

    def test_content_type_whitelist_bypass_nonexistent_or_none(self):
        """Verify that None content_type or ObjectType with missing model is rejected."""
        metric_none = Metric(
            name="NoneCTMetric",
            metric_name="none_ct_metric",
            metric_description="None CT probe",
            metric_type="gauge",
            metric_value="count",
            content_type=None,
            metric_labels=["name"],
        )
        with self.assertRaises(ValidationError) as ctx:
            metric_none.clean()
        self.assertIn("content_type", ctx.exception.message_dict)

    def test_filter_and_exclude_invalid_types(self):
        """Verify non-dict types (string, list, int) in filter and exclude are rejected with ValidationError."""
        invalid_types = ["not_a_dict", [1, 2], 123, True]
        for val in invalid_types:
            m_filt = Metric(
                name="InvalidFiltMetric",
                metric_name="inv_filt_metric",
                metric_description="Invalid filter type",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                filter=val,
            )
            with self.assertRaises(ValidationError) as ctx:
                m_filt.clean()
            self.assertIn("filter", ctx.exception.message_dict)

            m_excl = Metric(
                name="InvalidExclMetric",
                metric_name="inv_excl_metric",
                metric_description="Invalid exclude type",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                exclude=val,
            )
            with self.assertRaises(ValidationError) as ctx:
                m_excl.clean()
            self.assertIn("exclude", ctx.exception.message_dict)

    def test_non_string_keys_in_filter_and_exclude_rejected(self):
        """Verify non-string keys in filter and exclude dictionaries are rejected cleanly."""
        for invalid_key in (123, None, True):
            m_filt = Metric(
                name="NonStrFiltKey",
                metric_name="non_str_filt_key",
                metric_description="Non-string filter key",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                filter={invalid_key: "value"},
            )
            with self.assertRaises(ValidationError) as ctx:
                m_filt.clean()
            self.assertIn("filter", ctx.exception.message_dict)

            m_excl = Metric(
                name="NonStrExclKey",
                metric_name="non_str_excl_key",
                metric_description="Non-string exclude key",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                exclude={invalid_key: "value"},
            )
            with self.assertRaises(ValidationError) as ctx:
                m_excl.clean()
            self.assertIn("exclude", ctx.exception.message_dict)

    def test_non_string_items_in_metric_labels_rejected(self):
        """Verify non-string items in metric_labels are rejected cleanly."""
        for invalid_item in ([123], [None], [True], ["name", 123]):
            m_labels = Metric(
                name="NonStrLabelItem",
                metric_name="non_str_label_item",
                metric_description="Non-string label item",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=invalid_item,
            )
            with self.assertRaises(ValidationError) as ctx:
                m_labels.clean()
            self.assertIn("metric_labels", ctx.exception.message_dict)

    def test_filter_unsupported_lookup_parameters(self):
        """Verify unsupported lookups and invalid filter arguments are rejected."""
        unsupported_filters = [
            {"name__unaccent": "switch"},
            {"name__search": "switch"},
            {"name__doesnotexist": "switch"},
            {"name__in": 12345},  # Non-iterable for in lookup
        ]
        for filt in unsupported_filters:
            metric = Metric(
                name="UnsupportedLookupMetric",
                metric_name="unsupported_lookup_metric",
                metric_description="Unsupported lookup",
                metric_type="gauge",
                metric_value="count",
                content_type=self.device_ct,
                metric_labels=["name"],
                filter=filt,
            )
            with self.assertRaises(ValidationError) as ctx:
                metric.clean()
            self.assertIn("filter", ctx.exception.message_dict)

    def test_relational_traversal_deep_hierarchy(self):
        """Verify that deep 5-level legitimate relational traversal succeeds cleanly."""
        validate_field_path(Device, "rack__site__region__parent__name", is_filter=False)

    def test_relational_traversal_to_sensitive_models_blocked(self):
        """Verify traversal into sensitive models (e.g. User, Token) via relationships is blocked."""
        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(JournalEntry, "created_by__password", is_filter=False)
        self.assertIn("forbidden", str(ctx.exception).lower())

        with self.assertRaises(ValidationError) as ctx:
            validate_field_path(JournalEntry, "created_by__username", is_filter=False)
        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_relational_label_annotation_aliases_multiple_underscores(self):
        """Verify alias generator sanitizes multiple underscores and generates unique safe aliases."""
        collector = DynamicMetricCollector.__new__(DynamicMetricCollector)
        alias1 = collector.get_annotation_alias("site__name")
        alias2 = collector.get_annotation_alias("site____name")
        alias3 = collector.get_annotation_alias("site_name")

        self.assertNotIn("__", alias1)
        self.assertNotIn("__", alias2)
        self.assertNotIn("__", alias3)
        self.assertNotEqual(alias1, alias2)
        self.assertNotEqual(alias1, alias3)

    def test_relational_label_annotation_aliases_length_boundary(self):
        """Verify alias generator functions properly on 48+ character label names."""
        collector = DynamicMetricCollector.__new__(DynamicMetricCollector)
        long_label = "a" * 48
        alias = collector.get_annotation_alias(long_label)
        self.assertTrue(alias.startswith("_metric_label_"))

    def test_label_renaming_adversarial_shadowing_and_collision(self):
        """Verify shadowing of existing labels and renaming to reserved prefixes is rejected."""
        # Shadowing existing label
        m_shadow = Metric(
            name="ShadowMetric",
            metric_name="shadow_metric",
            metric_description="Shadow probe",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name", "site__name"],
            label_renames={"name": "site__name"},
        )
        with self.assertRaises(ValidationError) as ctx:
            m_shadow.clean()
        self.assertIn("label_renames", ctx.exception.message_dict)

        # Renaming nonexistent label
        m_nonexistent = Metric(
            name="NonexistentRename",
            metric_name="nonexistent_rename",
            metric_description="Nonexistent label rename",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=["name"],
            label_renames={"unknown_label": "target"},
        )
        with self.assertRaises(ValidationError) as ctx:
            m_nonexistent.clean()
        self.assertIn("label_renames", ctx.exception.message_dict)


class Tier5PrometheusValidatorsAdversarialTestCase(TestCase):
    """
    Tier 5: Adversarial testing for Prometheus metric and label name validators.
    Covers boundary characters, colons, unicode injection, control characters, and reserved prefixes.
    """

    def test_metric_name_single_character_boundary(self):
        for name in ("a", "Z", "_", ":"):
            validate_metric_name(name)

        for invalid in ("0", "9", "-", "@", " "):
            with self.assertRaises(ValidationError):
                validate_metric_name(invalid)

    def test_label_name_single_character_boundary(self):
        for name in ("a", "Z", "_"):
            validate_label_name(name)

        for invalid in (":", "0", "9", "-", "@", " "):
            with self.assertRaises(ValidationError):
                validate_label_name(invalid)

    def test_metric_and_label_colon_distinction(self):
        """Metric names allow colons; label names strictly forbid colons."""
        validate_metric_name(":root:metric:name:")
        with self.assertRaises(ValidationError):
            validate_label_name("label:name")
        with self.assertRaises(ValidationError):
            validate_label_name(":label")

    def test_unicode_and_special_character_rejection(self):
        """Unicode letters and control characters must be rejected for both metrics and labels."""
        adversarial_inputs = ["mëtric", "日本語", "üser", "name\n", "name\r", "name\x00", "name\t"]
        for adv in adversarial_inputs:
            with self.assertRaises(ValidationError):
                validate_metric_name(adv)
            with self.assertRaises(ValidationError):
                validate_label_name(adv)

    def test_reserved_internal_label_prefixes(self):
        """Label names starting with '__' are reserved and must be rejected."""
        reserved_labels = ["__reserved", "__name__", "___three_underscores"]
        for res in reserved_labels:
            with self.assertRaises(ValidationError) as ctx:
                validate_label_name(res)
            self.assertEqual(ctx.exception.code, "reserved")

    def test_validate_labels_duplicate_and_type(self):
        with self.assertRaises(ValidationError):
            validate_labels(["label1", "label1"])
        with self.assertRaises(ValidationError):
            validate_labels("not_a_list")

    def test_validate_label_renames_adversarial(self):
        # Non-dict
        with self.assertRaises(ValidationError):
            validate_label_renames(["not", "dict"])
        # Non-string key
        with self.assertRaises(ValidationError):
            validate_label_renames({123: "val"})
        # Non-string val
        with self.assertRaises(ValidationError):
            validate_label_renames({"key": 123})
        # Duplicate rename targets
        with self.assertRaises(ValidationError):
            validate_label_renames({"k1": "dup", "k2": "dup"})
        # Reserved target
        with self.assertRaises(ValidationError):
            validate_label_renames({"k": "__reserved"})


class Tier5FormAdversarialTestCase(TestCase):
    """
    Tier 5: Adversarial testing for MetricForm and MetricCollectionForm.
    Covers tag persistence, dynamic choices, malformed inputs, and validation errors.
    """

    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)

        cls.tag1 = Tag.objects.create(name="T5Tag1", slug="t5-tag1")
        cls.tag2 = Tag.objects.create(name="T5Tag2", slug="t5-tag2")

        cls.collection = MetricCollection.objects.create(name="T5FormCol", enabled=True)

    def test_metric_form_tag_persistence_create_and_update(self):
        form_data = {
            "name": "T5TaggedMetric",
            "metric_description": "Tags persistence test",
            "enabled": True,
            "metric_name": "t5_tagged_metric",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [self.tag1.pk, self.tag2.pk],
        }
        form = MetricForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Errors: {form.errors}")
        metric = form.save()
        self.assertEqual(metric.tags.count(), 2)

        # Update tags
        update_data = {
            "name": metric.name,
            "metric_description": "Updated tags",
            "enabled": True,
            "metric_name": metric.metric_name,
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "tags": [self.tag1.pk],
        }
        update_form = MetricForm(data=update_data, instance=metric)
        self.assertTrue(update_form.is_valid(), f"Errors: {update_form.errors}")
        update_form.save()
        metric.refresh_from_db()
        self.assertEqual(metric.tags.count(), 1)
        self.assertEqual(metric.tags.first(), self.tag1)

    def test_metric_form_dynamic_choices_device_vs_rack(self):
        f_device = MetricForm(data={"content_type": self.device_ct.pk})
        choices_device = [c[0] for c in f_device.fields["metric_value"].choices]
        self.assertIn("count", choices_device)
        self.assertNotIn("get_utilization", choices_device)

        f_rack = MetricForm(data={"content_type": self.rack_ct.pk})
        choices_rack = [c[0] for c in f_rack.fields["metric_value"].choices]
        self.assertIn("count", choices_rack)
        self.assertIn("get_utilization", choices_rack)
        self.assertIn("get_power_utilization", choices_rack)

    def test_metric_form_rejects_invalid_json_inputs(self):
        form_data = {
            "name": "BadJsonForm",
            "metric_description": "Bad json test",
            "enabled": True,
            "metric_name": "bad_json_metric",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
            "label_renames": "{not_valid_json",
        }
        form = MetricForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("label_renames", form.errors)

    def test_metric_form_rejects_mismatched_metric_value(self):
        form_data = {
            "name": "MismatchValForm",
            "metric_description": "Mismatch test",
            "enabled": True,
            "metric_name": "mismatch_val_metric",
            "metric_labels": ["name"],
            "metric_type": "gauge",
            "metric_value": "get_utilization",  # Invalid on Device
            "content_type": self.device_ct.pk,
            "collections": [self.collection.pk],
        }
        form = MetricForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("metric_value", form.errors)

    def test_metric_collection_form_tags_and_defaults(self):
        col_form = MetricCollectionForm(data={"name": "DefaultCol", "enabled": True, "tags": [self.tag1.pk]})
        self.assertTrue(col_form.is_valid(), f"Errors: {col_form.errors}")
        col = col_form.save()
        self.assertTrue(col.enabled)
        self.assertFalse(col.include_in_default)
        self.assertEqual(col.tags.count(), 1)

        # Unchecked checkbox omits 'enabled' and evaluates to False
        col_form_disabled = MetricCollectionForm(data={"name": "DisabledCol"})
        self.assertTrue(col_form_disabled.is_valid())
        col_disabled = col_form_disabled.save()
        self.assertFalse(col_disabled.enabled)


class Tier5FilterSetAdversarialTestCase(TestCase):
    """
    Tier 5: Adversarial testing for NetBoxModelFilterSets.
    Covers multi-value queries, invalid input handling, and search metacharacter safety.
    """

    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)

        cls.col_alpha = MetricCollection.objects.create(name="AlphaCol", description="Alpha desc", enabled=True)
        cls.col_beta = MetricCollection.objects.create(name="BetaCol", description="Beta desc", enabled=False)

        cls.m_counter = Metric.objects.create(
            name="DevCounter",
            metric_name="devcountert5",
            metric_description="Counter for devices",
            metric_type="counter",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["name", "status"],
            enabled=True,
        )
        cls.m_counter.collections.add(cls.col_alpha)

        cls.m_gauge = Metric.objects.create(
            name="DevGauge",
            metric_name="devgauget5",
            metric_description="Gauge for devices",
            metric_type="gauge",
            metric_value="count",
            content_type=cls.device_ct,
            metric_labels=["site__name"],
            enabled=False,
        )
        cls.m_gauge.collections.add(cls.col_beta)

    def test_metric_filterset_complex_multi_value_combinations(self):
        # Multi-value metric_type
        fs = MetricFilterSet({"metric_type": ["counter", "gauge"]}, queryset=Metric.objects.all())
        self.assertIn(self.m_counter, fs.qs)
        self.assertIn(self.m_gauge, fs.qs)

        # Multi-value metric_labels
        fs_labels = MetricFilterSet({"metric_labels": ["name", "status"]}, queryset=Metric.objects.all())
        self.assertIn(self.m_counter, fs_labels.qs)
        self.assertNotIn(self.m_gauge, fs_labels.qs)

    def test_metric_filterset_invalid_inputs_handled_safely(self):
        # Non-integer ID
        fs_id = MetricFilterSet({"id": ["not_an_int"]}, queryset=Metric.objects.all())
        self.assertFalse(fs_id.is_valid())

        # Invalid metric_type
        fs_type = MetricFilterSet({"metric_type": ["invalid_type"]}, queryset=Metric.objects.all())
        self.assertFalse(fs_type.is_valid())

    def test_filterset_search_with_metacharacters_and_sql_injection(self):
        metachar_queries = [
            ".*",
            "^$",
            "(?P<test>.*)",
            "[a-z]+",
            "%",
            "_",
            "' OR '1'='1",
            '" OR ""="',
            "\\",
        ]
        for q in metachar_queries:
            fs = MetricFilterSet({"q": q}, queryset=Metric.objects.all())
            self.assertEqual(fs.qs.count(), 0)

        # Whitespace only search returns full queryset
        fs_ws = MetricFilterSet({"q": "   "}, queryset=Metric.objects.all())
        self.assertEqual(fs_ws.qs.count(), Metric.objects.count())

    def test_metric_collection_filterset_metric_filters(self):
        fs_id = MetricCollectionFilterSet({"metric_id": [self.m_counter.pk]}, queryset=MetricCollection.objects.all())
        self.assertEqual(fs_id.qs.count(), 1)
        self.assertEqual(fs_id.qs.first(), self.col_alpha)

        fs_name = MetricCollectionFilterSet({"metric": [self.m_gauge.name]}, queryset=MetricCollection.objects.all())
        self.assertEqual(fs_name.qs.count(), 1)
        self.assertEqual(fs_name.qs.first(), self.col_beta)


class Tier5SearchIndexAdversarialTestCase(TestCase):
    """
    Tier 5: Adversarial testing for SearchIndex registration and query engine.
    Covers regex metacharacters, SQL wildcards, empty queries, and weight orderings.
    """

    def test_search_backend_special_characters_and_metacharacters(self):
        queries = [
            ".*",
            "^$",
            "(?P<group>.*)",
            "[a-zA-Z0-9]+",
            "%",
            "_",
            "' OR '1'='1",
            '" OR ""="',
            "\\",
        ]
        for q in queries:
            results = list(search_backend.search(q, user=self.user))
            self.assertIsInstance(results, list)

    def test_search_backend_empty_and_whitespace_queries(self):
        res_ws = list(search_backend.search("   ", user=self.user))
        self.assertEqual(len(res_ws), 0)

    def test_search_index_configuration_and_weights(self):
        self.assertEqual(MetricIndex.model, Metric)
        self.assertEqual(MetricCollectionIndex.model, MetricCollection)

        m_fields = dict(MetricIndex.fields)
        self.assertLess(m_fields["name"], m_fields["metric_description"])
        self.assertEqual(m_fields["name"], 100)
        self.assertEqual(m_fields["metric_description"], 500)


class Tier5RestApiAdversarialTestCase(TestCase):
    """
    Tier 5: Adversarial testing for REST API serializers and endpoints.
    Covers permission enforcement, malicious payloads, ReDoS rejection, and options security.
    """

    @classmethod
    def setUpTestData(cls):
        cls.device_ct = ObjectType.objects.get_for_model(Device)
        cls.rack_ct = ObjectType.objects.get_for_model(Rack)
        cls.token_ct = ObjectType.objects.get_for_model(Token)

        cls.collection = MetricCollection.objects.create(name="T5ApiCol", enabled=True)

    def setUp(self):
        super().setUp()
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.user)
        self.anon_client = APIClient()
        self.factory = APIRequestFactory()
        self.req = self.factory.get("/")

    def test_options_endpoint_unauthenticated_denied(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")
        res = self.anon_client.get(url)
        self.assertIn(res.status_code, (401, 403))

    def test_model_viewsets_unauthenticated_write_denied(self):
        col_list = reverse("plugins-api:netbox_more_metrics-api:metriccollection-list")
        col_detail = reverse("plugins-api:netbox_more_metrics-api:metriccollection-detail", args=[self.collection.pk])

        self.assertIn(self.anon_client.post(col_list, {"name": "Hacked"}).status_code, (401, 403))
        self.assertIn(self.anon_client.patch(col_detail, {"name": "Hacked"}).status_code, (401, 403))
        self.assertIn(self.anon_client.delete(col_detail).status_code, (401, 403))

    def test_serializer_rejects_malicious_content_type(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric-list")
        self.add_permissions("netbox_more_metrics.add_metric")

        malicious_cts = ["users.token", "auth.user", "contenttypes.contenttype", "sessions.session"]
        for ct in malicious_cts:
            payload = {
                "name": "MaliciousMetric",
                "metric_name": f"mal_{re.sub(r'[^a-zA-Z0-9_]', '_', ct)}",
                "metric_description": "Exfiltrate test",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": ct,
                "collections": [self.collection.pk],
                "metric_labels": ["id"],
            }
            res = self.api_client.post(url, payload, format="json")
            self.assertEqual(res.status_code, 400, f"Allowed sensitive content_type {ct}")
            self.assertIn("content_type", res.data)

    def test_serializer_rejects_redos_in_filter_and_exclude(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric-list")
        self.add_permissions("netbox_more_metrics.add_metric")

        payload_regex = {
            "name": "ReDoSFilterMetric",
            "metric_name": "redos_filter_metric",
            "metric_description": "ReDoS filter test",
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": "dcim.device",
            "collections": [self.collection.pk],
            "metric_labels": ["name"],
            "filter": {"name__regex": "^(a+)+$"},
        }
        res_filt = self.api_client.post(url, payload_regex, format="json")
        self.assertEqual(res_filt.status_code, 400)
        self.assertIn("filter", res_filt.data)

        payload_iregex = {
            "name": "ReDoSExcludeMetric",
            "metric_name": "redos_exclude_metric",
            "metric_description": "ReDoS exclude test",
            "metric_type": "gauge",
            "metric_value": "count",
            "content_type": "dcim.device",
            "collections": [self.collection.pk],
            "metric_labels": ["name"],
            "exclude": {"name__iregex": "^(a+)+$"},
        }
        res_excl = self.api_client.post(url, payload_iregex, format="json")
        self.assertEqual(res_excl.status_code, 400)
        self.assertIn("exclude", res_excl.data)

    def test_serializer_rejects_reserved_and_invalid_labels(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric-list")
        self.add_permissions("netbox_more_metrics.add_metric")

        # Reserved label prefix __
        res_res = self.api_client.post(
            url,
            {
                "name": "ReservedLabelMetric",
                "metric_name": "res_label_metric",
                "metric_description": "test",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": "dcim.device",
                "collections": [self.collection.pk],
                "metric_labels": ["__reserved"],
            },
            format="json",
        )
        self.assertEqual(res_res.status_code, 400)

        # Colon in label name
        res_col = self.api_client.post(
            url,
            {
                "name": "ColonLabelMetric",
                "metric_name": "col_label_metric",
                "metric_description": "test",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": "dcim.device",
                "collections": [self.collection.pk],
                "metric_labels": ["label:name"],
            },
            format="json",
        )
        self.assertEqual(res_col.status_code, 400)

        # Duplicate labels in list
        res_dup = self.api_client.post(
            url,
            {
                "name": "DupLabelMetric",
                "metric_name": "dup_label_metric",
                "metric_description": "test",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": "dcim.device",
                "collections": [self.collection.pk],
                "metric_labels": ["name", "name"],
            },
            format="json",
        )
        self.assertEqual(res_dup.status_code, 400)

    def test_serializer_rejects_missing_required_fields(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric-list")
        self.add_permissions("netbox_more_metrics.add_metric")

        # Missing collections
        res = self.api_client.post(
            url,
            {
                "name": "NoColMetric",
                "metric_name": "no_col_metric",
                "metric_description": "test",
                "metric_type": "gauge",
                "metric_value": "count",
                "content_type": "dcim.device",
                "metric_labels": ["name"],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("collections", res.data)

    def test_options_endpoint_sensitive_and_invalid_params(self):
        url = reverse("plugins-api:netbox_more_metrics-api:metric_value_type_options-list")

        # Sensitive model returns default 'count'
        res_sens = self.api_client.get(f"{url}?object_type=users.token")
        self.assertEqual(res_sens.status_code, 200)
        self.assertEqual(res_sens.data["results"], [{"id": "count", "display": "Count"}])

        # Nonexistent model returns default 'count'
        res_none = self.api_client.get(f"{url}?object_type=nonexistent.model")
        self.assertEqual(res_none.status_code, 200)
        self.assertEqual(res_none.data["results"], [{"id": "count", "display": "Count"}])

        # Rack returns utilization options
        res_rack = self.api_client.get(f"{url}?object_type=dcim.rack")
        self.assertEqual(res_rack.status_code, 200)
        ids = [opt["id"] for opt in res_rack.data["results"]]
        self.assertIn("get_utilization", ids)
        self.assertIn("get_power_utilization", ids)
        self.assertIn("count", ids)
