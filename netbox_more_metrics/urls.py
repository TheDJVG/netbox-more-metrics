from django.urls import path
from netbox.views.generic import ObjectChangeLogView, ObjectJournalView

from netbox_more_metrics import views
from netbox_more_metrics.models import Metric, MetricCollection

urlpatterns = [
    #
    # MetricCollection
    #
    path(
        "collections/",
        views.MetricCollectionListView.as_view(),
        name="metriccollection_list",
    ),
    path(
        "collections/add/",
        views.MetricCollectionEditView.as_view(),
        name="metriccollection_add",
    ),
    path(
        "collections/<int:pk>/",
        views.MetricCollectionView.as_view(),
        name="metriccollection",
    ),
    path(
        "collections/<int:pk>/edit/",
        views.MetricCollectionEditView.as_view(),
        name="metriccollection_edit",
    ),
    path(
        "collections/<int:pk>/metrics/",
        views.MetricCollectionExportView.as_view(),
        name="metriccollection_metrics",
    ),
    path(
        "collections/<int:pk>/delete/",
        views.MetricCollectionDeleteView.as_view(),
        name="metriccollection_delete",
    ),
    path(
        "collections/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="metriccollection_changelog",
        kwargs={"model": MetricCollection},
    ),
    path(
        "collections/<int:pk>/journal/",
        ObjectJournalView.as_view(),
        name="metriccollection_journal",
        kwargs={"model": MetricCollection},
    ),
    #
    # Metric
    #
    path("metrics/", views.MetricListView.as_view(), name="metric_list"),
    path("metrics/add/", views.MetricEditView.as_view(), name="metric_add"),
    path("metrics/<int:pk>/", views.MetricView.as_view(), name="metric"),
    path("metrics/<int:pk>/edit/", views.MetricEditView.as_view(), name="metric_edit"),
    path(
        "metrics/<int:pk>/metrics/",
        views.MetricExportView.as_view(),
        name="metric_metrics",
    ),
    path(
        "metrics/<int:pk>/delete/",
        views.MetricDeleteView.as_view(),
        name="metric_delete",
    ),
    path(
        "metrics/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="metric_changelog",
        kwargs={"model": Metric},
    ),
    path(
        "metrics/<int:pk>/journal/",
        ObjectJournalView.as_view(),
        name="metric_journal",
        kwargs={"model": Metric},
    ),
]
