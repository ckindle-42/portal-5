"""P1.4 -- ORG projection (LanceDB) + mandatory recall receipts + decision
impacts.

Hermetic: LanceDB itself is embedded/local (no server), so tests use a real
`tmp_path` table; only the :8917 embed HTTP call is faked (`Organ._embed`
monkeypatched per-instance -- no real network). FINAL_VALIDATION C3
(organ side): outbox->projection round trip, mandatory recall receipt,
embed-down honest block (never a silent lexical fallback), rebuild-by-
replay determinism.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully.organ import Organ, OrganUnavailable
from portal.modules.security.core.bully.store import Store


def _fake_embed(dim: int = 8):
    def _embed(texts: list[str]) -> list[list[float]]:
        # Deterministic per-text vector so knn results are reproducible.
        return [[float((hash(t) >> i) % 7) for i in range(dim)] for t in texts]

    return _embed


def _failing_embed(texts):
    raise OrganUnavailable(
        "embed service unreachable at http://localhost:8917/embed: connect failed"
    )


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    s.hunt_create(
        hunt_id="hunt-1",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    yield s
    s.close()


@pytest.fixture
def organ(tmp_path, store):
    o = Organ(store=store, db_path=tmp_path / "hunt_memory")
    o._embed = _fake_embed()
    yield o
    o.close()


def _record(text_seed="lateral movement"):
    return {
        "kind": "cousin",
        "hunt_id": "hunt-1",
        "episode_id": "ep-1",
        "tactic": "lateral-movement",
        "technique_ids": ["T1021.002"],
        "behavior_sequence": text_seed,
        "trust_tier": "VALIDATED",
        "provenance_class": "hunt_emission",
    }


# ── outbox -> projection upsert round trip (C3) ─────────────────────────────


def test_index_emissions_then_process_outbox_lands_in_projection(organ, store):
    organ.index_emissions([_record()])
    result = organ.process_outbox()
    assert result["completed"] == 1
    assert result["failed"] == 0
    assert organ.stats()["row_count"] == 1


def test_process_outbox_completes_the_outbox_row_with_matching_source_hash(organ, store):
    outbox_ids = organ.index_emissions([_record()])
    organ.process_outbox()
    row = store._conn.execute(
        "SELECT status FROM index_outbox WHERE outbox_id=?", (outbox_ids[0],)
    ).fetchone()
    assert row["status"] == "completed"


def test_duplicate_index_emission_upsert_converges(organ):
    rec = _record()
    organ.index_emissions([rec])
    organ.process_outbox()
    organ.index_emissions([rec])  # same content -> same record_id
    organ.process_outbox()
    assert organ.stats()["row_count"] == 1  # merge_insert, not a duplicate row


def test_batch_upsert_and_prepared_knn_preserve_snapshot_semantics(organ):
    embed_calls: list[list[str]] = []
    fake_embed = _fake_embed()

    def tracking_embed(texts):
        embed_calls.append(list(texts))
        return fake_embed(texts)

    organ._embed = tracking_embed
    record_ids = organ.upsert_many([_record("a"), _record("b"), _record("c")], batch_size=2)
    assert len(record_ids) == 3
    assert organ.stats()["row_count"] == 3
    assert [len(call) for call in embed_calls] == [2, 1]

    prepared = organ.prepare_knn(["query-a", "query-b", "query-a"], k=2, batch_size=2)
    assert prepared == 2
    calls_after_prepare = len(embed_calls)
    assert organ.knn("query-a", k=2)
    assert len(embed_calls) == calls_after_prepare

    organ.upsert(_record("d"))
    organ.knn("query-a", k=2)
    assert len(embed_calls) == calls_after_prepare + 2


# ── recall receipt shape + mandatory-ness ───────────────────────────────────


def test_recall_persists_a_receipt_and_returns_candidates(organ, store):
    organ.index_emissions([_record("wmi lateral movement")])
    organ.process_outbox()
    receipt = organ.recall(hunt_id="hunt-1", query="wmi lateral movement", k=4)
    assert receipt.hunt_id == "hunt-1"
    row = store._conn.execute(
        "SELECT recall_id FROM recall_receipts WHERE recall_id=?", (receipt.recall_id,)
    ).fetchone()
    assert row is not None


def test_recall_receipt_persisted_even_when_empty(organ, store):
    # No records indexed yet -- an empty projection is not an error.
    receipt = organ.recall(hunt_id="hunt-1", query="nothing indexed yet", k=4)
    assert receipt.candidates == []
    assert store.recall_receipt_exists("hunt-1") is True


# ── embed-down -> honest block, never a silent lexical fallback ────────────


def test_recall_raises_and_persists_degraded_receipt_when_embed_unreachable(organ, store):
    organ._embed = _failing_embed
    with pytest.raises(OrganUnavailable):
        organ.recall(hunt_id="hunt-1", query="anything", k=4)
    # C3 / DATA_MODEL SS1.11: persisted even when degraded.
    assert store.recall_receipt_exists("hunt-1") is True
    row = store._conn.execute(
        "SELECT source_health FROM recall_receipts WHERE hunt_id='hunt-1'"
    ).fetchone()
    assert "unreachable" in row["source_health"]


def test_process_outbox_fails_open_never_upserts_when_embed_unreachable(organ, store):
    organ.index_emissions([_record()])
    organ._embed = _failing_embed
    result = organ.process_outbox()
    assert result["completed"] == 0
    assert result["failed"] == 1
    assert organ.stats()["row_count"] == 0  # never a silent partial/lexical write


# ── rebuild-by-replay determinism ───────────────────────────────────────────


def test_rebuild_by_replay_is_idempotent(organ):
    records = [_record("a"), _record("b"), _record("c")]
    n1 = organ.rebuild_by_replay(records)
    stats1 = organ.stats()
    n2 = organ.rebuild_by_replay(records)
    stats2 = organ.stats()
    assert n1 == n2 == 3
    assert stats1["row_count"] == stats2["row_count"] == 3
