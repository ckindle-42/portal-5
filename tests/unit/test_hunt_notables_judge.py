from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.hunt.notables.judge_notables import (
    JUDGE_PROMPT_CHARS,
    CaseFacts,
    judge_cases,
    notable_prompt,
)


def _notable(key: str = "k1") -> dict[str, object]:
    return {
        "notable_id": key,
        "generator": "peer_rare",
        "basis": "behaviour_share",
        "what": "actor bob did cmd.exe to a shape",
        "entities": [{"role": "actor", "value": "bob"}],
        "source_id": "ix:st",
        "why": "on 1/20 hosts",
        "content_key": key,
        "evidence": [{"line": f"example {index}"} for index in range(5)],
    }


def test_notable_prompt_is_compact_and_carries_the_statement_and_examples():
    prompt = notable_prompt(_notable())
    assert "actor bob did cmd.exe" in prompt
    assert "actor=bob" in prompt
    assert "example 0" in prompt
    assert "example 2" in prompt
    assert "example 3" not in prompt
    assert len(prompt) <= JUDGE_PROMPT_CHARS


def test_a_case_with_an_unverified_anchor_is_reported_unverified(tmp_path: Path) -> None:
    case = {
        "case_id": "c1",
        "anchor_entity": "value",
        "members": [{"type": "episode", "id": "missing-0", "value": "value"}],
    }
    empty = CaseFacts({}, {}, {})
    cases, receipt = judge_cases(
        [case], out=tmp_path, client=None, model="", facts=empty, notables={}, request_budget=0
    )
    assert cases[0]["verified"] is False
    assert cases[0]["verification"] == "unverified"
    assert cases[0]["verify_reason"] == "episode_missing"
    assert receipt["unverified"] == 1 and receipt["judged"] == 0

    facts = CaseFacts({"e1": ("value in the stored row", "ix:st")}, {}, {"ep1": ("e1",)})
    verified, _receipt = judge_cases(
        [{**case, "members": [{"type": "episode", "id": "ep1", "value": "value"}]}],
        out=tmp_path,
        client=None,
        model="",
        facts=facts,
        notables={},
        request_budget=0,
    )
    assert verified[0]["verified"] is True and verified[0]["verification"] == "verified"
