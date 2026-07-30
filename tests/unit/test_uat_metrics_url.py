"""UAT runner metrics URL — same host-side resolution bug as tests/uat/config.py.

runner.py computed _PIPELINE_METRICS_URL from raw os.environ.get("PIPELINE_URL")
instead of config.PIPELINE_URL, so it inherited .env's compose-internal hostname
unchanged. _snapshot_tool_calls()'s bare except silently swallowed the resulting
connection failure and returned 0.0 unconditionally — before AND after every
test — making every pipeline_tool_called assertion's delta trivially 0
regardless of whether a tool was actually dispatched. This pins the fix.
"""

from __future__ import annotations


def test_metrics_url_derives_from_config_not_raw_environ(monkeypatch) -> None:
    from tests.uat import config, runner

    monkeypatch.setattr(config, "PIPELINE_URL", "http://localhost:9099", raising=True)
    assert runner._PIPELINE_METRICS_URL.startswith("http://localhost:9099")
    assert "portal-pipeline" not in runner._PIPELINE_METRICS_URL


def test_snapshot_tool_calls_hits_config_url(monkeypatch) -> None:
    from tests.uat import runner

    captured: dict[str, str] = {}

    class _FakeResponse:
        text = 'portal5_tool_calls_total{workspace="auto-coding"} 3.0\n'

    def _fake_get(url, timeout=5):
        captured["url"] = url
        return _FakeResponse()

    monkeypatch.setattr(runner.httpx, "get", _fake_get)
    total = runner._snapshot_tool_calls()
    assert total == 3.0
    assert captured["url"] == runner._PIPELINE_METRICS_URL


def test_snapshot_pipeline_errors_filters_by_workspace(monkeypatch) -> None:
    from tests.uat import runner

    class _FakeResponse:
        text = (
            'portal_errors_total{workspace="auto-coding",error_type="empty_completion"} 2.0\n'
            'portal_errors_total{workspace="auto-coding",error_type="tool_parse_failure"} 1.0\n'
            'portal_errors_total{workspace="tools-specialist",error_type="empty_completion"} 5.0\n'
        )

    monkeypatch.setattr(runner.httpx, "get", lambda url, timeout=5: _FakeResponse())
    counts = runner._snapshot_pipeline_errors("auto-coding")
    assert counts == {"empty_completion": 2.0, "tool_parse_failure": 1.0}


def test_snapshot_pipeline_errors_empty_on_unreachable(monkeypatch) -> None:
    from tests.uat import runner

    def _raise(url, timeout=5):
        raise ConnectionError("unreachable")

    monkeypatch.setattr(runner.httpx, "get", _raise)
    assert runner._snapshot_pipeline_errors("auto-coding") == {}


def test_new_pipeline_error_type_detects_growth() -> None:
    from tests.uat.runner import _new_pipeline_error_type

    before = {"empty_completion": 2.0}
    after_growth = {"empty_completion": 3.0}
    after_same = {"empty_completion": 2.0}
    after_new_type = {"empty_completion": 2.0, "tool_parse_failure": 1.0}

    assert _new_pipeline_error_type(before, after_growth) == "empty_completion"
    assert _new_pipeline_error_type(before, after_same) == ""
    assert _new_pipeline_error_type(before, after_new_type) == "tool_parse_failure"
    assert _new_pipeline_error_type({}, {}) == ""
