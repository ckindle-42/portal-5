from __future__ import annotations

from portal.modules.security.core.hunt.notables.judge_notables import (
    JUDGE_PROMPT_CHARS,
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
