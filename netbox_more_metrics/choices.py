from core.models import ObjectType
from netbox.choices import ChoiceSet
from prometheus_client.metrics_core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    InfoMetricFamily,
)


class MetricTypeChoices(ChoiceSet):
    TYPE_GAUGE = "gauge"
    TYPE_COUNTER = "counter"
    TYPE_INFO = "info"

    CHOICES = ((TYPE_COUNTER, "Counter"), (TYPE_INFO, "Info"), (TYPE_GAUGE, "Gauge"))

    TYPES = {
        TYPE_INFO: InfoMetricFamily,
        TYPE_COUNTER: CounterMetricFamily,
        TYPE_GAUGE: GaugeMetricFamily,
    }


class MetricValueChoices(ChoiceSet):
    DEFAULT_CHOICES = (("count", "Count"),)
    DEFAULT_CHOICE = "count"

    CHOICES = (
        (
            "dcim.Rack",
            (
                ("get_utilization", "Percentage Utilized"),
                ("get_power_utilization", "Power Percentage Utilized"),
            ),
        ),
        ("ipam.Prefix", (("get_utilization", "Percentage Utilized"),)),
        (
            "ipam.Aggregate",
            (("get_utilization", "Percentage Utilized"),),
        ),
    )
    CHOICES_BY_MODEL = dict(CHOICES)

    @classmethod
    def choices_for_model(cls, app_label: str, model_label: str) -> tuple:
        choices = cls.CHOICES_BY_MODEL.get(f"{app_label}.{model_label}", ())
        return tuple(choices) + cls.DEFAULT_CHOICES

    @classmethod
    def choices_for_contenttype(cls, model) -> tuple:
        if isinstance(model, int) or (isinstance(model, str) and model.isdigit()):
            try:
                obj_type = ObjectType.objects.get_for_id(int(model))
                model = obj_type.model_class()
                if not model:
                    return cls.DEFAULT_CHOICES
            except (ObjectType.DoesNotExist, ValueError):
                return cls.DEFAULT_CHOICES
        elif isinstance(model, str):
            if "." in model:
                try:
                    app_label, model_name = model.split(".", 1)
                    obj_type = ObjectType.objects.get_by_natural_key(app_label, model_name)
                    model = obj_type.model_class()
                    if not model:
                        return cls.DEFAULT_CHOICES
                except (ObjectType.DoesNotExist, ValueError):
                    return cls.DEFAULT_CHOICES
            else:
                return cls.DEFAULT_CHOICES

        if not hasattr(model, "_meta"):
            return cls.DEFAULT_CHOICES

        app_name, model_name = model._meta.label.split(".")
        return cls.choices_for_model(app_name, model_name)
