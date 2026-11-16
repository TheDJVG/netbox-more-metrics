import re

from circuits.models import Circuit, CircuitType, Provider
from core.models import ObjectType
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Rack, RackRole, Site
from django.contrib.auth import get_user_model
from django.urls import reverse
from ipam.models import RIR, Aggregate, IPAddress, Prefix
from tenancy.models import Tenant
from utilities.testing import TestCase
from virtualization.models import Cluster, ClusterType, VirtualMachine

from netbox_more_metrics.models import Metric, MetricCollection

User = get_user_model()


class PrometheusExpositionValidator:
    """Parser and validator for Prometheus exposition text format (0.0.4)."""

    HELP_RE = re.compile(r"^# HELP ([a-zA-Z_:][a-zA-Z0-9_:]*) (.*)$")
    TYPE_RE = re.compile(r"^# TYPE ([a-zA-Z_:][a-zA-Z0-9_:]*) (counter|gauge|info|histogram|summary|untyped)$")
    SAMPLE_RE = re.compile(
        r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})? (-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|NaN|\+Inf|-Inf)$"
    )
    LABEL_PAIR_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')

    @classmethod
    def validate_and_parse(cls, content: str) -> dict:
        lines = content.strip().split("\n")
        parsed = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("# HELP "):
                match = cls.HELP_RE.match(line)
                assert match, f"Malformed HELP line: {line}"
                name, doc = match.groups()
                parsed.setdefault(name, {"samples": []})["help"] = doc
            elif line.startswith("# TYPE "):
                match = cls.TYPE_RE.match(line)
                assert match, f"Malformed TYPE line: {line}"
                name, metric_type = match.groups()
                parsed.setdefault(name, {"samples": []})["type"] = metric_type
            elif line.startswith("#"):
                continue  # Other comment lines
            else:
                match = cls.SAMPLE_RE.match(line)
                assert match, f"Malformed SAMPLE line: {line}"
                sample_name, label_str, val_str = match.groups()
                labels = {}
                if label_str:
                    for l_match in cls.LABEL_PAIR_RE.finditer(label_str):
                        k, v = l_match.groups()
                        labels[k] = v.replace(r"\"", '"').replace(r"\\", "\\")
                val = float(val_str)
                parsed.setdefault(sample_name, {"samples": []})["samples"].append({"labels": labels, "value": val})

        return parsed


class ExpositionValidatorEngineTestCase(TestCase):
    """Tier 4: Verification of Prometheus Exposition Validation Engine."""

    def test_validator_parses_standard_exposition(self):
        sample_output = (
            "# HELP my_metric A test gauge\n" "# TYPE my_metric gauge\n" 'my_metric{label="val1",site="dc1"} 42.5\n'
        )
        parsed = PrometheusExpositionValidator.validate_and_parse(sample_output)
        self.assertIn("my_metric", parsed)
        self.assertEqual(parsed["my_metric"]["help"], "A test gauge")
        self.assertEqual(parsed["my_metric"]["type"], "gauge")
        self.assertEqual(len(parsed["my_metric"]["samples"]), 1)
        self.assertEqual(parsed["my_metric"]["samples"][0]["value"], 42.5)
        self.assertEqual(
            parsed["my_metric"]["samples"][0]["labels"],
            {"label": "val1", "site": "dc1"},
        )

    def test_validator_handles_scientific_notation_and_special_values(self):
        sample_output = (
            "# HELP complex_metric Complex metrics\n"
            "# TYPE complex_metric gauge\n"
            'complex_metric{mode="sci"} 1.25e+02\n'
            'complex_metric{mode="inf"} +Inf\n'
            'complex_metric{mode="nan"} NaN\n'
        )
        parsed = PrometheusExpositionValidator.validate_and_parse(sample_output)
        samples = parsed["complex_metric"]["samples"]
        self.assertEqual(len(samples), 3)
        self.assertEqual(samples[0]["value"], 125.0)
        self.assertEqual(samples[1]["value"], float("inf"))
        self.assertTrue(samples[2]["value"] != samples[2]["value"])  # NaN check

    def test_validator_detects_malformed_help(self):
        bad_output = "# HELP @invalid_name bad doc\n"
        with self.assertRaises(AssertionError):
            PrometheusExpositionValidator.validate_and_parse(bad_output)

    def test_validator_detects_malformed_type(self):
        bad_output = "# TYPE test_metric invalid_type\n"
        with self.assertRaises(AssertionError):
            PrometheusExpositionValidator.validate_and_parse(bad_output)

    def test_validator_unescapes_quotes_and_backslashes(self):
        sample_output = (
            "# HELP quote_metric Escaped quote metric\n"
            "# TYPE quote_metric gauge\n"
            r'quote_metric{desc="hello \"world\"",path="C:\\dir"} 1.0' + "\n"
        )
        parsed = PrometheusExpositionValidator.validate_and_parse(sample_output)
        labels = parsed["quote_metric"]["samples"][0]["labels"]
        self.assertEqual(labels["desc"], 'hello "world"')
        self.assertEqual(labels["path"], "C:\\dir")


class RealWorldScenario1DCIMTestCase(TestCase):
    """Scenario 1: DCIM Infrastructure Device Inventory & Status Monitoring."""

    def setUp(self):
        super().setUp()
        self.device_ct = ObjectType.objects.get_for_model(Device)
        self.site_ams = Site.objects.create(name="Amsterdam DC", slug="ams-dc")
        self.site_fra = Site.objects.create(name="Frankfurt DC", slug="fra-dc")
        self.mfr_cisco = Manufacturer.objects.create(name="Cisco", slug="cisco")
        self.mfr_arista = Manufacturer.objects.create(name="Arista", slug="arista")
        self.dt_cisco = DeviceType.objects.create(manufacturer=self.mfr_cisco, model="Catalyst 9300", slug="c9300")
        self.dt_arista = DeviceType.objects.create(manufacturer=self.mfr_arista, model="DCS-7050SX3", slug="7050sx3")
        self.role_core = DeviceRole.objects.create(name="Core Switch", slug="core")
        self.role_access = DeviceRole.objects.create(name="Access Switch", slug="access")

        self.dev1 = Device.objects.create(
            name="ams-core-01",
            site=self.site_ams,
            device_type=self.dt_cisco,
            role=self.role_core,
            status="active",
            serial="SN-CISCO-01",
        )
        self.dev2 = Device.objects.create(
            name="ams-core-02",
            site=self.site_ams,
            device_type=self.dt_cisco,
            role=self.role_core,
            status="active",
            serial="SN-CISCO-02",
        )
        self.dev3 = Device.objects.create(
            name="fra-acc-01",
            site=self.site_fra,
            device_type=self.dt_arista,
            role=self.role_access,
            status="offline",
            serial="SN-ARISTA-01",
        )
        self.dev4 = Device.objects.create(
            name="fra-acc-02",
            site=self.site_fra,
            device_type=self.dt_arista,
            role=self.role_access,
            status="planned",
            serial="SN-ARISTA-02",
        )

        self.user = User.objects.create(username="scenario1_user", is_active=True)
        self.add_permissions(
            "netbox_more_metrics.view_metric",
            "netbox_more_metrics.view_metriccollection",
        )
        self.client.force_login(self.user)

    def test_dcim_device_inventory_exposition_structure(self):
        m1 = Metric.objects.create(
            name="DevCount",
            metric_name="netbox_device_count",
            metric_description="Device count by status, role, site, and manufacturer",
            metric_type="gauge",
            metric_value="count",
            content_type=self.device_ct,
            metric_labels=[
                "status",
                "role__slug",
                "site__slug",
                "device_type__manufacturer__name",
            ],
            label_renames={
                "role__slug": "role",
                "site__slug": "site",
                "device_type__manufacturer__name": "manufacturer",
            },
            filter={"status__in": ["active", "offline"]},
        )
        m2 = Metric.objects.create(
            name="DevInfo",
            metric_name="netbox_device_info",
            metric_description="Device hardware information",
            metric_type="info",
            content_type=self.device_ct,
            metric_labels=["name", "serial"],
            filter={"status": "active"},
        )
        collection = MetricCollection.objects.create(
            name="DCIM Device Collection",
            enabled=True,
        )
        collection.metrics.set([m1, m2])

        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": collection.pk},
        )
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        parsed = PrometheusExpositionValidator.validate_and_parse(res.content.decode("utf-8"))
        self.assertIn("netbox_device_count", parsed)
        self.assertEqual(parsed["netbox_device_count"]["type"], "gauge")
        self.assertEqual(
            parsed["netbox_device_count"]["help"],
            "Device count by status, role, site, and manufacturer",
        )

        samples = parsed["netbox_device_count"]["samples"]
        self.assertEqual(len(samples), 2)

        ams_sample = next(s for s in samples if s["labels"].get("site") == "ams-dc")
        self.assertEqual(ams_sample["value"], 2.0)
        self.assertEqual(ams_sample["labels"]["role"], "core")
        self.assertEqual(ams_sample["labels"]["manufacturer"], "Cisco")
        self.assertEqual(ams_sample["labels"]["status"], "active")

        fra_sample = next(s for s in samples if s["labels"].get("site") == "fra-dc")
        self.assertEqual(fra_sample["value"], 1.0)
        self.assertEqual(fra_sample["labels"]["role"], "access")
        self.assertEqual(fra_sample["labels"]["manufacturer"], "Arista")
        self.assertEqual(fra_sample["labels"]["status"], "offline")

        # Planned status must be excluded
        self.assertFalse(any(s["labels"].get("status") == "planned" for s in samples))

        # Check Info metric
        self.assertIn("netbox_device_info_info", parsed)
        info_samples = parsed["netbox_device_info_info"]["samples"]
        self.assertEqual(len(info_samples), 2)
        dev_names = {s["labels"]["name"] for s in info_samples}
        self.assertEqual(dev_names, {"ams-core-01", "ams-core-02"})


class RealWorldScenario2IPAMTestCase(TestCase):
    """Scenario 2: IPAM IP Address Allocation & Prefix Utilization Monitoring."""

    def setUp(self):
        super().setUp()
        self.prefix_ct = ObjectType.objects.get_for_model(Prefix)
        self.ip_ct = ObjectType.objects.get_for_model(IPAddress)

        self.site_ams = Site.objects.create(name="AMS", slug="ams")
        self.site_fra = Site.objects.create(name="FRA", slug="fra")
        self.rir = RIR.objects.create(name="RFC 1918", slug="rfc-1918")
        self.aggregate = Aggregate.objects.create(prefix="10.0.0.0/8", rir=self.rir)

        self.p1 = Prefix.objects.create(prefix="10.1.0.0/24", scope=self.site_ams)
        self.p2 = Prefix.objects.create(prefix="10.2.0.0/24", scope=self.site_fra)

        for i in range(1, 5):
            IPAddress.objects.create(address=f"10.1.0.{i}/24", status="active")
        IPAddress.objects.create(address="10.1.0.5/24", status="reserved")

        self.collection = MetricCollection.objects.create(name="IPAM Collection", enabled=True)
        self.user = User.objects.create(username="scenario2_user", is_active=True)
        self.add_permissions("netbox_more_metrics.view_metric")
        self.client.force_login(self.user)

    def test_ipam_prefix_utilization_ratio(self):
        m = Metric.objects.create(
            name="PrefixUtilization",
            metric_name="netbox_prefix_utilization_ratio",
            metric_description="Prefix address utilization percentage",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.prefix_ct,
            metric_labels=["prefix", "site__slug"],
            label_renames={"site__slug": "site"},
        )
        self.collection.metrics.add(m)
        url = reverse("plugins:netbox_more_metrics:metric_metrics", kwargs={"pk": m.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        parsed = PrometheusExpositionValidator.validate_and_parse(res.content.decode("utf-8"))
        self.assertIn("netbox_prefix_utilization_ratio", parsed)
        samples = parsed["netbox_prefix_utilization_ratio"]["samples"]
        self.assertEqual(len(samples), 2)

        ams_prefix = next(s for s in samples if s["labels"].get("site") == "ams")
        self.assertGreater(ams_prefix["value"], 0.0)

        fra_prefix = next(s for s in samples if s["labels"].get("site") == "fra")
        self.assertEqual(fra_prefix["value"], 0.0)

    def test_ipam_ipaddress_total_counter(self):
        m = Metric.objects.create(
            name="IPTotal",
            metric_name="netbox_ipaddress_total",
            metric_description="Total IP addresses tracked in NetBox",
            metric_type="counter",
            metric_value="count",
            content_type=self.ip_ct,
            metric_labels=["status"],
        )
        self.collection.metrics.add(m)
        url = reverse("plugins:netbox_more_metrics:metric_metrics", kwargs={"pk": m.pk})

        # Scrape 1
        res1 = self.client.get(url)
        self.assertEqual(res1.status_code, 200)
        parsed1 = PrometheusExpositionValidator.validate_and_parse(res1.content.decode("utf-8"))
        self.assertIn("netbox_ipaddress_total", parsed1)
        self.assertEqual(parsed1["netbox_ipaddress_total"]["type"], "counter")
        samples1 = parsed1["netbox_ipaddress_total"]["samples"]

        active_s = next(s for s in samples1 if s["labels"].get("status") == "active")
        reserved_s = next(s for s in samples1 if s["labels"].get("status") == "reserved")
        self.assertEqual(active_s["value"], 4.0)
        self.assertEqual(reserved_s["value"], 1.0)

        # Scrape 2 (verify repeated scrape stability without collision)
        res2 = self.client.get(url)
        self.assertEqual(res2.status_code, 200)
        parsed2 = PrometheusExpositionValidator.validate_and_parse(res2.content.decode("utf-8"))
        self.assertIn("netbox_ipaddress_total", parsed2)


class RealWorldScenario3CircuitsTestCase(TestCase):
    """Scenario 3: WAN Circuits Capacity & Provider Distribution Monitoring."""

    def setUp(self):
        super().setUp()
        self.circuit_ct = ObjectType.objects.get_for_model(Circuit)
        self.prov_lumen = Provider.objects.create(name="Lumen", slug="lumen")
        self.prov_colt = Provider.objects.create(name="Colt", slug="colt")
        self.type_transit = CircuitType.objects.create(name="Transit", slug="transit")
        self.type_bb = CircuitType.objects.create(name="Backbone", slug="backbone")

        Circuit.objects.create(
            cid="CIR-01",
            provider=self.prov_lumen,
            type=self.type_transit,
            status="active",
            commit_rate=10000000,
        )
        Circuit.objects.create(
            cid="CIR-02",
            provider=self.prov_colt,
            type=self.type_bb,
            status="active",
            commit_rate=1000000,
        )
        Circuit.objects.create(
            cid="CIR-03",
            provider=self.prov_lumen,
            type=self.type_transit,
            status="decommissioned",
            commit_rate=5000000,
        )
        Circuit.objects.create(
            cid="CIR-04",
            provider=self.prov_colt,
            type=self.type_bb,
            status="active",
            commit_rate=None,
        )

        self.collection = MetricCollection.objects.create(name="WAN Collection", enabled=True)
        self.user = User.objects.create(username="scenario3_user", is_active=True)
        self.add_permissions("netbox_more_metrics.view_metric")
        self.client.force_login(self.user)

    def test_wan_circuits_provider_distribution_and_filtering(self):
        m = Metric.objects.create(
            name="CircuitActiveCount",
            metric_name="netbox_circuit_active_count",
            metric_description="Active WAN circuits by provider and type",
            metric_type="gauge",
            metric_value="count",
            content_type=self.circuit_ct,
            metric_labels=["provider__slug", "type__slug", "status"],
            label_renames={
                "provider__slug": "provider",
                "type__slug": "circuit_type",
            },
            filter={"status": "active"},
            exclude={"commit_rate__isnull": True},
        )
        self.collection.metrics.add(m)
        url = reverse("plugins:netbox_more_metrics:metric_metrics", kwargs={"pk": m.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        parsed = PrometheusExpositionValidator.validate_and_parse(res.content.decode("utf-8"))
        self.assertIn("netbox_circuit_active_count", parsed)
        samples = parsed["netbox_circuit_active_count"]["samples"]
        self.assertEqual(len(samples), 2)

        lumen_s = next(
            s
            for s in samples
            if s["labels"].get("provider") == "lumen" and s["labels"].get("circuit_type") == "transit"
        )
        self.assertEqual(lumen_s["value"], 1.0)
        self.assertEqual(lumen_s["labels"]["status"], "active")

        colt_s = next(
            s
            for s in samples
            if s["labels"].get("provider") == "colt" and s["labels"].get("circuit_type") == "backbone"
        )
        self.assertEqual(colt_s["value"], 1.0)
        self.assertEqual(colt_s["labels"]["status"], "active")


class RealWorldScenario4RacksTestCase(TestCase):
    """Scenario 4: Datacenter Rack Space & Power Utilization Monitoring."""

    def setUp(self):
        super().setUp()
        self.rack_ct = ObjectType.objects.get_for_model(Rack)
        self.site = Site.objects.create(name="DC-Central", slug="dc-central")
        self.role_compute = RackRole.objects.create(name="Compute Rack", slug="compute")
        self.role_net = RackRole.objects.create(name="Network Rack", slug="network")

        self.r1 = Rack.objects.create(name="Rack-01", site=self.site, role=self.role_compute, u_height=42)
        self.r2 = Rack.objects.create(name="Rack-02", site=self.site, role=self.role_compute, u_height=42)
        self.r3 = Rack.objects.create(name="Rack-03", site=self.site, role=self.role_net, u_height=42)

        self.user = User.objects.create(username="scenario4_user", is_active=True)
        self.add_permissions(
            "netbox_more_metrics.view_metric",
            "netbox_more_metrics.view_metriccollection",
        )
        self.client.force_login(self.user)

    def test_rack_space_and_power_utilization_coexistence(self):
        m_space = Metric.objects.create(
            name="RackSpace",
            metric_name="netbox_rack_space_utilization_percent",
            metric_description="Rack unit space utilization percentage",
            metric_type="gauge",
            metric_value="get_utilization",
            content_type=self.rack_ct,
            metric_labels=["site__slug", "role__slug", "name"],
            label_renames={
                "site__slug": "site",
                "role__slug": "role",
                "name": "rack",
            },
        )
        m_power = Metric.objects.create(
            name="RackPower",
            metric_name="netbox_rack_power_utilization_percent",
            metric_description="Rack power utilization percentage",
            metric_type="gauge",
            metric_value="get_power_utilization",
            content_type=self.rack_ct,
            metric_labels=["site__slug", "name"],
            label_renames={"site__slug": "site", "name": "rack"},
        )
        collection = MetricCollection.objects.create(
            name="Datacenter Racks Collection",
            enabled=True,
        )
        collection.metrics.set([m_space, m_power])

        url = reverse(
            "plugins:netbox_more_metrics:metriccollection_metrics",
            kwargs={"pk": collection.pk},
        )
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        parsed = PrometheusExpositionValidator.validate_and_parse(res.content.decode("utf-8"))
        self.assertIn("netbox_rack_space_utilization_percent", parsed)
        self.assertIn("netbox_rack_power_utilization_percent", parsed)

        space_samples = parsed["netbox_rack_space_utilization_percent"]["samples"]
        self.assertEqual(len(space_samples), 3)
        power_samples = parsed["netbox_rack_power_utilization_percent"]["samples"]
        self.assertEqual(len(power_samples), 3)

        for s in space_samples:
            self.assertIn(s["labels"]["rack"], ["Rack-01", "Rack-02", "Rack-03"])
            self.assertEqual(s["labels"]["site"], "dc-central")
            self.assertIsInstance(s["value"], float)


class RealWorldScenario5VirtualizationTestCase(TestCase):
    """Scenario 5: Multi-Tenant Virtualization Cluster & Virtual Machine Allocation."""

    def setUp(self):
        super().setUp()
        self.vm_ct = ObjectType.objects.get_for_model(VirtualMachine)
        self.tenant_acme = Tenant.objects.create(name="Acme Corp", slug="acme")
        self.tenant_globex = Tenant.objects.create(name="Globex", slug="globex")
        self.cluster_type = ClusterType.objects.create(name="Proxmox VE", slug="pve")
        self.cluster = Cluster.objects.create(name="Cluster-Alpha", type=self.cluster_type)

        VirtualMachine.objects.create(
            name="vm-acme-01",
            cluster=self.cluster,
            tenant=self.tenant_acme,
            status="active",
        )
        VirtualMachine.objects.create(
            name="vm-acme-02",
            cluster=self.cluster,
            tenant=self.tenant_acme,
            status="active",
        )
        VirtualMachine.objects.create(
            name="vm-globex-01",
            cluster=self.cluster,
            tenant=self.tenant_globex,
            status="active",
        )
        VirtualMachine.objects.create(
            name="vm-unassigned-01",
            cluster=self.cluster,
            tenant=None,
            status="active",
        )

        self.collection = MetricCollection.objects.create(name="VM Collection", enabled=True)
        self.user = User.objects.create(username="scenario5_user", is_active=True)
        self.add_permissions("netbox_more_metrics.view_metric")
        self.client.force_login(self.user)

    def test_virtualization_vm_tenant_segmentation_and_null_coalescence(self):
        m = Metric.objects.create(
            name="VMAllocation",
            metric_name="netbox_vm_allocation_count",
            metric_description="Active virtual machine allocations by cluster and tenant",
            metric_type="gauge",
            metric_value="count",
            content_type=self.vm_ct,
            metric_labels=["cluster__name", "tenant__slug", "status"],
            label_renames={
                "cluster__name": "cluster",
                "tenant__slug": "tenant",
            },
            filter={"status": "active"},
        )
        self.collection.metrics.add(m)
        url = reverse("plugins:netbox_more_metrics:metric_metrics", kwargs={"pk": m.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        parsed = PrometheusExpositionValidator.validate_and_parse(res.content.decode("utf-8"))
        self.assertIn("netbox_vm_allocation_count", parsed)
        samples = parsed["netbox_vm_allocation_count"]["samples"]
        self.assertEqual(len(samples), 3)

        acme_s = next(s for s in samples if s["labels"].get("tenant") == "acme")
        self.assertEqual(acme_s["value"], 2.0)
        self.assertEqual(acme_s["labels"]["cluster"], "Cluster-Alpha")
        self.assertEqual(acme_s["labels"]["status"], "active")

        globex_s = next(s for s in samples if s["labels"].get("tenant") == "globex")
        self.assertEqual(globex_s["value"], 1.0)
        self.assertEqual(globex_s["labels"]["cluster"], "Cluster-Alpha")

        null_tenant_s = next(s for s in samples if s["labels"].get("tenant") == "null")
        self.assertEqual(null_tenant_s["value"], 1.0)
        self.assertEqual(null_tenant_s["labels"]["cluster"], "Cluster-Alpha")
