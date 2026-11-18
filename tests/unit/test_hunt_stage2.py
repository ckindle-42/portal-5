from __future__ import annotations

from typing import Any

import pytest

from portal.modules.security.core.hunt.notables import stage2
from portal.modules.security.core.hunt.notables.stage2 import (
    judge_council,
    parse_council,
)

FIRST = 1616529600.0  # 2021-03-23T20:00:00Z

SOURCE = "/apache2/access.log.4"


def _stamp(moment: float) -> str:
    return stage2.time.strftime("%d/%b/%Y:%H:%M:%S", stage2.time.gmtime(moment))


def _line(term: str, moment: float = FIRST + 60.0) -> str:
    return f'10.0.0.5 - - [{_stamp(moment)} +0000] "GET /{term} HTTP/1.1" 200 12 "-" "curl"'


def _notable(key: str, term: str, generator: str, value: float) -> dict[str, Any]:
    query = f'search index="hb_kyoushi_s1" (source="{SOURCE}") TERM("{term}")'
    return {
        "notable_id": key,
        "generator": generator,
        "basis": "behaviour_share",
        "what": f"actor 10.0.0.5 did {term}",
        "why": "on 1/20 hosts",
        "content_key": key,
        "source_id": f"hb_kyoushi_s1:{SOURCE.rsplit('/', 1)[-1]}",
        "entities": [{"role": "actor", "value": "10.0.0.5"}],
        "measure": {"name": "similarity", "value": value},
        "evidence": [
            {"line": _line(term), "query": query, "earliest": FIRST, "latest": FIRST + 3600.0}
        ],
    }


def _council_response(bad: bool) -> dict[str, Any]:
    recommendation = "SUPPORT" if bad else "REJECT"
    votes = (
        {"SUPPORT": 3, "REVISE": 0, "REJECT": 0}
        if bad
        else {
            "SUPPORT": 0,
            "REVISE": 0,
            "REJECT": 3,
        }
    )
    return {
        "choices": [{"message": {"content": f"**Code-determined decision: {recommendation}**"}}],
        "portal_council": {
            "aggregate": {
                "decision": recommendation,
                "votes": votes,
                "participating": 3,
                "roster": 3,
            },
            "reviewers": [
                {
                    "member_id": f"seat{index}",
                    "recommendation": recommendation,
                    "confidence": 0.9,
                    "valid": True,
                    "error": "",
                }
                for index in range(3)
            ],
        },
    }


def test_parse_council_scores_the_vote_fraction_and_keeps_the_decision():
    result = parse_council(_council_response(True), 1.5)
    assert result.p_yes == pytest.approx(1.0)
    assert result.decision == "SUPPORT"
    assert result.votes == {"SUPPORT": 3, "REVISE": 0, "REJECT": 0}
    assert result.participating == 3 and result.roster == 3
    assert len(result.seats) == 3
    assert result.reason is None
    mixed = parse_council(
        {
            "portal_council": {
                "aggregate": {
                    "decision": "ESCALATE",
                    "votes": {"SUPPORT": 1, "REVISE": 1, "REJECT": 1},
                    "participating": 3,
                    "roster": 3,
                }
            }
        },
        0.5,
    )
    assert mixed.p_yes == pytest.approx(0.5)
    assert mixed.decision == "ESCALATE"


def test_parse_council_without_decisive_votes_or_block_is_unjudged():
    abstain = parse_council(
        {
            "portal_council": {
                "aggregate": {
                    "decision": "ESCALATE",
                    "votes": {"SUPPORT": 0, "REVISE": 0, "REJECT": 0},
                    "participating": 0,
                    "roster": 3,
                }
            }
        },
        0.5,
    )
    assert abstain.p_yes is None and abstain.reason == "no_decisive_votes"
    missing = parse_council({"choices": [{"message": {"content": "plain answer"}}]}, 0.5)
    assert missing.p_yes is None and missing.reason == "missing_council_block"


def test_judge_council_transport_failure_is_unjudged():
    class _Down:
        def complete(self, **request: Any) -> dict[str, Any]:
            raise RuntimeError("down")

    result = judge_council(_Down(), "auto-council", _notable("kb", "badterm", "peer_rare", 0.0))
    assert result.p_yes is None and result.reason == "request_failed"
