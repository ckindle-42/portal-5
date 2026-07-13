"""Unit tests for candidate-eval incumbent resolution fix.

Verifies:
- _get_incumbent_model resolves real fleet model from portal.yaml (not hardcoded)
- single-slot _build_step_models yields no empty model
- fail-loud guard fires when incumbent unresolvable and no --incumbent
- --incumbent override still works and takes precedence
- solo mode unaffected
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from portal.modules.security.core.candidate_eval import (
    _SLOT_TO_WORKSPACE,
    _build_step_models,
    _get_incumbent_model,
)

# ── Incumbent resolution ─────────────────────────────────────────────────────


class TestGetIncumbentModel:
    """_get_incumbent_model must resolve from portal.yaml, not return empty."""

    def test_exploit_resolves_real_model(self):
        """exploit slot should resolve to a real model from portal.yaml."""
        model = _get_incumbent_model("exploit")
        assert model, "exploit incumbent is empty — resolution broken"
        # Should look like an Ollama model tag (contains : or /)
        assert ":" in model or "/" in model, f"unexpected model format: {model}"

    def test_recon_resolves_real_model(self):
        model = _get_incumbent_model("recon")
        assert model, "recon incumbent is empty"

    def test_post_resolves_real_model(self):
        model = _get_incumbent_model("post")
        assert model, "post incumbent is empty"

    def test_solo_returns_empty(self):
        """solo slot has no incumbent mapping — returns empty (expected)."""
        model = _get_incumbent_model("solo")
        assert model == "" or _SLOT_TO_WORKSPACE.get("solo") is None

    def test_reads_from_portal_yaml(self):
        """Must read from portal.yaml, not return a hardcoded string."""
        # Mock portal.yaml to return a known model. "exploit" resolves via
        # ("auto-security", "pentest") post-collapse (BUILD_PROGRAM_COLLAPSE_V1
        # Phase 6 folded auto-pentest into auto-security's variants).
        mock_data = {
            "workspaces": {
                "auto-security": {
                    "variants": {
                        "pentest": {"model_hint": "test-model:latest"},
                    }
                },
            }
        }
        with patch(
            "portal.modules.security.core.candidate_eval.yaml.safe_load",
            return_value=mock_data,
        ):
            model = _get_incumbent_model("exploit")
            assert model == "test-model:latest"

    def test_returns_empty_on_missing_yaml(self):
        """Returns empty when portal.yaml can't be read."""
        with patch(
            "portal.modules.security.core.candidate_eval._PORTAL_YAML",
            Path("/nonexistent/portal.yaml"),
        ):
            model = _get_incumbent_model("exploit")
            assert model == ""

    def test_returns_empty_on_missing_workspace(self):
        """Returns empty when workspace not in portal.yaml."""
        mock_data = {"workspaces": {}}
        with patch(
            "portal.modules.security.core.candidate_eval.yaml.safe_load",
            return_value=mock_data,
        ):
            model = _get_incumbent_model("exploit")
            assert model == ""

    def test_not_hardcoded(self):
        """The returned model should match what's actually in portal.yaml."""
        portal_yaml = Path(__file__).resolve().parents[4] / "config" / "portal.yaml"
        data = yaml.safe_load(portal_yaml.read_text())
        workspace, variant = _SLOT_TO_WORKSPACE.get("exploit", ("", None))
        ws_cfg = data.get("workspaces", {}).get(workspace, {})
        if variant is None:
            expected = ws_cfg.get("model_hint", "")
        else:
            expected = ws_cfg.get("variants", {}).get(variant, {}).get("model_hint", "")
        actual = _get_incumbent_model("exploit")
        assert actual == expected, f"expected {expected!r}, got {actual!r}"


# ── No empty model in step_models ─────────────────────────────────────────────


class TestBuildStepModelsNoEmpty:
    """step_models must never contain an empty-string model."""

    def test_exploit_slot_no_empty(self):
        incumbent = _get_incumbent_model("exploit")
        assert incumbent, "incumbent must resolve for this test"
        sm = _build_step_models("exploit", "candidate-model", incumbent)
        for key, val in sm.items():
            assert val, f"step_models[{key!r}] is empty"

    def test_recon_slot_no_empty(self):
        incumbent = _get_incumbent_model("recon")
        assert incumbent
        sm = _build_step_models("recon", "candidate-model", incumbent)
        for key, val in sm.items():
            assert val, f"step_models[{key!r}] is empty"

    def test_post_slot_no_empty(self):
        incumbent = _get_incumbent_model("post")
        assert incumbent
        sm = _build_step_models("post", "candidate-model", incumbent)
        for key, val in sm.items():
            assert val, f"step_models[{key!r}] is empty"

    def test_solo_no_empty(self):
        sm = _build_step_models("solo", "candidate-model", "whatever")
        for key, val in sm.items():
            assert val, f"step_models[{key!r}] is empty"


# ── Fail-loud guard ──────────────────────────────────────────────────────────


class TestFailLoudGuard:
    """When incumbent can't be resolved and no --incumbent, fail loud."""

    def test_fail_loud_on_unresolvable(self):
        """candidate_eval_main should exit 1 when incumbent unresolvable."""
        from portal.modules.security.core.candidate_eval import candidate_eval_main

        with patch(
            "portal.modules.security.core.candidate_eval._get_incumbent_model",
            return_value="",
        ):
            rc = candidate_eval_main(
                [
                    "--candidate",
                    "test-model",
                    "--slot",
                    "exploit",
                    "--dry-run",
                ]
            )
            assert rc == 1, "should fail loud on unresolvable incumbent"

    def test_override_bypasses_resolution(self):
        """--incumbent override should work even when resolution returns empty."""
        from portal.modules.security.core.candidate_eval import candidate_eval_main

        with patch(
            "portal.modules.security.core.candidate_eval._get_incumbent_model",
            return_value="",
        ):
            rc = candidate_eval_main(
                [
                    "--candidate",
                    "test-model",
                    "--slot",
                    "exploit",
                    "--incumbent",
                    "override-model:latest",
                    "--dry-run",
                ]
            )
            assert rc == 0, "--incumbent override should succeed"

    def test_solo_needs_no_incumbent(self):
        """solo mode should work without any incumbent resolution."""
        from portal.modules.security.core.candidate_eval import candidate_eval_main

        rc = candidate_eval_main(
            [
                "--candidate",
                "test-model",
                "--slot",
                "solo",
                "--dry-run",
            ]
        )
        assert rc == 0, "solo mode should not need incumbent"
