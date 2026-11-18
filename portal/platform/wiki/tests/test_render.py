"""Tests for portal.platform.wiki.render — HUMAN-OWNED awareness, render_report."""

from __future__ import annotations

import textwrap

from portal.platform.wiki.render import (
    _find_unit_ids_outside_human_owned,
    host_section_depth,
    project_body,
)


class TestHumanOwnedAwareness:
    def test_markers_outside_human_owned_detected(self) -> None:
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=alpha -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == ["alpha"]

    def test_markers_inside_human_owned_excluded(self) -> None:
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED -->
            <!-- WIKI:GENERATED unit=alpha -->
            body
            <!-- /WIKI:GENERATED -->
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == []

    def test_mixed_markers(self) -> None:
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=outside -->
            body
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED -->
            <!-- WIKI:GENERATED unit=inside -->
            body
            <!-- /WIKI:GENERATED -->
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == ["outside"]

    def test_no_markers(self) -> None:
        assert _find_unit_ids_outside_human_owned("just plain text") == []

    def test_multiple_outside(self) -> None:
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=a -->
            body
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:GENERATED unit=b -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == ["a", "b"]


class TestProjectBody:
    def test_identity_when_no_headings(self) -> None:
        body = "Just prose.\n\nMore prose.\n"
        assert project_body(body, host_depth=3) == body

    def test_why_demoted_under_h3_host(self) -> None:
        body = "Some description.\n\n## Why\n\nBecause it matters.\n"
        out = project_body(body, host_depth=3)
        assert "#### Why" in out
        assert "## Why" not in out.replace("#### Why", "")

    def test_identity_when_already_seated_at_h1_host(self) -> None:
        body = "Description.\n\n## Why\n\nRationale.\n"
        assert project_body(body, host_depth=1) == body

    def test_relative_depth_preserved(self) -> None:
        body = "Text.\n\n## Why\n\nReason.\n\n### Detail\n\nMore.\n"
        out = project_body(body, host_depth=2)
        assert "### Why" in out
        assert "#### Detail" in out

    def test_headings_inside_fence_untouched(self) -> None:
        body = (
            "Text.\n\n```bash\n# Pull specialized models\nollama pull x\n```\n\n## Why\n\nReason.\n"
        )
        out = project_body(body, host_depth=3)
        assert "# Pull specialized models" in out
        assert "#### Why" in out

    def test_clamps_at_h6_for_h6_host(self) -> None:
        body = "Text.\n\n## Why\n\nReason.\n"
        out = project_body(body, host_depth=6)
        assert "###### Why" in out
        assert "####### Why" not in out


class TestHostSectionDepth:
    def test_ignores_prior_generated_blocks(self) -> None:
        text = (
            "## Real Section\n\n"
            "<!-- WIKI:GENERATED unit=a -->\n"
            "#### Some projected heading\n"
            "<!-- /WIKI:GENERATED -->\n\n"
            "<!-- WIKI:GENERATED unit=b -->\n"
        )
        assert host_section_depth(text, text.index("<!-- WIKI:GENERATED unit=b")) == 2

    def test_skips_why_headings(self) -> None:
        text = "### Host\n\n## Why\n\nblah\n\n<!-- WIKI:GENERATED unit=b -->\n"
        assert host_section_depth(text, text.index("<!-- WIKI:GENERATED unit=b")) == 3

    def test_zero_when_nothing_precedes(self) -> None:
        text = "<!-- WIKI:GENERATED unit=b -->\n"
        assert host_section_depth(text, 0) == 0
