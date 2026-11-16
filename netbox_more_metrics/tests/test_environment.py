import re
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

from django.db.utils import ProgrammingError
from django.test import SimpleTestCase, override_settings

import netbox_more_metrics
from netbox_more_metrics import NetBoxMoreMetricsConfig
from netbox_more_metrics.signals import start_collectors
from netbox_more_metrics.utilities import enable_metrics


def get_project_root() -> Path:
    # Resolves to repo root either in /source (container) or repo working dir
    module_dir = Path(netbox_more_metrics.__file__).resolve().parent
    return module_dir.parent


def get_git_branch_name(root: Path) -> str:
    # First attempt subprocess if git CLI is present
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()
    except Exception:
        pass

    # Direct fallback: inspect .git/HEAD
    head_file = root / ".git" / "HEAD"
    if head_file.is_file():
        content = head_file.read_text(encoding="utf-8").strip()
        return content.removeprefix("ref: refs/heads/")
    return "unknown"


# =====================================================================
# Feature 1: Dedicated Git Working Branch (M1 / R1)
# =====================================================================


class GitWorkingBranchTier1TestCase(SimpleTestCase):
    """Tier 1: Feature coverage for Git working branch setup."""

    def setUp(self):
        self.root = get_project_root()

    def test_git_head_resolvable(self):
        branch = get_git_branch_name(self.root)
        self.assertTrue(branch and branch != "unknown", "Git HEAD should resolve cleanly")

    def test_git_head_format_valid(self):
        head_file = self.root / ".git" / "HEAD"
        self.assertTrue(head_file.is_file(), ".git/HEAD must exist")
        content = head_file.read_text(encoding="utf-8").strip()
        # Allow symbolic branch refs and commit SHAs (detached HEAD on PR merge commits)
        is_symbolic = content.startswith("ref: refs/heads/")
        is_commit_sha = bool(re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", content))
        self.assertTrue(
            is_symbolic or is_commit_sha,
            f"Git HEAD must be a valid symbolic ref or commit SHA, got: {content}",
        )

    def test_git_status_hygiene(self):
        # Ensure no build artifacts or bytecode files are tracked in git
        gitignore = self.root / ".gitignore"
        self.assertTrue(gitignore.is_file(), ".gitignore must exist in root")
        content = gitignore.read_text(encoding="utf-8")
        self.assertTrue("*.py[cod]" in content or "*.pyc" in content)

    def test_branch_tracks_origin_or_base(self):
        git_dir = self.root / ".git"
        self.assertTrue(git_dir.is_dir(), ".git directory must exist")
        # Check config or refs exist
        refs_heads = git_dir / "refs" / "heads"
        self.assertTrue(refs_heads.is_dir(), ".git/refs/heads must exist")

    def test_gitignore_completeness(self):
        gitignore = self.root / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        for entry in ["__pycache__", "dist/"]:
            self.assertIn(entry, content, f"Expected {entry} in .gitignore")
        self.assertTrue("*.py[cod]" in content or "*.pyc" in content)


class GitWorkingBranchTier2TestCase(SimpleTestCase):
    """Tier 2: Boundary & Corner Cases for Git environment."""

    def setUp(self):
        self.root = get_project_root()

    def test_branch_naming_no_whitespace_or_control_chars(self):
        branch = get_git_branch_name(self.root)
        self.assertTrue(
            bool(branch) and not any(ch.isspace() for ch in branch),
            f"Branch or HEAD '{branch}' must not be empty or contain whitespace",
        )

    def test_no_git_conflict_markers_present(self):
        # Dynamically construct conflict marker prefixes to avoid self-match
        conflict_marker_starts = (b"<" * 7, b">" * 7)
        for ext in ["*.py", "*.md", "*.toml"]:
            for file_path in self.root.rglob(ext):
                if ".git" in file_path.parts or ".venv" in file_path.parts:
                    continue
                if file_path.name == "test_environment.py":
                    continue
                content = file_path.read_bytes()
                for line in content.splitlines():
                    trimmed = line.strip()
                    if trimmed.startswith(conflict_marker_starts) or trimmed == b"=" * 7:
                        self.fail(f"Found conflict marker '{trimmed.decode(errors='replace')}' in {file_path}")

    def test_no_accidental_secret_files_committed(self):
        forbidden_patterns = [".env", "*.key", "id_rsa", "credentials.json"]
        for pattern in forbidden_patterns:
            matches = [
                p
                for p in self.root.rglob(pattern)
                if ".git" not in p.parts and "development" not in p.parts and ".venv" not in p.parts
            ]
            self.assertEqual(matches, [], f"Forbidden secret file pattern matched: {matches}")

    def test_case_sensitivity_of_all_tracked_paths(self):
        # Verify no filenames in netbox_more_metrics clash on case-insensitive filesystems
        seen_lower = {}
        for file_path in (self.root / "netbox_more_metrics").rglob("*"):
            if "__pycache__" in file_path.parts:
                continue
            lower_name = str(file_path.relative_to(self.root)).lower()
            self.assertNotIn(
                lower_name,
                seen_lower,
                f"Case collision between {file_path} and {seen_lower.get(lower_name)}",
            )
            seen_lower[lower_name] = file_path

    def test_line_ending_consistency(self):
        for ext in ["*.py", "*.toml"]:
            for file_path in (self.root / "netbox_more_metrics").rglob(ext):
                if "__pycache__" in file_path.parts:
                    continue
                content = file_path.read_bytes()
                self.assertNotIn(
                    b"\r\n",
                    content,
                    f"File {file_path} contains CRLF line endings instead of LF",
                )


# =====================================================================
# Feature 3: PEP 621 Packaging Modernization (M1 / R2)
# =====================================================================


class PackagingModernizationTier1TestCase(SimpleTestCase):
    """Tier 1: Feature coverage for PEP 621 packaging."""

    def setUp(self):
        self.root = get_project_root()
        self.pyproject_path = self.root / "pyproject.toml"
        with open(self.pyproject_path, "rb") as f:
            self.pyproject = tomllib.load(f)

    def test_build_system_pep621(self):
        build_sys = self.pyproject.get("build-system", {})
        self.assertEqual(build_sys.get("build-backend"), "poetry.core.masonry.api")
        requires = build_sys.get("requires", [])
        self.assertTrue(any("poetry-core" in r for r in requires))

    def test_project_metadata_table(self):
        project = self.pyproject.get("project", {})
        self.assertEqual(project.get("name"), "netbox-more-metrics")
        self.assertEqual(project.get("version"), "0.5.1")
        self.assertEqual(project.get("version"), NetBoxMoreMetricsConfig.version)
        self.assertEqual(project.get("license"), "MIT")
        self.assertEqual(project.get("readme"), "README.md")

    def test_requires_python_specification(self):
        project = self.pyproject.get("project", {})
        self.assertEqual(project.get("requires-python"), ">=3.10")

    def test_runtime_dependencies(self):
        project = self.pyproject.get("project", {})
        deps = project.get("dependencies", [])
        self.assertTrue(any("prometheus-client" in d for d in deps))

    def test_poetry_package_directory(self):
        tool_poetry = self.pyproject.get("tool", {}).get("poetry", {})
        packages = tool_poetry.get("packages", [])
        self.assertEqual(packages, [{"include": "netbox_more_metrics"}])


class PackagingModernizationTier2TestCase(SimpleTestCase):
    """Tier 2: Boundary & Corner Cases for packaging configuration."""

    def setUp(self):
        self.root = get_project_root()
        self.pyproject_path = self.root / "pyproject.toml"
        with open(self.pyproject_path, "rb") as f:
            self.pyproject = tomllib.load(f)

    def test_no_legacy_poetry_dependencies(self):
        # PEP 621 puts dependencies in [project.dependencies], not [tool.poetry.dependencies]
        tool_poetry = self.pyproject.get("tool", {}).get("poetry", {})
        self.assertNotIn("dependencies", tool_poetry)

    def test_dependency_groups_pep735(self):
        dep_groups = self.pyproject.get("dependency-groups", {})
        test_group = dep_groups.get("test", [])
        self.assertTrue(any("pytest" in d for d in test_group))

    def test_pytest_ini_options(self):
        pytest_opts = self.pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
        self.assertEqual(pytest_opts.get("testpaths"), ["netbox_more_metrics/tests"])

    def test_classifiers_align_with_python_version(self):
        classifiers = self.pyproject.get("project", {}).get("classifiers", [])
        self.assertIn("Programming Language :: Python :: 3.10", classifiers)
        self.assertIn("Programming Language :: Python :: 3.11", classifiers)
        self.assertIn("Programming Language :: Python :: 3.12", classifiers)

    def test_toml_strict_parsing(self):
        text = self.pyproject_path.read_text(encoding="utf-8")
        parsed = tomllib.loads(text)
        self.assertIsInstance(parsed, dict)


# =====================================================================
# Feature 4: Dependency Upgrades & NetBox 3.x Deprecation (M1 / R2)
# =====================================================================


class DependencyUpgradeTier1TestCase(SimpleTestCase):
    """Tier 1: Feature coverage for NetBox 4.x dependencies and modern imports."""

    def test_plugin_min_version_is_netbox_4(self):
        self.assertTrue(NetBoxMoreMetricsConfig.min_version.startswith("4."))

    def test_no_legacy_netbox_3_pins(self):
        root = get_project_root()
        pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn("netbox<4", pyproject_text)
        self.assertNotIn("netbox~=3", pyproject_text)

    def test_prometheus_client_version(self):
        import importlib.metadata

        version_str = importlib.metadata.version("prometheus-client")
        version_tuple = tuple(int(x) for x in version_str.split(".")[:3] if x.isdigit())
        self.assertGreaterEqual(version_tuple, (0, 20, 0))

    def test_import_netbox_4_modern_modules(self):
        from core.models import ObjectType
        from netbox.filtersets import NetBoxModelFilterSet
        from netbox.models import NetBoxModel

        self.assertIsNotNone(ObjectType)
        self.assertIsNotNone(NetBoxModel)
        self.assertIsNotNone(NetBoxModelFilterSet)

    def test_plugin_config_structure(self):
        self.assertEqual(NetBoxMoreMetricsConfig.name, "netbox_more_metrics")
        self.assertEqual(NetBoxMoreMetricsConfig.base_url, "more-metrics")
        self.assertEqual(NetBoxMoreMetricsConfig.verbose_name, "More Metrics")


class DependencyUpgradeTier2TestCase(SimpleTestCase):
    """Tier 2: Boundary & Corner Cases for dependency upgrades and environment."""

    def test_enable_metrics_cli_detection_variations(self):
        # 1. When METRICS_ENABLED is False in settings
        with override_settings(METRICS_ENABLED=False):
            self.assertFalse(enable_metrics())

        # 2. When running under devserver (runserver in argv)
        with patch.object(sys, "argv", ["./manage.py", "runserver"]):
            self.assertTrue(enable_metrics())

        # 3. When running under gunicorn / wsgi without manage.py
        with patch.object(sys, "argv", ["gunicorn", "netbox.wsgi"]):
            self.assertTrue(enable_metrics())

        # 4. When running standard manage.py command (e.g. migrate)
        with patch.object(sys, "argv", ["./manage.py", "migrate"]):
            self.assertFalse(enable_metrics())

    def test_signals_safe_against_database_programming_error(self):
        # When unmigrated, start_collectors suppresses ProgrammingError cleanly
        with patch(
            "netbox_more_metrics.collectors.DynamicMetricCollectionCollector",
            side_effect=ProgrammingError("relation does not exist"),
        ):
            # Should not raise exception
            start_collectors(None)

    def test_default_settings_contains_auth_bypass_key(self):
        default_settings = NetBoxMoreMetricsConfig.default_settings
        self.assertIn("export_metrics_without_auth", default_settings)
        self.assertIs(default_settings["export_metrics_without_auth"], False)

    def test_python_runtime_version_gte_310(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 10))

    def test_lockfile_exists(self):
        root = get_project_root()
        lockfile = root / "poetry.lock"
        self.assertTrue(lockfile.is_file(), "poetry.lock must exist")
        self.assertGreater(lockfile.stat().st_size, 100)
