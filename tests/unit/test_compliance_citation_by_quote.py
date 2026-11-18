"""CITE_AND_SCOPE_V1 §P1 — citation by quote.

The resolver is the verbatim check inverted over the whole store. Its ground
truth in production is the set of stored determination quotes (receipt
p1/quote_resolution.json, recall 1.0); these unit tests pin the SEMANTICS the
receipt measured: typography folds, paraphrase does not resolve, elision
parts must all land in one document, and nothing ever resolves to a near
neighbour.
"""

from __future__ import annotations

import pytest

from portal.modules.compliance.core import document_scope
from portal.modules.compliance.core.candidate_links import Candidate, apply_scope
from portal.modules.compliance.core.citation_by_quote import quoted_spans


def test_quoted_spans_extracts_double_quotes_only() -> None:
    line = 'He said "keep it on" and it\u2019s \u201cfine\u201d — \u2018not this\u2019'
    assert quoted_spans(line) == ["keep it on", "fine"]


def _candidate() -> Candidate:
    return Candidate("isection-x", 0.45, "text", "h", "ACME/plan.pdf")


def test_filter_excludes_a_document_known_to_serve_other_standards() -> None:
    assert apply_scope(_candidate(), family="CIP-002", served={"CIP-006"}, mode="filter") is None


def test_filter_never_excludes_an_unscoped_document() -> None:
    assert apply_scope(_candidate(), family="CIP-002", served=None, mode="filter") is not None


def test_filter_keeps_a_serving_document() -> None:
    assert (
        apply_scope(_candidate(), family="CIP-006", served={"CIP-006"}, mode="filter") is not None
    )


def test_prior_boosts_a_serving_document_and_keeps_the_raw_score() -> None:
    boosted = apply_scope(_candidate(), family="CIP-002", served={"CIP-002"}, mode="prior")
    assert boosted is not None
    assert boosted.score == pytest.approx(0.45 + 0.125)
    assert boosted.rerank_score == pytest.approx(0.45)
    assert boosted.scope_boosted


def test_prior_leaves_everything_else_admissible() -> None:
    same = apply_scope(_candidate(), family="CIP-002", served={"CIP-009"}, mode="prior")
    assert same is not None and same.score == pytest.approx(0.45)
    same2 = apply_scope(_candidate(), family="CIP-002", served=None, mode="prior")
    assert same2 is not None and same2.score == pytest.approx(0.45)


def test_normalize_family_variants() -> None:
    assert document_scope.normalize_family("CIP-002-5.1a") == "CIP-002"
    assert document_scope.normalize_family("CIP 006") == "CIP-006"
    assert document_scope.normalize_family("NERC Standard, CIP-014-3") == "CIP-014"
    assert document_scope.normalize_family("the reliability standard") is None


def _scope(families: list[str], *, valid: bool = True, about: str = "a plan") -> dict:
    return {
        "claims": [{"standard": f, "quote": "q", "quote_valid": valid} for f in families],
        "about": about,
    }


def test_scope_line_says_when_the_document_serves_another_standard() -> None:
    from portal.modules.compliance.core.reading_material import _scope_line

    line = _scope_line(_scope(["CIP-014"]), "CIP-002")
    assert "serves CIP-014" in line and "does not include CIP-002" in line


def test_scope_line_says_when_the_document_serves_this_standard() -> None:
    from portal.modules.compliance.core.reading_material import _scope_line

    line = _scope_line(_scope(["CIP-002", "CIP-014"]), "CIP-002")
    assert "serves CIP-002, CIP-014" in line and "which includes CIP-002" in line


def test_scope_line_is_absent_for_an_unread_document() -> None:
    from portal.modules.compliance.core.reading_material import _scope_line

    # unread is not "serves nothing" — no row, no line
    assert _scope_line(None, "CIP-002") == ""


def test_scope_line_never_states_an_unevidenced_claim() -> None:
    from portal.modules.compliance.core.reading_material import _scope_line

    line = _scope_line(_scope(["CIP-002"], valid=False), "CIP-002")
    assert "states no NERC CIP standard" in line and "CIP-002 " not in line.split("about")[0]


def test_conversation_material_asks_for_quotes_not_handles() -> None:
    from portal.modules.compliance.core.reading_material import _standing_instruction

    sweep = _standing_instruction("")
    conversation = _standing_instruction("", "quote")
    assert "cite the bracketed handle exactly as shown" in sweep
    assert "cite the bracketed handle exactly as shown" not in conversation
    assert "the quote is the citation" in conversation
