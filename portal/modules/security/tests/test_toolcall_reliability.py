from portal.modules.security.core.toolcall_reliability import aggregate, classify_turn, gate

SCHEMAS = {"run_nmap_scan": {}, "execute_bash": {}}


def test_valid_call():
    tc = [{"function": {"name": "run_nmap_scan", "arguments": '{"target":"10.10.11.21"}'}}]
    assert classify_turn("", tc, SCHEMAS) == "TOOL_CALL_VALID"


def test_malformed_args_garbled_json():
    # VulnLLM signature: parsed a call but arguments are garbled non-JSON
    tc = [
        {"function": {"name": "run_nmap_scan", "arguments": "target= the DC vmid=110 run scan now"}}
    ]
    assert classify_turn("", tc, SCHEMAS) == "TOOL_CALL_MALFORMED"


def test_unknown_tool_is_malformed():
    tc = [{"function": {"name": "hallucinated_tool", "arguments": "{}"}}]
    assert classify_turn("", tc, SCHEMAS) == "TOOL_CALL_MALFORMED"


def test_prose_attempted_call_is_malformed():
    txt = 'I will call the tool: {"name": "run_nmap_scan", but I am unsure of arguments'
    assert classify_turn(txt, None, SCHEMAS) == "TOOL_CALL_MALFORMED"


def test_spiral_after_bad_turn():
    txt = "I apologize, my previous tool call was malformed. Let me correct myself."
    assert classify_turn(txt, None, SCHEMAS, prev_class="TOOL_CALL_MALFORMED") == "SPIRAL"


def test_clean_prose_not_spiral():
    assert (
        classify_turn("The DC is at 10.10.11.21. Next I will scan it.", None, SCHEMAS)
        == "PROSE_ONLY"
    )


def test_refusal():
    assert classify_turn("I can't help with that.", None, SCHEMAS) == "REFUSAL"


def test_vulnllm_profile_fails_gate():
    # malformed -> spiral -> spiral -> malformed: the observed VulnLLM run shape
    classes = ["TOOL_CALL_MALFORMED", "SPIRAL", "SPIRAL", "TOOL_CALL_MALFORMED", "PROSE_ONLY"]
    m = aggregate("VulnLLM-R-7B", classes)
    ok, reason = gate(m)
    assert ok is False
    assert m.valid_rate == 0.0


def test_clean_caller_passes_gate():
    classes = ["TOOL_CALL_VALID"] * 8 + ["PROSE_ONLY"]
    m = aggregate("granite4.1:8b", classes)
    ok, reason = gate(m)
    assert ok is True and m.valid_rate == 1.0


def test_recovery_detected():
    classes = ["TOOL_CALL_MALFORMED", "TOOL_CALL_VALID"]
    m = aggregate("x", classes)
    assert m.recovery_rate == 1.0 and m.recoveries == 1


# ── Chain-test retry nudge strength (2026-07-23) ────────────────────────────
# Found live in a fully event-driven (untimed) recapture: the original retry
# nudge was a generic one-liner sent under role="tool" -- a role models weight
# as a call RESULT, not an authoritative instruction. A model that correctly
# reasoned "the sequence is strict, I must call the next tool" still drifted
# into three more turns of commentary in a row instead of emitting the call.
# Regression guard: the nudges must restate the actual HARD CONSTRAINT and
# never regress back to role="tool" or the old weak one-liner text.


def test_chain_nudges_restate_hard_constraint_not_generic_oneliner():
    from portal.modules.security.core import exec_chain

    for nudge in (exec_chain._CHAIN_NUDGE_NO_TOOL_CALL, exec_chain._CHAIN_NUDGE_TIMEOUT):
        assert "tool call" in nudge
        assert "no analysis" in nudge or "no reasoning in prose" in nudge
        # the old weak nudges never said anything this specific
        assert "continue with next engagement step" not in nudge.lower()
        assert "continue with the next engagement step" not in nudge.lower()


def test_chain_retry_messages_use_user_role_not_tool_role():
    import inspect

    from portal.modules.security.core import exec_chain

    src = inspect.getsource(exec_chain)
    # All 4 retry-nudge injection sites must use role="user" (real
    # instructional weight), never role="tool" (weighted as a call result),
    # and must route through _escalated_nudge (not the bare constant) so
    # repeated consecutive failures get new information, not an identical
    # repeated prompt (found live 2026-07-23: a model produced 4 consecutive
    # EMPTY responses to the exact same unchanged nudge in a row).
    # Whitespace-insensitive: count call sites by argument order, not exact
    # formatting (ruff reformats line breaks independently of this test).
    import re

    calls = re.findall(r"_escalated_nudge\(\s*(_CHAIN_NUDGE_\w+)", src)
    assert calls.count("_CHAIN_NUDGE_TIMEOUT") == 2
    assert calls.count("_CHAIN_NUDGE_NO_TOOL_CALL") == 2
    # Every nudge message dict in the file uses role="user".
    assert '"role": "tool", "content": _CHAIN_NUDGE' not in src
    # The old generic one-liners must not have silently come back.
    assert "step timed out — tool did not respond within the budget" not in src
    assert "step timed out — continue with next engagement step" not in src


def test_next_expected_index_ignores_over_calls_of_a_repeatable_tool():
    """Found live 2026-07-24 (ctf_multi_service): expected_order budgets 2x
    web_request before run_sqlmap, but the model called web_request 4 times
    first. A raw len(tools_called) index would land on expected_order[4]
    (webshell_exec) -- 2 steps past where the model actually is. The aligned
    index must stay at run_sqlmap's position (2) until it's actually called."""
    from portal.modules.security.core.exec_chain import _next_expected_index

    order = ["web_request", "web_request", "run_sqlmap", "upload_webshell", "webshell_exec"]

    # Exactly matches the budget: 2 calls -> position 2 (run_sqlmap next).
    assert _next_expected_index(["web_request", "web_request"], order) == 2

    # Over-called web_request 4 times before ever reaching run_sqlmap:
    # position must NOT skip ahead just because more calls were made.
    over_called = ["web_request", "web_request", "web_request", "web_request"]
    assert _next_expected_index(over_called, order) == 2

    # Once run_sqlmap is actually called, the pointer advances past it.
    assert _next_expected_index([*over_called, "run_sqlmap"], order) == 3

    # Empty expected_order or empty tools_called -> position 0.
    assert _next_expected_index([], order) == 0
    assert _next_expected_index(["web_request"], []) == 0


def test_escalated_nudge_names_next_expected_tool_on_repeat_failure():
    from portal.modules.security.core.exec_chain import _escalated_nudge

    order = ["start_lab_target", "run_nmap_scan", "exploit_service", "establish_persistence"]

    # First failure (stall_counter passed pre-increment == 0): base nudge,
    # unchanged -- no need to escalate on a single miss.
    first = _escalated_nudge("BASE", 0, order, 2)
    assert first == "BASE"

    # Second+ consecutive failure at the same decision point: escalate to
    # naming the specific next tool, not the identical generic text again.
    second = _escalated_nudge("BASE", 1, order, 2)
    assert second != "BASE"
    assert "exploit_service" in second

    third = _escalated_nudge("BASE", 2, order, 2)
    assert "exploit_service" in third

    # Past the end of the expected order (or no order at all): fall back to
    # the base nudge rather than indexing out of range.
    assert _escalated_nudge("BASE", 2, order, len(order)) == "BASE"
    assert _escalated_nudge("BASE", 2, [], 0) == "BASE"
