"""READING_TRUTH_V1 - the offline instruments: blinding, the key, judgments, HJ."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
TRUTH = REPO / "scripts" / "compliance" / "truth"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


corpus = _load("truth_corpus", TRUTH / "truth_corpus.py")
answer_key = _load("answer_key", TRUTH / "answer_key.py")
judgments = _load("judgments", TRUTH / "judgments.py")


def _run_dir(tmp: pathlib.Path) -> pathlib.Path:
    run = tmp / "reports" / "compliance" / "era1" / "product"
    (run / "transcripts").mkdir(parents=True)
    rows = [
        {
            "standard": "CIP-007-6",
            "key": "coverage_gap",
            "question": "Q-cov",
            "verdict": "FAIL",
            "checks": {"answered": True, "cited_something": False},
        },
        {
            "standard": "CIP-007-6",
            "key": "exceedance",
            "question": "Q-exc",
            "verdict": "PASS",
            "checks": {"answered": True, "cited_something": True},
        },
    ]
    (run / "product_questions_family.json").write_text(
        json.dumps(
            {"run_id": "2026-09-27T02:56:55+00:00", "n_questions": 2, "n_passed": 1, "rows": rows}
        )
    )
    (run / "transcripts" / "CIP-007-6__coverage_gap.json").write_text(
        json.dumps(
            {
                "answer": 'Covered by "the procedure" [cite O-xxxxxx] and [cite R-xxxxxx]',
                "tool_calls": {"compliance_context": 2.0},
                "served_model": "m1",
                "http_status": 200,
            }
        )
    )
    (run / "transcripts" / "CIP-007-6__exceedance.json").write_text(
        json.dumps(
            {
                "question": "Q-exc",
                "answer": "",
                "tool_calls": {"compliance_read": 1},
                "http_status": 500,
            }
        )
    )
    return run


def test_provenance_row_counts_what_the_run_did(tmp_path):
    row = corpus.provenance_row(_run_dir(tmp_path), with_git=False)
    assert row["suite"] == "product"
    assert row["grader_signature"] == "answered+cited_something"
    assert row["verdict_basis"] == "mechanical"
    assert row["placeholder_tokens"] == 2
    assert row["quoted_spans"] == 1
    assert row["empty_answers"] == 1 and row["non_200"] == 1
    assert row["tool_calls"] == {"compliance_context": 2.0, "compliance_read": 1.0}


def test_queue_is_blind_and_resolves_questions(tmp_path):
    items, unblind = corpus.build_queue([_run_dir(tmp_path)], salt="s1")
    assert {tuple(sorted(i)) for i in items} == {("answer", "item_id", "question", "question_id")}
    by_q = {i["question_id"]: i for i in items}
    assert by_q["product:CIP-007-6:coverage_gap"]["question"] == "Q-cov"
    meta = unblind[by_q["product:CIP-007-6:exceedance"]["item_id"]]
    assert meta["mechanical_verdict"] == "PASS" and meta["answer_empty"] is True
    again, _ = corpus.build_queue([_run_dir(tmp_path / "x")], salt="s2")
    assert {i["item_id"] for i in again}.isdisjoint({i["item_id"] for i in items})


def test_queue_split_filter_keeps_one_split_and_names_unkeyed(tmp_path):
    items, unblind = corpus.build_queue([_run_dir(tmp_path)], salt="s1")
    key = _key()
    for entry in key["entries"]:
        entry["split"] = "dev" if entry["question_id"].endswith("coverage_gap") else "holdout"
    key_path = tmp_path / "key.yaml"
    key_path.write_text(yaml.safe_dump(key))
    kept, kept_unblind, unkeyed = corpus.split_filter(items, unblind, key_path, "dev")
    assert {i["question_id"] for i in kept} == {"product:CIP-007-6:coverage_gap"}
    assert set(kept_unblind) == {i["item_id"] for i in kept}
    keyed = {e["question_id"] for e in key["entries"]}
    assert unkeyed == sorted({i["question_id"] for i in items} - keyed)


def test_store_guard_names_changed_tables():
    provenance = _load("provenance", TRUTH / "provenance.py")
    guard = provenance.store_guard({"a": {"n": 1}, "b": {"n": 2}}, {"a": {"n": 1}, "b": {"n": 3}})
    assert guard["changed"] == ["b"]


def test_queue_refuses_public_output(tmp_path):
    code = corpus.main(
        [
            "queue",
            "--root",
            str(tmp_path),
            "--salt",
            "s",
            "--out",
            str(REPO / "reports" / "compliance" / "_never"),
        ]
    )
    assert code == 2
    assert not (REPO / "reports" / "compliance" / "_never").exists()


def _key() -> dict:
    return {
        "key_version": 1,
        "status": "IN_PROGRESS",
        "store_snapshot": {"db_sha256": "abc"},
        "entries": [
            {
                "question_id": "product:CIP-007-6:coverage_gap",
                "suite": "product",
                "question": "Q-cov",
                "confidence": "high",
                "governing": [
                    {"ref": "CIP-007-6 R2 Part 2.2", "section_id": "csection-1", "text": "35 days"}
                ],
                "operator_evidence": [{"section_id": "isection-9", "text": "thirty-five (35)"}],
                "facts": [
                    {
                        "id": "F1",
                        "statement": "2.2 covered by 3.3.1",
                        "required": True,
                        "evidence": ["csection-1", "isection-9"],
                    },
                    {
                        "id": "F2",
                        "statement": "no Part uncovered",
                        "required": True,
                        "kind": "absence",
                    },
                    {
                        "id": "F3",
                        "statement": "optional nuance",
                        "required": False,
                        "evidence": ["isection-9"],
                    },
                ],
                "traps": [{"id": "T1", "statement": "VA cadence treated as relevant"}],
            },
            {
                "question_id": "acceptance:interval",
                "suite": "acceptance",
                "question": "Q-int",
                "confidence": "medium",
                "governing": [
                    {"ref": "CIP-007-6 R2 Part 2.2", "section_id": "csection-1", "text": "35 days"}
                ],
                "facts": [{"id": "F1", "statement": "x", "evidence": ["csection-1"]}],
            },
        ],
    }


def test_key_validates_and_catches_structural_errors():
    assert answer_key.validate(_key()) == []
    bad = _key()
    bad["entries"][0]["facts"][0]["evidence"] = ["isection-unlisted"]
    bad["entries"][1]["question_id"] = "product:dup"
    errors = answer_key.validate(bad)
    assert any("not in governing/operator_evidence" in e for e in errors)
    assert any("must start with 'acceptance:'" in e for e in errors)


def test_split_is_stable_and_acceptance_is_always_holdout():
    key = _key()
    answer_key.assign_split(key, 0.34)
    first = [e["split"] for e in key["entries"]]
    assert key["entries"][1]["split"] == "holdout"
    assert answer_key.assign_split(key, 0.99) == []
    assert [e["split"] for e in key["entries"]] == first


def test_manifest_carries_no_text():
    key = _key()
    answer_key.assign_split(key, 0.34)
    body = json.dumps(answer_key.manifest(key, yaml.safe_dump(key).encode()))
    assert "thirty-five" not in body and "35 days" not in body and "Q-cov" not in body


def _rec(item: str, pas: str, facts: dict, **extra) -> dict:
    return {
        "item_id": item,
        "pass": pas,
        "question_id": "product:CIP-007-6:coverage_gap",
        "facts": facts,
        **extra,
    }


def test_overall_is_derived_by_one_rule():
    entry = judgments.key_entries(_key())["product:CIP-007-6:coverage_gap"]
    ok = {"F1": "correct", "F2": "correct", "F3": "omitted"}
    assert judgments.derive_overall(_rec("i", "A", ok), entry) == "CORRECT"
    assert judgments.derive_overall(_rec("i", "A", {**ok, "F2": "omitted"}), entry) == "PARTIAL"
    assert judgments.derive_overall(_rec("i", "A", {**ok, "F3": "wrong"}), entry) == "WRONG"
    assert judgments.derive_overall(_rec("i", "A", ok, traps_hit=["T1"]), entry) == "WRONG"
    claims = [{"text": "Part 2.4 uncovered", "verdict": "incorrect"}]
    assert judgments.derive_overall(_rec("i", "A", ok, absence_claims=claims), entry) == "WRONG"
    assert judgments.derive_overall(_rec("i", "A", {}, non_answer=True), entry) == "NON_ANSWER"


def test_validate_demands_every_fact_and_known_traps():
    entries = judgments.key_entries(_key())
    errors = judgments.validate([_rec("i", "A", {"F1": "correct"}, traps_hit=["T9"])], entries)
    assert any("facts must judge exactly" in e for e in errors)
    assert any("traps_hit not in the key entry" in e for e in errors)


def test_aggregate_reports_agreement_and_mechanical_confusion():
    entries = judgments.key_entries(_key())
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    records = [
        _rec("i1", "A", ok),
        _rec("i1", "B", ok),
        _rec("i2", "A", {**ok, "F1": "wrong"}),
        _rec("i2", "B", {**ok, "F2": "omitted"}),
    ]
    unblind = {
        "i1": {"run_dir": "r", "suite": "product", "mechanical_verdict": "FAIL"},
        "i2": {"run_dir": "r", "suite": "product", "mechanical_verdict": "PASS"},
    }
    result = judgments.aggregate(records, unblind, entries)
    assert result["overall"]["counts"]["CORRECT"] == 1 and result["overall"]["counts"]["WRONG"] == 1
    assert result["mechanical_vs_judged"] == {
        "mechanical_FAIL__judged_CORRECT": 1,
        "mechanical_PASS__judged_WRONG": 1,
    }
    assert result["agreement"]["n_double_judged"] == 2 and result["agreement"]["disagreements"] == [
        "i2"
    ]


def test_compare_applies_the_predeclared_keep_rules():
    key = _key()
    key["entries"][0]["split"] = "dev"
    entries = judgments.key_entries(key)
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    wrong = {**ok, "F1": "wrong"}
    records = [_rec(f"b{n}", "A", ok) for n in range(6)] + [
        _rec(f"a{n}", "A", wrong if n < 2 else ok) for n in range(6)
    ]
    unblind = {
        **{f"b{n}": {"run_dir": f"p6/B0/rep{n}"} for n in range(6)},
        **{f"a{n}": {"run_dir": f"p6/B1/rep{n}"} for n in range(6)},
    }
    result = judgments.compare(records, unblind, entries, ["p6/B0"], ["p6/B1"])
    assert result["regressions"] == ["product:CIP-007-6:coverage_gap"]
    assert result["keep_if_truth_fix"] is False and result["keep_if_optimisation"] is False


def test_compare_p6m_one_wrong_rep_is_not_a_regression():
    """The legacy rule tripped on one WRONG rep — on identical A3 answers judged
    in two rounds it did so in 3 of 12 null comparisons. P6M needs two."""
    key = _key()
    key["entries"][0]["split"] = "dev"
    entries = judgments.key_entries(key)
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    records = [_rec(f"b{n}", "A", ok) for n in range(6)] + [
        _rec(f"a{n}", "A", {**ok, "F1": "wrong"} if n == 0 else ok) for n in range(6)
    ]
    unblind = {
        **{f"b{n}": {"run_dir": f"p6/B0/rep{n}"} for n in range(6)},
        **{f"a{n}": {"run_dir": f"p6/B1/rep{n}"} for n in range(6)},
    }
    result = judgments.compare(records, unblind, entries, ["p6/B0"], ["p6/B1"])
    assert result["regressions"] == []
    assert result["legacy_any_wrong_trips"] == ["product:CIP-007-6:coverage_gap"]
    assert result["keep_if_truth_fix"] is True


def test_compare_p6m_unstable_baseline_cannot_regress_and_short_reps_cannot_keep():
    key = _key()
    key["entries"][0]["split"] = "dev"
    entries = judgments.key_entries(key)
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    part = {**ok, "F2": "omitted"}
    wrong = {**ok, "F1": "wrong"}
    # baseline C C P P C C (two non-CORRECT) is not stable-correct
    records = [_rec(f"b{n}", "A", part if n in (2, 3) else ok) for n in range(6)] + [
        _rec(f"a{n}", "A", wrong if n < 3 else ok) for n in range(6)
    ]
    unblind = {
        **{f"b{n}": {"run_dir": f"p6/B0/rep{n}"} for n in range(6)},
        **{f"a{n}": {"run_dir": f"p6/B1/rep{n}"} for n in range(6)},
    }
    result = judgments.compare(records, unblind, entries, ["p6/B0"], ["p6/B1"])
    assert result["regressions"] == [] and result["insufficient_reps"] == []
    three = judgments.compare(records[:3] + records[6:9], unblind, entries, ["p6/B0"], ["p6/B1"])
    assert three["insufficient_reps"] == ["product:CIP-007-6:coverage_gap"]
    assert three["keep_if_truth_fix"] is False


def test_wilson_and_kappa_edges():
    assert judgments.wilson(0, 0) == (0.0, 0.0)
    low, high = judgments.wilson(5, 10)
    assert 0.2 < low < 0.5 < high < 0.8
    assert judgments.cohen_kappa([("CORRECT", "CORRECT")]) == 1.0


def test_hj_audits_only_post_cutoff_receipts(tmp_path):
    # Through the package, never by path: once A8 registers HJ, a second exec of the
    # module would register its slug twice (the registry refuses duplicates).
    from scripts.validation import compliance_truth as check

    root = tmp_path / "r"
    (root / "old").mkdir(parents=True)
    (root / "new").mkdir()
    (root / "old" / "conversational_proof.json").write_text(
        json.dumps({"run_id": "2026-09-01T00:00:00+00:00"})
    )
    (root / "new" / "conversational_proof.json").write_text(
        json.dumps({"run_id": "2026-10-01T00:00:00+00:00"})
    )
    status, _, findings = check.audit((root,), "2026-09-28T00:00:00+00:00")
    assert status == "FAIL" and len(findings) == 1 and "new" in findings[0]["receipt"]
    good = {
        "run_id": "2026-10-01T00:00:00+00:00",
        "verdict_basis": "mechanical",
        "provenance": {"git_head": "abc", "workspace_settings": {}},
    }
    (root / "new" / "conversational_proof.json").write_text(json.dumps(good))
    assert check.audit((root,), "2026-09-28T00:00:00+00:00")[0] == "PASS"
    judged = {**good, "verdict_basis": "judged"}
    (root / "new" / "conversational_proof.json").write_text(json.dumps(judged))
    assert check.audit((root,), "2026-09-28T00:00:00+00:00")[0] == "FAIL"


@pytest.mark.parametrize(
    "module", ["truth_corpus.py", "answer_key.py", "judgments.py", "provenance.py"]
)
def test_truth_scripts_have_no_prompt_side_imports(module):
    """The instruments measure the reading; nothing here may feed a prompt."""
    text = (TRUTH / module).read_text()
    for forbidden in (
        "reading_material.render(",
        "system_prompt_append =",
        "record_determination(",
    ):
        assert forbidden not in text


def test_interpretations_are_decided_not_deferred():
    key = _key()
    entry = key["entries"][0]
    entry["interpretations"] = [
        {
            "id": "I1",
            "question": "does a policy restatement cover 2.2?",
            "readings": ["yes", "no"],
            "chosen": 1,
            "rationale": "the Measures ask for evidence of the practice",
            "sources": ["csection-1"],
        }
    ]
    assert answer_key.validate(key) == []
    entry["interpretations"][0]["chosen"] = None
    assert any("chosen index" in e for e in answer_key.validate(key))
    entry["interpretations"][0].update({"chosen": 0, "rationale": ""})
    assert any("rationale and sources" in e for e in answer_key.validate(key))


def test_finished_key_records_its_search_space_and_part_coverage():
    key = _key()
    key["status"] = "AGENT_FINAL"
    assert any("documents_considered" in e for e in answer_key.validate(key))
    key["documents_considered"] = {"CIP-007-6": [{"document": "d", "in_scope": True, "why": "w"}]}
    key["entries"][0]["facts"][0].update({"part": "CIP-007-6 R2 Part 2.2", "coverage": "covered"})
    assert answer_key.validate(key) == []
    key["entries"][0]["facts"][0]["coverage"] = "mostly"
    assert any("coverage must be one of" in e for e in answer_key.validate(key))


def test_run_names_are_relative_to_their_root(tmp_path):
    run = _run_dir(tmp_path)
    root = tmp_path / "reports" / "compliance"
    items, unblind = corpus.build_queue([run], salt="s", roots=(root,))
    assert {u["run"] for u in unblind.values()} == {"era1/product"}


def test_every_output_refuses_the_public_tree(tmp_path):
    public = REPO / "reports" / "compliance" / "_never"
    assert (
        corpus.main(["provenance", "--root", str(tmp_path), "--out", str(public), "--no-git"]) == 2
    )
    key_path = tmp_path / "key.yaml"
    key_path.write_text(yaml.safe_dump(_key()))
    assert answer_key.main(["manifest", str(key_path), "--out", str(public / "m.json")]) == 2
    empty = tmp_path / "judgments.jsonl"
    empty.write_text("")
    code = judgments.main(
        [
            "aggregate",
            "--key",
            str(key_path),
            "--judgments",
            str(empty),
            "--out",
            str(public / "a.json"),
        ]
    )
    assert code == 2
    assert not public.exists()
    assert answer_key.main(["manifest", str(key_path), "--out", str(tmp_path / "m.json")]) == 0


def test_compare_counts_pass_c_records_in_a_final_set():
    """A final set is A with C substituted; a bare pass=="A" filter dropped
    exactly the contested items pass C settled and hid a keep-rule trip (A6)."""
    key = _key()
    key["entries"][0]["split"] = "dev"
    entries = judgments.key_entries(key)
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    wrong = {**ok, "F1": "wrong"}
    records = (
        [_rec(f"b{n}", "A", ok) for n in range(6)]
        + [_rec(f"a{n}", "A", ok) for n in range(4)]
        + [_rec("a4", "C", wrong), _rec("a5", "C", wrong)]
    )
    unblind = {
        **{f"b{n}": {"run_dir": f"p6/A3/rep{n}"} for n in range(6)},
        **{f"a{n}": {"run_dir": f"p6/A6/rep{n}"} for n in range(6)},
    }
    result = judgments.compare(records, unblind, entries, ["p6/A3"], ["p6/A6"])
    assert result["regressions"] == ["product:CIP-007-6:coverage_gap"]
    assert result["keep_if_truth_fix"] is False


def test_aggregate_final_set_counts_c_records_in_the_headline():
    entries = judgments.key_entries(_key())
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    records = [
        _rec("i1", "A", ok),
        _rec("i2", "A", {**ok, "F1": "wrong"}),
        _rec("i3", "C", {**ok, "F2": "omitted"}),
    ]
    unblind = {
        "i1": {"run_dir": "r", "suite": "product", "mechanical_verdict": "PASS"},
        "i2": {"run_dir": "r", "suite": "product", "mechanical_verdict": "PASS"},
        "i3": {"run_dir": "r", "suite": "product", "mechanical_verdict": "PASS"},
    }
    result = judgments.aggregate(records, unblind, entries)
    assert result["overall"]["n"] == 3
    assert result["overall"]["counts"]["PARTIAL"] == 1


@pytest.mark.parametrize(
    "extra",
    [
        lambda ok: _rec("b1", "B", ok),  # a double-judged B record
        lambda ok: _rec("a0", "C", ok),  # A and C both present for one item
    ],
)
def test_compare_refuses_a_set_that_is_not_final(extra):
    """compare scores the set as given, so a B record or a repeated item_id
    would silently count a rep twice; it refuses instead."""
    entries = judgments.key_entries(_key())
    ok = {"F1": "correct", "F2": "correct", "F3": "correct"}
    records = [_rec("b0", "A", ok), _rec("a0", "A", ok), extra(ok)]
    unblind = {"b0": {"run_dir": "p6/A3/rep0"}, "a0": {"run_dir": "p6/A6/rep0"}}
    with pytest.raises(ValueError):
        judgments.compare(records, unblind, entries, ["p6/A3"], ["p6/A6"])
