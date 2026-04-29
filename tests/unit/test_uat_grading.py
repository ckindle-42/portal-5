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
