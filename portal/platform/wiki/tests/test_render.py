"""Tests for portal.platform.wiki.render — HUMAN-OWNED awareness, render_report."""

from __future__ import annotations

import textwrap

from portal.platform.wiki.render import (
    _find_unit_ids_outside_human_owned,
    render_report,
)


class TestHumanOwnedAwareness:
    def test_markers_outside_human_owned_detected(self):
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=alpha -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == ["alpha"]

    def test_markers_inside_human_owned_excluded(self):
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED -->
            <!-- WIKI:GENERATED unit=alpha -->
            body
            <!-- /WIKI:GENERATED -->
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == []

    def test_mixed_markers(self):
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

    def test_no_markers(self):
        assert _find_unit_ids_outside_human_owned("just plain text") == []

    def test_multiple_outside(self):
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=a -->
            body
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:GENERATED unit=b -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert _find_unit_ids_outside_human_owned(text) == ["a", "b"]


class TestRenderReport:
    def test_report_structure(self, tmp_path):
        """render_report returns correct keys and types."""
        # Create a minimal doc surface by writing a TIER1_DOCS entry
        doc = tmp_path / "README.md"
        doc.write_text("# Title\n\nSome real content.\n")
        report = render_report(tmp_path)
        assert "migrated" in report
        assert "unmigrated" in report
        assert "blocks_total" in report
        assert "coverage_pct" in report
        assert isinstance(report["coverage_pct"], float)

    def test_migrated_doc_detected(self, tmp_path):
        doc = tmp_path / "README.md"
        doc.write_text(
            textwrap.dedent("""\
            # Title

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        )
        report = render_report(tmp_path)
        assert "README.md" in report["migrated"]

    def test_unmigrated_doc_detected(self, tmp_path):
        doc = tmp_path / "README.md"
        doc.write_text(
            textwrap.dedent("""\
            # Title

            This is real un-migrated content.
        """)
        )
        report = render_report(tmp_path)
        assert "README.md" in report["unmigrated"]

    def test_blocks_counted(self, tmp_path):
        doc = tmp_path / "README.md"
        doc.write_text(
            textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=a -->
            body a
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:GENERATED unit=b -->
            body b
            <!-- /WIKI:GENERATED -->
        """)
        )
        report = render_report(tmp_path)
        assert report["blocks_total"] == 2

    def test_coverage_pct_calculation(self, tmp_path):
        # One migrated, one unmigrated
        (tmp_path / "README.md").write_text(
            textwrap.dedent("""\
            # Title
            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        )
        (tmp_path / "P5_ROADMAP.md").write_text("# Roadmap\n\nReal content here.\n")
        report = render_report(tmp_path)
        assert report["coverage_pct"] == 50.0
