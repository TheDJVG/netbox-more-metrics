from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import (
    FieldDoesNotExist,
    FieldError,
    ObjectDoesNotExist,
    ValidationError,
)
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext as _
from netbox.models import NetBoxModel

from netbox_more_metrics.choices import MetricTypeChoices, MetricValueChoices
from netbox_more_metrics.validators import (
    validate_label_name,
    validate_label_renames,
    validate_labels,
    validate_metric_name,
)

# Sensitive app labels and models that must never be queried or traversed into
SENSITIVE_APP_LABELS = {
    "auth",
    "users",
    "sessions",
    "admin",
    "contenttypes",
}

SENSITIVE_MODEL_NAMES = {
    "users.user",
    "users.token",
    "users.objectpermission",
    "users.group",
    "auth.user",
    "auth.group",
    "auth.permission",
    "sessions.session",
    "admin.logentry",
}

# Sensitive terminal field names that should not be exposed or queried
SENSITIVE_FIELD_NAMES = {
    "password",
    "token",
    "secret",
    "hash",
    "api_key",
}

# Allowed ORM lookup suffixes
ALLOWED_LOOKUP_TYPES = {
    "exact",
    "iexact",
    "in",
    "gt",
    "gte",
    "lt",
    "lte",
    "isnull",
    "startswith",
    "endswith",
    "contains",
    "icontains",
}


def get_allowed_object_types():
    from core.models import ObjectType

    return ObjectType.objects.exclude(app_label__in=SENSITIVE_APP_LABELS)


def validate_field_path(model, path: str, is_filter: bool = False):
    """
    Validates a double-underscore ('__') traversal path against:
    1. Sensitive models (users.User, users.Token, etc.)
    2. Sensitive field names (password, token, secret, hash, api_key)
    3. Forbidden regex/iregex lookups
    4. Whitelisted lookups
    """
    if not isinstance(path, str):
        raise ValidationError(_("Field path must be a string."))
    parts = path.split("__")
    if not parts:
        return

    # Check for forbidden regex lookups immediately
    for forbidden in ("regex", "iregex"):
        if forbidden in parts:
            raise ValidationError(f"Lookup '{forbidden}' is not permitted in '{path}'.")

    # Check sensitive field names across all parts
    for part in parts:
        if part.lower() in SENSITIVE_FIELD_NAMES:
            raise ValidationError(f"Access to sensitive field '{part}' in path '{path}' is forbidden.")

    # If this is filter/exclude, check if the last token is a lookup
    if is_filter and len(parts) > 1 and parts[-1] in ALLOWED_LOOKUP_TYPES:
        parts.pop()

    current_model = model
    for i, part in enumerate(parts):
        # Handle custom_field_data JSON traversal
        if part == "custom_field_data" and i == 0:
            break

        try:
            field = current_model._meta.get_field(part)
        except (FieldDoesNotExist, FieldError, AttributeError):
            # Let Django ORM query verification handle nonexistent fields
            break

        # If it's a relational field, inspect the related model
        if getattr(field, "is_relation", False) and getattr(field, "related_model", None):
            related_model = field.related_model
            app_label = related_model._meta.app_label
            model_name = related_model._meta.model_name
            full_label = f"{app_label}.{model_name}".lower()

            if app_label in SENSITIVE_APP_LABELS or full_label in SENSITIVE_MODEL_NAMES:
                raise ValidationError(
                    f"Traversal to sensitive model '{related_model._meta.label}' via '{part}' in '{path}' is forbidden."
                )
            current_model = related_model


class ObjectAbsoluteUrlMixin:
    def get_absolute_url(self):
        path = f"plugins:{self._meta.app_label}:{self._meta.model_name}"
        return reverse(path, args=[self.pk])


class MetricCollection(ObjectAbsoluteUrlMixin, NetBoxModel):
    """
    Model that represents a CollectorRegistry.
    You can connect Metric instances to this to export only these specific metrics.
    """

    name = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    include_in_default = models.BooleanField(
        default=False, help_text=_("Include collection in default metric REGISTRY.")
    )

    class Meta:
        ordering = ("name", "pk")  # Name may be non-unique

    def __str__(self):
        return self.name


class Metric(ObjectAbsoluteUrlMixin, NetBoxModel):
    """
    Represents a single Metric to be exported.
    """

    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    metric_name = models.CharField(unique=True, max_length=50, validators=[validate_metric_name])
    metric_description = models.CharField(max_length=255)
    metric_labels = ArrayField(
        base_field=models.CharField(max_length=50, validators=[validate_label_name]),
        validators=[validate_labels],
    )
    metric_type = models.CharField(max_length=50, choices=MetricTypeChoices)
    metric_value = models.CharField(max_length=50, default="count")
    content_type = models.ForeignKey(
        to="core.ObjectType",
        related_name="+",
        verbose_name="Object type",
        help_text=_("The object to which this Metric applies."),
        on_delete=models.CASCADE,
        limit_choices_to=~models.Q(app_label__in=SENSITIVE_APP_LABELS),
    )
    filter = models.JSONField(null=False, default=dict, blank=True, help_text=_("QuerySet filter"))
    exclude = models.JSONField(null=False, default=dict, blank=True, help_text=_("QuerySet exclude"))
    label_renames = models.JSONField(
        null=False,
        default=dict,
        blank=True,
        help_text=_("Label renaming"),
        validators=[validate_label_renames],
    )
    collections = models.ManyToManyField(to=MetricCollection, related_name="metrics")

    class Meta:
        ordering = ("name", "pk")  # Name may be non-unique

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        try:
            if not getattr(self, "content_type_id", None) or self.content_type is None:
                raise ValidationError({"content_type": _("A valid ContentType is required.")})
        except (AttributeError, ObjectDoesNotExist):
            raise ValidationError({"content_type": _("A valid ContentType is required.")})

        if (
            getattr(self.content_type, "app_label", "") in SENSITIVE_APP_LABELS
            or f"{getattr(self.content_type, 'app_label', '')}.{getattr(self.content_type, 'model', '')}".lower()
            in SENSITIVE_MODEL_NAMES
        ):
            raise ValidationError(
                {
                    "content_type": _("Object type '%(type)s' is restricted and cannot be used for metrics.")
                    % {"type": self.content_type}
                }
            )

        model = self.content_type.model_class()
        if model is None:
            raise ValidationError({"content_type": _("Invalid object type: model class not found.")})

        if self.metric_labels is None:
            raise ValidationError({"metric_labels": _("Metric labels must be a list.")})
        if not isinstance(self.metric_labels, list):
            raise ValidationError({"metric_labels": _("Metric labels must be a list.")})

        for label_path in self.metric_labels:
            if not isinstance(label_path, str):
                raise ValidationError({"metric_labels": _("Each label must be a string.")})

        # Sort the labels, so they're in the same order as the exported metrics.
        self.metric_labels.sort()

        # Validate relational traversal and sensitive fields on metric_labels
        for label_path in self.metric_labels:
            if not isinstance(label_path, str):
                raise ValidationError({"metric_labels": _("Each label must be a string.")})
            try:
                validate_field_path(model, label_path, is_filter=False)
            except ValidationError as e:
                raise ValidationError({"metric_labels": e.message if hasattr(e, "message") else str(e)})

        # Test the labels
        try:
            model.objects.values(*self.metric_labels)
        except (FieldError, ValueError, TypeError) as e:
            raise ValidationError({"metric_labels": f"Labels invalid: {e}"})

        # Test the filter
        if self.filter is not None:
            if not isinstance(self.filter, dict):
                raise ValidationError({"filter": _("Filter must be a dictionary of ORM lookups.")})
            for filter_path in self.filter:
                if not isinstance(filter_path, str):
                    raise ValidationError({"filter": _("Filter keys must be string ORM lookups.")})
                try:
                    validate_field_path(model, filter_path, is_filter=True)
                except ValidationError as e:
                    raise ValidationError({"filter": e.message if hasattr(e, "message") else str(e)})
            try:
                model.objects.filter(**self.filter)
            except (FieldError, ValueError, TypeError) as e:
                raise ValidationError({"filter": f"Filter invalid: {e}"})
        else:
            self.filter = {}

        # Test the exclude filter
        if self.exclude is not None:
            if not isinstance(self.exclude, dict):
                raise ValidationError({"exclude": _("Exclude must be a dictionary of ORM lookups.")})
            for exclude_path in self.exclude:
                if not isinstance(exclude_path, str):
                    raise ValidationError({"exclude": _("Exclude keys must be string ORM lookups.")})
                try:
                    validate_field_path(model, exclude_path, is_filter=True)
                except ValidationError as e:
                    raise ValidationError({"exclude": e.message if hasattr(e, "message") else str(e)})
            try:
                model.objects.filter(**self.exclude)
            except (FieldError, ValueError, TypeError) as e:
                raise ValidationError({"exclude": f"Exclude invalid: {e}"})
        else:
            self.exclude = {}

        # Check that the metric_value is valid for the model
        choices_list = MetricValueChoices.choices_for_contenttype(model)
        metric_value_choices = next(zip(*choices_list)) if choices_list else ()
        if self.metric_value not in metric_value_choices:
            raise ValidationError(
                {
                    "metric_value": f"Metric value '{self.metric_value}' is not valid for the object type. "
                    f"Choices: {', '.join(metric_value_choices)}"
                }
            )

        if self.label_renames:
            if not isinstance(self.label_renames, dict):
                raise ValidationError({"label_renames": _("Label renames must be a dictionary.")})
            # Make sure all renamed labels exists as labels
            for label in self.label_renames:
                if label not in self.metric_labels:
                    raise ValidationError({"label_renames": f"Label '{label}' is not in the metric labels."})

            # Make sure there's no duplicate label names
            for label in self.metric_labels:
                # First check if the label is in the label_renames:
                if label in self.label_renames.values() and (
                    label not in self.label_renames or label == self.label_renames.get(label)
                ):
                    raise ValidationError({"label_renames": f"Label '{label}' is being shadowed by a label rename."})

    def get_metric_value_display(self):
        try:
            if not getattr(self, "content_type_id", None) or not self.content_type:
                return self.metric_value
            model = self.content_type.model_class()
            choices = dict(MetricValueChoices.choices_for_contenttype(model))
            return choices.get(self.metric_value, self.metric_value)
        except (AttributeError, KeyError, TypeError, ValueError, ObjectDoesNotExist):
            return self.metric_value

    @property
    def metric_family(self):
        return MetricTypeChoices.TYPES[self.metric_type]
