"""Unit tests for UAT result grading (regression for inverted-critical bug)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from portal5_uat_driver import compute_status


def test_critical_fail_overrides_high_pct():
    """A critical assertion failing must FAIL the test even at >=70% non-critical pass."""
    spec = [{"critical": True}, {"critical": False}, {"critical": False}, {"critical": False}]
    results = [("a", False, "critical-fail"), ("b", True, ""), ("c", True, ""), ("d", True, "")]
    assert compute_status(results, spec) == "FAIL"


def test_no_critical_marker_defaults_to_critical():
    spec = [{}, {}, {}]
    results = [("a", False, ""), ("b", True, ""), ("c", True, "")]
    assert compute_status(results, spec) == "FAIL"


def test_all_pass_returns_pass():
    spec = [{"critical": True}, {"critical": False}]
    results = [("a", True, ""), ("b", True, "")]
    assert compute_status(results, spec) == "PASS"


# ----- Phase 1 driver-hardening tests -----


def test_word_boundary_excludes_substring_match():
    """word_boundary=True must NOT match keywords inside longer words."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from portal5_uat_driver import assert_any_of

    _label, passed, _detail = assert_any_of(
        "I had olives for lunch", ["lives"], "lives mentioned", word_boundary=True
    )
    assert passed is False, "word_boundary=True must reject substring-only matches"

    _label, passed, _detail = assert_any_of(
        "He lives in Boston", ["lives"], "lives mentioned", word_boundary=True
    )
    assert passed is True, "word_boundary=True must still find the word as a word"


def test_word_boundary_default_preserves_legacy_behavior():
    """word_boundary defaults to False — substring matching is preserved."""
    from portal5_uat_driver import assert_any_of

    _label, passed, _detail = assert_any_of("I had olives", ["lives"], "lives mentioned")
    assert passed is True, "Default substring matching must be unchanged"


def test_remove_rows_for_test_ids(tmp_path, monkeypatch):
    """_remove_rows_for_test_ids drops rows for the given IDs and leaves others."""
    import portal5_uat_driver as drv
    from portal5_uat_driver import _remove_rows_for_test_ids

    f = tmp_path / "UAT_RESULTS.md"
    f.write_text(
        "# Header\n"
        "## Summary\n"
        "- **PASS**: 0\n"
        "## Results\n"
        "| 1 | PASS | [WS-01 first](url) | `auto` | ok | 1.0s |\n"
        "| 2 | FAIL | [WS-02 second](url) | `auto` | bad | 1.0s |\n"
        "| 3 | PASS | [WS-03 third](url) | `auto` | ok | 1.0s |\n"
    )
    monkeypatch.setattr(drv, "RESULTS_FILE", f)
    removed = _remove_rows_for_test_ids({"WS-02", "WS-03"})
    assert removed == 2
    text = f.read_text()
    assert "WS-01" in text
    assert "WS-02" not in text
    assert "WS-03" not in text


def test_rebuild_summary_from_rows(tmp_path, monkeypatch):
    """_rebuild_summary_from_rows recomputes the summary header from row data."""
    import portal5_uat_driver as drv
    from portal5_uat_driver import _rebuild_summary_from_rows

    f = tmp_path / "UAT_RESULTS.md"
    f.write_text(
        "## Summary\n"
        "- **PASS**: 99\n"
        "- **FAIL**: 99\n"
        "- **WARN**: 99\n"
        "- **SKIP**: 99\n"
        "- **MANUAL**: 99\n"
        "## Results\n"
        "| 1 | PASS | [A test](u) | m | x | 1s |\n"
        "| 2 | PASS | [B test](u) | m | x | 1s |\n"
        "| 3 | FAIL | [C test](u) | m | x | 1s |\n"
        "| 4 | SKIP | [D test](u) | m | x | 1s |\n"
    )
    monkeypatch.setattr(drv, "RESULTS_FILE", f)
    _rebuild_summary_from_rows()
    text = f.read_text()
    assert "- **PASS**: 2" in text
    assert "- **FAIL**: 1" in text
    assert "- **SKIP**: 1" in text
    assert "- **WARN**: 0" in text
    assert "- **MANUAL**: 0" in text


def test_word_boundary_keyword_with_trailing_nonword():
    """Keywords ending in non-word chars (like 'lives--') CANNOT use word_boundary.

    Regression test for the silent-mismatch bug: \\b only fires at \\w<->\\W
    transitions. A keyword ending in '--' would need its closing \\b to find a
    \\w after the '--', but in real JS code (`this.lives--;`) the next char is
    ';' (non-word). No transition, no match.

    This test pins the BEHAVIOR (silent fail) rather than fixing it, because
    fixing would require either a different anchoring strategy or per-keyword
    logic. The catalog must avoid combining word_boundary=True with keywords
    that begin or end with non-word characters.
    """
    from portal5_uat_driver import _kw_in

    # The keyword's trailing -- is non-word, and ;/whitespace after is also
    # non-word, so \b doesn't fire. This is a known limitation of \b.
    assert _kw_in("lives--", "this.lives--;", word_boundary=True) is False
    assert _kw_in("lives--", "this.lives--;", word_boundary=False) is True

    # Leading non-word: only fails when the preceding char is ALSO non-word.
    # In "(--lives)", '(' is \W and '-' is \W — no \b between them.
    assert _kw_in("--lives", "(--lives)", word_boundary=True) is False
    assert _kw_in("--lives", "(--lives)", word_boundary=False) is True

    # Keywords with non-word INSIDE (not at edges) work fine
    assert _kw_in("player.lives", "if (player.lives <= 0)", word_boundary=True) is True


def test_word_boundary_word_to_word_transition_does_not_fire():
    """\\b only fires \\w<->\\W. Smashed keywords (R1.2.6) don't match '1.2.6'.

    This documents another foot-gun: if a keyword is preceded immediately by
    a word character (like 'R' before '1.2.6' in 'R1.2.6'), the leading \\b
    in the regex doesn't fire and the match silently fails.
    """
    from portal5_uat_driver import _kw_in

    # In 'R1.2.6', R is \w, 1 is \w, so no \b between them
    assert _kw_in("1.2.6", "Reference R1.2.6 applies", word_boundary=True) is False
    # But under legacy substring matching, it works
    assert _kw_in("1.2.6", "Reference R1.2.6 applies", word_boundary=False) is True


# ----- TASK_UAT_TIMING_V1 tests -----


def test_wait_for_response_arrival_returns_immediately_on_content(monkeypatch):
    """When the API has content on first poll, the helper returns it without sleeping."""
    import asyncio

    import portal5_uat_driver as drv

    monkeypatch.setattr(drv, "owui_get_last_response", lambda t, c: "hello world")
    sleep_calls: list[float] = []

    async def fake_sleep(s):
        sleep_calls.append(s)

    monkeypatch.setattr(drv.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        drv._wait_for_response_arrival("tok", "chat-1", max_wait=15.0)
    )
    assert result == "hello world"
    assert sleep_calls == [], "should not sleep when content is available immediately"


def test_wait_for_response_arrival_no_token_falls_back_to_safety_buffer(monkeypatch):
    """When token or chat_id is missing, helper sleeps a fixed 2s and returns ''."""
    import asyncio

    import portal5_uat_driver as drv

    sleep_calls: list[float] = []

    async def fake_sleep(s):
        sleep_calls.append(s)

    monkeypatch.setattr(drv.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        drv._wait_for_response_arrival("", "chat-1")
    )
    assert result == ""
    assert sleep_calls == [2.0], f"expected single 2s safety buffer, got {sleep_calls}"


def test_wait_for_backend_alive_returns_true_on_recovery(monkeypatch):
    """Helper polls _backend_alive and returns True as soon as it reports alive."""
    import asyncio

    import portal5_uat_driver as drv

    states = iter([(False, "down"), (False, "down"), (True, "ok")])
    monkeypatch.setattr(drv, "_backend_alive", lambda tier: next(states))

    async def fake_sleep(s):
        pass

    monkeypatch.setattr(drv.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        drv._wait_for_backend_alive("mlx_small", max_wait=10.0)
    )
    assert result is True


def test_wait_for_backend_alive_skips_polling_for_non_backend_tier(monkeypatch):
    """For tier='any' or 'media_heavy', helper does not call _backend_alive."""
    import asyncio

    import portal5_uat_driver as drv

    call_count = 0

    def mock_backend_alive(tier):
        nonlocal call_count
        call_count += 1
        return (False, "should not be called")

    monkeypatch.setattr(drv, "_backend_alive", mock_backend_alive)

    async def fake_sleep(s):
        pass

    monkeypatch.setattr(drv.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        drv._wait_for_backend_alive("any", max_wait=10.0)
    )
    assert result is True
    assert call_count == 0, "tier='any' should not poll backend"


def test_polling_constants_present():
    """The new tiered-polling constants exist at module level with expected types."""
    import portal5_uat_driver as drv

    assert isinstance(drv.PHASE1_FAST_S, (int, float)) and drv.PHASE1_FAST_S > 0
    assert isinstance(drv.PHASE1_FAST_DURATION_S, (int, float))
    assert isinstance(drv.PHASE1_MID_S, (int, float)) and drv.PHASE1_MID_S > drv.PHASE1_FAST_S
    assert isinstance(drv.PHASE2_STREAMING_POLL_S, (int, float))
    assert drv.PHASE2_STREAMING_POLL_S < drv.PROGRESS_POLL_S, (
        "Phase 2 streaming poll must be tighter than legacy heartbeat"
    )
    assert isinstance(drv.PHASE2_DOM_STABLE_NEEDED, int)
    assert drv.PHASE2_DOM_STABLE_NEEDED >= 2
    assert isinstance(drv.POST_STREAM_API_WAIT_S, (int, float))


def test_send_and_wait_signature_accepts_token_and_chat_id():
    """_send_and_wait accepts token= and chat_id= kwargs (additive, backward compatible)."""
    import inspect

    import portal5_uat_driver as drv

    sig = inspect.signature(drv._send_and_wait)
    assert "token" in sig.parameters
    assert "chat_id" in sig.parameters
    assert sig.parameters["token"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["chat_id"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["token"].default == ""
    assert sig.parameters["chat_id"].default == ""
