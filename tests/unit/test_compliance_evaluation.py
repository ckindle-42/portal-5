"""Property 4, after the split (PROVE_THEN_SCALE_V1 P6).

The scorer measures citation behaviour only, over the HUMAN-CONFIRMED SAMPLE
and nothing else. The operational machine_determined set is never the ground
truth — measuring determinations against determinations would report a
system's agreement with itself. An empty or undecided sample is honest-BLOCKED,
never a zero. And the scorer is an offline instrument: nothing in the product
path imports it.
"""

from __future__ import annotations

from portal.modules.compliance.core import evaluation


def _reading(sections: list[str], ref: str = "CIP-007-6 R2 Part 2.2") -> dict:
    return {
        "ref": ref,
        "answer": "...",
        "verification": {"citations": [{"cited_ref": s, "resolved": True} for s in sections]},
    }


class TestScoreReading:
    def test_an_empty_labelled_set_is_honest_blocked_never_zero(self) -> None:
        score = evaluation.score_reading(_reading(["isection-aaaa1111"]), [])
        assert score["verdict"] == "honest-BLOCKED"
        assert "empty" in score["reason"]
        assert score["citation_recall"] is None
        assert score["citation_precision"] is None
