from netbox.api.routers import NetBoxRouter

from netbox_more_metrics.api import views

router = NetBoxRouter()
router.register("collections", views.MetricCollectionViewSet)
urlpatterns = router.urls
