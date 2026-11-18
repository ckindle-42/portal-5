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
