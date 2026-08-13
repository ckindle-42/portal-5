"""mine_closeout_verdict()'s retracted-verdict bug, fixed 477d7646."""

from __future__ import annotations

import scripts.pending_verdicts_evidence as pve


def test_final_verdict_marker_overrides_earlier_retracted_verdict(tmp_path):
    report = tmp_path / "closeout.md"
    report.write_text(
        "## portal5/deepwen-3.6:q4.5-moq-ctx32k\n"
        "First pass: declined for low quality. **Also wrong** — rescored.\n"
        + ("padding " * 150)
        + "\nFinal verdict: pass, with real caveats about latency.\n"
    )
    verdict = pve.mine_closeout_verdict(report, "portal5/deepwen-3.6:q4.5-moq-ctx32k")
    assert verdict == "pass"


def test_final_verdict_window_prefers_closest_token_not_substring_match(tmp_path):
    report = tmp_path / "closeout.md"
    report.write_text(
        "## some-tag\nFinal verdict: pass. Both earlier declines are retracted as bugs.\n"
    )
    verdict = pve.mine_closeout_verdict(report, "some-tag")
    assert verdict == "pass"


def test_no_final_verdict_marker_falls_back_to_narrow_window(tmp_path):
    report = tmp_path / "closeout.md"
    report.write_text("## other-tag\ndeclined for low quality, no further discussion.\n")
    verdict = pve.mine_closeout_verdict(report, "other-tag")
    assert verdict == "decline"


def test_unmatched_tag_returns_none(tmp_path):
    report = tmp_path / "closeout.md"
    report.write_text("## unrelated-tag\nFinal verdict: pass.\n")
    verdict = pve.mine_closeout_verdict(report, "not-in-this-file")
    assert verdict is None
