from django.conf import settings
from django.db.backends.signals import connection_created
from netbox.plugins import PluginConfig

from netbox_more_metrics.signals import start_collectors
from netbox_more_metrics.utilities import enable_metrics


class NetBoxMoreMetricsConfig(PluginConfig):
    name = "netbox_more_metrics"
    verbose_name = "More Metrics"
    description = "Export custom metrics from NetBox data."
    version = "0.4.1"
    min_version = "4.0"
    author = "Daan van Gorkum"
    author_email = "me+netbox@dj.vg"
    base_url = "more-metrics"
    default_settings = {
        "export_metrics_without_auth": False,
    }

    def ready(self):
        # Make sure we call the NetBox plugin initialization to add the menus etc.
        super().ready()

        # NetBox 4.0-4.1 enforces LOGIN_REQUIRED globally in CoreMiddleware unless exempted in
        # AUTH_EXEMPT_PATHS; UI views enforce LOGIN_REQUIRED directly so export views can honor
        # export_metrics_without_auth dynamically.
        if hasattr(settings, "AUTH_EXEMPT_PATHS"):
            plugin_prefix = f"/{getattr(settings, 'BASE_PATH', '')}plugins/{self.base_url}/"
            if plugin_prefix not in settings.AUTH_EXEMPT_PATHS:
                settings.AUTH_EXEMPT_PATHS = (*tuple(settings.AUTH_EXEMPT_PATHS), plugin_prefix)

        # Only enable the global metrics if we want to and the application is ready to serve them.
        if enable_metrics():
            connection_created.connect(start_collectors)


config = NetBoxMoreMetricsConfig
