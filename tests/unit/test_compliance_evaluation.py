"""Property 4: the approved mappings are the evaluation set they were declared
to be (SUBSTRATE_PROPERTIES_V1 P5).

The scorer measures citation behaviour only, over the labelled set the mapping
store already owns. An empty labelled set is honest-BLOCKED, never a zero. And
the scorer is an offline instrument: nothing in the product path imports it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from portal.modules.compliance.core import evaluation
from portal.modules.compliance.core.models import RelationshipAssertion
from portal.modules.compliance.core.repository import Repository

EVALUATION_PATH = Path(evaluation.__file__)


def _link(
    repo: Repository,
    ref: str,
    section_id: str,
    *,
    status: str = "approved",
    review_state: str = "CONFIRMED",
    decided_by: str = "sme-1",
    corrected_coverage: str | None = None,
) -> None:
    rel = RelationshipAssertion(
        assertion_id="",
        relation_type="IMPLEMENTS",
        src_ref=ref,
        src_revision_id=None,
        dst_ref=f"LSPG/procedure.pdf::{section_id}",
        dst_revision_id=None,
        scope="",
        citations=[],
        status=status,
        review_state=review_state,
        coverage="FULL",
        proposed_coverage="FULL",
        confidence=0.9,
    )
    saved = repo.propose_relationship(rel)
    if status in ("approved", "rejected", "revoked"):
        repo.decide_relationship(
            saved.assertion_id,
            review_state if status == "approved" else status.upper(),
            decided_by,
            expected_version=saved.version,
            corrected_coverage=corrected_coverage,
        )


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    r = Repository(tmp_path / "eval.db")
    _link(r, "CIP-007-6 R2 Part 2.2", "isection-aaaa1111")
    _link(r, "CIP-007-6 R2 Part 2.2", "isection-bbbb2222")
    _link(
        r,
        "CIP-007-6 R2 Part 2.2",
        "isection-cccc3333",
        status="rejected",
        review_state="REJECTED",
    )
    _link(
        r,
        "CIP-007-6 R2 Part 2.1",
        "isection-dddd4444",
        review_state="CORRECTED",
        corrected_coverage="PARTIAL",
    )
    yield r
    r.close()


def _reading(sections: list[str], ref: str = "CIP-007-6 R2 Part 2.2") -> dict:
    return {
        "ref": ref,
        "answer": "...",
        "verification": {"citations": [{"cited_ref": s, "resolved": True} for s in sections]},
    }


class TestLabelledExamples:
    def test_settled_mappings_export_with_their_labels(self, repo: Repository) -> None:
        examples = evaluation.labelled_examples(repo)
        by_ref = {e["requirement_id"]: e for e in examples}
        part22 = by_ref["CIP-007-6 R2 Part 2.2"]
        assert part22["settled_sections"] == ["isection-aaaa1111", "isection-bbbb2222"]
        assert part22["rejected_sections"] == ["isection-cccc3333"]
        assert part22["approved_by"] == "sme-1"
        # The decision date is when the decision was MADE — `decide_relationship`
        # stamps it and deliberately takes no override, because a back-datable
        # approval is not an audit trail. Asserting a literal here only worked on
        # the day the test was written.
        assert part22["approved_date"] == datetime.now(UTC).strftime("%Y-%m-%d")
        part21 = by_ref["CIP-007-6 R2 Part 2.1"]
        assert part21["correction"] is True, "a corrected mapping is the sharpest label"

    def test_the_eval_set_shape_carries_labels_and_negatives(self, repo: Repository) -> None:
        eval_set = evaluation.as_eval_set(evaluation.labelled_examples(repo))
        assert eval_set["eval_set"] == "compliance_requirement_sections"
        assert eval_set["n_examples"] == len(eval_set["examples"]) == 2
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

    def test_proposed_rows_only_with_an_explicit_widening(self, repo: Repository) -> None:
        _link(repo, "CIP-007-6 R2 Part 3.1", "isection-eeee5555", status="proposed")
        assert all(
            e["requirement_id"] != "CIP-007-6 R2 Part 3.1"
            for e in evaluation.labelled_examples(repo)
        )
        widened = evaluation.labelled_examples(repo, min_status="proposed")
        assert any(e["requirement_id"] == "CIP-007-6 R2 Part 3.1" for e in widened)


class TestScoreReading:
    def test_citing_exactly_the_mapped_sections_scores_recall_one(self, repo: Repository) -> None:
        examples = evaluation.labelled_examples(repo)
        score = evaluation.score_reading(
            _reading(["isection-aaaa1111", "isection-bbbb2222"]), examples
        )
        assert score["verdict"] == "scored"
        assert score["citation_recall"] == 1.0
        assert score["citation_precision"] == 1.0
        assert score["unlabelled"] == []
        assert score["rejected_cited"] == []

    def test_an_unmapped_citation_is_unlabelled_not_wrong(self, repo: Repository) -> None:
        examples = evaluation.labelled_examples(repo)
        score = evaluation.score_reading(
            _reading(["isection-aaaa1111", "isection-zzzz9999"]), examples
        )
        # recall only counts what it missed; the extra citation is not a
        # precision miss because the mapping set is incomplete by construction
        assert score["citation_recall"] == 0.5
        assert score["citation_precision"] == 1.0
        assert score["unlabelled"] == ["isection-zzzz9999"]

    def test_citing_a_rejected_mapping_is_flagged_by_name(self, repo: Repository) -> None:
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
