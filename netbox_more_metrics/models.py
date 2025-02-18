from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import FieldError, ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext as _
from netbox.models import NetBoxModel

from netbox_more_metrics.choices import MetricTypeChoices
from netbox_more_metrics.validators import (
    validate_label_name,
    validate_label_renames,
    validate_metric_name,
)


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

    def __str__(self):
        return self.name


class Metric(ObjectAbsoluteUrlMixin, NetBoxModel):
    """
    Represents a single Metric to be exported.
    """

    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    metric_name = models.CharField(
        unique=True, max_length=50, validators=[validate_metric_name]
    )
    metric_description = models.CharField(max_length=255)
    metric_labels = ArrayField(
        base_field=models.CharField(max_length=50, validators=[validate_label_name])
    )
    metric_type = models.CharField(max_length=50, choices=MetricTypeChoices)
    metric_value = models.CharField(max_length=50, default="count")
    content_type = models.ForeignKey(
        to="core.ObjectType",
        related_name="+",
        verbose_name="Object type",
        help_text=_("The object to which this Metric applies."),
        on_delete=models.CASCADE,
    )
    filter = models.JSONField(
        null=False, default=dict, blank=True, help_text=_("QuerySet filter")
    )
    label_renames = models.JSONField(
        null=False,
        default=dict,
        blank=True,
        help_text=_("Label renaming"),
        validators=[validate_label_renames],
    )
    collections = models.ManyToManyField(to=MetricCollection, related_name="metrics")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        # Sort the labels, so they're in the same order as the exported metrics.
        self.metric_labels.sort()

        model = self.content_type.model_class()

        # Test the labels
        try:
            model.objects.values(*self.metric_labels)
        except FieldError as e:
            raise ValidationError({"metric_labels": f"Labels invalid: {e}"})

        # Test the filter
        if self.filter:
            try:
                model.objects.filter(**self.filter)
            except FieldError as e:
                raise ValidationError({"filter": f"Filter invalid: {e}"})
        else:
            self.filter = {}

        if self.label_renames:
            # Make sure all renamed labels exists as labels
            for label in self.label_renames:
                if label not in self.metric_labels:
                    raise ValidationError(
                        {
                            "label_renames": f"Label '{label}' is not in the metric labels."
                        }
                    )

            # Make sure there's no duplicate label names
            for label in self.metric_labels:
                # First check if the label is in the label_renames:
                if label in self.label_renames.values():
                    # If it is it's possible that the label is being renamed to something else, if not, trigger a
                    # ValidationError
                    if (
                        label not in self.label_renames
                        or label == self.label_renames.get(label)
                    ):
                        raise ValidationError(
                            {
                                "label_renames": f"Label '{label}' is being shadowed by a label rename."
                            }
                        )

    @property
    def metric_family(self):
        return MetricTypeChoices.TYPES[self.metric_type]
