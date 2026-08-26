"""RE client — URL shape + payload construction, no live server (monkeypatched)."""

from portal.modules.binary_research.harness.re_client import REClient, REClientError


def test_exec_posts_correct_shape(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    import portal.modules.binary_research.harness.re_client as mod

    monkeypatch.setattr(mod.httpx, "Client", _Client)

    client = REClient(base_url="http://127.0.0.1:8930")
    result = client.exec(command="readelf -h x", project="j1", timeout=60)
    assert result["stdout"] == "ok"
    assert captured["url"] == "http://127.0.0.1:8930/tools/re_exec"
    assert captured["json"]["arguments"]["command"] == "readelf -h x"
    assert captured["json"]["arguments"]["project"] == "j1"


def test_exec_wraps_http_error(monkeypatch):
    import httpx

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json):
            raise httpx.ConnectError("refused")

    import portal.modules.binary_research.harness.re_client as mod

    monkeypatch.setattr(mod.httpx, "Client", _Client)

    try:
        REClient().exec(command="x")
        raise AssertionError("should have raised")
    except REClientError as exc:
        assert "re_exec failed" in str(exc)
