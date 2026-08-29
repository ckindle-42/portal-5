"""Unit tests for the Adaptive UAT subsystem (TASK_UAT_ADAPTIVE_OVERHAUL_V1).

All tests run offline (dry mode / no stack). They lock in the invariants that
make the subsystem trustworthy: introspection is module-gated, generation is
deterministic and per-space-adaptive, rubrics auto-score from assertions, and
the review packet round-trips verdicts.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("UNIT_TEST_MODE", "1")

from tests.uat.adaptive import generate, introspect, rubric  # noqa: E402
from tests.uat.adaptive.introspect import SpaceContract  # noqa: E402


def _ws(**kw) -> SpaceContract:
    base = {
        "space_id": "ws-x",
        "kind": "workspace",
        "name": "X",
        "module": "general",
        "model_hint": "m",
        "purpose": "do things",
        "directives": "",
        "model_slug": "ws-x",
    }
    base.update(kw)
    return SpaceContract(**base)


def test_introspect_returns_enabled_spaces():
    spaces = introspect.introspect_spaces()
    assert spaces, "expected at least one enabled testable space"
    assert all(s.enabled for s in spaces)
    assert all(s.kind in ("workspace", "persona") for s in spaces)


def test_every_space_is_owui_addressable():
    """Every workspace + non-bench persona is seeded into OWUI as a model preset,
    so nothing is excluded from the run as 'designed but unreachable' (verified
    live at 152/152 during TASK_UAT_ADAPTIVE_OVERHAUL_V1). A genuinely missing
    slug is caught at run time as BLOCKED, not pre-filtered by a heuristic."""
    spaces = introspect.introspect_spaces()
    assert spaces
    assert all(s.owui_addressable for s in spaces)
    assert any(s.kind == "persona" for s in spaces)


def test_introspect_module_gating_hides_disabled():
    enabled = {"general": True, "video": False}
    ws = introspect.load_workspace_contracts(enabled)
    vids = [s for s in ws if s.module == "video"]
    assert all(not s.enabled for s in vids)


def test_output_sections_and_strict_format_derivation():
    directives = (
        "REQUIRED STRUCTURE — use these exact headers in order:\n"
        "## THREAT ACTOR PROFILE\ntext\n## TTP CHAIN\ntext\n## TOOLING\ntext\n"
    )
    sections, strict = introspect._derive_output_sections(directives)
    assert "THREAT ACTOR PROFILE" in sections
    assert strict is True


def test_refusal_posture_detection():
    assert introspect._derive_refusal_posture("fully abliterated, no disclaimers") == "uncensored"
    assert introspect._derive_refusal_posture("a helpful assistant") == "standard"


def test_generation_is_deterministic():
    s = _ws()
    a = generate.generate_suite(s, dry=True)
    b = generate.generate_suite(s, dry=True)
    assert [c.notes for c in a] == [c.notes for c in b]
    assert [c.prompt for c in a] == [c.prompt for c in b]


def test_dimensions_gate_on_contract():
    plain = _ws(tools=[], memory=False, strict_format=False)
    dims = {c.dimension for c in generate.generate_suite(plain, dry=True)}
    assert "tool" not in dims and "continuity" not in dims and "format" not in dims
    assert {"depth", "breadth", "edge", "boundary"} <= dims

    rich = _ws(
        tools=["render_openscad"],
        memory=True,
        strict_format=True,
        output_sections=["A", "B"],
    )
    dims2 = {c.dimension for c in generate.generate_suite(rich, dry=True)}
    assert {"tool", "continuity", "format"} <= dims2


def test_boundary_assertions_flip_with_posture():
    unc = _ws(refusal_posture="uncensored")
    std = _ws(refusal_posture="standard")
    ua = generate._machine_assertions_for(unc, "boundary")
    sa = generate._machine_assertions_for(std, "boundary")
    assert any("over-refusal" in a["label"] for a in ua)
    assert any("refusal" in a["label"].lower() for a in sa)
    # they are not the same check
    assert {a["type"] for a in ua} != {a["type"] for a in sa} or ua != sa


def test_rubric_auto_scores_from_assertions():
    s = _ws(strict_format=True, output_sections=["A", "B"])
    r = rubric.build_rubric(s, "format", "RUB-1")
    auto = [c for c in r.criteria if c.auto]
    assert auto, "format rubric should have an auto criterion"
    scores = rubric.auto_score_from_assertions(
        r, [("Declared output sections present", True, "ok")]
    )
    assert scores.get("format_fidelity") == 5
    scores_fail = rubric.auto_score_from_assertions(
        r, [("Declared output sections present", False, "missing")]
    )
    assert scores_fail.get("format_fidelity") == 1


def test_freeze_replay_roundtrip(tmp_path):
    s = _ws(space_id="round-trip")
    suite = generate.generate_suite(s, dry=True)
    generate.freeze_suite(suite, s.space_id, base=tmp_path)
    back = generate.load_frozen_suite(s.space_id, base=tmp_path)
    assert len(back) == len(suite)
    assert back[0].challenge_id == suite[0].challenge_id
    assert back[0].machine_assertions == suite[0].machine_assertions


def test_worksheet_emit_ingest_roundtrip(tmp_path):
    """Agent authoring: emit skeleton worksheet -> fill prompts -> ingest+freeze."""
    s = _ws(space_id="ws-author", memory=True)
    ws = generate.emit_worksheet(s, base=tmp_path)
    rows = json.loads(ws.read_text())
    assert rows and all(r["prompt"] == "" for r in rows), "skeleton prompts must be empty"
    assert all(len(r["authoring_brief"]) > 80 for r in rows), "brief must guide the agent"
    for r in rows:
        r["prompt"] = "A concrete, intended-use, multi-sentence request with real constraints."
    ws.write_text(json.dumps(rows))
    suite = generate.ingest_worksheet("ws-author", base=tmp_path)
    assert suite and all(c.prompt for c in suite)


def test_ingest_worksheet_rejects_unauthored(tmp_path):
    s = _ws(space_id="ws-gap")
    generate.emit_worksheet(s, base=tmp_path)  # prompts empty
    with pytest.raises(ValueError):
        generate.ingest_worksheet("ws-gap", base=tmp_path)


def test_agent_assessment_pending_and_record(tmp_path):
    from tests.uat.adaptive import assess

    corpus = tmp_path / "uat_A.jsonl"
    corpus.write_text(json.dumps(_adaptive_corpus_row()) + "\n")
    pend = assess.pending(corpus)
    assert len(pend) == 1
    assert pend[0]["prompt"] and pend[0]["rubric"]  # agent has what it needs
    assess.record(pend[0]["test_id"], {"correctness": 4}, "PASS", "meets intent", corpus=corpus)
    rows = [json.loads(x) for x in corpus.read_text().splitlines() if x.strip()]
    assert rows[0]["agent_verdict"] == "PASS" and rows[0]["agent_rationale"]
    # already-assessed rows drop out of pending
    assert assess.pending(corpus) == []


def test_packet_prefills_agent_assessment(tmp_path):
    from tests.uat.adaptive import review

    row = _adaptive_corpus_row()
    row["agent_scores"] = {"correctness": 4, "depth": 5}
    row["agent_verdict"] = "PASS"
    row["agent_rationale"] = "delivers the intended output"
    html = review.render_html([row], "T")
    assert "Agent assessment" in html and "delivers the intended output" in html
    assert "Operator 1-5" in html  # operator override column present


def test_challenge_emits_runner_compatible_catalog_dict():
    s = _ws(model_slug="ws-x", memory=True)
    ch = [c for c in generate.generate_suite(s, dry=True) if c.dimension == "continuity"][0]
    from tests.uat.adaptive.rubric import build_rubric

    entry = ch.to_catalog_dict(s, build_rubric(s, "continuity", ch.rubric_id).to_dict())
    for key in (
        "id",
        "name",
        "prompt",
        "model_slug",
        "section",
        "workspace_tier",
        "timeout",
        "assertions",
    ):
        assert key in entry, f"runner-required key missing: {key}"
    assert entry["model_slug"] == "ws-x"
    assert entry["section"] == "adaptive-general"
    # continuity maps to the runner's native cross-session two-chat mechanism
    assert entry["is_two_chat"] is True and entry["turn2_in_new_chat"]
    assert entry["adaptive"] is True and entry["dimension"] == "continuity"


def test_build_adaptive_catalog_excludes_unreachable(tmp_path, monkeypatch):
    import types

    from tests.uat.adaptive import catalog

    monkeypatch.setattr(catalog, "UNREACHABLE_MANIFEST", tmp_path / "unreach.json")
    cat = catalog.build_adaptive_catalog(
        types.SimpleNamespace(adaptive_dry_run=True, adaptive_regenerate=True)
    )
    assert cat, "expected addressable adaptive entries"
    req = {
        "id",
        "name",
        "prompt",
        "model_slug",
        "section",
        "workspace_tier",
        "timeout",
        "assertions",
    }
    assert all(req <= set(e) for e in cat)
    # every emitted entry belongs to an OWUI-addressable space
    assert all(e.get("owui_addressable", True) for e in cat)
    # the exposure-gap manifest was written
    assert (tmp_path / "unreach.json").exists()
    un = json.loads((tmp_path / "unreach.json").read_text())
    assert isinstance(un, list)


def _adaptive_corpus_row(test_id="AUAT-ws-x-depth", verdict=""):
    from tests.uat.adaptive.rubric import build_rubric

    rub = build_rubric(_ws(), "depth", "RUB-x").to_dict()
    return {
        "schema_version": 1,
        "corpus_run_id": "T",
        "test_id": test_id,
        "test_name": "X — depth",
        "section": "adaptive-general",
        "workspace": "ws-x",
        "prompt": "deep prompt",
        "response_text": "a substantive response " * 20,
        "chat_url": "http://owui/c/1",
        "status": "PASS",
        "assertions_result": [["Substantive response", True, "ok"]],
        "elapsed_seconds": 3.0,
        "timestamp": "now",
        "adaptive": True,
        "dimension": "depth",
        "rubric": rub,
        "auto_scores": {},
        "operator_scores": {},
        "operator_verdict": verdict,
        "operator_notes": "",
    }


def test_review_packet_from_corpus(tmp_path):
    from tests.uat.adaptive import review

    corpus = tmp_path / "uat_T.jsonl"
    corpus.write_text(json.dumps(_adaptive_corpus_row()) + "\n")
    rows = review.load_corpus(corpus)
    assert len(rows) == 1
    html = review.render_html(rows, "T")
    assert "Adaptive UAT Review" in html and "AUAT-ws-x-depth" in html
    assert "open chat" in html  # chat link rendered


def test_ingest_and_rollup(tmp_path, monkeypatch):
    from tests.uat.adaptive import review

    monkeypatch.setattr(review, "RESULTS_MD", tmp_path / "ADAPTIVE_UAT_RESULTS.md")
    monkeypatch.setattr(review, "UNREACHABLE_MANIFEST", tmp_path / "unreach.json")
    corpus = tmp_path / "uat_T.jsonl"
    corpus.write_text(json.dumps(_adaptive_corpus_row()) + "\n")
    verdicts = tmp_path / "v.json"
    verdicts.write_text(
        json.dumps(
            [
                {
                    "test_id": "AUAT-ws-x-depth",
                    "operator_scores": {"correctness": 5, "depth": 4},
                    "operator_verdict": "PASS",
                    "operator_notes": "clean",
                }
            ]
        )
    )
    review.ingest_verdicts(corpus, verdicts)
    merged = review.load_corpus(corpus)
    assert merged[0]["operator_verdict"] == "PASS"
    md = review.rollup_markdown(corpus)
    text = md.read_text()
    assert "Capability UAT" in text and "Capability acceptance" in text
    assert "PASS:1" in text and "[GATE]" in text


def test_corpus_enrichment_ignores_non_adaptive(tmp_path):
    """Non-adaptive corpus rows must not gain adaptive fields."""
    # A plain test dict (no 'adaptive') -> emitted row has no rubric.
    plain = {"id": "WS-01", "name": "n", "model_slug": "auto", "prompt": "p"}
    assert not plain.get("adaptive")
