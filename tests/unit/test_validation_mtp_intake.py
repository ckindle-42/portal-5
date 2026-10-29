"""Unit coverage for HZ (MTP intake rule): a qualifying dense/light-MoE oMLX
seat carries a Lightning MTP twin (-oQ4e-mtp), or documents its decline.

Eligibility is the proven twin profile — 24-32B total params, dense or MoE
with <=4B active (Qwen3.8-27B dense, Nemotron-3.5-Lightning-30B-A3B). The twin
replaces the plain build of its family unless ``keep_reason:`` (or
``mtp: none`` + ``mtp_reason:``) says why both stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.validation import all_checks
from scripts.validation.inference import _mtp_eligible, check_mtp_intake_rule


def _run(tmp_path: Path, backends: list[dict]) -> tuple[str, str, list[dict]]:
    path = tmp_path / "backends.yaml"
    path.write_text(yaml.dump({"backends": backends}), encoding="utf-8")
    return check_mtp_intake_rule(path)


def _omlx(models: list, aliases: dict | None = None) -> dict:
    return {
        "group": "general",
        "id": "omlx-general",
        "models": models,
        "priority": 10,
        "aliases": aliases or {},
        "type": "omlx",
        "url": "http://omlx",
    }


# ── eligibility ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("model_id", "eligible"),
    [
        # The proven twins: dense 27B and MoE 30B-A3B.
        ("Qwen3.8-27B-oQ4e-mtp", True),
        ("NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp", True),
        # Plain builds in the band.
        ("Fam-27B-4bit", True),
        ("Fam-24B-4bit", True),
        ("Fam-32B-4bit", True),
        ("Fam-30B-A3B-4bit", True),
        ("gemma-4-26b-a4b-it-QAT-4bit", True),
        # Outside the band, or no parseable size at all.
        ("DeepSeek-R1-0528-Qwen3-8B-4bit", False),
        ("Fam-8B-4bit", False),
        ("Fam-35B-A3B-4bit", False),
        ("Laguna-XS-2.1-4bit", False),
        # MoE with a heavy active backbone is not the proven profile.
        ("Fam-30B-A18B-4bit", False),
    ],
)
def test_eligibility_is_the_proven_profile(model_id: str, eligible: bool):
    assert _mtp_eligible(model_id) is eligible


# ── the check ────────────────────────────────────────────────────────────────
def test_registered_in_the_check_registry():
    slugs = {slug for slug, _label, _fn in all_checks()}
    assert "mtp_intake_rule" in slugs


@pytest.mark.parametrize(
    "model_id",
    ["Fam-27B-4bit", "Fam-30B-A3B-4bit"],  # dense and light-MoE both qualify
)
def test_qualifying_without_twin_warns(tmp_path, model_id):
    status, detail, subs = _run(tmp_path, [_omlx([{"id": model_id}])])
    assert status == "WARN"
    assert [s["name"] for s in subs] == [model_id]
    assert "without an MTP twin" in subs[0]["detail"]
    assert "mtp: none + mtp_reason" in subs[0]["detail"]


def test_family_served_by_the_twin_alone_passes(tmp_path):
    status, detail, subs = _run(tmp_path, [_omlx([{"id": "Fam-27B-oQ4e-mtp"}])])
    assert status == "PASS", detail
    assert subs == []


def test_mtp_none_with_reason_passes(tmp_path):
    entry = {"id": "Fam-27B-4bit", "mtp": "none", "mtp_reason": "upstream ships no mtp.* weights"}
    status, detail, subs = _run(tmp_path, [_omlx([entry])])
    assert status == "PASS", detail
    assert subs == []


def test_mtp_none_without_reason_warns(tmp_path):
    entry = {"id": "Fam-27B-4bit", "mtp": "none"}
    status, _detail, subs = _run(tmp_path, [_omlx([entry])])
    assert status == "WARN"
    assert "without a reason" in subs[0]["detail"]


def test_twin_replaces_the_plain_build(tmp_path):
    """Plain build kept beside its twin with no keep_reason is a WARN."""
    status, _detail, subs = _run(
        tmp_path, [_omlx([{"id": "Fam-27B-4bit"}, {"id": "Fam-27B-oQ4e-mtp"}])]
    )
    assert status == "WARN"
    assert [s["name"] for s in subs] == ["Fam-27B-4bit"]
    assert "should replace this plain build" in subs[0]["detail"]


def test_keep_reason_keeps_plain_build_beside_its_twin(tmp_path):
    """The Qwen3.8-27B DFlash2 seat shape: plain build + twin, documented."""
    entry = {"id": "Fam-27B-4bit", "keep_reason": "DFlash2 speculative-decoding seat"}
    status, detail, subs = _run(tmp_path, [_omlx([entry, {"id": "Fam-27B-oQ4e-mtp"}])])
    assert status == "PASS", detail
    assert subs == []


def test_twin_in_another_omlx_group_still_counts(tmp_path):
    """The twin serves from a sibling group; the family is fleet-wide."""
    plain = _omlx([{"id": "Fam-27B-4bit"}])
    twin = _omlx([{"id": "Fam-27B-oQ4e-mtp"}])
    twin["id"] = "omlx-other"
    status, _detail, subs = _run(tmp_path, [plain, twin])
    assert status == "WARN"
    assert [s["name"] for s in subs] == ["Fam-27B-4bit"]


@pytest.mark.parametrize(
    "model_id",
    [
        "Fam-8B-4bit",  # below the band
        "Fam-35B-A3B-4bit",  # above the band
        "Fam-DFlash2-27B",  # draft helper, not a served family of its own
        "Fam-27B-oQ4e-mtp",  # the twin itself
    ],
)
def test_exempt_entries_pass(tmp_path, model_id):
    status, detail, subs = _run(tmp_path, [_omlx([{"id": model_id}])])
    assert status == "PASS", detail
    assert subs == []
