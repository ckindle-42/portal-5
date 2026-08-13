from __future__ import annotations

import json
from unittest.mock import patch

import bench_cad_probe as cad


def _fake_response(payload: dict):
    body = json.dumps(payload).encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body

    return _Resp()


def test_run_case_sends_think_false():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return _fake_response(
            {
                "message": {"content": "cube([10,10,10]);"},
                "eval_count": 10,
                "eval_duration": 1_000_000_000,
            }
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        cad.run_case("some-model", {"id": "c1", "prompt": "make a cube", "expect_dims": None})

    assert captured["payload"]["think"] is False


def test_run_case_reads_content_not_thinking_field():
    def fake_urlopen(req, timeout=None):
        return _fake_response(
            {
                "message": {"content": "", "thinking": "long deliberation " * 200},
                "eval_count": 10,
                "eval_duration": 1_000_000_000,
                "done_reason": "length",
            }
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = cad.run_case(
            "some-model", {"id": "c1", "prompt": "make a cube", "expect_dims": None}
        )

    assert result["ok"] is True
    assert result["response_preview"] == ""
    assert result["matched"] is False
