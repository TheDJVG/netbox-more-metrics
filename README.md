__*Early development, not ready for production usage.*__
# netbox-more-metrics

Create custom metrics and export information from NetBox into your timeseries database.

# Background
### Why?
For example, you could track the amount of active devices over time by rack and site
![Example metric](docs/img/example1.png)

Any model can be exported, data is grouped by the labels.

### Filter validation
Every filter is tested on save and also when the metric is initiated for exporting.
![Example invalid filter](docs/img/example2.png)

### Heavy lifting is done by the database
As much as possible is done in the database directly to take advantage of any Model specific optimizations.

`null` database values are converted to a string `"null"`.

# Functions
- Metrics can be included in the global metric endpoint (`/metrics`).
- Metrics and MetricCollections can be individually exported (as long as the Metric(Collection) is enabled)

# Future ideas
- Adding a way to export utilization (e.g. how many IPs of a prefix are used, or how much power is still available on a feed).

**More ideas welcome!**

# Missing
- Tests
- Documentation
