"""Unit tests for lab setup / readiness / targets (dry-run/synthetic — no Docker/network)."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import yaml


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
    def test_ready_runs_without_crash(self, monkeypatch):
        from scripts.lab_ready import run_readiness

        # Hermetic per this module's docstring: every probe fails fast instead
        # of reaching real Docker/ssh/lab hosts, and the harness must still
        # return a well-formed verdict over the whole check registry.
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""),
        )

        def _unreachable(*a, **k):
            raise OSError("unit tests do not probe the lab")

        monkeypatch.setattr("socket.socket.connect", _unreachable)
        passed, results = run_readiness()
        assert isinstance(passed, bool)
        assert len(results) >= 5

    def test_ready_has_required_checks(self):
        from scripts.lab_ready import CHECKS

        assert any(c["required"] for c in CHECKS.values())

    def test_port_probe_uses_pid1_safe_netcat(self, monkeypatch):
        from scripts import lab_ready

        observed = {}

        def fake_run(args, **kwargs):
            observed["args"] = args
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        assert lab_ready._check_port_reachable("10.10.11.21", 445) == "GREEN"
        assert observed["args"][-6:] == ["nc", "-z", "-w", "3", "10.10.11.21", "445"]


class TestChallengeDirsCheck:
    """_check_challenge_dirs must verify what it claims (2026-11-07: empty
    placeholder dirs scored GREEN). GREEN = every declared purpose-built class
    has a dir with a compose file; AMBER with the count when some; RED with the
    missing names when none. Hermetic: synthetic config + LAB_DIR."""

    @staticmethod
    def _config(tmp_path, entries):
        cfg = tmp_path / "config"
        cfg.mkdir(exist_ok=True)
        classes = [{"id": cid, "purpose_built": pb} for cid, pb in entries]
        (cfg / "challenge_classes.yaml").write_text(yaml.safe_dump({"classes": classes}))

    def _patch(self, monkeypatch, tmp_path):
        from scripts import lab_ready

        self._config(tmp_path, self.ENTRIES)
        monkeypatch.setattr(lab_ready, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(lab_ready, "LAB_DIR", str(tmp_path / "lab"))
        return lab_ready

    def _materialise(self, tmp_path, rel, compose="docker-compose.yml"):
        base = tmp_path / "lab" / "challenges" / rel
        base.mkdir(parents=True)
        (base / compose).write_text("services: {}\n")

    ENTRIES = [("alpha", "challenges/alpha/"), ("beta", "meta3/beta/")]

    def test_green_when_all_declared_composes_exist(self, monkeypatch, tmp_path):
        lab_ready = self._patch(monkeypatch, tmp_path)
        self._materialise(tmp_path, "challenges/alpha/")
        self._materialise(tmp_path, "meta3/beta/")
        assert lab_ready._check_challenge_dirs() == "GREEN"

    def test_compose_dot_yaml_also_counts(self, monkeypatch, tmp_path):
        lab_ready = self._patch(monkeypatch, tmp_path)
        self._materialise(tmp_path, "challenges/alpha/", compose="compose.yaml")
        self._materialise(tmp_path, "meta3/beta/")
        assert lab_ready._check_challenge_dirs() == "GREEN"

    def test_empty_placeholder_dirs_are_not_green(self, monkeypatch, tmp_path):
        lab_ready = self._patch(monkeypatch, tmp_path)
        (tmp_path / "lab" / "challenges" / "challenges" / "alpha").mkdir(parents=True)
        (tmp_path / "lab" / "challenges" / "meta3" / "beta").mkdir(parents=True)
        assert lab_ready._check_challenge_dirs() == "RED"
        assert "alpha" in lab_ready.CHECKS["challenge_dirs"]["desc"]

    def test_amber_reports_count_when_some_materialised(self, monkeypatch, tmp_path):
        lab_ready = self._patch(monkeypatch, tmp_path)
        self._materialise(tmp_path, "challenges/alpha/")
        assert lab_ready._check_challenge_dirs() == "AMBER"
        assert "1/2" in lab_ready.CHECKS["challenge_dirs"]["desc"]

    def test_red_lists_missing_names_when_none_materialised(self, monkeypatch, tmp_path):
        lab_ready = self._patch(monkeypatch, tmp_path)
        assert lab_ready._check_challenge_dirs() == "RED"
        desc = lab_ready.CHECKS["challenge_dirs"]["desc"]
        assert "alpha" in desc and "beta" in desc

    def test_real_config_declares_purpose_built(self):
        from scripts import lab_ready

        declared = lab_ready._declared_purpose_built()
        assert len(declared) >= 1
        assert all(rel for _, rel in declared)


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

    def test_contract_verifier_executes_runtime_smoke_checks(self, tmp_path):
        from scripts.verify_attack_image import verify

        contract = tmp_path / "contract.json"
        contract.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "lab-exercise",
                    "tools": ["python3"],
                    "files": [],
                    "runtime_checks": {
                        "python3 --version": "Python",
                        "python3 -c 'print(123)'": "not-present",
                    },
                }
            )
        )
        result = verify(contract)
        assert result["runtime_checks"]["python3 --version"] is True
        assert result["runtime_checks"]["python3 -c 'print(123)'"] is False
        assert result["ready"] is False

    def test_contract_verifier_rejects_empty_required_file(self, tmp_path):
        from scripts.verify_attack_image import verify

        empty = tmp_path / "empty.jar"
        empty.touch()
        contract = tmp_path / "contract.json"
        contract.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "lab-exercise",
                    "tools": ["python3"],
                    "files": [str(empty)],
                }
            )
        )
        result = verify(contract)
        assert result["files"][str(empty)] is False
        assert result["ready"] is False
