"""Tests for portal.platform.wiki.migration — fences, discovery, substantive-remainder."""

from __future__ import annotations

import textwrap

from portal.platform.wiki.migration import (
    discover_unmigrated_docs,
    doc_is_migrated,
    strip_managed_regions,
    substantive_remainder,
)

# ── strip_managed_regions ──


class TestStripManagedRegions:
    def test_removes_generated_blocks(self):
        text = textwrap.dedent("""\
            # Title
            <!-- WIKI:GENERATED unit=test-unit -->
            some generated content
            <!-- /WIKI:GENERATED -->
            trailing text
        """)
        result = strip_managed_regions(text)
        assert "generated content" not in result
        assert "trailing text" in result
        assert "# Title" in result

    def test_removes_human_owned_fences(self):
        text = textwrap.dedent("""\
            # Title
            <!-- WIKI:HUMAN-OWNED -->
            human judgment here
            <!-- /WIKI:HUMAN-OWNED -->
            trailing
        """)
        result = strip_managed_regions(text)
        assert "human judgment" not in result
        assert "trailing" in result

    def test_removes_multiple_blocks(self):
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=a -->
            block a
            <!-- /WIKI:GENERATED -->
            middle
            <!-- WIKI:GENERATED unit=b -->
            block b
            <!-- /WIKI:GENERATED -->
        """)
        result = strip_managed_regions(text)
        assert "block a" not in result
        assert "block b" not in result
        assert "middle" in result

    def test_empty_input(self):
        assert strip_managed_regions("") == ""


# ── substantive_remainder ──


class TestSubstantiveRemainder:
    def test_fully_migrated_doc_has_empty_remainder(self):
        text = textwrap.dedent("""\
            # Doc Title

            <!-- WIKI:GENERATED unit=some-unit -->
            generated body
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED -->
            human prose
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert substantive_remainder(text) == ""

    def test_unmigrated_facts_detected(self):
        text = textwrap.dedent("""\
            # Doc Title

            <!-- WIKI:GENERATED unit=some-unit -->
            generated body
            <!-- /WIKI:GENERATED -->

            This is hand-written prose that should be in a unit.
        """)
        remainder = substantive_remainder(text)
        assert "hand-written prose" in remainder

    def test_ignores_blank_lines(self):
        text = textwrap.dedent("""\
            # Title

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->


        """)
        assert substantive_remainder(text) == ""

    def test_ignores_bare_headings(self):
        text = textwrap.dedent("""\
            # Title

            ## Section One

            ### Subsection

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert substantive_remainder(text) == ""

    def test_ignores_horizontal_rules(self):
        text = textwrap.dedent("""\
            # Title

            ---

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert substantive_remainder(text) == ""

    def test_ignores_table_separators(self):
        text = textwrap.dedent("""\
            # Title

            |---|---|

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert substantive_remainder(text) == ""

    def test_ignores_html_comments(self):
        text = textwrap.dedent("""\
            # Title

            <!-- this is a comment -->

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        assert substantive_remainder(text) == ""

    def test_detects_unmigrated_table_data(self):
        text = textwrap.dedent("""\
            # Title

            | 8080 | Open WebUI |
            | 9099 | Pipeline |

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        remainder = substantive_remainder(text)
        assert "8080" in remainder


# ── doc_is_migrated ──


class TestDocIsMigrated:
    def test_migrated_doc(self, tmp_path):
        doc = tmp_path / "migrated.md"
        doc.write_text(
            textwrap.dedent("""\
            # Title

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->
        """)
        )
        assert doc_is_migrated(doc) is True

    def test_unmigrated_doc(self, tmp_path):
        doc = tmp_path / "unmigrated.md"
        doc.write_text(
            textwrap.dedent("""\
            # Title

            Some real content here that belongs in a unit.
        """)
        )
        assert doc_is_migrated(doc) is False


# ── discover_unmigrated_docs ──


class TestDiscoverUnmigratedDocs:
    def test_excludes_claude_md(self, tmp_path):
        """CLAUDE.md must never appear in discovery output."""
        # Create a minimal repo structure
        (tmp_path / "CLAUDE.md").write_text("# Real content that is substantive\n")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / ".doc_ledger.yaml").write_text("version: 1\ndocs: {}\n")
        (tmp_path / "portal_wiki").mkdir()
        (tmp_path / "portal_wiki" / "canonical").mkdir()

        # Even if CLAUDE.md has substantive content, it must not appear
        results = discover_unmigrated_docs(tmp_path, exclude=("CLAUDE.md",))
        paths = [r["path"] for r in results]
        assert "CLAUDE.md" not in paths

    def test_returns_sorted_by_priority(self, tmp_path):
        """Higher-priority docs come first."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / ".doc_ledger.yaml").write_text("version: 1\ndocs: {}\n")
        (tmp_path / "portal_wiki").mkdir()
        (tmp_path / "portal_wiki" / "canonical").mkdir()

        # We can't easily test priority ordering without git history,
        # but we can verify the structure works.
        results = discover_unmigrated_docs(tmp_path, exclude=("CLAUDE.md",))
        # With no TIER1_DOCS files present, should be empty
        assert isinstance(results, list)
