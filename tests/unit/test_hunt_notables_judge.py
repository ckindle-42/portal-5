from __future__ import annotations

from pathlib import Path

from portal.modules.security.core.hunt.notables import similar
from portal.modules.security.core.hunt.notables.behaviours import Behaviour
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.judge_notables import (
    JUDGE_PROMPT_CHARS,
    CaseFacts,
    judge_cases,
    notable_body,
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


def test_the_notable_prompt_carries_the_measure_and_not_the_label(monkeypatch):
    generic = {**_notable(), "measure": {"name": "host_share_x_actor_share", "value": 0.0123}}
    assert "measure: host_share_x_actor_share = 0.0123" in notable_body(generic)

    behaviour = Behaviour(
        source_id="run:activity",
        actor_field="user",
        actor="alice",
        action_field="action",
        action="execute",
        object_field="path",
        object="shell",
        actor_mode="literal",
        action_mode="literal",
        object_mode="literal",
        events=2,
        first_seen=10.0,
        last_seen=20.0,
        hosts=1,
        actors=1,
        example_time=10.0,
        example_query='search index="run" TERM("alice") | head 5',
        example_raw="event line",
        example_earliest=0.0,
        example_latest=60.0,
    )
    card = SourceCard(
        index="run",
        sourcetype="activity",
        kind="activity",
        roles={"actor": ("user",), "action": ("action",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="",
    )
    matches = {
        0: {
            "known_bad": [
                {
                    "label": "escalate",
                    "label_kind": "known_bad",
                    "label_basis": "attack_step",
                    "family": "kyoushi",
                    "similarity": 0.986,
                }
            ],
            "known_good": [
                {
                    "label": "login",
                    "label_kind": "known_good",
                    "label_basis": "routine",
                    "family": "kyoushi",
                    "similarity": 0.876,
                }
            ],
        }
    }
    monkeypatch.setattr(similar, "_matches", lambda _pool, _ids: matches)
    notables, skipped = similar._ranked_notables(
        None,
        [behaviour],
        [card],
        {0: {"known_bad": 0.986, "known_good": 0.876}},
        {"score": "known_bad_minus_good", "auc": 0.443},
    )
    assert skipped == {}
    body = notable_body(notables[0].as_dict())
    assert "margin = 0.11 (threshold 0)" in body
    assert "matched item 0.986 (kyoushi)" in body
    assert "known_bad" not in body and "known-bad" not in body
    assert "escalate" not in body
    assert notables[0].measure_name == "known_bad_minus_good"
    assert "margin 0.110 (threshold 0)" in notables[0].why
    assert "escalate" not in notables[0].why and "known-bad" not in notables[0].why


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
