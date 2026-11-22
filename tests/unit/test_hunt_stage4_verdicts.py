from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest

from portal.modules.security.core.hunt.notables.knowledge import KnowledgeItem, build_store
from portal.modules.security.core.hunt.notables.verdicts import (
    apply_verdict_priors,
    query_verdict_priors,
    record_verdict,
    stage4_verdicts_enabled,
)

SIGNATURE = {"generators": ["alerts"], "entity_roles": ["actor"]}


class _Embedder:
    model = "stage4-test"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def _store(path: Path) -> Path:
    connection = duckdb.connect(str(path))
    connection.close()
    return path


def _record(
    store: Path,
    verdict: str,
    confidence: float = 0.9,
    *,
    index_name: str = "hb_ait_santos",
    allow_proof_for_tests: bool = False,
) -> str:
    return record_verdict(
        store=store,
        index_name=index_name,
        case_id=f"case-{verdict}",
        entity_key="actor",
        behaviour_sig=SIGNATURE,
        verdict=verdict,
        confidence=confidence,
        rationale="analyst reviewed the generalized case",
        source="operator",
        family="ait",
        allow_proof_for_tests=allow_proof_for_tests,
    )


def test_default_off_is_an_exact_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cases: list[dict[str, Any]] = [{"case_id": "c1", "score": 1.0}]
    store = tmp_path / "absent.duckdb"
    monkeypatch.delenv("PORTAL_HUNT_STAGE4_VERDICTS", raising=False)

    assert stage4_verdicts_enabled() is False
    assert apply_verdict_priors(cases, store=store) is cases
    assert store.exists() is False

    monkeypatch.setenv("PORTAL_HUNT_STAGE4_VERDICTS", "false")
    assert apply_verdict_priors(cases, store=store) is cases


def test_verdicts_persist_and_produce_bounded_damped_priors(tmp_path: Path) -> None:
    store = _store(tmp_path / "knowledge.duckdb")
    _record(store, "true_positive", 0.8)
    _record(store, "false_positive", 0.7)
    _record(store, "benign_expected", 0.6)

    connection = duckdb.connect(str(store), read_only=True)
    try:
        rows = connection.execute(
            "SELECT verdict, confidence, source, family FROM hunt_verdicts ORDER BY verdict"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [
        ("benign_expected", 0.6, "operator", "ait"),
        ("false_positive", 0.7, "operator", "ait"),
        ("true_positive", 0.8, "operator", "ait"),
    ]

    prior = query_verdict_priors(
        store=store,
        index_name="hb_ait_santos",
        family="ait",
        entity_key="actor",
        behaviour_sig=SIGNATURE,
    )
    assert prior["support"] == 3
    assert -0.25 <= prior["delta"] < 0.0


def test_a_single_verdict_is_damped_and_apply_updates_case_metadata(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "knowledge.duckdb")
    _record(store, "true_positive", 1.0)
    cases = [
        {
            "case_id": "case-candidate",
            "index_name": "hb_ait_santos",
            "score": 2.0,
            "rank": 0,
            "behaviour_sig": SIGNATURE,
            "family": "ait",
            "entity_key": "actor",
        }
    ]

    adjusted = apply_verdict_priors(cases, store=store, enabled=True)

    assert adjusted is not cases
    assert adjusted[0]["verdict_support"] == 1
    assert 0.0 < adjusted[0]["verdict_prior_delta"] <= 0.05
    assert adjusted[0]["score"] == pytest.approx(2.0 + adjusted[0]["verdict_prior_delta"])


@pytest.mark.parametrize("verdict", ["false_positive", "benign_expected"])
def test_negative_verdicts_reduce_the_prior(verdict: str, tmp_path: Path) -> None:
    store = _store(tmp_path / f"{verdict}.duckdb")
    _record(store, verdict, 1.0)

    prior = query_verdict_priors(
        store=store,
        index_name="hb_ait_santos",
        family="ait",
        entity_key="actor",
        behaviour_sig=SIGNATURE,
    )

    assert -0.25 <= prior["delta"] < 0.0


def test_proof_index_writes_are_refused(tmp_path: Path) -> None:
    store = _store(tmp_path / "knowledge.duckdb")

    with pytest.raises(ValueError, match="proof index"):
        _record(store, "true_positive", index_name="botsv1")


def test_static_ioc_values_cannot_become_behaviour_signatures(tmp_path: Path) -> None:
    store = _store(tmp_path / "knowledge.duckdb")

    with pytest.raises(ValueError, match="generalized category"):
        record_verdict(
            store=store,
            index_name="hb_ait_santos",
            case_id="case-1",
            entity_key="actor",
            behaviour_sig={"sourcetypes": ["192.168.1.10"]},
            verdict="true_positive",
            confidence=1.0,
            rationale="reviewed",
            source="operator",
            family="ait",
        )


def test_test_only_proof_write_never_enters_a_prior(tmp_path: Path) -> None:
    store = _store(tmp_path / "knowledge.duckdb")
    _record(store, "true_positive", index_name="botsv1", allow_proof_for_tests=True)

    prior = query_verdict_priors(
        store=store,
        index_name="hb_ait_santos",
        family="ait",
        entity_key="actor",
        behaviour_sig=SIGNATURE,
    )

    assert prior == {"delta": 0.0, "support": 0}


def test_knowledge_store_rebuild_preserves_verdict_history(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.duckdb"
    item = KnowledgeItem(
        statement="actor=service action=login",
        label="login-step",
        label_kind="known_bad",
        label_basis="attack_step",
        family="ait",
        split="build",
        index="santos",
        source_kind="activity",
        query='search index="santos" TERM("login")',
    )
    build_store([item], _Embedder(), store)
    _record(store, "true_positive")

    build_store([item], _Embedder(), store)

    prior = query_verdict_priors(
        store=store,
        index_name="hb_ait_santos",
        family="ait",
        entity_key="actor",
        behaviour_sig=SIGNATURE,
    )
    assert prior["support"] == 1
    assert float(prior["delta"]) > 0.0


def test_apply_does_not_consult_training_priors_for_proof_cases(tmp_path: Path) -> None:
    store = _store(tmp_path / "knowledge.duckdb")
    _record(store, "true_positive")
    cases = [
        {
            "case_id": "proof-case",
            "index_name": "botsv1",
            "score": 1.0,
            "behaviour_sig": SIGNATURE,
            "family": "ait",
            "entity_key": "actor",
        }
    ]

    adjusted = apply_verdict_priors(cases, store=store, enabled=True)

    assert adjusted[0]["score"] == 1.0
    assert "verdict_prior_delta" not in adjusted[0]
