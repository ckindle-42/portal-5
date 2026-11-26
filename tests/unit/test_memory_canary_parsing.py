"""Parsing-only unit tests for scripts/memory_canary.py (no live access)."""

import importlib

canary = importlib.import_module("scripts.memory_canary")


VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              102400.
Pages active:                            512000.
Pages inactive:                          300000.
Pages speculative:                        10000.
Pages wired down:                        262144.
Pages purgeable:                          50000.
"""


def test_parse_vm_stat():
    out = canary.parse_vm_stat(VM_STAT)
    assert out["page_size"] == 16384
    assert out["wired_bytes"] == 262144 * 16384
    assert out["free_bytes"] == 102400 * 16384


def test_parse_swap_usage():
    line = "vm.swapusage: total = 4096.00M  used = 1536.50M  free = 2559.50M  (encrypted)"
    out = canary.parse_swap_usage(line)
    assert out["used_bytes"] == int(1536.50 * 1024**2)
    assert out["free_bytes"] == int(2559.50 * 1024**2)


def test_parse_swap_usage_gigabytes():
    out = canary.parse_swap_usage("vm.swapusage: total = 3.00G  used = 1.25G  free = 1.75G")
    assert out["used_bytes"] == int(1.25 * 1024**3)


PS_OUT = """  101   2048 /usr/sbin/syslogd
  202 1048576 omlx-server --port 8085
  303  524288 /opt/engines/ollama-current/ollama serve
  404 8388608 /opt/engines/ollama-live/llama-server --model /x --port 50398
"""


def test_parse_ps_rss_totals_only_engine_processes():
    out = canary.parse_ps_rss(PS_OUT)
    assert out["totals"]["omlx-server"] == 1048576 * 1024
    assert out["totals"]["ollama serve"] == 524288 * 1024
    assert out["totals"]["llama-server"] == 8388608 * 1024
    assert len(out["procs"]) == 3


LOG = """2026-11-25T10:00:01Z INFO load_guard: evicted Qwen3.8-27B-oQ4e-mtp on omlx, 15.8 GiB freed (reason=idle LRU)
2026-11-25T10:00:02Z INFO load_guard: eviction pass for gemma4:26b: shortage_gib=4.2 evicted=omlx:Qwen3.8-27B-oQ4e-mtp
2026-11-25T10:00:03Z INFO load_guard: inkling-2-mini:ctx256k needs 22.9 GiB, 18.1 available; waiting for engine activity
2026-11-25T10:00:04Z ERROR Cannot load qwen3-vl:32b-ctx16k: projected memory 21.6 GiB would exceed host headroom 12.0 GiB (oMLX headroom 9.0 + idle Ollama 4.0 - margin 1) after waiting 30.0s
2026-11-25T10:00:05Z INFO load_guard: protecting ollama:granite4.1:8b-ctx16k for 120s after it served a failover
2026-11-25T10:00:06Z INFO some unrelated line
"""


def test_parse_load_guard_log_kinds():
    events = canary.parse_load_guard_log(LOG)
    kinds = [e["kind"] for e in events]
    assert kinds == ["evicted", "eviction_pass", "needs_wait", "refused", "protect"]
    assert events[0]["model"] == "Qwen3.8-27B-oQ4e-mtp"
    assert events[0]["engine"] == "omlx"
    assert events[0]["gib"] == "15.8"
    assert events[3]["model"] == "qwen3-vl:32b-ctx16k"


METRICS = """# HELP portal5_load_guard_admissions_total x
# TYPE portal5_load_guard_admissions_total counter
portal5_load_guard_admissions_total{engine="ollama"} 12.0
portal5_load_guard_admissions_total{engine="omlx"} 5.0
portal5_load_guard_refusals_total{engine="ollama"} 1.0
http_requests_total 999.0
"""


def test_parse_prometheus_counters_folds_labels_and_filters_prefix():
    out = canary.parse_prometheus_counters(METRICS, "portal5_load_guard_")
    assert out == {
        "portal5_load_guard_admissions_total": 17.0,
        "portal5_load_guard_refusals_total": 1.0,
    }


def test_parse_ollama_ps():
    payload = {"models": [{"name": "granite4.1:8b-ctx16k", "size": 5347737600, "size_vram": 0}]}
    assert canary.parse_ollama_ps(payload) == {"granite4.1:8b-ctx16k": 5347737600}


def test_parse_omlx_status():
    payload = {
        "final_ceiling": 63228006400,
        "models": [
            {"id": "Qwen3.8-27B-oQ4e-mtp", "loaded": True, "estimated_size": 1.7e10},
            {"id": "other", "loaded": False},
        ],
    }
    out = canary.parse_omlx_status(payload)
    assert out["loaded"] == {"Qwen3.8-27B-oQ4e-mtp": 1.7e10}
    assert out["final_ceiling"] == 63228006400.0


def test_build_filler_prompt_size():
    p = canary.build_filler_prompt(1000, 4.0)
    body = p.split("\n", 1)[1]
    assert len(body) >= 1000 * 4.0 - len(
        "Read this context fill and reply READY after reading it.\n"
    )
    assert len(body) < 1000 * 4.0 + len("context ")


def test_cross_engine_evictions_flags_preexisting_residents_only():
    events = [
        {"kind": "evicted", "model": "Qwen3.8-27B-oQ4e-mtp", "engine": "omlx", "gib": "15.8"},
        {"kind": "evicted", "model": "granite4.1:8b-ctx16k", "engine": "ollama", "gib": "5.0"},
        {"kind": "needs_wait", "model": "x"},
    ]
    pre = {"ollama": {"granite4.1:8b-ctx16k"}, "omlx": set()}
    pair_models = {"Qwen3.8-27B-oQ4e-mtp"}
    out = canary.cross_engine_evictions(events, pre, pair_models)
    assert [e["model"] for e in out] == ["granite4.1:8b-ctx16k"]


class _Args:
    max_swap_growth_gib = 1.0


def _pair_result(turns, cross=(), swap=0.0):
    pr = canary.PairResult("p")
    pr.turns = turns
    pr.load_guard_log_parsed = True
    pr.cross_evictions = list(cross)
    pr.swap_growth_gib = swap
    canary.judge(pr, _Args())
    return pr


def _turn(seat="ws", status=200, outcome="complete", error=""):
    return canary.TurnResult(
        seat,
        http_status=status,
        prompt_tokens=100,
        fill_ratio=0.85,
        outcome=outcome,
        error=error,
        backend="engine",
        model="model",
        trace_matched=True,
        valid=True,
    )


def test_judge_pass():
    pr = _pair_result([_turn(), _turn("ws2")])
    assert pr.verdict == "PASS" and pr.reasons == []


def test_judge_fail_on_507():
    turn = _turn(status=507, outcome="no-trace", error="would exceed host headroom")
    turn.valid = False
    turn.validation_errors = ["HTTP 507: would exceed host headroom"]
    pr = _pair_result([turn])
    assert pr.verdict == "INVALID"


def test_judge_fail_on_refusal_text_without_status():
    turn = _turn(status=200, error="Cannot load x: projected memory would exceed")
    turn.valid = False
    turn.validation_errors = ["no measured prompt_tokens"]
    pr = _pair_result([turn])
    assert pr.verdict == "INVALID"


def test_judge_fail_on_bad_outcome():
    turn = _turn(outcome="backend.failed")
    turn.valid = False
    turn.validation_errors = ["trace outcome 'backend.failed' is not a successful outcome"]
    pr = _pair_result([turn])
    assert pr.verdict == "INVALID"


def test_judge_invalidates_unmeasured_turn_instead_of_scoring_it():
    turn = _turn()
    turn.prompt_tokens = 0
    turn.valid = False
    turn.validation_errors = ["no measured prompt_tokens"]
    pr = _pair_result([turn], swap=2.5)
    assert pr.verdict == "INVALID"
    assert "ws: no measured prompt_tokens" in pr.reasons


def test_judge_invalidates_fill_above_window_before_scoring_swap_growth():
    turn = _turn()
    turn.prompt_tokens = 69600
    turn.fill_ratio = 2.125
    pr = _pair_result([turn], swap=2.5)
    assert pr.verdict == "INVALID"
    assert any("fill 2.125 is outside 0.80-0.95" in reason for reason in pr.reasons)


def test_judge_does_not_flag_ok_as_a_warning():
    pr = _pair_result([_turn(outcome="ok")])
    assert pr.verdict == "PASS"


def test_judge_invalidates_an_unparsed_load_guard_window():
    pr = _pair_result([_turn()])
    pr.load_guard_log_parsed = False
    canary.judge(pr, _Args())
    assert pr.verdict == "INVALID"
    assert "load_guard log window was not parsed" in pr.reasons


def test_judge_fail_on_cross_eviction_and_swap():
    ev = {"kind": "evicted", "model": "m", "engine": "omlx", "gib": "9"}
    pr = _pair_result([_turn()], cross=[ev], swap=2.5)
    assert pr.verdict == "FAIL"
    assert any("unplanned eviction" in r for r in pr.reasons)
    assert any("swap grew" in r for r in pr.reasons)


def test_render_table_has_a_row_per_turn():
    pr = _pair_result([_turn(), _turn("ws2")])
    pr.pre = {"host": {"rss": {"totals": {}}}}
    pr.post = {"host": {"rss": {"totals": {}}}}
    table = canary.render_table([pr])
    assert table.count("\n") >= 3
    assert "ws2" in table and "PASS" in table
