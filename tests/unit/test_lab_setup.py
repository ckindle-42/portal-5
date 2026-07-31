"""Unit tests for lab setup / readiness / targets (dry-run/synthetic — no Docker/network)."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace


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
    def test_manifest_is_required(self):
        from scripts.lab_ready import CHECKS

        assert CHECKS["attack_manifest"]["required"] is True

    def test_current_complete_manifest_is_green(self, monkeypatch):
        from scripts import lab_ready

        contract = lab_ready.REPO_ROOT / "config" / "attack_image_contract.json"
        manifest = {
            "contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
            "ready": True,
            "tools": {"nmap": True},
            "files": {"rockyou": True},
        }
        monkeypatch.setattr(
            "subprocess.run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout=json.dumps(manifest), stderr=""
            ),
        )
        assert lab_ready._check_attack_manifest() == "GREEN"

    def test_stale_or_incomplete_manifest_is_red(self, monkeypatch):
        from scripts import lab_ready

        stale = {
            "contract_sha256": "stale",
            "ready": True,
            "tools": {"nmap": True},
            "files": {},
        }
        monkeypatch.setattr(
            "subprocess.run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout=json.dumps(stale), stderr=""
            ),
        )
        assert lab_ready._check_attack_manifest() == "RED"

    def test_contract_verifier_reports_missing_requirement(self, tmp_path):
        from scripts.verify_attack_image import verify

        present = tmp_path / "present"
        present.write_text("ok")
        contract = tmp_path / "contract.json"
        contract.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "lab-exercise",
                    "tools": ["python3", "definitely-not-a-real-command"],
                    "files": [str(present), str(tmp_path / "missing")],
                }
            )
        )
        result = verify(contract)
        assert result["ready"] is False
        assert result["tools"]["definitely-not-a-real-command"] is False
        assert result["files"][str(tmp_path / "missing")] is False
