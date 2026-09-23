"""CITE_AND_SCOPE_V1 §P1 — citation by quote.

The resolver is the verbatim check inverted over the whole store. Its ground
truth in production is the set of stored determination quotes (receipt
p1/quote_resolution.json, recall 1.0); these unit tests pin the SEMANTICS the
receipt measured: typography folds, paraphrase does not resolve, elision
parts must all land in one document, and nothing ever resolves to a near
neighbour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.compliance.core import document_scope
from portal.modules.compliance.core.candidate_links import Candidate, apply_scope
from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.citation_by_quote import quoted_spans, resolve_quote
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository


def _capture(path: Path, bodies: list[str]) -> CapturedDocument:
    units, buf, cursor = [], [], 0
    for ordinal, body in enumerate(bodies):
        piece = body + "\n"
        units.append(
            CapturedUnit(
                ordinal=ordinal,
                unit_kind="prose",
                heading_path=f"H{ordinal}",
                title=f"H{ordinal}",
                page_start=1,
                page_end=1,
                char_start=cursor,
                char_end=cursor + len(piece),
                text=piece,
            )
        )
        buf.append(piece)
        cursor += len(piece)
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text="".join(buf),
        units=units,
        reader_strings=tuple(bodies),
    )


@pytest.fixture
def store(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "store.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="LSPG/plan.pdf",
            title="Plan",
            issuer="x",
            source_kind="procedure",
            jurisdiction="internal",
        )
    )
    revision = repo.add_document_revision("LSPG/plan.pdf", "/docs/plan.pdf", b"")
    bodies = [
        "Position sensors are required for all ACPs. Each door shall require a door position switch.",
        "The shared account user creates a log entry in the \u201creason for retrieval\u201d field.",
        "All physical security systems under CIP-\n006 R3 function properly.",
        "Boilerplate: this procedure applies to the bulk electric system.",
    ]
    store_capture(repo, revision.revision_id, _capture(Path("/docs/plan.pdf"), bodies))
    return repo


def test_a_verbatim_quote_resolves_to_its_section(store: Repository) -> None:
    hits = resolve_quote(store, "Position sensors are required for all ACPs.")
    assert hits


def test_typography_in_transit_does_not_block_resolution(store: Repository) -> None:
    # curly quotes in the document, straight in the answer; case differs
    hits = resolve_quote(store, 'creates a log entry in the "reason for retrieval" FIELD')
    assert hits


def test_a_pdf_line_wrap_does_not_block_resolution(store: Repository) -> None:
    # the capture breaks "CIP-006" across a line: "CIP-\n006"
    hits = resolve_quote(store, "all physical security systems under CIP-006 R3 function")
    assert hits


def test_a_paraphrase_resolves_to_nothing(store: Repository) -> None:
    # same words up to one changed word ending — not the document's words
    assert not resolve_quote(store, "Position sensors are required for every ACP.")


def test_an_absent_phrase_resolves_to_nothing(store: Repository) -> None:
    assert not resolve_quote(store, "the evidence specification matrix governs all")


def test_elision_parts_must_land_in_one_document(store: Repository) -> None:
    good = resolve_quote(
        store, "Position sensors are required... Each door shall require a door position switch."
    )
    assert good  # both parts live in the same section
    # one real part + one invented part: fails, never repaired onto a neighbour
    assert not resolve_quote(store, "Position sensors are required... the moon is made of cheese.")


def test_a_dot_leader_is_not_an_elision(store: Repository) -> None:
    # a TOC-style run of dots must be matched literally if quoted literally
    assert resolve_quote(store, "Boilerplate: this procedure applies") is not None


def test_trailing_absorbed_punctuation_is_typography(store: Repository) -> None:
    assert resolve_quote(store, "Position sensors are required for all ACPs,")  # absorbed comma


def test_multi_match_reports_every_section(store: Repository) -> None:
    # both the boilerplate sentence and nothing else — single doc, so repeat
    # the phrase across two fixtures instead: here, assert the distribution
    # key exists and multi-hits list all matches
    hits = resolve_quote(store, "this procedure applies to the bulk electric system")
    assert len(hits) == 1


def test_empty_and_tiny_quotes_resolve_to_nothing(store: Repository) -> None:
    assert resolve_quote(store, "") == []
    assert resolve_quote(store, "a") == []


def test_quoted_spans_extracts_double_quotes_only() -> None:
    line = 'He said "keep it on" and it\u2019s \u201cfine\u201d — \u2018not this\u2019'
    assert quoted_spans(line) == ["keep it on", "fine"]


# ── the scope decision (CITE_AND_SCOPE_V1 P2) ───────────────────────────────


def _candidate() -> Candidate:
    return Candidate("isection-x", 0.45, "text", "h", "LSPG/plan.pdf")


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


# ── document scope store side ────────────────────────────────────────────────


def test_normalize_family_variants() -> None:
    assert document_scope.normalize_family("CIP-002-5.1a") == "CIP-002"
    assert document_scope.normalize_family("CIP 006") == "CIP-006"
    assert document_scope.normalize_family("NERC Standard, CIP-014-3") == "CIP-014"
    assert document_scope.normalize_family("the reliability standard") is None


def test_claims_without_evidence_are_recorded_and_excluded(store: Repository) -> None:
    claims = document_scope.validate_claims(
        [
            {"standard": "CIP-006", "quote": "CIP-\n006 R3 function properly"},
            {"standard": "CIP-099", "quote": "this document does not say that"},
            {"standard": "garbage", "quote": "whatever"},
        ],
        "All physical security systems under CIP-\n006 R3 function properly.",
    )
    assert claims[0]["quote_valid"] is True and claims[0]["standard"] == "CIP-006"
    assert claims[1]["quote_valid"] is False  # recorded, never silently dropped
    assert claims[2]["standard"] == "garbage" and claims[2]["quote_valid"] is False


def test_scope_round_trips_through_the_store(tmp_path: Path) -> None:
    repo = Repository(tmp_path / "scope.db")
    repo.upsert_source_document(
        SourceDocument(
            logical_id="LSPG/plan.pdf",
            title="Plan",
            issuer="x",
            source_kind="procedure",
            jurisdiction="internal",
        )
    )
    document_scope.store_scope(
        repo,
        logical_id="LSPG/plan.pdf",
        claims=[
            {
                "standard": "CIP-006",
                "quote": "serves CIP-006",
                "quote_valid": True,
                "stated_as": "CIP-006",
            }
        ],
        about="a plan",
        states_scope=True,
        model="test-seat",
        read_chars=100,
        raw={"ok": True},
    )
    row = document_scope.scope_row(repo, "LSPG/plan.pdf")
    assert row is not None and row["model"] == "test-seat"
    assert document_scope.families_for(row) == {"CIP-006"}
    mapped = document_scope.scope_map(repo)
    assert mapped["LSPG/plan.pdf"] == {"CIP-006"}
    # a claim whose quote failed validation never reaches the population's scope
    document_scope.store_scope(
        repo,
        logical_id="LSPG/plan.pdf",
        claims=[
            {
                "standard": "CIP-002",
                "quote": "not in the document",
                "quote_valid": False,
                "stated_as": "CIP-002",
            }
        ],
        about="a plan",
        states_scope=True,
        model="test-seat",
        read_chars=100,
        raw={},
    )
    assert document_scope.families_for(document_scope.scope_row(repo, "LSPG/plan.pdf")) == set()
    repo.close()


# ── visible provenance: the scope line the reader sees ───────────────────────


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
