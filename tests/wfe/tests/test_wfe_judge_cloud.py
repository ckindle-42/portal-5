"""Tests for tests/wfe/judge_cloud.py — all mock, no network."""

from __future__ import annotations

import json

import pytest

from tests.wfe import judge_cloud as cloud


class TestCloudConfig:
    def test_cloud_yaml_is_read(self, monkeypatch):
        monkeypatch.delenv("WFE_JUDGE_CLOUD_MODEL", raising=False)
        monkeypatch.delenv("WFE_JUDGE_CLOUD_URL", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        assert cloud.cloud_url() == "https://api.deepseek.com/v1"
        assert cloud.cloud_model() == "deepseek-v4.1-flash"

    def test_env_overrides_yaml(self, monkeypatch):
        monkeypatch.setenv("WFE_JUDGE_CLOUD_MODEL", "env-model")
        monkeypatch.setenv("WFE_JUDGE_CLOUD_URL", "http://localhost:9999")
        assert cloud.cloud_model() == "env-model"
        assert cloud.cloud_url() == "http://localhost:9999"

    def test_no_model_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv("WFE_JUDGE_CLOUD_MODEL", raising=False)
        monkeypatch.setattr(cloud, "CLOUD_CONFIG_PATH", tmp_path / "absent.yaml")
        with pytest.raises(ValueError, match="no cloud judge model"):
            cloud.cloud_model()

    def test_no_api_key_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(cloud, "CLOUD_CONFIG_PATH", tmp_path / "absent.yaml")
        with pytest.raises(ValueError, match="no cloud API key"):
            cloud.cloud_api_key()


class TestAskCloudJudge:
    def test_posts_to_openai_compatible_api(self, monkeypatch):
        seen = {}

        class _Resp:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": '{"preference":"A","reason":"x"}'}}]}
                ).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=0):
            seen["url"] = req.full_url
            seen["headers"] = dict(req.headers)
            seen["body"] = json.loads(req.data)
            return _Resp()

        monkeypatch.setattr(cloud.urllib.request, "urlopen", fake_urlopen)
        out = cloud.ask_cloud_judge(
            [{"role": "user", "content": "hi"}],
            "test-model",
            "https://example.com/v1",
            "key123",
            timeout=1,
        )
        assert seen["url"] == "https://example.com/v1/chat/completions"
        assert seen["body"]["model"] == "test-model"
        assert seen["body"]["temperature"] == 0
        assert seen["headers"]["Authorization"] == "Bearer key123"
        assert cloud.parse_cloud_verdict(out) == ("A", "x")


class TestRefuseCloudForSecurity:
    def test_security_suites_are_refused(self, tmp_path):
        campaign = tmp_path / "sec-camp"
        campaign.mkdir()
        (campaign / "manifest.json").write_text(
            json.dumps({"rows": [{"suite": "realuse_security_01"}]})
        )
        with pytest.raises(ValueError, match="refusing cloud judge"):
            cloud.refuse_cloud_for_security(campaign)

    def test_compliance_suites_are_refused(self, tmp_path):
        campaign = tmp_path / "camp"
        campaign.mkdir()
        (campaign / "manifest.json").write_text(json.dumps({"rows": [{"suite": "x_compliance_y"}]}))
        with pytest.raises(ValueError, match="refusing cloud judge"):
            cloud.refuse_cloud_for_security(campaign)

    def test_detection_suites_are_refused(self, tmp_path):
        campaign = tmp_path / "camp"
        campaign.mkdir()
        (campaign / "manifest.json").write_text(json.dumps({"rows": [{"suite": "x_detection_y"}]}))
        with pytest.raises(ValueError, match="refusing cloud judge"):
            cloud.refuse_cloud_for_security(campaign)

    def test_ok_suites_pass_through(self, tmp_path):
        campaign = tmp_path / "camp"
        campaign.mkdir()
        (campaign / "manifest.json").write_text(json.dumps({"rows": [{"suite": "realuse_ops_01"}]}))
        cloud.refuse_cloud_for_security(campaign)  # no raise

    def test_empty_rows_pass_through(self, tmp_path):
        campaign = tmp_path / "camp"
        campaign.mkdir()
        (campaign / "manifest.json").write_text(json.dumps({"rows": []}))
        cloud.refuse_cloud_for_security(campaign)  # no raise
