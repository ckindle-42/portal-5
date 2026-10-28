"""Unit coverage for HY (fleet fallback rule): one oMLX checkpoint + one Ollama
GGUF fallback per model family, derived from the alias graph in backends.yaml.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validation import all_checks
from scripts.validation.inference import check_fleet_fallback_rule


def _run(tmp_path: Path, backends: list[dict]) -> tuple[str, str, list[dict]]:
    path = tmp_path / "backends.yaml"
    path.write_text(yaml.dump({"backends": backends}), encoding="utf-8")
    return check_fleet_fallback_rule(path)


def _omlx(models: list, aliases: dict | None = None, priority: int = 10) -> dict:
    return {
        "group": "general",
        "id": "omlx-general",
        "models": models,
        "priority": priority,
        "aliases": aliases or {},
        "type": "omlx",
        "url": "http://omlx",
    }


def _ollama(models: list) -> dict:
    return {
        "group": "general",
        "id": "ollama-general",
        "models": models,
        "type": "ollama",
        "url": "http://ollama",
    }


def test_registered_in_the_check_registry():
    slugs = {slug for slug, _label, _fn in all_checks()}
    assert "fleet_fallback_rule" in slugs


def test_clean_family_passes(tmp_path):
    status, detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m-ctx8k", "supports_tools": True}]),
            _omlx([{"id": "Fam-4bit", "supports_tools": True}], {"fam:q4_k_m-ctx8k": "Fam-4bit"}),
        ],
    )
    assert status == "PASS", detail
    assert subs == []


def test_ctx_variants_are_one_weights_tag(tmp_path):
    status, detail, _ = _run(
        tmp_path,
        [
            _ollama(
                [{"id": "fam:q4_k_m"}, {"id": "fam:q4_k_m-ctx8k"}, {"id": "fam:q4_k_m-ctx32k"}]
            ),
            _omlx(
                [{"id": "Fam-4bit"}],
                {"fam:q4_k_m-ctx8k": "Fam-4bit", "fam:q4_k_m-ctx32k": "Fam-4bit"},
            ),
        ],
    )
    assert status == "PASS", detail


def test_omlx_seat_without_fallback_warns(tmp_path):
    status, detail, subs = _run(tmp_path, [_omlx([{"id": "Orphan-4bit"}])])
    assert status == "WARN"
    assert "Orphan-4bit" in detail
    assert [s["name"] for s in subs] == ["Orphan-4bit"]
    assert "no Ollama GGUF fallback" in subs[0]["detail"]


def test_draft_helper_is_exempt(tmp_path):
    status, detail, _ = _run(tmp_path, [_omlx([{"id": "Fam-DFlash2"}, {"id": "Other-4bit-draft"}])])
    assert status == "PASS", detail


def test_two_omlx_checkpoints_in_one_family_warns(tmp_path):
    status, detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}],
                {"fam:q4_k_m-ctx8k": "Fam-4bit", "fam:q4_k_m-ctx16k": "Fam-oQ4e-mtp"},
            ),
        ],
    )
    assert status == "WARN"
    assert "2 oMLX checkpoints" in subs[0]["detail"]
    assert "Fam-4bit" in detail and "Fam-oQ4e-mtp" in detail


def test_two_gguf_weights_in_one_family_warns(tmp_path):
    status, _detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_k_m": "Fam-4bit", "fam:q8_0": "Fam-4bit"}),
        ],
    )
    assert status == "WARN"
    assert "2 distinct GGUF weights tags" in subs[0]["detail"]


def test_keep_reason_exempts_the_family(tmp_path):
    status, detail, _ = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m"}, {"id": "fam:q8_0"}]),
            _omlx(
                [{"id": "Fam-4bit"}],
                {"fam:q4_k_m": "Fam-4bit", "fam:q8_0": "Fam-4bit"},
            ),
        ],
    )
    assert status == "WARN", detail

    status, detail, _ = _run(
        tmp_path,
        [
            _ollama(
                [
                    {"id": "fam:q4_k_m"},
                    {"id": "fam:q8_0", "keep_reason": "A/B eval lane needs Q8"},
                ]
            ),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_k_m": "Fam-4bit", "fam:q8_0": "Fam-4bit"}),
        ],
    )
    assert status == "PASS", detail


def test_bare_string_model_entries_are_handled(tmp_path):
    status, detail, subs = _run(tmp_path, [_omlx(["Orphan-4bit"])])
    assert status == "WARN"
    assert subs[0]["name"] == "Orphan-4bit"
