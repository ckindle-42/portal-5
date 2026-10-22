"""Regression tests for seat screening's card-conformance audit rows."""

import json
import textwrap
from pathlib import Path

import pytest

from tests.wfe import settings_audit as audit


def _card() -> dict:
    return {
        "qwen3.8": {
            "harness_policy": {"think": "false"},
            "recommended_sampling_modes": {
                "thinking": {"temperature": 1.0, "top_p": 0.95, "top_k": 20},
                "instruct": {"temperature": 0.7, "top_p": 0.8, "top_k": 20},
            },
            "recommended_max_output": 32768,
        }
    }


def test_think_policy_mismatch_warns_without_a_variant_override() -> None:
    rows: list[dict] = []

    audit._audit_think_vs_card_policy(
        "seat", {"think": True}, "qwen3.8-test", _card(), {"seat": {}}, rows
    )

    assert [(row["kind"], row["severity"]) for row in rows] == [("think_vs_card_policy", "WARN")]


def test_reasoned_variant_think_override_is_info() -> None:
    workspaces = {
        "seat": {"variants": {"think-on": {"think": True, "think_override_reason": "screen arm"}}}
    }
    rows: list[dict] = []

    audit._audit_think_vs_card_policy(
        "seat::think-on", {"think": True}, "qwen3.8-test", _card(), workspaces, rows
    )

    assert [(row["kind"], row["severity"]) for row in rows] == [("think_vs_card_policy", "INFO")]


def test_sampling_mode_mismatch_warns_for_the_opposite_think_mode() -> None:
    rows: list[dict] = []

    audit._audit_sampling_mode_mismatch(
        "seat",
        {"think": True, "temperature": 0.7, "top_p": 0.8, "top_k": 20},
        "qwen3.8-test",
        {},
        _card(),
        rows,
    )

    assert [(row["kind"], row["severity"]) for row in rows] == [("sampling_mode_mismatch", "WARN")]
    assert "instruct" in rows[0]["detail"]


def test_sampling_mode_matching_think_setting_is_clean() -> None:
    rows: list[dict] = []

    audit._audit_sampling_mode_mismatch(
        "seat",
        {"think": False, "temperature": 0.7, "top_p": 0.8, "top_k": 20},
        "qwen3.8-test",
        {},
        _card(),
        rows,
    )

    assert rows == []


def test_think_true_without_predict_limit_warns_when_card_has_output_budget() -> None:
    rows: list[dict] = []

    audit._audit_thinking_unbounded("seat", {"think": True}, "qwen3.8-test", _card(), rows)

    assert [(row["kind"], row["severity"]) for row in rows] == [("thinking_unbounded", "WARN")]
    assert "predict_limit" in rows[0]["detail"]


def test_explicit_predict_limit_or_missing_card_budget_is_clean() -> None:
    rows: list[dict] = []
    registry = _card()

    audit._audit_thinking_unbounded(
        "seat", {"think": True, "predict_limit": 32768}, "qwen3.8-test", registry, rows
    )
    audit._audit_thinking_unbounded("other", {"think": True}, "uncatalogued-model", registry, rows)

    assert rows == []


def test_thinking_budget_bounds_thinking_without_predict_limit() -> None:
    rows: list[dict] = []

    audit._audit_thinking_unbounded(
        "seat", {"think": True, "thinking_budget": 8192}, "qwen3.8-test", _card(), rows
    )

    assert rows == []


def test_emits_reasoning_true_with_think_false_warns() -> None:
    rows: list[dict] = []

    audit._audit_emits_reasoning_think("seat", {"think": False, "emits_reasoning": True}, rows)

    assert [(row["kind"], row["severity"]) for row in rows] == [
        ("emits_reasoning_without_think", "WARN")
    ]


def test_emits_reasoning_consistent_or_absent_is_clean() -> None:
    rows: list[dict] = []

    audit._audit_emits_reasoning_think("a", {"think": True, "emits_reasoning": True}, rows)
    audit._audit_emits_reasoning_think("b", {"think": False, "emits_reasoning": False}, rows)
    audit._audit_emits_reasoning_think("c", {"think": False}, rows)

    assert rows == []


def _store(tmp_path: Path, params: str) -> Path:
    root = tmp_path / "ollama"
    manifest = root / "manifests" / "registry.ollama.ai" / "library" / "qwen3.8-test" / "latest"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    (root / "blobs").mkdir(exist_ok=True)
    digest = "a" * 64
    manifest.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.params",
                        "digest": f"sha256:{digest}",
                    }
                ]
            }
        )
    )
    (root / "blobs" / f"sha256-{digest}").write_text(params)
    return root


def test_baked_params_from_store_reads_the_local_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _store(tmp_path, '{"temperature": 1.0, "top_k": 20, "top_p": 0.95}')
    monkeypatch.setenv("OLLAMA_MODELS", str(root))

    assert audit.baked_params_from_store("qwen3.8-test") == {
        "temperature": 1.0,
        "top_k": 20,
        "top_p": 0.95,
    }
    assert audit.baked_params_from_store("absent-model") == {}


def _partial_seat_repo(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "portal.yaml").write_text(
        textwrap.dedent(
            """\
            workspaces:
              seat:
                module: coding
                name: Partial seat
                description: declares three sampling keys, omits the rest
                model_hint: qwen3.8-test
                think: true
                temperature: 0.7
                top_p: 0.8
                top_k: 20
            """
        )
    )
    (config / "model_card_expectations.yaml").write_text(
        textwrap.dedent(
            """\
            models:
              qwen3.8:
                status: verified-card
                recommended_sampling_modes:
                  thinking: {temperature: 1.0, top_p: 0.95, top_k: 20, min_p: 0.0, presence_penalty: 0.0, repeat_penalty: 1.0}
                  instruct: {temperature: 0.7, top_p: 0.8, top_k: 20, min_p: 0.0, presence_penalty: 1.5, repeat_penalty: 1.0}
            """
        )
    )
    (config / "backends.yaml").write_text("backends: []\n")


def test_config_only_audit_fills_store_defaults_for_a_partial_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _partial_seat_repo(tmp_path)
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-store"))

    without_store = audit.audit_config_seats(repo=tmp_path, workspace_ids=["seat"])

    assert without_store["violations"] == []
    _store(tmp_path, '{"min_p": 0.0, "presence_penalty": 1.5, "repeat_penalty": 1.0}')
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "ollama"))

    with_store = audit.audit_config_seats(repo=tmp_path, workspace_ids=["seat"])

    assert [(row["kind"], row["severity"]) for row in with_store["violations"]] == [
        ("sampling_mode_mismatch", "WARN")
    ]
    assert "instruct" in with_store["violations"][0]["detail"]
