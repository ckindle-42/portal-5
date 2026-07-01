"""Unit tests for loop-driven validation (synthetic/dry-run)."""

from __future__ import annotations

from tests.benchmarks.bench_security.validation import validate_usecase


class TestValidateUsecase:
    def test_dry_run_plans_usecase(self):
        usecase = {
            "name": "test-usecase",
            "target": "10.10.11.50",
            "cve": "CVE-2021-44228",
            "red_models": ["model-a"],
            "blue_models": ["model-b"],
            "hardened_twin": {"method": "image_tag", "value": "patched"},
        }
        result = validate_usecase(usecase, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["usecase"] == "test-usecase"

    def test_no_lab_exec_indeterminate(self, monkeypatch):
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.validation._LAB_EXEC_AVAILABLE", False
        )
        result = validate_usecase({"name": "test"})
        assert result["status"] == "indeterminate"
