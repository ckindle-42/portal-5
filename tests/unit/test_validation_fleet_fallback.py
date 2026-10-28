"""Unit coverage for HY (fleet fallback rule): one oMLX checkpoint + one Ollama
GGUF fallback per model *family*.

A family is the union of two relations — the `aliases:` graph (GGUF hint → oMLX
checkpoint, i.e. the fallback path itself) and the normalised lineage key of the
id, so quant/format variants that were never aliased are still one model.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.validation import all_checks
from scripts.validation.inference import (
    _lineage_key,
    _weights_tag,
    check_fleet_fallback_rule,
)


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


def _family_findings(subs: list[dict]) -> list[dict]:
    return [s for s in subs if "no Ollama GGUF fallback" not in s["detail"]]


# ── lineage tokeniser ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("left", "right"),
    [
        # One model, two Ollama tags (plain q4 vs QAT).
        ("gemma4:26b-a4b-it-q4_K_M", "gemma4:26b-a4b-it-qat"),
        # The operator's example: one oMLX seat's two checkpoints.
        ("gemma-4-26b-a4b-it-QAT-4bit", "mlx-community--gemma-4-26b-a4b-it-4bit"),
        # MLX build vs hf.co GGUF repo with ctx tag and org prefix.
        ("unsloth--Qwen3.6-27B-UD-MLX-4bit", "qwen3.6:27b-q4_K_M-ctx16k"),
        # Plain Ollama size tag vs HF-style instruct/8bit name.
        ("llama3.2:3b", "Llama-3.2-3B-Instruct-8bit"),
        # mxfp8 format suffix vs plain size tag.
        ("granite-4.1-8b-mxfp8", "granite4.1:8b"),
        # Namespace-less vs namespaced tag.
        ("omnicoder2:9b-q4_k_m", "portal5/omnicoder2-9b:q4_K_M"),
        # :latest is the same weights; case is not identity.
        ("devstral-small-2", "devstral-small-2:latest"),
        ("VulnLLM-7b", "vulnllm-7B"),
    ],
)
def test_variants_of_one_model_share_a_lineage(left: str, right: str):
    assert _lineage_key(left) == _lineage_key(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # abliterated / uncensored / heretic / distill builds are other models.
        ("gemma-4-26b-a4b-it-4bit", "gemma-4-26B-A4B-it-heretic-GGUF:Q4_K_M"),
        (
            "gemma-4-26B-A4B-it-heretic-GGUF:Q4_K_M",
            "gemma-4-26B-A4B-it-uncensored-heretic-GGUF:Q4_K_M",
        ),
        ("gemma-4-26b-a4b-it-4bit", "gemma-4-26b-a4b-it-distill-4bit"),
        # Different release of the same size class.
        ("huihui_ai/qwen3.5-abliterated:9b", "huihui_ai/qwen3.6-abliterated:27b"),
        # Different size / different family entirely.
        ("Qwen3.8-27B-oQ4e-mtp", "Qwen3.6-35B-A3B-UD-MLX-4bit"),
        ("deepseek-r1:32b-q4_k_m", "DeepSeek-R1-0528-Qwen3-8B-4bit"),
        ("gemma4:12b-it-qat", "gemma4:26b-a4b-it-qat"),
    ],
)
def test_distinct_models_keep_distinct_lineages(left: str, right: str):
    assert _lineage_key(left) != _lineage_key(right)


def test_weights_tag_collapses_ctx_latest_and_case():
    assert _weights_tag("fam:q4_k_m-ctx8k") == _weights_tag("fam:q4_k_m")
    assert _weights_tag("Devstral-Small-2:latest") == _weights_tag("devstral-small-2")
    assert _weights_tag("fam:q4_k_m-ctx32k") != _weights_tag("fam:q8_0")


# ── the check ────────────────────────────────────────────────────────────────
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


def test_lineage_twin_without_alias_still_warns_no_fallback(tmp_path):
    """Family grouping is for bloat; the alias is the actual fallback path."""
    status, _detail, subs = _run(
        tmp_path,
        [_ollama([{"id": "fam:q4_k_m"}]), _omlx([{"id": "Fam-4bit"}])],
    )
    assert status == "WARN"
    assert [s["name"] for s in subs] == ["Fam-4bit"]
    assert subs[0]["detail"] == "oMLX seat has no Ollama GGUF fallback"


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
    assert _family_findings(subs)[0]["detail"] == ("2 oMLX checkpoints: Fam-4bit, Fam-oQ4e-mtp")
    assert "Fam-4bit" in detail


def test_two_gguf_weights_in_one_family_warns(tmp_path):
    status, _detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m"}, {"id": "fam:q8_0"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_k_m": "Fam-4bit", "fam:q8_0": "Fam-4bit"}),
        ],
    )
    assert status == "WARN"
    assert _family_findings(subs)[0]["detail"] == "2 GGUF weights tags: fam:q4_k_m, fam:q8_0"


def test_reported_weights_tag_is_the_registered_id(tmp_path):
    """A ctx-capped tag keeps its suffix: the worklist must name real config ids."""
    status, _detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q8_0-ctx8k"}, {"id": "fam:q4_k_m"}]),
            _omlx([{"id": "Fam-4bit"}], {"fam:q4_k_m": "Fam-4bit", "fam:q8_0-ctx8k": "Fam-4bit"}),
        ],
    )
    assert status == "WARN"
    assert _family_findings(subs)[0]["detail"] == "2 GGUF weights tags: fam:q4_k_m, fam:q8_0-ctx8k"


def test_unaliased_quant_variants_land_in_one_family(tmp_path):
    """The operator's example, with no alias edges at all (lineage only)."""
    status, _detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "gemma4:26b-a4b-it-q4_K_M"}, {"id": "gemma4:26b-a4b-it-qat"}]),
            _omlx(
                [
                    {"id": "gemma-4-26b-a4b-it-QAT-4bit"},
                    {"id": "mlx-community--gemma-4-26b-a4b-it-4bit"},
                ]
            ),
        ],
    )
    assert status == "WARN"
    findings = _family_findings(subs)
    assert len(findings) == 1
    assert findings[0]["detail"] == (
        "2 oMLX checkpoints: gemma-4-26b-a4b-it-QAT-4bit, "
        "mlx-community--gemma-4-26b-a4b-it-4bit; "
        "2 GGUF weights tags: gemma4:26b-a4b-it-q4_K_M, gemma4:26b-a4b-it-qat"
    )


def test_heretic_build_is_its_own_family(tmp_path):
    status, detail, subs = _run(
        tmp_path,
        [_ollama([{"id": "fam:4bit"}, {"id": "fam-heretic:4bit"}])],
    )
    assert status == "PASS", detail
    assert subs == []


def test_keep_reason_exempts_only_its_own_entry(tmp_path):
    """Two variants, one marked: the family is compliant."""
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


def test_keep_reason_does_not_exempt_the_whole_family(tmp_path):
    """Three variants, one marked: the remaining two still WARN."""
    status, _detail, subs = _run(
        tmp_path,
        [
            _ollama(
                [
                    {"id": "fam:q4_k_m"},
                    {"id": "fam:q5_k_m"},
                    {"id": "fam:q8_0", "keep_reason": "A/B eval lane needs Q8"},
                ]
            ),
            _omlx(
                [{"id": "Fam-4bit"}],
                dict.fromkeys(("fam:q4_k_m", "fam:q5_k_m", "fam:q8_0"), "Fam-4bit"),
            ),
        ],
    )
    assert status == "WARN"
    findings = _family_findings(subs)
    assert len(findings) == 1
    assert findings[0]["detail"] == "2 GGUF weights tags: fam:q4_k_m, fam:q5_k_m"
    assert "fam:q8_0" not in findings[0]["detail"]


def test_keep_reason_exempts_only_its_own_checkpoint(tmp_path):
    status, detail, _ = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m"}]),
            _omlx(
                [{"id": "Fam-4bit"}, {"id": "Fam-oQ4e-mtp"}],
                {"fam:q4_k_m": "Fam-4bit", "fam:q4_k_m-ctx16k": "Fam-oQ4e-mtp"},
            ),
        ],
    )
    assert status == "WARN", detail

    status, detail, subs = _run(
        tmp_path,
        [
            _ollama([{"id": "fam:q4_k_m"}]),
            _omlx(
                [
                    {"id": "Fam-4bit", "keep_reason": "only oQ4e variant is benchmarked"},
                    {"id": "Fam-oQ4e-mtp"},
                ],
                {"fam:q4_k_m": "Fam-4bit", "fam:q4_k_m-ctx16k": "Fam-oQ4e-mtp"},
            ),
        ],
    )
    assert status == "PASS", detail
    assert subs == []


def test_bare_string_model_entries_are_handled(tmp_path):
    status, _detail, subs = _run(tmp_path, [_omlx(["Orphan-4bit"])])
    assert status == "WARN"
    assert subs[0]["name"] == "Orphan-4bit"
