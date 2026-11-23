"""BW + settings_audit must parse colon-form :ctxNk tags as well as dash-form -ctxNk."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.validation import personas
from tests.wfe.settings_audit import ctx_from_tag


def _run_bw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspaces: dict) -> tuple[str, str]:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "portal.yaml").write_text("workspaces: {}\n", encoding="utf-8")
    (cfg / "bench_workspaces.yaml").write_text(
        yaml.safe_dump({"workspaces": workspaces}), encoding="utf-8"
    )
    monkeypatch.setattr(personas, "REPO_ROOT", tmp_path)
    status, detail, _subs = personas.check_eval_workspace_config_hygiene()
    return status, detail


def test_bw_colon_ctx_tag_with_context_limit_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, detail = _run_bw(
        tmp_path,
        monkeypatch,
        {
            "bench-seeded-colon": {
                "module": "eval",
                "model_hint": "inkling-2-mini:ctx256k",
                "context_limit": 262144,
                "ctx_validated": True,
            }
        },
    )
    assert status == "PASS", detail


def test_bw_dash_ctx_tag_with_context_limit_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, detail = _run_bw(
        tmp_path,
        monkeypatch,
        {
            "bench-seeded-dash": {
                "module": "eval",
                "model_hint": "granite4.1:30b-ctx96k",
                "context_limit": 98304,
                "ctx_validated": True,
            }
        },
    )
    assert status == "PASS", detail


def test_bw_colon_ctx_tag_without_ctx_validated_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, detail = _run_bw(
        tmp_path,
        monkeypatch,
        {
            "bench-seeded-colon-unvalidated": {
                "module": "eval",
                "model_hint": "inkling-2-mini:ctx256k",
            }
        },
    )
    assert status == "FAIL"
    assert "ctx_validated" in detail
    assert "bench-seeded-colon-unvalidated" in detail


def test_bw_context_limit_without_baked_ctx_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, detail = _run_bw(
        tmp_path,
        monkeypatch,
        {
            "bench-seeded-plain": {
                "module": "eval",
                "model_hint": "inkling-2-mini:latest",
                "context_limit": 262144,
            }
        },
    )
    assert status == "FAIL"
    assert "bench-seeded-plain" in detail


def test_bw_passes_on_head() -> None:
    status, detail, _subs = personas.check_eval_workspace_config_hygiene()
    assert status == "PASS", detail


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("inkling-2-mini:ctx256k", 262144),
        ("orcacyber-nano-1.0:ctx64k", 65536),
        ("granite4.1:30b-ctx96k", 98304),
        ("some-model-ctx32k", 32768),
        ("inkling-2-mini:CTX256K", 262144),
        ("inkling-2-mini:latest", None),
        ("some-model-ctx32k-extra", None),
    ],
)
def test_ctx_from_tag_parses_dash_and_colon_forms(tag: str, expected: int | None) -> None:
    assert ctx_from_tag(tag) == expected
