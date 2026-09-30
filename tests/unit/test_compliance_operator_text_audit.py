"""Synthetic tests for the operator-text detector (READING_TRUTH_V1 P1.1).

No store, no network: every OperatorIndex here is built from literal sets.
"""

from __future__ import annotations

import pytest

from scripts.compliance.truth import operator_text_audit as audit
from scripts.compliance.truth.operator_text_audit import (
    OperatorIndex,
    _fold_with_map,
    _local_class,
    _norm_for_verbatim_mirror,
    _span_lines,
    _tokens_with_spans,
    parse_replacement_lines,
)

MODULE_FOLD = None  # imported lazily; candidate_links is heavy


def _module_fold(text: str) -> str:
    global MODULE_FOLD
    if MODULE_FOLD is None:
        from portal.modules.compliance.core.candidate_links import _norm_for_verbatim

        MODULE_FOLD = _norm_for_verbatim
    return MODULE_FOLD(text)


def _index(op=(), reg=(), terms=()) -> OperatorIndex:
    return OperatorIndex(
        operator_shingles=frozenset(op),
        regulatory_shingles=frozenset(reg),
        identity_terms=tuple(terms),
    )


def _shingles(text: str) -> set[str]:
    tokens, _ = _tokens_with_spans(text)
    n = audit.SHINGLE_N
    return {" ".join(tokens[i : i + n]) for i in range(0, max(0, len(tokens) - n + 1))}


SENTENCE = 'the operator shall ensure that every patch is "tested" before deployment'


def test_regulatory_shared_shingles_are_excluded():
    shared = _shingles(SENTENCE)
    index = _index(op=shared, reg=shared)
    assert index.scan(f"Intro. {SENTENCE.capitalize()} Done.") == []


def test_maximal_runs_merge_into_one_span():
    index = _index(op=_shingles(SENTENCE))
    found = [f for f in index.scan(SENTENCE + " tonight.") if f.kind == "text_span"]
    assert len(found) == 1
    assert found[0].match == SENTENCE


def test_exact_original_substrings_are_recovered_through_typography():
    styled = "The OPERATOR shall ensure that every\npatch is “tested” before\tdeployment"
    index = _index(op=_shingles(SENTENCE))
    found = [f for f in index.scan(styled) if f.kind == "text_span"]
    assert len(found) == 1
    f = found[0]
    assert f.match == styled[f.start : f.end]
    assert f.match.startswith("The OPERATOR shall")
    assert f.match.endswith("deployment")


def test_a_seven_token_overlap_is_not_a_span():
    index = _index(op=_shingles(SENTENCE))
    truncated = " ".join(SENTENCE.split()[:7])
    assert [f for f in index.scan(truncated) if f.kind == "text_span"] == []


def test_identity_terms_match_on_word_boundaries_longest_first():
    long_org = "acme grid development llc"
    terms = ((long_org, "the operator"), ("acme", "the operator"))
    index = _index(terms=terms)
    text = f"Contact ACMEtools? No - email ACME, or {long_org.upper()} directly."
    found = index.scan(text)
    hits = [(f.match, f.replacement) for f in found if f.kind == "identity_term"]
    assert ("ACME", "the operator") in hits
    assert ("ACME GRID DEVELOPMENT LLC", "the operator") in hits
    assert not any("ACMEtools" in match for match, _ in hits)
    assert not any(match == "ACME Grid" for match, _ in hits)


def test_operator_id_regexes():
    index = _index()
    long_id = "isection-" + "a1" * 10
    token = "O-" + "abc123"
    found = index.scan(
        f"see {long_id} and {token}; not {long_id[:-1]}, not {token}4, not X{token}, not R{token}"
    )
    matches = [f.match for f in found if f.kind == "operator_id"]
    assert matches == [long_id, token]


def test_all_zero_synthetic_ids_never_flag():
    index = _index()
    assert index.scan("isection-00000000000000000000 and O-000000.") == []


def test_replacement_lines_round_trip():
    lines = [
        audit._filter_repo_line("ACME Grid Development LLC", "the operator"),
        audit._filter_repo_line("ACME", "the operator"),
    ]
    lines += _span_lines("quoted text that spans\nseveral operator lines", audit.SPAN_REPLACEMENT)
    pairs = parse_replacement_lines(lines)
    assert ("ACME Grid Development LLC", "the operator") in pairs
    assert ("ACME", "the operator") in pairs
    assert ("quoted text that spans", audit.SPAN_REPLACEMENT) in pairs
    assert ("several operator lines", audit.SPAN_REPLACEMENT) in pairs
    assert not any("\n" in literal for literal, _ in pairs)


def test_span_lines_never_carry_a_newline():
    lines = _span_lines("first line\n\nlast line", audit.SPAN_REPLACEMENT)
    assert len(lines) == 2
    assert all("\n" not in line for line in lines)


@pytest.mark.parametrize(
    "text",
    [
        'the "reason for retrieval" field — a CIP-\n006 dash wrap\u00a0 here',
        "MIXED case TEXT with\u2014em dashes, ‘curly quotes’, and  double  spaces.",
        "- leading dash- space fold -\tand tabs",
        "plain text",
        "",
    ],
)
def test_fold_map_matches_the_module_verbatim_fold(text):
    folded, _ = _fold_with_map(text)
    assert folded == _norm_for_verbatim_mirror(text)
    assert folded == _module_fold(text)


def test_fold_map_offsets_recover_exact_spans():
    text = "Contact ACME (via “portal”)\ntoday."
    folded, spans = _fold_with_map(text)
    assert len(folded) == len(spans)
    for i, (start, end) in enumerate(spans):
        slice_folded = _fold_with_map(text[start:end])[0]
        assert slice_folded == folded[i] if folded[i] != " " else slice_folded == ""


def test_local_class_paths():
    assert _local_class("reports/compliance/run/transcripts/q1.json")
    assert _local_class("config/compliance/cases/cip_007_6.yaml")
    assert _local_class("docs/RAG_COMPLIANCE_QA_REALIGNMENT_V1.md")
    assert not _local_class("reports/other/summary.md")
    assert not _local_class("docs/ADMIN_GUIDE.md")
    assert not _local_class("portal/modules/compliance/core/repository.py")


# ── P1R: provenance, no tip veto, punctuation-blind tokens ──────────────────

import subprocess  # noqa: E402

OPERATOR_SENTENCE = "the crew in conjunction with Zorbex, shall review all approved sources monthly"
FIXTURE = "the crew in conjunction with Zorbex shall review all approved sources monthly"


def test_protected_file_is_never_flagged_even_when_operator_text_quotes_it():
    index = OperatorIndex(
        operator_shingles=frozenset(_shingles(SENTENCE)),
        regulatory_shingles=frozenset(),
        protected_globs=("data/regulatory/*",),
    )
    assert index.is_protected("data/regulatory/register.json")
    collector = audit._HistoryCollector(index)
    collector.record(SENTENCE, "data/regulatory/register.json")
    assert collector.lines == set() and collector.local_paths == set()
    collector.record(SENTENCE, "tests/t.py")
    assert collector.lines


def test_operator_text_quoting_public_text_is_flagged_only_in_its_non_public_part():
    public = "requirement one every responsible entity shall implement its documented process"
    private = "additionally our crew escalates every unresolved finding to the night supervisor"
    index = _index(op=_shingles(public + " " + private), reg=_shingles(public))
    found = [f for f in index.scan(f"{public} {private}") if f.kind == "text_span"]
    assert found
    assert not any("requirement one" in f.match for f in found)
    assert any("night supervisor" in f.match for f in found)


def test_punctuation_no_longer_hides_a_sentence_from_the_detector():
    index = _index(op=_shingles(OPERATOR_SENTENCE))
    found = [f for f in index.scan(FIXTURE) if f.kind == "text_span"]
    assert len(found) == 1 and found[0].match == FIXTURE


def test_a_vendor_term_inside_a_sentence_is_flagged():
    index = _index(terms=(("zorbex", "the vendor"),))
    found = index.scan("Sources are reviewed in conjunction with Zorbex, monthly.")
    assert [(f.kind, f.match) for f in found] == [("identity_term", "Zorbex")]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path, files):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for k, name in (("user.email", "t@t"), ("user.name", "t")):
        _git(repo, "config", k, name)
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    return repo


def test_history_scan_censuses_a_finding_even_when_the_same_text_is_at_the_tip(tmp_path):
    repo = _repo(tmp_path, {"t.py": FIXTURE + "\n"})
    index = _index(op=_shingles(OPERATOR_SENTENCE))
    result = audit.history_scan(repo / ".git", index, tip_root=repo)
    assert result["census"].get("text_span") == 1
    assert any(FIXTURE in line for line in result["tip_withheld"])  # input filter only
    assert result["local_paths"] == []  # a kept path is never deleted, only replaced


def test_history_scan_withholds_a_literal_that_also_occurs_in_a_protected_file(tmp_path):
    repo = _repo(
        tmp_path,
        {"data/reg.json": "the standard mentions Zorbex once\n", "t.py": "ask Zorbex now\n"},
    )
    index = OperatorIndex(
        operator_shingles=frozenset(),
        regulatory_shingles=frozenset(),
        identity_terms=(("zorbex", "the vendor"),),
        protected_globs=("data/*",),
    )
    result = audit.history_scan(repo / ".git", index)
    assert result["blob_replacements"] == []
    assert result["protected_conflicts"] == [audit._term_line("Zorbex", "the vendor")]


def test_has_findings_agrees_with_scan_text():
    index = _index(op=_shingles(OPERATOR_SENTENCE), terms=(("zorbex", "the vendor"),))
    for text in (FIXTURE, "nothing here", "ask Zorbex", "isection-" + "a1" * 10):
        assert audit.has_findings(text, index) == bool(audit.scan_text(text, index))


def test_compliance_run_outputs_are_local_class_anywhere():
    assert _local_class("tests/benchmarks/results/persona_matrix_auto-compliance_20260503.json")
    assert _local_class("results/_archive/judgment_probe_v6_20260906.json")
    assert not _local_class("tests/benchmarks/results/persona_matrix_auto-coding_20260503.json")


def test_numeric_and_reference_runs_are_structure_not_prose():
    numeric = '"2.1", "2.2", "2.3", "2.4" and 2.5 in CIP-007-6 R2 Part 2.2 on 10 20'
    index = _index(op=_shingles(numeric))
    assert [f for f in index.scan(numeric) if f.kind == "text_span"] == []


def test_a_lone_shingle_is_a_phrase_collision_not_a_span():
    eight = "at least once every thirty five calendar days"
    index = _index(op=_shingles(eight))
    assert [f for f in index.scan(eight) if f.kind == "text_span"] == []
    nine = eight + " later"
    index = _index(op=_shingles(nine))
    assert len([f for f in index.scan(nine) if f.kind == "text_span"]) == 1


def test_identity_term_lines_are_word_bounded_and_case_insensitive():
    import re

    line = audit._term_line("Quonk", "an operator tool")
    pattern, _, repl = line[len("regex:") :].rpartition("==>")
    assert repl == "an operator tool"
    assert re.sub(pattern, "X", "an Quonk and quonk, not PHQUONKS or quonkx") == (
        "an X and X, not PHQUONKS or quonkx"
    )


def test_a_blob_kept_under_two_paths_is_judged_under_both(tmp_path):
    repo = _repo(tmp_path, {"reports/compliance/a.json": "{}\n", "other/b.json": "{}\n"})
    index = _index()
    result = audit.history_scan(repo / ".git", index, tip_root=repo)
    assert result["local_paths"] == []  # nothing tracked at the tip is deleted from history
    repo2 = _repo(tmp_path / "x", {"reports/compliance/a.json": "{}\n", "other/b.json": "{}\n"})
    (repo2 / "reports/compliance/a.json").unlink()
    (repo2 / "other/b.json").unlink()
    _git(repo2, "add", "-A")
    _git(repo2, "commit", "-q", "-m", "drop")
    result = audit.history_scan(repo2 / ".git", index, tip_root=repo2)
    assert "reports/compliance/a.json" in result["local_paths"]


def test_undecodable_and_unknown_extension_files_are_path_classified(tmp_path):
    repo = _repo(
        tmp_path,
        {"reports/compliance/run/cell.exit": "0\n", "reports/compliance/run/run.log": "x\n"},
    )
    (repo / "reports/compliance/run/cell.exit").unlink()
    (repo / "reports/compliance/run/run.log").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "drop")
    result = audit.history_scan(repo / ".git", _index(), tip_root=repo)
    assert result["local_paths"] == [
        "reports/compliance/run/cell.exit",
        "reports/compliance/run/run.log",
    ]
