import django_filters
from core.models import ObjectType
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet
from utilities.filters import (
    ContentTypeFilter,
    MultiValueArrayFilter,
)

from netbox_more_metrics.choices import MetricTypeChoices
from netbox_more_metrics.models import Metric, MetricCollection


class MetricCollectionFilterSet(NetBoxModelFilterSet):
    metric_id = django_filters.ModelMultipleChoiceFilter(
        field_name="metrics",
        queryset=Metric.objects.all(),
        label=_("Metric (ID)"),
    )
    metric = django_filters.ModelMultipleChoiceFilter(
        field_name="metrics__name",
        to_field_name="name",
        queryset=Metric.objects.all(),
        label=_("Metric (name)"),
    )

    class Meta:
        model = MetricCollection
        fields = (
            "id",
            "name",
            "description",
            "enabled",
            "include_in_default",
        )

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class MetricLabelsFilter(MultiValueArrayFilter):
    def get_filter_predicate(self, v):
        if v is None:
            return {self.field_name: None}
        return {f"{self.field_name}__contains": [v]}


class MetricFilterSet(NetBoxModelFilterSet):
    metric_type = django_filters.MultipleChoiceFilter(
        choices=MetricTypeChoices,
        null_value=None,
    )
    content_type = ContentTypeFilter()
    content_type_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ObjectType.objects.all(),
        label=_("Object type (ID)"),
    )
    collection_id = django_filters.ModelMultipleChoiceFilter(
        field_name="collections",
        queryset=MetricCollection.objects.all(),
        label=_("Collection (ID)"),
    )
    collection = django_filters.ModelMultipleChoiceFilter(
        field_name="collections__name",
        to_field_name="name",
        queryset=MetricCollection.objects.all(),
        label=_("Collection (name)"),
    )
    metric_collection_id = django_filters.ModelMultipleChoiceFilter(
        field_name="collections",
        queryset=MetricCollection.objects.all(),
        label=_("Metric collection (ID)"),
    )
    metric_labels = MetricLabelsFilter(
        label=_("Metric labels"),
    )

    class Meta:
        model = Metric
        fields = (
            "id",
            "name",
            "metric_name",
            "metric_description",
            "metric_value",
            "enabled",
        )

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(metric_name__icontains=value) | Q(metric_description__icontains=value)
        )
