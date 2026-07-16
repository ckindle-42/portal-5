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
