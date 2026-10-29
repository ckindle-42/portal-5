"""The blind pairwise judge: local by default, order randomised, labels hidden, reported
beside the pass rates and never read by the decision rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.wfe import judge
from tests.wfe import report as rep

WS, SUITE, TASK = "auto-general", "realuse", "realuse-01"
INC, CAND = "inc:tag", "cand:tag"


@pytest.fixture
def campaign(tmp_path):
    """One two-arm task with a rubric, and a recorded row per arm."""
    suite = tmp_path / "suites" / f"{SUITE}.jsonl"
    suite.parent.mkdir()
    suite.write_text(
        json.dumps(
            {
                "id": TASK,
                "workspace": WS,
                "category": "ops",
                "source": "operator",
                "rubric": ["answers the question", "does not invent a source"],
                "turns": [
                    {
                        "user": "what changed?",
                        "checks": [{"type": "answer_contains", "patterns": ["x"]}],
                    }
                ],
            }
        )
        + "\n"
    )
    d = tmp_path / "campaigns" / "c1"
    (d / "rows").mkdir(parents=True)
    manifest = {
        "campaign_id": "c1",
        "env": {"fingerprint": "fp"},
        "instrument": {"fingerprint": "fp"},
        "rows": [
            {
                "run_id": f"{WS}|{INC}|{SUITE}|{TASK}|r0",
                "workspace": WS,
                "arm": INC,
                "model": INC,
                "arm_role": "incumbent",
                "suite": SUITE,
                "suite_path": str(suite),
                "task_id": TASK,
                "repeat": 0,
                "is_home": True,
                "state": "PASS",
            },
            {
                "run_id": f"{WS}|{CAND}|{SUITE}|{TASK}|r0",
                "workspace": WS,
                "arm": CAND,
                "model": CAND,
                "arm_role": "challenger",
                "suite": SUITE,
                "suite_path": str(suite),
                "task_id": TASK,
                "repeat": 0,
                "is_home": True,
                "state": "PASS",
            },
        ],
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    for i, (arm, text) in enumerate(
        ((INC, "the answer from the incumbent"), (CAND, "the challenger answer"))
    ):
        (d / "rows" / f"{i}.json").write_text(
            json.dumps(
                {
                    "run_id": f"{WS}|{arm}|{SUITE}|{TASK}|r0",
                    "workspace": WS,
                    "arm": arm,
                    "arm_role": "incumbent" if arm == INC else "challenger",
                    "suite": SUITE,
                    "task_id": TASK,
                    "repeat": 0,
                    "outcome": "PASS",
                    "final_text": text,
                    "transcript": [{"turn": 0, "scripted_turn": 0, "content": text}],
                }
            )
        )
    return d


def _verdict(preference="A", reason="more specific"):
    return json.dumps({"preference": preference, "reason": reason})


class TestEndpointPolicy:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://192.168.0.9:11434",
            "http://10.1.2.3:11434",
            "http://p40:11434",
            "http://judge.local:11434",
        ],
    )
    def test_local_and_lan_endpoints_are_allowed(self, url):
        assert judge.endpoint_is_local(url)
        judge.assert_local(url)

    @pytest.mark.parametrize(
        "url",
        ["https://api.openai.com/v1", "https://api.anthropic.com", "https://8.8.8.8:11434"],
    )
    def test_public_endpoints_are_not_a_default(self, url):
        assert not judge.endpoint_is_local(url)
        with pytest.raises(ValueError, match="not a local/LAN host"):
            judge.assert_local(url)

    def test_an_explicit_override_allows_a_remote_endpoint(self, monkeypatch):
        monkeypatch.setenv("WFE_JUDGE_ALLOW_REMOTE", "1")
        judge.assert_local("https://api.openai.com/v1")

    def test_no_model_configured_is_an_error(self, monkeypatch):
        monkeypatch.delenv("WFE_JUDGE_MODEL", raising=False)
        with pytest.raises(ValueError, match="WFE_JUDGE_MODEL"):
            judge.judge_model()


class TestParsing:
    def test_ask_judge_posts_to_the_ollama_chat_api(self, monkeypatch):
        """The one network call: the Ollama /api/chat body, temperature 0, and the reply
        read from message.content."""
        seen = {}

        class _Resp:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=0):
            seen.update(url=req.full_url, body=json.loads(req.data), timeout=timeout)
            body = {"message": {"content": json.dumps({"preference": "B", "reason": "ok"})}}
            return _Resp(json.dumps(body).encode())

        monkeypatch.setattr(judge.urllib.request, "urlopen", fake_urlopen)
        out = judge.ask_judge([{"role": "user", "content": "hi"}], "judge:tag", "http://p40:11434/")
        assert seen["url"] == "http://p40:11434/api/chat"
        assert seen["body"]["model"] == "judge:tag" and seen["body"]["stream"] is False
        assert seen["body"]["options"] == {"temperature": 0, "seed": 7}
        assert judge.parse_verdict(out) == ("B", "ok")

    def test_json_object(self):
        assert judge.parse_verdict('{"preference": "B", "reason": "clearer"}') == ("B", "clearer")

    def test_json_object_inside_prose(self):
        text = 'Here it is: {"preference": "tie", "reason": "both fine"} — done.'
        assert judge.parse_verdict(text) == ("tie", "both fine")

    def test_bare_token(self):
        assert judge.parse_verdict("Preference: A")[0] == "A"

    def test_unparseable_reply_raises(self):
        with pytest.raises(ValueError):
            judge.parse_verdict("I cannot compare these.")

    def test_a_reply_without_a_preference_key_falls_through_to_the_token(self):
        assert judge.parse_verdict('{"reason": "B is better"}')[0] == "B"


class TestJudgeCampaign:
    def test_a_pair_is_judged_once_labels_hidden_and_the_winner_mapped(self, campaign, monkeypatch):
        seen = []

        def fake_ask(messages, model, url, timeout=0):
            seen.append(messages)
            return _verdict("A")

        monkeypatch.setattr(judge, "ask_judge", fake_ask)
        monkeypatch.setattr(judge, "order_flipped", lambda key: False)
        res = judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        assert (res["judged"], res["skipped"], res["errors"], res["pairs"]) == (1, 0, 0, 1)
        prompt = json.dumps(seen[0])
        assert INC not in prompt and CAND not in prompt
        assert "answers the question" in prompt
        rec = json.loads(next((campaign / "judgements").glob("*.json")).read_text())
        assert rec["arms"] == {"A": CAND, "B": INC}
        assert rec["winner"] == CAND and rec["preference"] == "A"
        assert rec["rubric_sha"] and rec["judge_model"] == "judge:tag"

    def test_the_order_flip_is_mapped_back(self, campaign, monkeypatch):
        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: _verdict("B"))
        monkeypatch.setattr(judge, "order_flipped", lambda key: True)
        judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        rec = json.loads(next((campaign / "judgements").glob("*.json")).read_text())
        assert rec["arms"] == {"A": INC, "B": CAND}
        assert rec["winner"] == CAND

    def test_a_tie_records_no_winner(self, campaign, monkeypatch):
        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: _verdict("tie", "equal"))
        judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        rec = json.loads(next((campaign / "judgements").glob("*.json")).read_text())
        assert rec["winner"] is None and rec["preference"] == "tie"

    def test_a_second_pass_re_asks_nothing(self, campaign, monkeypatch):
        calls = []
        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: calls.append(1) or _verdict("A"))
        judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        res = judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        assert len(calls) == 1 and res["skipped"] == 1 and res["judged"] == 0

    def test_a_judge_error_is_recorded_and_retried(self, campaign, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("judge unreachable")

        monkeypatch.setattr(judge, "ask_judge", boom)
        res = judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        assert res["errors"] == 1
        rec = json.loads(next((campaign / "judgements").glob("*.json")).read_text())
        assert "judge unreachable" in rec["error"] and rec["winner"] is None

        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: _verdict("A"))
        res = judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        assert res["judged"] == 1 and res["skipped"] == 0

    def test_a_task_without_a_rubric_is_not_judged(self, campaign, monkeypatch):
        suite = Path(campaign / "suite.jsonl")
        suite.write_text(json.dumps({"id": TASK, "instruction": "x"}) + "\n")
        manifest = json.loads((campaign / "manifest.json").read_text())
        for row in manifest["rows"]:
            row["suite_path"] = str(suite)
        (campaign / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: _verdict("A"))
        res = judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        assert res["pairs"] == 0 and res["judged"] == 0

    def test_an_instrument_row_is_never_judged(self, campaign, monkeypatch):
        for f in (campaign / "rows").glob("*.json"):
            d = json.loads(f.read_text())
            if d["arm"] == CAND:
                d["outcome"] = "HARNESS_ERROR"
                f.write_text(json.dumps(d))
        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: _verdict("A"))
        assert judge.judge_campaign(campaign, model="m", url="http://localhost:11434")["pairs"] == 0


class TestReportShowsPreferences:
    def test_the_comparison_carries_the_blind_preference_beside_the_rates(
        self, campaign, monkeypatch
    ):
        monkeypatch.setattr(judge, "ask_judge", lambda *a, **k: _verdict("A"))
        judge.judge_campaign(campaign, model="judge:tag", url="http://localhost:11434")
        rep_report = rep.build(campaign)
        comparison = rep_report["comparisons"][0]
        assert comparison["challenger"] == CAND
        assert comparison["judge"] == "1W/0L/0T"
        assert rep_report["judge"]["records"] == 1
        text = rep.render_markdown(rep_report)
        assert "Judge (blind)" in text and "1W/0L/0T" in text
        assert "not gated" in text

    def test_without_judgements_the_column_is_empty(self, campaign):
        rep_report = rep.build(campaign)
        assert rep_report["comparisons"][0]["judge"] == "—"
