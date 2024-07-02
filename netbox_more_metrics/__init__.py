from contextlib import suppress

from django.db.utils import ProgrammingError
from extras.plugins import PluginConfig
from prometheus_client import REGISTRY

from netbox_more_metrics.utilities import enable_metrics


class NetBoxMoreMetricsConfig(PluginConfig):
    name = "netbox_more_metrics"
    verbose_name = "More Metrics"
    description = "Export custom metrics from NetBox data."
    version = "0.2.2"
    author = "Daan van Gorkum"
    author_email = "me+netbox@dj.vg"
    base_url = "more-metrics"

    def ready(self):
        # Make sure we call the NetBox plugin initialization to add the menus etc.
        super().ready()

        # Only enable the global metrics if we want to and the application is ready to serve them.
        if enable_metrics():
            with suppress(ProgrammingError):
                from netbox_more_metrics.collectors import (
                    DynamicMetricCollectionCollector,
                )
                from netbox_more_metrics.metrics import (  # noqa: F401
                    dynamic_metric_collectors,
                )

                DynamicMetricCollectionCollector(registry=REGISTRY)


config = NetBoxMoreMetricsConfig
