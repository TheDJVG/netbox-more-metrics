# Changelog

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
