"""P5 — the one citation-integrity diagnostic, and harness parity.

Synthetic where hermetic; the live-store cases run against the real store and
skip when it is absent (CI parity with the operator-profile rule).
"""

from __future__ import annotations

import pathlib

import pytest

from scripts.compliance.truth import citation_integrity
from scripts.compliance.truth.citation_integrity import MIN_QUOTE_WORDS, integrity

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _store():
    pytest.importorskip("portal")
    try:
        from portal.modules.compliance.core.repository import Repository

        return Repository()
    except Exception as exc:  # noqa: BLE001 - no store in CI is the expected case
        pytest.skip(f"compliance store unavailable: {exc}")


REAL_ID = "csection-7700dd5499cead0994ec"  # CIP-007-6 R2 Part 2.2 row
REAL_QUOTE = "At least once every 35 calendar days"


def test_placeholder_is_fabricated():
    store = _store()
    res = integrity(store, "Per [cite O-xxxxxx], done.")
    assert "O-xxxxxx" in res["fabricated_tokens"]


def test_sub_threshold_scare_quote_is_not_evidence():
    store = _store()
    res = integrity(
        store, f'A "35 calendar days" mention and nothing else, {REAL_ID} resolves though.'
    )
    line = res["lines"][0]
    assert line["quotes"][0]["status"] == "not_evidence"
    assert MIN_QUOTE_WORDS >= 2


def test_unresolved_address_evidences_no_side():
    store = _store()
    bogus = "csection-" + "0" * 19 + "1"
    res = integrity(store, f"See {bogus} for the rule.")
    assert res["lines"][0]["grounded"] is False
    assert res["sides_evidenced"] == []


def test_fabricated_ids_are_reported_among_resolving_ones():
    store = _store()
    bogus = "csection-" + "f" * 19 + "e"
    res = integrity(store, f"{REAL_ID} is the rule; {bogus} is not.")
    if not any(t["resolved"] for t in res["tokens"]):
        pytest.skip("REAL_ID not in this store (conftest may supply an isolated db)")
    assert bogus in [t["token"] for t in res["tokens"] if not t["resolved"]]
    assert REAL_ID in [t["token"] for t in res["tokens"] if t["resolved"]]


def test_resolve_token_full_id_and_unique_prefix():
    store = _store()
    if citation_integrity.resolve_token(store, REAL_ID) is None:
        pytest.skip("REAL_ID not in this store (conftest may supply an isolated db)")
    got = citation_integrity.resolve_token(store, REAL_ID)
    assert got is not None and got["section_id"] == REAL_ID
    prefix = citation_integrity.resolve_token(store, "csection-7700dd5499cead0")
    assert prefix is not None and prefix["section_id"] == REAL_ID


def test_harness_parity_all_three_import_integrity():
    """All three harnesses reference the one integrity module (source check)."""
    for rel in (
        "scripts/compliance/ask_conversational.py",
        "scripts/compliance/ask_product_questions.py",
        "scripts/compliance_acceptance.py",
    ):
        src = (REPO_ROOT / rel).read_text()
        assert "citation_integrity" in src, f"{rel} does not reference the integrity module"
        assert "from scripts.compliance.truth.citation_integrity import" in src or (
            "citation_integrity import integrity" in src
        ), f"{rel} does not import integrity"


def test_min_quote_words_is_module_constant():
    assert MIN_QUOTE_WORDS in (2, 3, 4, 5, 6, 8)
