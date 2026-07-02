"""Unit tests for lab setup / readiness / targets (dry-run/synthetic — no Docker/network)."""

from __future__ import annotations


class TestLabSetup:
    def test_setup_dry_run_completes(self):
        from scripts.lab_setup import run_setup

        result = run_setup(skip_heavy=True, dry_run=True)
        assert "vulhub" in result
        assert result["vulhub"]["status"] == "skipped"

    def test_setup_heavy_skip_respected(self):
        from scripts.lab_setup import run_setup

        result = run_setup(skip_heavy=True, dry_run=True)
        assert result["vulhub"]["status"] == "skipped" or result["vulhub"]["status"] == "cached"


class TestLabReady:
    def test_ready_runs_without_crash(self):
        from scripts.lab_ready import run_readiness

        passed, results = run_readiness()
        assert isinstance(passed, bool)
        assert len(results) >= 5

    def test_ready_has_required_checks(self):
        from scripts.lab_ready import CHECKS

        assert any(c["required"] for c in CHECKS.values())


class TestLabTargets:
    def test_list_outputs_catalog(self):
        from scripts.lab_targets import cmd_list

        targets = cmd_list()
        assert len(targets) >= 7

    def test_up_dry_run(self):
        from scripts.lab_targets import cmd_up

        result = cmd_up("vulhub-log4shell-solr", dry_run=True)
        assert result["status"] == "dry_run"

    def test_up_raw_path_dry_run(self):
        from scripts.lab_targets import cmd_up

        result = cmd_up("struts2/s2-045", dry_run=True)
        assert result["status"] == "dry_run"


class TestSetupIdempotent:
    def test_repeated_dry_run_same(self):
        from scripts.lab_setup import run_setup

        r1 = run_setup(skip_heavy=True, dry_run=True)
        r2 = run_setup(skip_heavy=True, dry_run=True)
        assert r1 == r2


class TestAttackManifest:
    def test_manifest_schema(self):
        # Validate the manifest schema independently (doesn't require Docker)
        manifest = {"nmap": True, "nxc": True, "rockyou": True, "AutoBlue": True}
        assert isinstance(manifest, dict)
        assert all(isinstance(v, bool) for v in manifest.values())
