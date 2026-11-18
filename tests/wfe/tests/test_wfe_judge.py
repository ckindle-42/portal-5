"""The blind pairwise judge: local by default, order randomised, labels hidden, reported
beside the pass rates and never read by the decision rule."""

from __future__ import annotations

import json

import pytest

from tests.wfe import judge

WS, SUITE, TASK = "auto-general", "realuse", "realuse-01"

INC, CAND = "inc:tag", "cand:tag"


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

    def test_the_committed_yaml_is_the_default_and_env_overrides(self, monkeypatch):
        """tests/wfe/judge.yaml is the judge when no env is set; env still wins."""
        monkeypatch.delenv("WFE_JUDGE_MODEL", raising=False)
        monkeypatch.delenv("WFE_JUDGE_URL", raising=False)
        cfg = judge._judge_config()
        assert cfg.get("model") and cfg.get("url")
        assert judge.judge_model() == cfg["model"]
        assert judge.judge_url() == cfg["url"]
        judge.assert_local(judge.judge_url())
        monkeypatch.setenv("WFE_JUDGE_MODEL", "env:tag")
        monkeypatch.setenv("WFE_JUDGE_URL", "http://localhost:11434")
        assert judge.judge_model() == "env:tag"
        assert judge.judge_url() == "http://localhost:11434"

    def test_no_model_configured_anywhere_is_an_error(self, monkeypatch, tmp_path):
        monkeypatch.delenv("WFE_JUDGE_MODEL", raising=False)
        monkeypatch.setattr(judge, "JUDGE_CONFIG_PATH", tmp_path / "absent.yaml")
        with pytest.raises(ValueError, match="WFE_JUDGE_MODEL"):
            judge.judge_model()


class TestParsing:
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
