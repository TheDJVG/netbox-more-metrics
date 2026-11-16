# Changelog

## 0.5.1 (2026-11-16)

### Features & Enhancements
* Add verified compatibility and CI matrix coverage for NetBox 4.6 & 4.7 (Django 6.0/6.1, Python 3.13/3.14) plus a weekly `latest` canary build
* Decorate export endpoints with Django's `@login_not_required` for forward-compatibility with NetBox 5.0 mandatory authentication
* Modernize MkDocs configuration and lock documentation dependencies for GitHub Pages deployments

### Bugfixes
* Replace removed legacy `actions` dict on `ObjectListView` with `AddObject` (`netbox.object_actions`) for NetBox 4.6/4.7 compatibility
* Resolve `core.ObjectType` by natural key `(app_label, model)` in `MetricSerializer` rather than assuming `ContentType.pk == ObjectType.pk`
* Enforce strict `ALLOWED_LOOKUP_TYPES` on scalar fields and eager SQL compilation during validation for Django 6.1 ORM lookups

## 0.5.0 (2026-11-16)

### Features & Enhancements
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Add `FilterSet` classes and global NetBox `SearchIndex` integration for `Metric` and `MetricCollection`
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Expand REST API serializers with standard NetBox model fields (`description`, `tags`, `custom_fields`, `created`, `last_updated`, `display_url`) and NetBox 4.x `ObjectType` write support
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Harden ORM/API security boundaries against sensitive model traversal, ReDoS regex lookups, and unauthenticated option queries
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Optimize `/metrics` scrape queries by reconciling enabled collectors in a single prefetched pass
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Migrate packaging to PEP 621, add automated test suite, and configure GitHub Actions CI matrix across NetBox 4.x

### Bugfixes
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Fix `export_metrics_without_auth` redirecting to login or returning 404 when `LOGIN_REQUIRED=True`
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Fix duplicate collector registration crashes on counters ending in `_total` and info metrics ending in `_info`
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Prevent disabled `MetricCollection` endpoints from exporting metrics shared with enabled collections
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Fix `IPAddress` count grouping, empty-labelset count aggregation, utilization series deduplication, and `0U` rack zero-division handling
* [PR#47](https://github.com/TheDJVG/netbox-more-metrics/pull/47) - Restore `tags` field on `MetricForm`, align metric/label validators with the Prometheus specification, and display human-readable `metric_value` labels in the UI

## 0.4.0 (2026-01-12)

First release for 0.4.0.

The main changes in this version are enhanced API support, exclude filter and  the ability to disable authentication
the metric(collection) endpoints.


## 0.3.4 (2026-01-12)

Generic dependencies updates.

### Bugfixes
* [PR#42](https://github.com/TheDJVG/netbox-more-metrics/pull/42) - Use Netbox BooleanColumn for tables

## 0.3.3 (2025-12-10)

### Bugfixes
* [#40](https://github.com/TheDJVG/netbox-more-metrics/issues/40) - Resolve QuerySetNotOrdered exception when trying to paginate unordered API querysets
* [#43](https://github.com/TheDJVG/netbox-more-metrics/issues/43) - Resolve nested labels not being renamed

## 0.3.2 (2025-02-18)

### Features
* [#9](https://github.com/TheDJVG/netbox-more-metrics/issues/9) - Allow renaming of label names

### Bugfixes
* [#37](https://github.com/TheDJVG/netbox-more-metrics/issues/37) - Incorrect mixin for models does not override `get_obsolute_url` from NetBox model.


## 0.3.1 (2024-08-03)

### Bugfixes
* [#28](https://github.com/TheDJVG/netbox-more-metrics/issues/28) - Label value from JSON field contains double quotes.
* [#30](https://github.com/TheDJVG/netbox-more-metrics/issues/30) - Info metric was show wrong result data causing incorrect label names.


## 0.3.0 (2024-07-04)

First release compatible for NetBox 4.0. Earlier Netbox versions are not supported.

## 0.2.2 (2024-07-02)

### Bugfixes

* [#22](https://github.com/TheDJVG/netbox-more-metrics/issues/22) - Incorrect exception handler when Metric does not
  exist.

## 0.2.1 (2023-03-14)

### Bugfixes

* [#15](https://github.com/TheDJVG/netbox-more-metrics/issues/15) - Initial choices not set for existing metric on edit.

## 0.2.0 (2023-03-09)

### Features

* [#3](https://github.com/TheDJVG/netbox-more-metrics/issues/5) - Metric value based on NetBox objects.
    * For example get the percentage of IPs in a Prefix/Aggregate occupied, or how full a rack is.

## 0.1.1 (2023-02-27)

### Bugfixes

* [#2](https://github.com/TheDJVG/netbox-more-metrics/issues/2) - Fixes missing validation on metric labels.

## 0.1.0 (2023-02-08)

* First release with main functionality working.
