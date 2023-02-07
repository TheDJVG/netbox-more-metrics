from prometheus_client import Counter

__all__ = ("dynamic_metric_collectors",)

dynamic_metric_collectors = Counter(
    "dynamic_metric_collectors",
    "Information about active dynamic metric collectors.",
    ["id", "metric_name"],
)
