from django.db.backends.signals import connection_created
from netbox.plugins import PluginConfig

from netbox_more_metrics.signals import start_collectors
from netbox_more_metrics.utilities import enable_metrics


class NetBoxMoreMetricsConfig(PluginConfig):
    name = "netbox_more_metrics"
    verbose_name = "More Metrics"
    description = "Export custom metrics from NetBox data."
    version = "0.3.0"
    min_version = "4.0"
    author = "Daan van Gorkum"
    author_email = "me+netbox@dj.vg"
    base_url = "more-metrics"

    def ready(self):
        # Make sure we call the NetBox plugin initialization to add the menus etc.
        super().ready()

        # Only enable the global metrics if we want to and the application is ready to serve them.
        if enable_metrics():
            connection_created.connect(start_collectors)


config = NetBoxMoreMetricsConfig
