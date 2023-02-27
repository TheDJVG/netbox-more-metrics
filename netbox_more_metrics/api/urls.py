from netbox.api.routers import NetBoxRouter

from netbox_more_metrics.api import views

router = NetBoxRouter()
router.register("collections", views.MetricCollectionViewSet)
router.register(
    "metric-value-type-options",
    views.MetricValueTypeOptionsViewSet,
    basename="metric_value_type_options",
)
urlpatterns = router.urls
