"""Unit tests for CI/local parity — guards the gap that forced fix-churn after every push."""

from __future__ import annotations

import os
from pathlib import Path


class TestCiParity:
    def test_pythonpath_config_present(self):
        """pyproject.toml has pythonpath including tests/benchmarks."""
        import tomllib

        cfg = (Path(__file__).parents[2] / "pyproject.toml").read_text()
        data = tomllib.loads(cfg)
        pp = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("pythonpath", [])
        assert "tests/benchmarks" in pp, f"pythonpath missing tests/benchmarks: {pp}"
        assert "." in pp, f"pythonpath missing '.': {pp}"

    def test_conftest_sets_lab_defaults(self):
        """conftest.py sets LAB_* + SANDBOX_LAB_EXEC setdefaults."""
        conftest = (Path(__file__).parents[1] / "conftest.py").read_text()
        assert "LAB_TARGET_DC" in conftest, "conftest must set LAB_TARGET_DC"
        assert "LAB_TARGET_SRV" in conftest, "conftest must set LAB_TARGET_SRV"
        assert "SANDBOX_LAB_EXEC" in conftest, "conftest must set SANDBOX_LAB_EXEC"
        assert "setdefault" in conftest, "conftest must use setdefault for .env override"

    def test_bench_imports_without_pythonpath(self):
        """Representative bench import succeeds via pyproject.toml pythonpath."""
        # Verify pyproject.toml pythonpath config is correct (pytest injects it at collection)
        import tomllib

        cfg = (Path(__file__).parents[2] / "pyproject.toml").read_text()
        data = tomllib.loads(cfg)
        pp = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("pythonpath", [])
        assert "tests/benchmarks" in pp, f"pythonpath missing tests/benchmarks: {pp}"

        # The import itself: verify the module resolves (pytest's pythonpath injection
        # puts tests/benchmarks on sys.path at collection time, so this works in CI too)
        from portal.modules.security.core import matrix  # noqa: F401

        assert matrix is not None

    def test_ci_local_sh_exists_and_executable(self):
        """scripts/ci_local.sh exists and is executable."""
        ci_sh = Path(__file__).parents[2] / "scripts" / "ci_local.sh"
        assert ci_sh.exists(), f"{ci_sh} does not exist"
        assert os.access(ci_sh, os.X_OK), f"{ci_sh} is not executable"

    def test_ci_local_sh_mirrors_workflow(self):
        """ci_local.sh mirrors the CI workflow's key commands."""
        ci_sh = (Path(__file__).parents[2] / "scripts" / "ci_local.sh").read_text()
        assert "pip install -e" in ci_sh, "ci_local.sh must run editable install"
        assert "tests/unit" in ci_sh, "ci_local.sh must run tests/unit"
        assert "env -i" in ci_sh, "ci_local.sh must use clean env (env -i)"
        assert "ruff" in ci_sh, "ci_local.sh must run ruff"
