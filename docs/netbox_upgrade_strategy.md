# Long-Term NetBox Upgrade and Maintenance Strategy Guide

This document establishes the official long-term upgrade, compatibility maintenance, and operational lifecycle strategy for the `netbox-more-metrics` plugin. It is designed as an exhaustive, production-grade guide for maintainers, contributors, and enterprise site reliability engineers managing custom Prometheus metric exports across NetBox minor (4.0 &rarr; 4.1 &rarr; 4.2 &rarr; ...) and major (4.x &rarr; 5.x) version transitions.

---

## 1. Document Overview & Guiding Architecture Principles

### 1.1 Purpose and Scope
The `netbox-more-metrics` plugin bridges the NetBox Network Source of Truth (NSoT) with Prometheus monitoring infrastructure by exposing dynamic database queries as standardized Prometheus exposition metrics. Because the plugin interfaces directly with NetBox internal data models, Django ORM internals, NetBox plugin lifecycle hooks, and Prometheus exposition registries, upstream changes in NetBox core, Django, or Python runtime environments have direct architectural implications.

This guide provides the protocols, checklists, and technical patterns necessary to guarantee seamless upgrades, eliminate backward-compatibility breaks, and ensure continuous automated testing at zero infrastructure cost.

### 1.2 Guiding Engineering Principles
All maintenance, feature development, and upstream upgrades must adhere strictly to four core engineering tenets:

1. **Zero Infrastructure Cost**: Continuous integration and validation workflows must execute entirely on free GitHub-hosted runners (`ubuntu-latest`) using open-source service containers and native caching. No paid build runners, third-party SaaS CI tiers, or proprietary hosting services are permitted.
2. **Zero Prometheus Scrape Disruption (Fail-Soft Isolation)**: A single misconfigured metric, database query error, or transient upstream model change must never cause an unhandled HTTP 500 error on `/plugins/more-metrics/export/` or `/metrics`. Scrapes must fail-soft: capture exceptions, log diagnostic warnings, and yield healthy metric families without crashing Prometheus scrapers or triggering false-positive alerts.
3. **Zero Unannounced Breakages (Proactive Cadence Tracking)**: Maintainers must never discover upstream incompatibilities from end-user failure reports. Weekly automated canary pipelines and pre-release testing against NetBox release candidates provide a 3-to-4 week remediation window before upstream general availability (GA).
4. **Strict Architectural Adherence**: Never introduce monkey-patches, bypass Django migration graphs, or violate NetBox plugin extension patterns. Always leverage official NetBox APIs (`NetBoxModel`, `NetBoxModelFilterSet`, `SearchIndex`, `ObjectType`, `PluginConfig`).

### 1.3 NetBox & Dependency Version Support Matrix

| Component | Minimum Supported | Active / Tested Target | Future / Planned Target | Deprecated / Unsupported |
|---|---|---|---|---|
| **NetBox Core** | `4.0.0` | `4.0.x`, `4.1.x`, `4.2.x`, `4.5.x` | `4.6+`, `5.0.x` | NetBox `< 3.4` (Dropped) |
| **Python Runtime** | `3.10` (for NetBox 4.0–4.2) | `3.11`, `3.12` | `3.13` (upon NetBox adoption) | Python `< 3.10` (Dropped) |
| **Django Framework** | `5.0` | `5.0.x`, `5.1.x` | `5.2 LTS`, `6.0` | Django `< 4.2` (Dropped) |
| **PostgreSQL Database** | `14.0` | `15.x`, `16.x`, `18-alpine` (dev) | `17.x+` | PostgreSQL `< 14` |
| **Redis / Valkey** | `7.0` | `7.x`, `8.x` | `8.x+` | Redis `< 7.0` |
| **`prometheus-client`** | `0.20.0` | `0.20.0+` | `0.21+` / OpenMetrics 1.0 | `prometheus-client < 0.14` |

---

## 2. Upstream NetBox Release Tracking & Monitoring

### 2.1 Upstream Release Lifecycle & Deprecation Policy
Upstream NetBox follows Semantic Versioning (`MAJOR.MINOR.PATCH`) aligned with a predictable release schedule:
- **Patch Releases (`4.x.Y`)**: Released weekly to bi-weekly. Contain bug fixes, security remediations, and performance adjustments. Patch releases strictly preserve backward compatibility for database schemas, models, and public plugin APIs.
- **Minor Releases (`4.X.0`)**: Released approximately every four months (typically April, August, and December). Minor releases introduce new features, model changes, and UI improvements.
- **The "2-Minor Deprecation Rule"**: Upstream NetBox policy dictates that when a core API or pattern is slated for deprecation, it emits `DeprecationWarning` or `PendingDeprecationWarning` for at least **two minor releases** before removal. For instance, a feature deprecated in NetBox `4.1` remains functional with warnings in `4.1` and `4.2`, and is only removed in `4.3` or `5.0`.
- **Major Releases (`X.0.0`)**: Released every 18 to 24 months. Major releases mark significant architectural evolutions (e.g., dropping legacy Django versions, transitioning core model inheritance, or overhauling UI frameworks).

### 2.2 Monitoring Channels & Feeds
Maintainers must track upcoming changes across four primary upstream channels:
1. **GitHub Releases Feed**: Subscribe to `https://github.com/netbox-community/netbox/releases.atom` via RSS or GitHub Notifications ("Custom &rarr; Releases").
2. **Upstream Release Notes**: Consult `https://netboxlabs.com/docs/netbox/en/stable/release-notes/` prior to every minor release upgrade.
3. **GitHub Discussions (Feature Requests & Architecture)**: Monitor `https://github.com/netbox-community/netbox/discussions/categories/announcements` for early notice on major architectural shifts.
4. **Upstream Commit Stream on `develop`**: Periodically review commits targeting `netbox-community/netbox:develop` to identify database schema modifications and deprecations months before release.

### 2.3 Automated Upstream Canary Workflow
To eliminate manual monitoring overhead, an automated canary workflow runs weekly on GitHub Actions. It queries the GitHub REST API for the latest NetBox release tag, verifies whether the tag is currently tested in the CI matrix, and opens an issue if a new minor release is detected.

The workflow definition (`.github/workflows/canary.yml` or integrated cron) runs at zero cost on `ubuntu-latest`:

```yaml
---
name: Upstream NetBox Release Canary

on:
  schedule:
    - cron: '0 6 * * 1' # Every Monday at 06:00 UTC
  workflow_dispatch:

concurrency:
  group: upstream-canary
  cancel-in-progress: true

jobs:
  check-upstream:
    name: Check Upstream NetBox Releases
    runs-on: ubuntu-latest
    permissions:
      issues: write
      contents: read
    steps:
      - name: Fetch Latest NetBox Release
        id: get_release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          LATEST_TAG=$(gh api repos/netbox-community/netbox/releases/latest --jq .tag_name)
          echo "latest_tag=${LATEST_TAG}" >> "$GITHUB_OUTPUT"
          echo "Latest upstream NetBox release is: ${LATEST_TAG}"

      - name: Check Against Active Support Matrix
        id: verify_matrix
        run: |
          LATEST="${{ steps.get_release.outputs.latest_tag }}"
          # Extract major.minor (e.g. v4.5)
          MINOR=$(echo "$LATEST" | grep -oE '^v[0-9]+\.[0-9]+')
          echo "Upstream minor branch: ${MINOR}"
          # Read supported versions from repository configuration
          SUPPORTED="v4.0 v4.1 v4.2 v4.5"
          if [[ ! " ${SUPPORTED} " =~ " ${MINOR} " ]]; then
            echo "new_minor_detected=true" >> "$GITHUB_OUTPUT"
          else
            echo "new_minor_detected=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Open Issue for New Upstream Minor Release
        if: steps.verify_matrix.outputs.new_minor_detected == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          TAG="${{ steps.get_release.outputs.latest_tag }}"
          gh issue create \
            --title "Upstream Compatibility: New NetBox Minor Release ${TAG}" \
            --body "A new upstream NetBox release **${TAG}** has been published. Maintainers must execute the Minor Upgrade Playbook to update the CI matrix and certify plugin compatibility."
```

### 2.4 Pre-Release Testing Protocol
Before each NetBox minor release (e.g., `4.3.0`), the NetBox core team publishes Beta and Release Candidate (RC) builds (e.g., `v4.3.0-beta1`, `v4.3.0-rc1`):
1. **Lead Time**: Beta/RC builds appear 3 to 4 weeks prior to general availability.
2. **Local RC Verification**: Maintainers test the RC container image locally:
   ```bash
   NETBOX_VER=v4.3.0-rc1 docker compose build netbox
   NETBOX_VER=v4.3.0-rc1 docker compose run --rm netbox ./manage.py makemigrations --check
   NETBOX_VER=v4.3.0-rc1 docker compose run --rm netbox ./manage.py test netbox_more_metrics --keepdb
   ```
3. **Deprecation Trapping**: Run test executions with warning escalation to capture upcoming breaks:
   ```bash
   docker compose run --rm netbox python -W error::DeprecationWarning ./manage.py test netbox_more_metrics --keepdb
   ```

---

## 3. Framework Deprecation & Lifecycle Management

### 3.1 Django Upgrade Cycles
NetBox tracks modern Django LTS and stable branches. NetBox 4.x runs on Django 5.x; NetBox 5.0 is slated to adopt Django 5.2 LTS or Django 6.0:
- **`django.utils.timezone`**: Avoid deprecated naive datetime comparisons; always use `timezone.now()` and timezone-aware timestamps for collector scheduling and metric timestamps.
- **QuerySet Semantics**: Django 5.0+ introduces stricter rules for annotation aliases and grouping. Avoid raw `extra()` or direct SQL fragment injection.
- **Escalation Testing**: CI test runs should periodically execute with `PYTHONWARNINGS="error::DeprecationWarning"` to pinpoint APIs scheduled for removal in future Django releases.

### 3.2 NetBox Core Model & ObjectType Abstractions
NetBox 4.0 replaced Django's generic `django.contrib.contenttypes.models.ContentType` with `core.models.ObjectType`:
- **Model References**: `Metric.content_type` points to `core.ObjectType`. All dynamic queries querying available object types must filter via `ObjectType.objects.public()` or exclude sensitive apps:
  ```python
  SENSITIVE_APP_LABELS = {
      "users",
      "auth",
      "contenttypes",
      "sessions",
      "admin",
  }
  ```
- **Relational Field Path Traversal**: In `netbox_more_metrics/models.py`, `validate_field_path()` traverses relational lookups using Django `_meta.get_field()`. When NetBox renames models or replaces relations (e.g., converting foreign keys to generic relations), maintainers must verify that `_meta.get_field(part).related_model` correctly resolves the destination model without leaking private attributes or throwing unhandled `FieldDoesNotExist` exceptions.

### 3.3 NetBox Plugin Framework Evolution
The plugin configuration class (`netbox_more_metrics/__init__.py:NetBoxMoreMetricsConfig`) defines the plugin's operational boundaries:
```python
class NetBoxMoreMetricsConfig(PluginConfig):
    name = "netbox_more_metrics"
    verbose_name = "More Metrics"
    description = "Export custom metrics from NetBox data."
    version = "0.4.1"
    min_version = "4.0.0"
    max_version = "4.99.9"
    author = "Daan van Gorkum"
    author_email = "me+netbox@dj.vg"
    base_url = "more-metrics"
    default_settings = {
        "export_metrics_without_auth": False,
    }
```
- **`min_version`**: Set to `"4.0.0"`. Never lower this below 4.0 because legacy NetBox 3.x support has been completely dropped.
- **`max_version`**: Pin to `"4.99.9"`. This prevents end-users from installing the plugin on uncertified NetBox 5.x major versions where breaking core changes could cause system instability.
- **`ready()` Lifecycle**: Keep `ready()` fast and non-blocking. Database queries in `ready()` must be wrapped in `try/except (OperationalError, ProgrammingError)` to ensure management commands like `migrate` or `collectstatic` can execute during initial database provisioning.

### 3.4 NetBox FilterSets, SearchIndex, and Tables Modernization
- **`FilterSet` Standards**: Subclass `netbox.filtersets.NetBoxModelFilterSet`. Ensure all custom models (`MetricCollection`, `Metric`) implement filter parameters for standard attributes (`q`, `name`, `enabled`, `tags`).
- **`SearchIndex` Standards**: Register all user-facing models using `netbox.search.SearchIndex` and `register_search()`. Assign weighted relevance (`1000` for primary identifiers like `name`, `2000` for metric identifiers like `metric_name`).
- **`Table` Classes**: Subclass `netbox.tables.NetBoxTable`. Ensure table actions, column selections, and tag badges utilize standard NetBox UI components.

### 3.5 Django REST Framework (DRF) & API Serializer Compatibility
- **Model Serializers**: Subclass `netbox.api.serializers.NetBoxModelSerializer`.
- **Mandatory Audit Fields**: Always include standard audit attributes: `id`, `url`, `display`, `name`, `description`, `tags`, `custom_fields`, `created`, `last_updated`.
- **Brief Serializers**: Subclass `netbox.api.serializers.NestedGroupModelSerializer` or `WritableNestedSerializer` providing lightweight representations (`id`, `url`, `display`, `name`) for nested relational serialization.
- **Authentication & ViewSet Permissions**: Ensure all viewsets enforce `NetBoxModelViewSet` permission classes. Never set `permission_classes = []` on operational endpoints.

### 3.6 UI Templates & Frontend Asset Evolution
- **Template Inheritance**: Extend official NetBox templates:
  - Detail views: `{% extends 'generic/object.html' %}`
  - List views: `{% extends 'generic/object_list.html' %}`
  - Edit/Create views: `{% extends 'generic/object_edit.html' %}`
- **HTMX & Bootstrap 5**: NetBox 4.x utilizes Bootstrap 5 and HTMX. Avoid bundling separate heavy JavaScript dependencies (e.g., jQuery, Vue, React). Use native HTML5 data attributes and NetBox CSS helper classes.

---

## 4. Safe Database Migration Architecture & Rollout

### 4.1 Database Migration Hygiene & CI Validation
Database migrations are the most critical aspect of plugin upgrade safety. An unmigrated model modification or invalid migration dependency can prevent NetBox from starting or corrupt production database schemas.
- **Strict Migration Immutability**: Once a migration file (e.g., `0001` through `0008`) is merged into the default branch or published in a release, it is **permanently immutable**. Never alter, re-generate, or delete existing migration files.
- **Mandatory CI Gate**: Every CI build executes:
  ```bash
  docker compose run --rm netbox ./manage.py makemigrations --check
  ```
  This command fails with a non-zero exit code if any model change was made without generating a matching migration file.

### 4.2 The "Leaf Migration Dependency" Pitfall & Manual Dependency Pinning

> **CRITICAL ARCHITECTURAL WARNING: THE LEAF-MIGRATION DEPENDENCY TRAP**
>
> When developers execute `./manage.py makemigrations netbox_more_metrics` inside a modern development environment (e.g., NetBox 4.5), Django inspects all foreign keys pointing to external apps (such as `core.ObjectType`). By default, Django automatically sets the dependency of the new migration to the **current leaf migration** of the target app.
>
> In NetBox 4.5, the leaf migration for `core` is `0021_job_queue_name`.
>
> If the newly generated plugin migration contains:
> ```python
> dependencies = [
>     ('core', '0021_job_queue_name'),
>     ('netbox_more_metrics', '0007_metric_exclude'),
> ]
> ```
> Then any user running NetBox 4.0, 4.1, 4.2, 4.3, or 4.4 who upgrades or installs the plugin will experience an immediate crash during `python manage.py migrate`:
> ```text
> django.db.migrations.exceptions.NodeNotFoundError: Migration netbox_more_metrics.0008_...
> dependencies reference nonexistent parent node ('core', '0021_job_queue_name')
> ```
> Because `core.0021` does not exist in earlier NetBox 4.x releases, the entire upgrade aborts.

#### Remediation Protocol: Manual Dependency Pinning
Whenever `makemigrations` creates a new migration file:
1. Open the generated file in `netbox_more_metrics/migrations/`.
2. Inspect the `dependencies` list.
3. Identify dependencies on upstream NetBox core apps (`core`, `dcim`, `ipam`, `extras`).
4. Pin the dependency to the **earliest migration** that introduced the required model or field, rather than the latest leaf migration.
   - For `core.ObjectType`, model proxying was introduced in `('core', '0008_contenttype_proxy')` and stabilized in `('core', '0010_gfk_indexes')` or `('core', '0018_concrete_objecttype')`.
   - Update the dependency to reference the lowest common denominator present across all supported versions (`v4.0+`):
     ```python
     dependencies = [
         ('core', '0008_contenttype_proxy'),
         ('netbox_more_metrics', '0007_metric_exclude'),
     ]
     ```
5. Test the migration across the CI version matrix (`v4.0`, `v4.1`, `v4.2`, `v4.5`) to verify that all versions can resolve the migration dependency graph.

### 4.3 Safe Schema Evolution & Preserving User Configurations
When introducing new fields or database schema changes to `Metric` or `MetricCollection`:
1. **Always Provide Defaults or Allow Nulls**:
   - New boolean fields: `default=False` or `default=True` with `db_index=True` if queried frequently.
   - New relational fields: `null=True, blank=True, on_delete=models.SET_NULL`.
   - New JSON/Array fields: `default=dict` or `default=list` with `blank=True`.
2. **Never Rename Columns in a Single Destructive Step**:
   Renaming a database column directly causes immediate downtime for active scrapers during rolling NetBox container upgrades. Use multi-phase field deprecation.

### 4.4 Multi-Phase Field Deprecation & Data Migrations
When removing or transforming database fields:
- **Phase 1 (Release N)**: Add the new column with `null=True`. Update models and collectors to read from the new field if populated, falling back to the legacy field.
- **Phase 2 (Release N)**: Include a Python data migration (`RunPython`) that iterates over existing records and copies data from the legacy field to the new field:
  ```python
  def forward_copy_data(apps, schema_editor):
      Metric = apps.get_model('netbox_more_metrics', 'Metric')
      for metric in Metric.objects.all():
          if metric.legacy_field and not metric.new_field:
              metric.new_field = transform(metric.legacy_field)
              metric.save(update_fields=['new_field'])

  class Migration(migrations.Migration):
      operations = [
          migrations.RunPython(forward_copy_data, reverse_code=migrations.RunPython.noop),
      ]
  ```
- **Phase 3 (Release N+1)**: Emit deprecation warnings in UI forms and API serializers if the legacy field is supplied.
- **Phase 4 (Release N+2 or Major Bump)**: Remove the legacy field from models and generate the final schema drop migration.

### 4.5 Migration Reversibility Testing & PostgreSQL Specifics
- **Reversibility Testing**: Maintainers must verify that all schema migrations can be unapplied cleanly without data loss or integrity violations:
  ```bash
  # Step backwards one migration
  docker compose run --rm netbox ./manage.py migrate netbox_more_metrics 0007
  # Re-apply forward
  docker compose run --rm netbox ./manage.py migrate netbox_more_metrics
  ```
- **PostgreSQL Concurrency Considerations**:
  - Adding non-null columns without defaults in PostgreSQL locks the entire table.
  - Adding indexes on large tables in production should use `ConcurrentAddIndex` if supported, or keep index footprint minimal.

---

## 5. Dynamic Collector Compatibility & Prometheus Exposition Stability

### 5.1 Dynamic Collector Architecture Overview & Scrape Flow
The plugin operates an in-memory dynamic collector architecture:
1. An incoming HTTP request hits `/plugins/more-metrics/export/` or a specific collection/metric endpoint.
2. The view authenticates the request or verifies `export_metrics_without_auth == True`.
3. `DynamicMetricCollectionCollector` instantiates or retrieves the collection's active metrics.
4. Each metric is evaluated by `DynamicMetricCollector`, which translates model selections, filters, exclusions, and relational lookups into an optimized Django ORM QuerySet.
5. The QuerySet executes against PostgreSQL, extracting counts, values, or utilization percentages.
6. The collector constructs Prometheus metric families (`GaugeMetricFamily`, `CounterMetricFamily`, `InfoMetricFamily`) and serializes them to exposition format.

### 5.2 Upstream Model & Method Changes
Dynamic collectors frequently evaluate model methods (e.g., `get_utilization`, `get_power_utilization`):
- **Defensive Evaluation**: NetBox model methods may change signatures, return `None`, or be deprecated. The evaluation loop in `netbox_more_metrics/collectors.py` must guard method invocations defensively:
  ```python
  try:
      raw_val = getattr(result, self.metric_value)
      value = raw_val() if callable(raw_val) else raw_val
      if value is None:
          continue
  except (AttributeError, TypeError, Exception) as exc:
      logger.warning("Failed evaluating metric value '%s' on %r: %s", self.metric_value, result, exc)
      continue
  ```
- **ORM Traversal Hardening**: Relational paths (`device__rack__site__name`) must be validated against `validate_field_path()` to ensure that intermediate models cannot traverse into sensitive objects (`User`, `Token`, `Session`).

### 5.3 Fail-Soft Error Isolation
Under no circumstances should an error in one metric abort the scrape of all other metrics. If an admin configures an invalid filter or an upstream NetBox model alters an attribute:
1. Catch exceptions within `DynamicMetricCollector.collect()`.
2. Emit a structured log message (`logger.error("Error collecting metric %s (pk=%d): %s", self.metric_name, self.pk, exc, exc_info=True)`).
3. Do not re-raise the exception to the top-level view.
4. Allow all remaining metrics in the collection to complete and yield valid Prometheus metrics.
5. This guarantees that Prometheus scrapers receive HTTP 200 with all healthy metrics, preventing scrape alert storms across production network monitoring infrastructure.

### 5.4 Relational Label Sanitization & PostgreSQL JSON Extraction
- **Label Sanitization (`get_annotation_alias`)**: Django ORM forbids double underscores in annotation aliases (e.g., `device__site__name` is invalid as an alias). The plugin transforms relational label paths into safe PostgreSQL aliases (`_metric_label_device_site_name`) with collision-resistant SHA-256 truncation.
- **PostgreSQL JSONB Custom Fields**: NetBox custom fields are stored in `custom_field_data` JSONB columns. Dynamic collectors use `jsonb_extract_path_text` to extract values directly in the database engine, avoiding costly Python deserialization loops. Maintain compatibility with PostgreSQL JSONB query semantics across PostgreSQL 14, 15, and 16.

### 5.5 Prometheus Client Library Lifecycle
- **Registry Suffix Collision Prevention**:
  `prometheus_client` automatically strips `_total` from Counters and `_info` from Info metrics in its internal name map (`_names_to_collectors`). Previous plugin versions crashed when querying `self.registry._names_to_collectors` because checking `metric.metric_name` resulted in false-negative existence checks, triggering duplicate registration errors.
- **Explicit Collector Tracking**: The plugin explicitly manages active collectors via an internal dictionary keyed by primary key:
  ```python
  self._active_metric_collectors: dict[int, DynamicMetricCollector] = {}
  ```
  This eliminates duplicate collector registration crashes regardless of suffix naming (`_total`, `_info`, `_count`, `_bucket`).
- **OpenMetrics Compliance**: Ensure exposition conforms to Prometheus text format 0.0.4 and OpenMetrics 1.0 specifications.

---

## 6. Zero-Cost GitHub Actions CI/CD Maintenance Strategy

### 6.1 GitHub-Hosted Runner Economics
Public open-source repositories on GitHub receive **unlimited free runner minutes** on standard GitHub-hosted runners (`ubuntu-latest`). Private repositories receive 2,000 free minutes per month.

To ensure long-term maintenance costs remain **$0.00**:
- **Concurrency Auto-Cancellation**: Every workflow includes a concurrency group with `cancel-in-progress: true`:
  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: true
  ```
  When a developer pushes multiple commits in quick succession, previous in-flight runs are immediately terminated, preserving runner capacity.
- **Aggressive Timeouts**: All jobs specify `timeout-minutes: 10` (or `15` for matrix tests) to ensure hung processes or stalled container pulls cannot consume hours of runner time.
- **Execution Efficiency**: With Docker Compose and caching, a full test run of 231 tests completes in under 20 seconds. Total pipeline wall-clock time across the 4-version NetBox matrix is under 2.5 minutes.

### 6.2 Native Service Container Architecture
The CI architecture leverages Docker Compose running directly on the `ubuntu-latest` host. This guarantees:
1. Complete parity with local development environments (`compose.yaml`).
2. Immediate availability of official pre-built `netboxcommunity/netbox` images without requiring developers to clone NetBox core and compile 50+ Python dependencies from scratch.
3. Isolated database and caching services using official alpine containers (`postgres:18-alpine`, `redis:8-alpine`).

### 6.3 Aggressive Multi-Tier Caching
- **Docker Layer Caching**: GitHub Actions runner SSDs cache container layers and intermediate build stages.
- **Python Package Caching**: The fast `packaging-and-quality` job uses `actions/setup-python@v5` with `cache: "pip"` to cache wheel downloads for Poetry and dependencies.

### 6.4 Matrix Execution Optimization
The CI matrix covers all active NetBox 4.x minor releases:
```yaml
matrix:
  netbox-version: ["v4.0", "v4.1", "v4.2", "v4.5"]
```
All matrix cells execute in parallel on separate free runners, finishing the entire validation suite in parallel within 3 minutes.

### 6.5 Canary Cron & Automated Issue Generation
The weekly canary cron (`schedule: - cron: '0 6 * * 1'`) acts as an early-warning radar. If upstream NetBox pushes an update that breaks the plugin, maintainers are notified immediately via GitHub issues and workflow failure notifications before any end-users are impacted.

---

## 7. Step-by-Step Minor Upgrade Procedure (NetBox 4.x &rarr; 4.y)

When upstream NetBox publishes a new minor version (for example, upgrading from `4.2` to `4.3`), follow this systematic 5-phase procedure:

```
[Phase 1: Upstream Reconnaissance]
  ├── Read Upstream Release Notes & Breaking Changes
  └── Identify Model & API Changes in core, dcim, ipam
          │
          ▼
[Phase 2: Local Docker Development & Test Execution]
  ├── Update NETBOX_VER in development/dev.env or Dockerfile
  ├── Run docker compose run --rm netbox ./manage.py makemigrations --check
  └── Run docker compose run --rm netbox ./manage.py test netbox_more_metrics --keepdb
          │
          ▼
[Phase 3: Migration Dependency Audit]
  ├── If new migrations generated, check dependencies list
  └── Pin upstream dependencies to lowest viable migration (e.g. core.0008)
          │
          ▼
[Phase 4: CI Matrix & Configuration Update]
  ├── Add new minor version (v4.y) to .github/workflows/ci.yml matrix
  └── Verify 100% green build on GitHub Actions
          │
          ▼
[Phase 5: Version Bump, Changelog & Release]
  ├── Bump version in pyproject.toml and netbox_more_metrics/__init__.py
  ├── Update docs/changelog.md
  └── Tag release (e.g. v0.4.2) and push
```

### Phase 1: Pre-Upgrade Upstream Reconnaissance
1. Read the upstream NetBox release notes for `v4.y.0`.
2. Inspect the "Breaking Changes" and "Deprecations" sections.
3. Check if any core models used in metric filters (e.g., `Device`, `Site`, `Prefix`, `VirtualMachine`) have renamed fields or altered relational foreign keys.

### Phase 2: Local Docker Development & Test Execution
1. Update `NETBOX_VER` to test against the new version:
   ```bash
   NETBOX_VER=v4.y docker compose build netbox
   ```
2. Start test dependencies and verify migration status:
   ```bash
   NETBOX_VER=v4.y docker compose run --rm netbox ./manage.py makemigrations --check
   ```
3. Execute the full automated test suite:
   ```bash
   NETBOX_VER=v4.y docker compose run --rm netbox ./manage.py test netbox_more_metrics --keepdb
   ```
4. If any tests fail, address the specific API changes following minimal-change and backward-compatible principles.

### Phase 3: Migration Dependency Audit & `makemigrations` Verification
1. If any new migrations were created during the update:
   ```bash
   ls -la netbox_more_metrics/migrations/
   ```
2. Inspect the latest migration file.
3. Verify that any dependency on `core` is pinned to the earliest viable migration (`core.0008_contenttype_proxy` or `core.0010_gfk_indexes`) rather than the leaf migration of `v4.y`.
4. Re-run `makemigrations --check` to ensure no lingering schema drifts.

### Phase 4: CI Matrix Update & Verification
1. Open `.github/workflows/ci.yml`.
2. Add `v4.y` to the `test` job matrix:
   ```yaml
   matrix:
     netbox-version: ["v4.0", "v4.1", "v4.2", "v4.5", "v4.y"]
   ```
3. Commit to the working branch and push to trigger CI.
4. Verify that all packaging and test matrix cells pass with 100% success.

### Phase 5: Version Bump, Changelog, and Release Tagging
1. Update version number in `pyproject.toml` and `netbox_more_metrics/__init__.py`.
2. Add release highlights to `docs/changelog.md`.
3. Create and push a signed Git tag:
   ```bash
   git tag -s v0.4.2 -m "Release v0.4.2: NetBox 4.y compatibility"
   git push origin v0.4.2
   ```

---

## 8. Step-by-Step Major Upgrade Playbook (NetBox 4.x &rarr; 5.x)

Major upgrades introduce fundamental architectural shifts (such as Python version deprecations, Django major upgrades, or plugin API restructuring).

### Phase 1: Breaking Changes & Deprecation Removal Audit
1. Audit all deprecations removed in NetBox 5.0.
2. Check whether Django has removed previously deprecated queryset methods or template tags.
3. Identify whether NetBox 5.0 has introduced a new plugin base class, navigation menu system, or authentication pipeline.

### Phase 2: Platform Version Bumps (Python, Django, Poetry dependencies)
1. Verify minimum Python runtime. If NetBox 5.0 drops Python 3.10 and requires Python 3.12+, update `pyproject.toml`:
   ```toml
   requires-python = ">=3.12"
   ```
2. Update Poetry lockfile:
   ```bash
   poetry update
   ```

### Phase 3: Core Framework Shims & Model Traversal Adaptations
1. If NetBox 5.0 introduces breaking changes to `NetBoxModel` or `NetBoxModelFilterSet`, create backward-compatible adapter shims:
   ```python
   try:
       from netbox.filtersets import NetBoxModelFilterSet
   except ImportError:
       # Fallback or shim for evolving framework classes
       ...
   ```
2. Verify that `validate_field_path()` continues to correctly resolve fields across modified models.

### Phase 4: Migration Path & Data Transformation
1. Ensure the migration path from 4.x to 5.x is linear and non-destructive.
2. If major schema refactoring is required, generate squashed migrations for old releases or maintain a clean transition migration.
3. Test migration rollback and re-application against live PostgreSQL test databases.

### Phase 5: PluginConfig Boundary Update & E2E Validation
1. Update `NetBoxMoreMetricsConfig` in `netbox_more_metrics/__init__.py`:
   ```python
   min_version = "4.0.0"
   max_version = "5.99.9"
   ```
2. Update `.github/workflows/ci.yml` matrix to include NetBox 5.0 images.
3. Run complete adversarial stress testing across all metrics collectors and export endpoints.

---

## 9. Troubleshooting, Rollback, and Emergency Response Runbook

### 9.1 Scrape 500 Internal Server Errors & Scrape Timeout Remediation
- **Symptom**: Prometheus server alerts with `ScrapeFailed` or HTTP 500 status when scraping `/plugins/more-metrics/export/`.
- **Diagnosis**:
  1. Inspect the NetBox container logs:
     ```bash
     docker compose logs --tail=100 netbox
     ```
  2. Identify the specific metric causing the failure:
     - Scrape metrics individually via the single-metric endpoint:
       `http://netbox:8000/api/plugins/more-metrics/metrics/<pk>/metrics/`
     - Iterate across all configured metrics to pinpoint the failing primary key.
- **Immediate Mitigation**:
  1. Log in to the NetBox admin UI (`/plugins/more-metrics/metrics/`).
  2. Locate the failing metric record and toggle `enabled = False`.
  3. Scrapes will immediately recover.
- **Root-Cause Fix**:
  If the failure was caused by an upstream model change (e.g., a field was renamed or a method return type changed), update `collectors.py` with defensive try/except containment and deploy a patch release.

### 9.2 Migration Conflict / `NodeNotFoundError` Invalidation & Resolution
- **Symptom**: During `manage.py migrate`, NetBox crashes with:
  `NodeNotFoundError: Migration netbox_more_metrics.000X dependencies reference nonexistent parent node ('core', '...')`.
- **Diagnosis**:
  A plugin migration file was generated in an environment running a newer NetBox version, capturing a leaf migration that does not exist in the user's NetBox installation.
- **Remediation**:
  1. Open the offending migration file in `netbox_more_metrics/migrations/`.
  2. Locate the invalid dependency (e.g., `('core', '0021_job_queue_name')`).
  3. Replace it with the base dependency present in all 4.x versions: `('core', '0008_contenttype_proxy')`.
  4. Save and re-run:
     ```bash
     python manage.py migrate netbox_more_metrics
     ```

### 9.3 Registry Collision & Duplicate Timeseries Triage
- **Symptom**: Scrape endpoint returns Prometheus formatting error:
  `Duplicated timeseries in CollectorRegistry: ...`.
- **Diagnosis**:
  Two separate metrics within the same collection share the same `metric_name` and produce identical label sets, or a utilization metric was queried without unique identifying labels.
- **Remediation**:
  1. The plugin automatically deduplicates utilization samples in `DynamicMetricCollector._collect_utilization()`.
  2. If custom user labels collide, adjust the `metric_labels` configuration to include distinguishing attributes (e.g., `id`, `name`, or `slug`).

### 9.4 Emergency Patching & Rollback Workflow
If a critical defect is identified in a published release:
1. **Branch from Release Tag**:
   ```bash
   git checkout -b hotfix/v0.4.2 v0.4.1
   ```
2. **Apply Minimal Fix**: Follow the minimal-change principle. Fix only the defect.
3. **Run Regression Tests**:
   ```bash
   docker compose run --rm netbox ./manage.py test netbox_more_metrics --keepdb
   ```
4. **Publish Hotfix**:
   Tag and publish `v0.4.2` immediately.
5. **Merge Back to Development**:
   Merge `hotfix/v0.4.2` into `development`.

---

## Appendix A: Diagnostic Commands Quick Reference

| Action | Executable Command |
|---|---|
| **Validate Packaging** | `poetry check` |
| **Build Artifacts** | `poetry build` |
| **Check Migrations** | `docker compose run --rm netbox ./manage.py makemigrations --check` |
| **Run All Tests** | `docker compose run --rm netbox ./manage.py test netbox_more_metrics --keepdb` |
| **Run Specific Test** | `docker compose run --rm netbox ./manage.py test netbox_more_metrics.tests.test_collectors --keepdb` |
| **Test With Warnings** | `docker compose run --rm netbox python -W error::DeprecationWarning ./manage.py test netbox_more_metrics --keepdb` |
| **Inspect DB Migrations** | `docker compose run --rm netbox ./manage.py showmigrations` |
| **Rollback Migration** | `docker compose run --rm netbox ./manage.py migrate netbox_more_metrics 0007` |
| **Re-apply Migrations** | `docker compose run --rm netbox ./manage.py migrate netbox_more_metrics` |
| **Validate Workflow YAML**| `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` |

---

## Appendix B: Migration Dependency Inspection Cheat Sheet

```
NetBox Core App Migration Flow:
core.0001_squashed_0005
     │
     ▼
core.0008_contenttype_proxy   <--- PIN HERE for core.ObjectType dependencies!
     │                             (Guaranteed to exist across ALL NetBox 4.x)
     ▼
core.0010_gfk_indexes
     │
     ▼
core.0018_concrete_objecttype
     │
     ▼
core.0021_job_queue_name      <--- DO NOT PIN HERE!
                                   (Only exists in NetBox 4.5+; breaks 4.0-4.4)
```

**Rule of Thumb**: When referencing any NetBox core model in plugin migrations, never rely on auto-generated leaf migrations. Always pin to the earliest migration that introduced the model definition.
