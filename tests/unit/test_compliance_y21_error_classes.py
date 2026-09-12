"""Y21 — one regression case per adjudicated council error class.

`scripts/compliance_y21_adjudicate.py` classifies every seat-sweep disagreement
as extraction / bridge / gate / judgment. Six false-supported rows survived on
the SHIPPED roster (granite4.1:30b, mistral-small3.2:24b, Qwen3.8-27B); they
collapse to three distinct cases, and Y21's bar is that none of them stays
*unresolved*. Each is pinned here so a future prompt, gate or roster change that
reintroduces it fails a test rather than a bench run.

These are hermetic: they assert the CLASSIFIER and the shipped prompt contract,
not model output. Adjudication of the models themselves lives in the JSON record
next to the sweep (`y21_adjudication.json`).
"""

from __future__ import annotations

import importlib

adj = importlib.import_module("scripts.compliance_y21_adjudicate")
council = importlib.import_module("portal.modules.compliance.core.council")


def _row(**score):
    base = {
        "schema_ok": True,
        "correct": True,
        "citation_ok": True,
        "must_not_flag_fp": False,
        "false_supported": False,
    }
    base.update(score)
    return {"parsed": {"determination": "SUPPORTED"}, "score": base}


# ── the four causes are mutually exclusive and exhaustive ────────────────────


def test_clean_row_is_not_a_disagreement():
    assert adj.classify(_row()) is None


def test_unparseable_output_is_extraction_not_judgment():
    """A seat whose JSON never parsed tells you nothing about its reasoning —
    counting it as a judgment error inflates the ceiling with harness noise."""
    row = _row(schema_ok=False, correct=False)
    assert adj.classify(row) == "extraction"
    row2 = {"parsed": None, "score": {**_row()["score"], "correct": False}}
    assert adj.classify(row2) == "extraction"


def test_right_call_wrong_citation_is_bridge():
    """The determination is correct and only the reference failed: a vocabulary
    /mapping defect, fixable without touching the judge."""
    assert adj.classify(_row(citation_ok=False)) == "bridge"


def test_allowlist_violation_is_gate_even_when_label_is_right():
    """must_not_flag is the no-model gate's job. It outranks the label, because
    a correct determination that flags a forbidden standard is still a gate
    escape, not a good answer."""
    assert adj.classify(_row(must_not_flag_fp=True)) == "gate"
    assert adj.classify(_row(must_not_flag_fp=True, correct=False)) == "gate"


def test_wrong_label_with_clean_parse_and_citation_is_judgment():
    """The only class a better model fixes."""
    assert adj.classify(_row(correct=False, false_supported=True)) == "judgment"


# ── the three surviving false-supported cases, pinned by their mechanism ─────


def test_p6j12_class_stricter_direction_is_gate_computed_not_model_judged():
    """P6J-12 (mistral): asserted a one-year deadline was 'stricter than' a
    180-day maximum — backwards; 365 > 180 is more permissive. In the SHIPPED
    council this class is pre-empted: the gate hands the seat a candidate
    already marked MORE_RESTRICTIVE or EQUIVALENT, so direction is computed
    rather than reasoned. This test fails if that guarantee leaves the prompt."""
    s = council._SEAT_SYSTEM
    assert "MORE_RESTRICTIVE" in s and "EQUIVALENT" in s
    assert "stricter is never a violation" in s
    assert "constraint direction" in s


def test_p6j14_class_weak_mapping_remains_a_declarable_finding():
    """P6J-14 (2 seats): read 'monitors more frequently' as satisfying a duty
    the gold scored WEAK_MAPPING. A stricter *frequency* on a weakly-mapped
    *duty* is not satisfaction, so the seat must still be able to say so."""
    assert "WEAK_MAPPING" in council._SEAT_SYSTEM


def test_p6j19_outdated_language_has_a_stated_trigger():
    """P6J-19 is the one all three roster seats missed together, from three
    different lineages — a systematic blind spot, not a bad case. The packet
    stated the local term was 'last aligned to the glossary in 2019'; every seat
    read the alignment and dropped the date.

    Root cause found in adjudication: `_SEAT_SYSTEM` OFFERS OUTDATED_LANGUAGE as
    a finding_type but never says what triggers it, while every other rule in
    the prompt is spelled out. A finding type with no trigger is unreachable by
    construction. This test requires the trigger to be stated."""
    s = council._SEAT_SYSTEM
    assert "OUTDATED_LANGUAGE" in s, "finding type disappeared from the contract"

    # Look for a TRIGGER, not for the finding type's own name. The literal
    # "OUTDATED_LANGUAGE" token lowercases to contain "outdated", so searching
    # the whole prompt would pass on the enum alone — which is exactly the
    # defect. Search the RULES section only, with the enum line removed.
    rules = s.split("RULES:", 1)[-1].split("Return ONE JSON object", 1)[0].lower()
    assert any(
        k in rules for k in ("outdated", "stale", "no longer current", "last aligned", "superseded")
    ), (
        "OUTDATED_LANGUAGE is offered as a finding_type but the RULES never say "
        "what triggers it. That is the P6J-19 blind spot: all three roster seats "
        "read 'last aligned to the glossary in 2019' and dropped the date. Every "
        "other rule in this prompt is spelled out; give this one a rule too."
    )


# ── the ceilings themselves ──────────────────────────────────────────────────


def test_false_gap_ceiling_is_ten_percent():
    """Y21's bar, pinned so a change to the harness cannot quietly relax it."""
    rows = [
        {"score": {"pred": "PARTIAL"}, "gold_label": "SUPPORTED"},  # a false gap
        *[{"score": {"pred": "SUPPORTED"}, "gold_label": "SUPPORTED"} for _ in range(9)],
    ]
    fg = [
        r
        for r in rows
        if str(r["score"]["pred"]).upper() != "SUPPORTED"
        and str(r["gold_label"]).upper() == "SUPPORTED"
    ]
    assert len(fg) / len(rows) <= 0.10
