"""P5 — the one citation-integrity diagnostic, and harness parity.

Every case runs against a fixture store built in ``tmp_path`` (one regulatory
document, one operator document, synthetic text) so nothing skips: the
resolving, fabricated and side-evidencing paths are all exercised.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from portal.modules.compliance.core.capture import CapturedDocument, CapturedUnit, store_capture
from portal.modules.compliance.core.models import SourceDocument
from portal.modules.compliance.core.repository import Repository
from scripts.compliance.truth import citation_integrity
from scripts.compliance.truth.citation_integrity import MIN_QUOTE_WORDS, integrity, recompute

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

REG_TEXT = "Evaluate security patches for applicability at least once every 35 calendar days."
OPS_TEXT = "The OT team evaluates every released patch within thirty days of its release."


def _capture(path: pathlib.Path, text: str) -> CapturedDocument:
    piece = text + "\n"
    unit = CapturedUnit(
        ordinal=0,
        unit_kind="prose",
        heading_path="1",
        title="1",
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=len(piece),
        text=piece,
    )
    return CapturedDocument(
        path=path,
        page_count=1,
        full_text=piece,
        units=[unit],
        extractor="docling",
        reader_strings=(text,),
    )


@pytest.fixture
def store(tmp_path: pathlib.Path):
    repo = Repository(tmp_path / "store.db")
    for logical_id, jurisdiction, kind, text in (
        ("NERC/CIP-007-6", "US", "regulatory_standard", REG_TEXT),
        ("ACME/patching", "internal", "procedure", OPS_TEXT),
    ):
        repo.upsert_source_document(
            SourceDocument(
                logical_id=logical_id,
                title=logical_id,
                issuer="x",
                source_kind=kind,
                jurisdiction=jurisdiction,
            )
        )
        revision = repo.add_document_revision(
            logical_id, f"/docs/{logical_id}.pdf", logical_id.encode()
        )
        store_capture(repo, revision.revision_id, _capture(pathlib.Path(logical_id), text))
    yield repo
    repo.close()


def _section_id(repo: Repository, logical_id: str) -> str:
    row = repo._conn.execute(
        """SELECT s.section_id FROM source_sections s
           JOIN document_revisions r ON s.revision_id = r.revision_id
           WHERE r.logical_id = ?""",
        (logical_id,),
    ).fetchone()
    return str(row[0])


def test_quote_only_answer_evidences_both_sides(store):
    answer = (
        'The standard says "at least once every 35 calendar days".\n'
        'We say "evaluates every released patch within thirty days".'
    )
    res = integrity(store, answer)
    assert res["sides_evidenced"] == ["operator", "regulatory"]
    assert res["grounded"] is True
    assert not res["tokens"]


def test_placeholder_is_fabricated(store):
    res = integrity(store, "Per [cite O-xxxxxx], done.")
    assert "O-xxxxxx" in res["fabricated_tokens"]


def test_address_only_mention_evidences_no_side(store):
    res = integrity(store, "CIP-007-6 R2 Part 2.2 covers this, and so does our procedure.")
    assert res["sides_evidenced"] == []
    assert res["n_claims"] == 0


def test_sub_threshold_scare_quote_is_not_evidence(store):
    sid = _section_id(store, "NERC/CIP-007-6")
    res = integrity(store, f'A "35 calendar days" mention, and {sid} resolves.')
    quote = res["lines"][0]["quotes"][0]
    assert quote["status"] == "not_evidence"
    assert len(quote["quote"].split()) < MIN_QUOTE_WORDS


def test_fabricated_id_is_reported_among_resolving_ones(store):
    real = _section_id(store, "NERC/CIP-007-6")
    bogus = "csection-" + "f" * 19 + "e"
    res = integrity(store, f"{real} is the rule; {bogus} is not.")
    assert [t["token"] for t in res["tokens"] if t["resolved"]] == [real]
    assert res["fabricated_tokens"] == [bogus]
    assert res["sides_evidenced"] == ["regulatory"]


def test_resolve_token_full_id_and_unique_prefix(store):
    real = _section_id(store, "ACME/patching")
    assert citation_integrity.resolve_token(store, real)["section_id"] == real
    assert citation_integrity.resolve_token(store, real[:16])["section_id"] == real


def test_recompute_reads_run_dir_transcripts(store, tmp_path):
    run = tmp_path / "run"
    (run / "transcripts").mkdir(parents=True)
    (run / "transcripts" / "q.json").write_text(
        json.dumps({"answer": 'We say "evaluates every released patch within thirty days".'})
    )
    rows = recompute(store, [run], min_quote_words=7)
    assert len(rows) == 1
    assert rows[0]["quotes"][0]["status"] == "resolved"
    rows = recompute(store, [run], min_quote_words=8)
    assert rows[0]["quotes"][0]["status"] == "not_evidence"


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/compliance/ask_conversational.py",
        "scripts/compliance/ask_product_questions.py",
        "scripts/compliance_acceptance.py",
    ],
)
def test_harness_parity_imports_integrity(rel):
    """Every harness imports ``integrity`` from the one module (AST check)."""
    tree = ast.parse((REPO_ROOT / rel).read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "scripts.compliance.truth.citation_integrity"
        for alias in node.names
    }
    assert "integrity" in imported


def test_min_quote_words_is_a_calibration_value():
    assert MIN_QUOTE_WORDS in (1, 2, 3, 4, 5, 6, 8)
