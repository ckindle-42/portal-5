"""The compliance classifier's detectors are not vacuous: a tool that calls a model, writes the
store, or answers differently after earlier calls is caught (root-fix Part 2c-2)."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import urllib.error
import urllib.request

from tests.wfe.e2e import compliance_classify as cc


def test_the_trap_counts_a_model_call_and_the_store_diff_sees_a_write(tmp_path, monkeypatch):
    from portal.modules.compliance.tools import compliance_mcp as cm

    class OfflineTrap:
        server_port = 43210

        def __init__(self, *_args):
            pass

        def serve_forever(self):
            pass

    def refuse_request(request, timeout=5):
        cc._Trap.hits += 1
        raise urllib.error.HTTPError(str(request), 503, "offline trap", {}, None)

    cc._Trap.hits = 0
    monkeypatch.setattr(cc, "HTTPServer", OfflineTrap)
    monkeypatch.setattr(urllib.request, "urlopen", refuse_request)

    db = tmp_path / "compliance_store.db"
    con = sqlite3.connect(db)
    con.execute("create table notes(x text)")
    con.commit()
    con.close()

    def calls_a_model():
        import os

        with contextlib.suppress(Exception):  # the trap refuses (503)
            urllib.request.urlopen(os.environ["PIPELINE_BASE"] + "/v1/chat/completions", timeout=5)
        return {"ok": True}

    def writes():
        c = sqlite3.connect(db)
        c.execute("insert into notes values ('n')")
        c.commit()
        c.close()
        return {"ok": True}

    monkeypatch.setitem(cm._DISPATCH, "rig_calls_a_model", calls_a_model)
    monkeypatch.setitem(cm._DISPATCH, "rig_writes", writes)
    monkeypatch.setattr(cc, "_quiet", lambda store, timeout=60: cc._items(store))
    rows = {
        r["tool"]: r for r in cc.run_one(tmp_path, [["rig_calls_a_model", {}], ["rig_writes", {}]])
    }
    assert (
        rows["rig_calls_a_model"]["model_calls"] == 1 and not rows["rig_calls_a_model"]["changed"]
    )
    assert rows["rig_writes"]["changed"] == ["db:notes"] and rows["rig_writes"]["model_calls"] == 0


def test_volatile_ids_and_times_do_not_make_equal_answers_differ():
    a = {"run_id": "3f2a9c1b7d6e5f40a1b2", "at": "2026-10-14T01:02:03Z", "answer": "35 days"}
    b = {"run_id": "9e8d7c6b5a4f3e2d1c0b", "at": "2026-10-15T09:08:07Z", "answer": "35 days"}
    assert cc._norm(a) == cc._norm(b) and cc._norm(a) != cc._norm({**a, "answer": "90 days"})
    assert json.loads(cc._norm(a))["answer"] == "35 days"


def test_a_malformed_tool_call_is_a_model_fail_not_a_harness_error():
    """oMLX refusing the model's own tool-call markup (invalid_tool_call) is the seat's
    failure; as HARNESS_ERROR it halted whole arms (wfe_tools confirms d and g)."""
    from tests.wfe import runner

    err = RuntimeError(
        "engine error mid-stream: {'message': 'Model output contains an unrecoverable tool call.',"
        " 'code': 'invalid_tool_call'}"
    )
    assert runner._is_malformed_tool_call(err)
    assert not runner._is_malformed_tool_call(RuntimeError("engine error mid-stream: HTTP 502"))
    transcript = [{"turn": 1, "malformed_tool_call": str(err)}]
    outcome, note, _ = runner._classify(
        {"checkers": []}, None, transcript, runner.Outcome.FAIL, [], 0
    )
    assert outcome is runner.Outcome.FAIL and note.startswith("malformed tool call")
