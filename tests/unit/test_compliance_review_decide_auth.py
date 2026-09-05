"""TASK_COMPLIANCE_REASONING_V2 P7 / F09 — compliance_review_decide requires
an authenticated reviewer token; decided_by can no longer be caller-supplied
text alone.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("lancedb")


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    from portal.modules.compliance.core import auth as auth_mod
    from portal.platform.retrieval import store as _store

    monkeypatch.setattr(_store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(_store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(auth_mod, "REVIEWERS_PATH", tmp_path / "reviewers.json")
    _store._db = None
    yield
    _store._db = None


def _configure_reviewer(tmp_path, token: str = "tok-abc", name: str = "alice") -> None:
    from portal.modules.compliance.core import auth as auth_mod

    auth_mod.REVIEWERS_PATH.write_text(json.dumps({token: name}), encoding="utf-8")


def test_review_decide_without_token_is_rejected(tmp_path):
    from portal.modules.compliance.core import review_queue as rq
    from portal.modules.compliance.tools.compliance_mcp import compliance_review_decide

    item = rq.propose("applicability_scope", "entity", {"impact_present": ["high"]}, confidence=0.5)
    result = compliance_review_decide(item.id, "CONFIRMED", "a model calling itself SME")
    assert result.get("status") == "UNAUTHENTICATED"
    # the item must still be OPEN — no decision happened
    assert item in rq.open_items("applicability_scope")


def test_review_decide_with_valid_token_records_the_verified_principal(tmp_path):
    from portal.modules.compliance.core import review_queue as rq
    from portal.modules.compliance.tools.compliance_mcp import compliance_review_decide

    _configure_reviewer(tmp_path)
    item = rq.propose("applicability_scope", "entity", {"impact_present": ["high"]}, confidence=0.5)
    result = compliance_review_decide(
        item.id, "CONFIRMED", "whatever the caller claims", reviewer_token="tok-abc"
    )
    assert result["status"] == "CONFIRMED"
    # decided_by is the VERIFIED principal, not the caller-supplied label
    assert result["decided_by"] == "alice"
    assert result["caller_label"] == "whatever the caller claims"


def test_review_decide_with_wrong_token_is_rejected_and_does_not_decide(tmp_path):
    from portal.modules.compliance.core import review_queue as rq
    from portal.modules.compliance.tools.compliance_mcp import compliance_review_decide

    _configure_reviewer(tmp_path)
    item = rq.propose("document_tier", "doc.pdf", {"layer": "procedure"}, confidence=0.3)
    result = compliance_review_decide(item.id, "CONFIRMED", "someone", reviewer_token="tok-wrong")
    assert result.get("status") == "UNAUTHENTICATED"
    assert item in rq.open_items("document_tier")


def test_review_decide_confirmed_mapping_uses_verified_identity_not_caller_text(
    tmp_path, monkeypatch
):
    from portal.modules.compliance.core import mapping_store as ms_mod
    from portal.modules.compliance.core import review_queue as rq
    from portal.modules.compliance.core.mapping_store import MappingStore
    from portal.modules.compliance.tools.compliance_mcp import compliance_review_decide

    store_path = tmp_path / "m.json"
    monkeypatch.setattr(ms_mod, "STORE_PATH", store_path)
    # `compliance_review_decide` constructs `MappingStore()` with no override
    # — its default arg was already bound to the OLD STORE_PATH at class
    # definition time, so the module-level patch above alone would not
    # redirect it. Rebind the bound default directly.
    monkeypatch.setattr(ms_mod.MappingStore.__init__, "__defaults__", (store_path,))
    _configure_reviewer(tmp_path)
    store = MappingStore(store_path)
    mp = store.propose("CIP-007-6 R2 Part 2.2", "POL", "§1", "FULL")
    rq.sync_proposed_mappings(store)
    item = rq.open_items(kind="mapping_proposal")[0]

    compliance_review_decide(item.id, "CONFIRMED", "an untrusted label", reviewer_token="tok-abc")
    approved = MappingStore(store_path)._by_id(mp.id)  # noqa: SLF001
    assert approved.approved_by == "alice"  # never "an untrusted label"
