"""Tests for portal.platform.wiki.render — HUMAN-OWNED awareness, render_report."""

from __future__ import annotations

import textwrap
from pathlib import Path

from portal.platform.wiki.render import (
    _find_unit_ids_outside_human_owned,
    check_generated_blocks_current,
    host_section_depth,
    project_body,
    render_report,
    render_unit_into_doc,
)
from portal.platform.wiki.schema import KnowledgeUnit, SourceRef


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


def _fake_unit(body: str):
    return KnowledgeUnit(
        id="unit-x",
        kind="mixed",
        title="X",
        sources=[SourceRef(type="doc", path="README.md")],
        body=body,
    )


class TestProjectionSymmetry:
    def test_render_then_currency_check_agree(self, tmp_path: Path, monkeypatch) -> None:
        doc = tmp_path / "README.md"
        doc.write_text(
            "### Host Section\n\n<!-- WIKI:GENERATED unit=unit-x -->\n\n<!-- /WIKI:GENERATED -->\n"
        )
        monkeypatch.setattr(
            "portal.platform.wiki.render.load_unit",
            lambda _id: _fake_unit("Body text.\n\n## Why\n\nBecause it is needed here always.\n"),
        )
        assert render_unit_into_doc(doc, "unit-x") is True
        assert "#### Why" in doc.read_text()
        assert check_generated_blocks_current(tmp_path, doc_paths=[doc]) == []

    def test_second_render_is_idempotent(self, tmp_path: Path, monkeypatch) -> None:
        doc = tmp_path / "README.md"
        doc.write_text(
            "### Host\n\n<!-- WIKI:GENERATED unit=unit-x -->\n\n<!-- /WIKI:GENERATED -->\n"
        )
        monkeypatch.setattr(
            "portal.platform.wiki.render.load_unit",
            lambda _id: _fake_unit(
                "Text.\n\n## Why\n\nA sufficiently long rationale sentence here.\n"
            ),
        )
        assert render_unit_into_doc(doc, "unit-x") is True
        assert render_unit_into_doc(doc, "unit-x") is False


class TestRenderReport:
    def test_report_structure(self, tmp_path: Path) -> None:
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

    def test_migrated_doc_detected(self, tmp_path: Path) -> None:
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

    def test_unmigrated_doc_detected(self, tmp_path: Path) -> None:
        doc = tmp_path / "README.md"
        doc.write_text(
            textwrap.dedent("""\
            # Title

            This is real un-migrated content.
        """)
        )
        report = render_report(tmp_path)
        assert "README.md" in report["unmigrated"]

    def test_blocks_counted(self, tmp_path: Path) -> None:
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

    def test_coverage_pct_calculation(self, tmp_path: Path) -> None:
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
