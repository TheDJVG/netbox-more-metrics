from django import forms
from django.shortcuts import reverse
from utilities.forms.widgets import APISelect

from netbox_more_metrics.choices import MetricValueChoices


class DynamicMetricValueOptionField(forms.ChoiceField):
    widget = APISelect

    def __init__(self, query_params=None, object_type_field=None, *args, **kwargs):
        self.query_params = query_params or {}
        self.object_type_field = object_type_field

        # These are always valid and should be the default.
        kwargs["choices"] = MetricValueChoices.DEFAULT_CHOICES
        kwargs["initial"] = MetricValueChoices.DEFAULT_CHOICE

        super().__init__(*args, **kwargs)

    def get_bound_field(self, form, field_name):
        bound_field = forms.BoundField(form, self, field_name)
        widget = bound_field.field.widget

        # Attach any query parameters
        if len(self.query_params) > 0:
            widget.add_query_params(self.query_params)

        widget.attrs["data-url"] = reverse(
            "plugins-api:netbox_more_metrics-api:metric_value_type_options-list"
        )

        return bound_field
