"""Property 4, after the split (PROVE_THEN_SCALE_V1 P6).

The scorer measures citation behaviour only, over the HUMAN-CONFIRMED SAMPLE
and nothing else. The operational machine_determined set is never the ground
truth — measuring determinations against determinations would report a
system's agreement with itself. An empty or undecided sample is honest-BLOCKED,
never a zero. And the scorer is an offline instrument: nothing in the product
path imports it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from portal.modules.compliance.core import evaluation
from portal.modules.compliance.core.models import RelationshipAssertion
from portal.modules.compliance.core.repository import Repository

EVALUATION_PATH = Path(evaluation.__file__)


def _determined(
    repo: Repository,
    ref: str,
    section_id: str,
    *,
    relation_type: str = "IMPLEMENTS",
    confidence: float = 0.9,
) -> str:
    rel = RelationshipAssertion(
        assertion_id="",
        relation_type=relation_type,
        src_ref=ref,
        src_revision_id=None,
        dst_ref=f"LSPG/procedure.pdf::{section_id}",
        dst_revision_id=None,
        scope="",
        citations=[{"answer_id": "answer-test", "sentence": "test"}],
        status="machine_determined",
        review_state="machine_determined",
        coverage="",
        proposed_coverage="",
        confidence=confidence,
        derivation="reading",
    )
    return repo.propose_relationship(rel).assertion_id


def _sampled(repo: Repository, ref: str, section_id: str, **kwargs) -> str:
    assertion_id = _determined(repo, ref, section_id, **kwargs)
    row = repo._conn.execute(
        "SELECT sample_id FROM evaluation_sample WHERE assertion_id = ?", (assertion_id,)
    ).fetchone()
    if row is None:
        selection = evaluation.select_sample(repo, n=50, seed=f"test|{ref}|{section_id}")
        assert selection["selected"] >= 1, "the fixture row must be selectable"
        row = repo._conn.execute(
            "SELECT sample_id FROM evaluation_sample WHERE assertion_id = ?", (assertion_id,)
        ).fetchone()
    return str(row[0])


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "eval.db")
    confirmed_a = _sampled(r, "CIP-007-6 R2 Part 2.2", "isection-aaaa1111")
    confirmed_b = _sampled(r, "CIP-007-6 R2 Part 2.2", "isection-bbbb2222", confidence=0.6)
    evaluation.record_sample_decision(r, confirmed_a, "CONFIRMED", decided_by="sme-1")
    evaluation.record_sample_decision(r, confirmed_b, "CONFIRMED", decided_by="sme-1")
    rejected = _sampled(r, "CIP-007-6 R2 Part 2.2", "isection-cccc3333", confidence=0.3)
    evaluation.record_sample_decision(r, rejected, "REJECTED", decided_by="sme-1")
    corrected = _sampled(r, "CIP-007-6 R2 Part 2.1", "isection-dddd4444", relation_type="EVIDENCES")
    evaluation.record_sample_decision(
        r, corrected, "CORRECTED", human_relation="IMPLEMENTS", decided_by="sme-1"
    )
    yield r
    r.close()


def _reading(sections: list[str], ref: str = "CIP-007-6 R2 Part 2.2") -> dict:
    return {
        "ref": ref,
        "answer": "...",
        "verification": {"citations": [{"cited_ref": s, "resolved": True} for s in sections]},
    }


class TestTheSampleIsTheEvaluationSet:
    def test_confirmed_and_corrected_sections_settle_rejected_are_negatives(
        self, repo: Repository
    ) -> None:
        examples = evaluation.labelled_examples(repo)
        by_ref = {e["requirement_id"]: e for e in examples}
        part22 = by_ref["CIP-007-6 R2 Part 2.2"]
        assert part22["settled_sections"] == ["isection-aaaa1111", "isection-bbbb2222"]
        assert part22["rejected_sections"] == ["isection-cccc3333"]
        assert part22["approved_by"] == "sme-1"
        # The decision date is when the decision was MADE — recorded by
        # record_sample_decision at decision time.
        assert part22["approved_date"] == datetime.now(UTC).strftime("%Y-%m-%d")
        part21 = by_ref["CIP-007-6 R2 Part 2.1"]
        assert part21["correction"] is True, "a corrected mapping is the sharpest label"

    def test_the_operational_set_never_leaks_into_the_evaluation_set(
        self, repo: Repository
    ) -> None:
        # a determined row that was never sampled and never decided is not a
        # label, whatever the widening
        _determined(repo, "CIP-007-6 R2 Part 3.1", "isection-eeee5555")
        examples = evaluation.labelled_examples(repo)
        assert all(e["requirement_id"] != "CIP-007-6 R2 Part 3.1" for e in examples), (
            "an approved-in-passing determined row must not become ground truth"
        )
        # a row SELECTED into the sample but not yet decided widens as pending,
        # never as a label (the selection may also pick up the Part 3.1 row
        # from above — it must then appear as PENDING too, still not a label)
        _sampled(repo, "CIP-007-6 R2 Part 3.2", "isection-ffff6666")  # selected, undecided
        widened = evaluation.labelled_examples(repo, min_status="proposed")
        for pending_ref in ("CIP-007-6 R2 Part 3.1", "CIP-007-6 R2 Part 3.2"):
            pending = [e for e in widened if e["requirement_id"] == pending_ref]
            assert pending and all(
                e["settled_sections"] == [] and e["rejected_sections"] == [] for e in pending
            ), f"{pending_ref} widened as PENDING, not as a label"

    def test_the_eval_set_shape_carries_labels_and_negatives(self, repo: Repository) -> None:
        eval_set = evaluation.as_eval_set(evaluation.labelled_examples(repo))
        assert eval_set["eval_set"] == "compliance_requirement_sections"
        assert eval_set["n_examples"] == len(eval_set["examples"]) == 2
        assert eval_set["label_source"] == "evaluation_sample"
        example = eval_set["examples"][0]
        assert set(example) == {
            "requirement_id",
            "expected_sections",
            "rejected_sections",
            "approved_by",
            "approved_date",
            "correction",
            "label_source",
        }

    def test_agreement_is_the_mapping_accuracy_number(self, repo: Repository) -> None:
        report = evaluation.agreement(repo)
        assert report["verdict"] == "scored"
        assert report["n_decided"] == 4
        assert report["n_confirmed"] == 2
        assert report["n_corrected"] == 1
        assert report["n_rejected"] == 1
        assert report["agreement_rate"] == 0.5

    def test_an_undecided_sample_is_honest_blocked_not_zero(self, tmp_path: Path) -> None:
        r = Repository(tmp_path / "empty.db")
        try:
            report = evaluation.agreement(r)
            assert report["verdict"] == "honest-BLOCKED"
            assert report["agreement_rate"] is None
        finally:
            r.close()

    def test_selection_is_deterministic_and_never_resamples(self, tmp_path: Path) -> None:
        r = Repository(tmp_path / "sample.db")
        try:
            for i in range(8):
                _determined(
                    r,
                    f"CIP-007-6 R2 Part 2.{(i % 4) + 1}",
                    f"isection-{i:08d}aaaa",
                    confidence=[0.9, 0.6, 0.3][i % 3],
                )
            first = evaluation.select_sample(r, n=6, seed="s")
            second = evaluation.select_sample(r, n=6, seed="s")
            assert first["selected"] == 6
            assert second["selected"] == 2, "a re-run tops up only with UNSAMPLED rows"
            first_ids = {row["assertion_id"] for row in evaluation.sample_rows(r)}
            third = evaluation.select_sample(r, n=6, seed="s")
            assert third["selected"] == 0, "exhausted strata select nothing, never resample"
            rows = evaluation.sample_rows(r)
            assert len(rows) == 8
            assert {row["assertion_id"] for row in rows} == first_ids
            assert len({row["confidence_band"] for row in rows}) > 1, "confidence is a stratum"
        finally:
            r.close()


class TestScoreReading:
    def test_citing_exactly_the_confirmed_sections_scores_recall_one(
        self, repo: Repository
    ) -> None:
        examples = evaluation.labelled_examples(repo)
        score = evaluation.score_reading(
            _reading(["isection-aaaa1111", "isection-bbbb2222"]), examples
        )
        assert score["verdict"] == "scored"
        assert score["citation_recall"] == 1.0
        assert score["citation_precision"] == 1.0
        assert score["unlabelled"] == []
        assert score["rejected_cited"] == []

    def test_an_unsampled_citation_is_unlabelled_not_wrong(self, repo: Repository) -> None:
        examples = evaluation.labelled_examples(repo)
        score = evaluation.score_reading(
            _reading(["isection-aaaa1111", "isection-zzzz9999"]), examples
        )
        # recall only counts what it missed; the extra citation is not a
        # precision miss because the sample is small by construction
        assert score["citation_recall"] == 0.5
        assert score["citation_precision"] == 1.0
        assert score["unlabelled"] == ["isection-zzzz9999"]

    def test_citing_a_sample_rejected_section_is_flagged_by_name(self, repo: Repository) -> None:
        examples = evaluation.labelled_examples(repo)
        score = evaluation.score_reading(
            _reading(["isection-aaaa1111", "isection-cccc3333"]), examples
        )
        assert score["rejected_cited"] == ["isection-cccc3333"]
        assert score["rejected_mapping_avoidance"] is False

    def test_closure_honesty_is_carried_when_present_and_none_otherwise(
        self, repo: Repository
    ) -> None:
        examples = evaluation.labelled_examples(repo)
        plain = evaluation.score_reading(_reading(["isection-aaaa1111"]), examples)
        assert plain["closure_honesty"] is None, "absent is None, never 0"
        carrying = _reading(["isection-aaaa1111"])
        carrying["closure_receipt"] = {"complete": True}
        assert evaluation.score_reading(carrying, examples)["closure_honesty"] == {"complete": True}

    def test_an_empty_labelled_set_is_honest_blocked_never_zero(self) -> None:
        score = evaluation.score_reading(_reading(["isection-aaaa1111"]), [])
        assert score["verdict"] == "honest-BLOCKED"
        assert "empty" in score["reason"]
        assert score["citation_recall"] is None
        assert score["citation_precision"] is None

    def test_a_pending_widening_blocks_per_requirement_not_falsely_scores(
        self, repo: Repository
    ) -> None:
        _sampled(repo, "CIP-007-6 R2 Part 3.1", "isection-eeee5555")  # selected, undecided
        examples = evaluation.labelled_examples(repo, min_status="proposed")
        score = evaluation.score_reading(
            _reading(["isection-eeee5555"], ref="CIP-007-6 R2 Part 3.1"), examples
        )
        assert score["verdict"] == "honest-BLOCKED"
        assert "no confirmed section mapping" in score["reason"]

    def test_an_unknown_requirement_is_honest_blocked_naming_the_shortfall(
        self, repo: Repository
    ) -> None:
        examples = evaluation.labelled_examples(repo)
        score = evaluation.score_reading(
            _reading(["isection-aaaa1111"], ref="CIP-009-6 R1"), examples
        )
        assert score["verdict"] == "honest-BLOCKED"
        assert "CIP-009-6 R1" in score["reason"]
        assert "2 labelled requirement(s)" in score["reason"]

    def test_addresses_are_not_citations(self, repo: Repository) -> None:
        examples = evaluation.labelled_examples(repo)
        payload = _reading(["isection-aaaa1111"])
        payload["verification"]["citations"].append(
            {"cited_ref": "CIP-007-6 R2 Part 2.2", "resolved": True}
        )
        score = evaluation.score_reading(payload, examples)
        assert score["cited"] == ["isection-aaaa1111"]


class TestTheInstrumentIsNotTheVerdict:
    def test_nothing_in_the_product_path_imports_the_scorer(self) -> None:
        portal_root = EVALUATION_PATH.parents[3]
        offenders: list[str] = []
        for path in portal_root.rglob("*.py"):
            if path == EVALUATION_PATH:
                continue
            text = path.read_text(encoding="utf-8")
            if "core.evaluation" in text or "core import evaluation" in text:
                offenders.append(str(path))
        assert offenders == [], (
            "score_reading is an offline instrument over a labelled set — "
            f"the product path must never import it: {offenders}"
        )

    def test_min_status_is_a_closed_vocabulary(self, repo: Repository) -> None:
        with pytest.raises(ValueError):
            evaluation.labelled_examples(repo, min_status="rejected")

    def test_sample_decisions_are_a_closed_vocabulary(self, repo: Repository) -> None:
        sample_id = evaluation.sample_rows(repo)[0]["sample_id"]
        with pytest.raises(ValueError):
            evaluation.record_sample_decision(repo, sample_id, "MAYBE")

    def test_a_correction_without_the_corrected_relation_is_refused(self, repo: Repository) -> None:
        sample_id = evaluation.sample_rows(repo)[0]["sample_id"]
        with pytest.raises(ValueError):
            evaluation.record_sample_decision(repo, sample_id, "CORRECTED")
