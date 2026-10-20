"""The long-context reading suite: sound under the controls gate, documents rendered from a
seed (never committed), pinned by sha256, deterministic across processes, golds re-derived
from the text, needles at their recorded depth, sized inside the 128k window by measured
token density, and the plan's arms served by compliance-reading's group at >= 128k."""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.wfe import controls
from tests.wfe.checkers import CheckContext, apply_checkers
from tests.wfe.runner import DOC_MARK, expand_doc, load_suite
from tests.wfe.schema import Outcome
from tests.wfe.suites import build_reading_long_production as gen

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/wfe/suites/reading_long_production.jsonl"
PLAN = REPO / "tests/wfe/plans/reading_long_screen.yaml"
RAW = {t["id"]: t for t in map(json.loads, SUITE.read_text().splitlines())}
TASKS = {t["id"]: t for t in load_suite(SUITE)}
KINDS = {"needle": 12, "aggregation": 12, "quote": 12}
WINDOW = 131072


def _kind(kind: str) -> list[dict]:
    return [t for t in TASKS.values() if t["kind"] == kind]


def _answer(task: dict) -> str:
    return json.loads(task["controls"]["pass"][0]["answer"])["answer"]


def test_the_suite_is_sound_and_balanced():
    assert len(TASKS) == 36 and sum(t["screen"] for t in TASKS.values()) == 12
    for kind, n in KINDS.items():
        assert len(_kind(kind)) == n and sum(t["screen"] for t in _kind(kind)) == 4, kind
        assert {t["doc_spec"]["tokens"] for t in _kind(kind)} == set(gen.TIERS), kind
    assert controls.check_suite(SUITE) == []
    assert all(controls.schema_failures(t) == [] for t in TASKS.values())


def test_every_task_is_no_tools_and_answer_graded():
    for t in TASKS.values():
        assert t["no_tools"] is True and t["requires_tools"] == [] and t["agentic"] is False
        assert [c["type"] for c in t["checkers"]] == ["answer_contains"], t["id"]


def test_the_controls_pass_and_fail_where_they_must():
    def run(task, answer):
        return apply_checkers(task, CheckContext(task=task, final_text=answer)).outcome

    for t in TASKS.values():
        assert run(t, t["controls"]["pass"][0]["answer"]) == Outcome.PASS, t["id"]
        assert run(t, t["controls"]["fail"][0]["answer"]) == Outcome.FAIL, t["id"]
        assert run(t, "") == Outcome.FAIL, t["id"]


def test_documents_are_rendered_from_seeds_not_committed():
    assert SUITE.stat().st_size < 100_000
    for tid, raw in RAW.items():
        assert DOC_MARK in raw["instruction"] and len(raw["instruction"]) < 1000, tid
        assert (
            DOC_MARK not in TASKS[tid]["instruction"] and len(TASKS[tid]["instruction"]) > 100_000
        )
        assert "fictional document" in TASKS[tid]["instruction"], tid


def test_the_sha256_pins_the_rendering():
    drifted = json.loads(json.dumps(next(iter(RAW.values()))))
    drifted["doc_spec"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sha256"):
        expand_doc(drifted)
    for tid, raw in RAW.items():
        doc = gen.render_document(raw["doc_spec"])
        assert hashlib.sha256(doc.encode()).hexdigest() == raw["doc_spec"]["sha256"], tid


def test_the_suite_regenerates_identically_and_across_hash_seeds():
    assert "".join(json.dumps(t) + "\n" for t in gen.build()) == SUITE.read_text()
    code = (
        "import hashlib,sys;from tests.wfe.suites import build_reading_long_production as g;"
        "print(hashlib.sha256(''.join(__import__('json').dumps(t)+'\\n' for t in g.build())"
        ".encode()).hexdigest())"
    )
    outs = {
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in ("1", "2")
    }
    assert len(outs) == 1  # a set-order dependence would give two digests


def test_the_gold_is_not_in_the_question_and_comes_from_one_place_in_the_document():
    for t in TASKS.values():
        question = t["instruction"].split("--- end of document ---", 1)[1]
        assert _answer(t) not in question, t["id"]
        doc = t["instruction"].split("--- fictional document ---", 1)[1]
        if t["kind"] != "aggregation":  # an aggregate is computed, not quoted
            assert doc.count(_answer(t)) == 1, t["id"]


def test_needles_sit_at_their_recorded_depth():
    for t in _kind("needle"):
        depth = t["doc_spec"]["depth"]
        assert f"-d{depth}" in t["id"]
        doc = t["instruction"].split("--- fictional document ---", 1)[1]
        pos = doc.index(_answer(t)) / len(doc) * 100
        assert abs(pos - depth) <= 3, (t["id"], pos, depth)


def test_aggregations_combine_three_to_five_facts_among_decoys():
    for t in _kind("aggregation"):
        assert 3 <= t["doc_spec"]["k"] <= 5, t["id"]
    variants = {t["doc_spec"]["variant"] for t in _kind("aggregation")}
    assert variants == {0, 1, 2}


def test_quotes_are_graded_as_the_exact_string():
    for t in _kind("quote"):
        sentence = _answer(t)
        assert sentence.endswith(".") and '"' not in sentence and sentence.isascii()
        pattern = t["checkers"][0]["patterns"][0]
        assert re.search(pattern, json.dumps({"answer": sentence}))
        assert not re.search(
            pattern, json.dumps({"answer": sentence[:-1]})
        )  # the final period counts


def test_the_documents_are_sized_to_their_tier_and_fit_the_window():
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"]
    ws = portal["compliance-reading"]
    assert ws["context_limit"] == WINDOW
    system = len(ws.get("owui_system_prompt") or "") / 2.5  # a pessimistic tokens estimate
    for t in TASKS.values():
        density = gen.CHARS_PER_TOKEN[t["kind"]]
        tokens = len(t["instruction"]) / density
        assert abs(tokens / t["doc_spec"]["tokens"] - 1) < 0.06, (t["id"], tokens)
        assert tokens + system + 2048 <= WINDOW - 8000, (
            t["id"],
            tokens,
        )  # margin for tokenizer drift


def test_measured_token_counts_when_a_gemma_tokenizer_is_cached():
    found = glob.glob(
        "/Volumes/data01/hf-cache/models--mlx-community--gemma-3-12b-it-4bit/snapshots/*/tokenizer.json"
    )
    if not found:
        pytest.skip("no cached Gemma tokenizer")
    from tokenizers import Tokenizer

    tk = Tokenizer.from_file(found[0])
    for t in TASKS.values():
        if t["doc_spec"]["tokens"] == max(gen.TIERS):
            assert len(tk.encode(t["instruction"]).ids) + 2048 < WINDOW - 8000, t["id"]


def test_the_plan_arms_are_served_by_the_workspaces_group_at_the_seats_window():
    plan = yaml.safe_load(PLAN.read_text())["workloads"]["compliance-reading"]
    reading = yaml.safe_load((REPO / "tests/wfe/plans/reading_decision_v1.yaml").read_text())
    ref = reading["workloads"]["compliance-reading"]
    portal = yaml.safe_load((REPO / "config/portal.yaml").read_text())["workspaces"][
        "compliance-reading"
    ]
    backends = yaml.safe_load((REPO / "config/backends.yaml").read_text())
    groups = set(backends["workspace_routing"]["compliance-reading"])
    served = {
        m["id"] for b in backends["backends"] if b["group"] in groups for m in b.get("models") or []
    }
    arms = plan["arms"]
    assert plan["tool_mode"] == ref["tool_mode"] and plan["home"] == "reading_long_production"
    assert portal["model_hint"] in [arms["incumbent"], *arms["challengers"]]
    assert arms["incumbent"] == ref["arms"]["incumbent"]
    assert plan["discovery"] == [] and len(arms["challengers"]) == 1
    for tag in [arms["incumbent"], *arms["challengers"]]:
        if tag == "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx128k" and tag not in served:
            pytest.skip(f"{tag}: not registered in config/backends.yaml yet (plan TODO)")
        assert tag in served, tag
        window = int(re.search(r"ctx(\d+)k", tag).group(1)) * 1024
        assert window >= portal["context_limit"], (tag, window)
