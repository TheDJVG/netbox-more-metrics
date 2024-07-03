from contextlib import suppress

from django.db.backends.signals import connection_created
from django.db.utils import ProgrammingError
from prometheus_client import REGISTRY


def start_collectors(sender, **kwargs):
    with suppress(ProgrammingError):
        from netbox_more_metrics.collectors import DynamicMetricCollectionCollector
        from netbox_more_metrics.metrics import dynamic_metric_collectors  # noqa: F401

        DynamicMetricCollectionCollector(registry=REGISTRY)

    # Disconnect the signal, so we don't run it again.
    connection_created.disconnect(start_collectors)
