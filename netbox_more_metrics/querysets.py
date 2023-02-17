import sys

from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    Case,
    Exists,
    F,
    FloatField,
    Func,
    IntegerField,
    Model,
    OuterRef,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Power
from ipam.models import Prefix


class AggregateExtendedQuerySet(QuerySet):
    prefixes_in_aggregate = (
        Prefix.objects.filter(prefix__net_contained_or_equal=OuterRef("prefix"))
        .exclude(Exists(Prefix.objects.filter(prefix__net_contains=OuterRef("prefix"))))
        .order_by()
        .values("prefix")
        .annotate(
            _prefix_length=Func(
                "prefix", function="masklen", output_field=IntegerField()
            ),
            _ips_in_prefix=Power(
                Value(2), OuterRef("_prefix_family_bits") - F("_prefix_length")
            ),
            _total_ips=Func(F("_ips_in_prefix"), function="Sum"),  # Prevent GROUP BY.
        )
        .values("_total_ips")[:1]
    )

    def aggregate_usage(self):
        return self.alias(
            _prefix_family=Func(
                "prefix", function="family", output_field=IntegerField()
            ),
            _prefix_length=Func(
                "prefix", function="masklen", output_field=IntegerField()
            ),
            _prefix_family_bits=Case(
                When(_prefix_family=6, then=Value(128)),
                default=Value(32),
            ),
        ).annotate(
            prefix_ips_used=Coalesce(
                Subquery(self.prefixes_in_aggregate), 0.0, output_field=FloatField()
            ),
            prefix_total_ips=Power(
                Value(2), F("_prefix_family_bits") - F("_prefix_length")
            ),
            prefix_percent_used=F("prefix_ips_used") / F("prefix_total_ips") * 100,
        )

    CHOICES = (
        ("count", "Count"),
        ("aggregate_usage.prefix_percent_used", "Percentage of aggregate used"),
        ("aggregate_usage.prefix_total_ips", "Total IPs in aggregate"),
        ("aggregate_usage.prefix_ips_used", "IPs used in aggregate"),
    )


class DefaultExtendedQuerySet(QuerySet):
    CHOICES = (("count", "Count"),)


def get_extended_queryset_for_model(model: Model | int | str) -> type:
    if isinstance(model, (str, int)):
        try:
            model = ContentType.objects.get_for_id(model).model_class()
        except ContentType.DoesNotExist:
            return DefaultExtendedQuerySet

    app_name, model_name = model._meta.label.split(".")
    queryset_name = f"{model_name}ExtendedQuerySet"
    try:
        return getattr(sys.modules[__name__], queryset_name)
    except AttributeError:
        return DefaultExtendedQuerySet
