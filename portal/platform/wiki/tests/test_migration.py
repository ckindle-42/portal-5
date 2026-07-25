"""Tests for portal.platform.wiki.migration — V2 anti-gaming rules."""

from __future__ import annotations

import textwrap

from portal.platform.wiki.migration import (
    doc_is_migrated,
    fenced_human_lines,
    generated_block_count,
    human_owned_reasons,
    strip_managed_regions,
    substantive_remainder,
)

# ── strip_managed_regions ──


class TestStripManagedRegions:
    def test_removes_v2_reasoned_fences(self):
        text = textwrap.dedent("""\
            # Title
            <!-- WIKI:HUMAN-OWNED reason="design rationale" -->
            human prose
            <!-- /WIKI:HUMAN-OWNED -->
            trailing
        """)
        result = strip_managed_regions(text)
        assert "human prose" not in result
        assert "trailing" in result

    def test_removes_v1_fences(self):
        text = textwrap.dedent("""\
            # Title
            <!-- WIKI:HUMAN-OWNED -->
            old fence
            <!-- /WIKI:HUMAN-OWNED -->
            trailing
        """)
        result = strip_managed_regions(text)
        assert "old fence" not in result
        assert "trailing" in result

    def test_removes_generated_blocks(self):
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=test-unit -->
            generated content
            <!-- /WIKI:GENERATED -->
        """)
        result = strip_managed_regions(text)
        assert "generated content" not in result

    def test_empty_input(self):
        assert strip_managed_regions("") == ""


# ── substantive_remainder ──


class TestSubstantiveRemainder:
    def test_fully_migrated_doc_has_empty_remainder(self):
        text = textwrap.dedent("""\
            # Title

            <!-- WIKI:GENERATED unit=some-unit -->
            generated body
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED reason="design rationale" -->
            human prose
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert substantive_remainder(text) == ""

    def test_unmigrated_facts_detected(self):
        text = textwrap.dedent("""\
            # Title

            This is hand-written prose that should be in a unit.
        """)
        remainder = substantive_remainder(text)
        assert "hand-written prose" in remainder

    def test_ignores_bare_headings(self):
        text = textwrap.dedent("""\
            # Title

            ## Section One

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


# ── generated_block_count ──


class TestGeneratedBlockCount:
    def test_counts_blocks(self):
        text = textwrap.dedent("""\
            <!-- WIKI:GENERATED unit=a -->
            body a
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:GENERATED unit=b -->
            body b
            <!-- /WIKI:GENERATED -->
        """)
        assert generated_block_count(text) == 2

    def test_zero_blocks(self):
        assert generated_block_count("just plain text") == 0


# ── fenced_human_lines ──


class TestFencedHumanLines:
    def test_counts_substantive_lines_in_fence(self):
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED reason="test" -->
            Line one of real content.
            Line two of real content.

            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert fenced_human_lines(text) == 2

    def test_ignores_inert_lines(self):
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED reason="test" -->
            Real content.

            ## Just a heading

            <!-- /WIKI:HUMAN-OWNED -->
        """)
        # "Real content." is 1 substantive line; heading is inert
        assert fenced_human_lines(text) == 1

    def test_handles_v1_fences(self):
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED -->
            Old fence content.
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        assert fenced_human_lines(text) == 1


# ── human_owned_reasons ──


class TestHumanOwnedReasons:
    def test_extracts_reason(self):
        text = '<!-- WIKI:HUMAN-OWNED reason="design rationale" -->'
        reasons = human_owned_reasons(text)
        assert reasons == ["design rationale"]

    def test_missing_reason_from_v1_fence(self):
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED -->
            content
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        reasons = human_owned_reasons(text)
        assert "[MISSING]" in reasons

    def test_multiple_fences(self):
        text = textwrap.dedent("""\
            <!-- WIKI:HUMAN-OWNED reason="first" -->
            content
            <!-- /WIKI:HUMAN-OWNED -->

            <!-- WIKI:HUMAN-OWNED reason="second" -->
            content
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        reasons = human_owned_reasons(text)
        assert len(reasons) == 2
        assert "[MISSING]" not in reasons


# ── doc_is_migrated — V2 anti-gaming rules ──


class TestDocIsMigratedV2:
    def test_v1_fence_everything_not_migrated(self, tmp_path):
        """Regression: V1 wrapped entire doc in one mega-fence. Must be False."""
        doc = tmp_path / "README.md"
        doc.write_text(
            textwrap.dedent("""\
            # Portal 5

            <!-- WIKI:HUMAN-OWNED -->
            A complete private AI platform.
            Everything runs locally.
            No cloud dependencies.
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        )
        assert doc_is_migrated(doc) is False

    def test_real_generated_block_with_small_fence_is_migrated(self, tmp_path):
        doc = tmp_path / "real.md"
        doc.write_text(
            textwrap.dedent("""\
            # Doc

            <!-- WIKI:GENERATED unit=some-unit -->
            generated content line one
            generated content line two
            generated content line three
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED reason="brief aside" -->
            A small note.
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        )
        # ratio = 1/(3+1) = 0.25 < 0.40 → True
        assert doc_is_migrated(doc) is True

    def test_fence_without_reason_not_migrated(self, tmp_path):
        doc = tmp_path / "bad.md"
        doc.write_text(
            textwrap.dedent("""\
            # Doc

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED -->
            content without reason
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        )
        assert doc_is_migrated(doc) is False

    def test_no_generated_blocks_not_migrated(self, tmp_path):
        doc = tmp_path / "nogen.md"
        doc.write_text(
            textwrap.dedent("""\
            # Doc

            <!-- WIKI:HUMAN-OWNED reason="all judgment" -->
            This has no generated blocks at all.
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        )
        assert doc_is_migrated(doc) is False

    def test_ratio_boundary_at_max(self, tmp_path):
        """Doc with human ratio exactly at HUMAN_FENCE_MAX should pass."""
        # 2 gen lines + 2 human lines = ratio 0.50 > 0.40
        doc = tmp_path / "ratio.md"
        doc.write_text(
            textwrap.dedent("""\
            # Doc

            <!-- WIKI:GENERATED unit=a -->
            gen line one
            gen line two
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED reason="test" -->
            human line one
            human line two
            human line three
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        )
        # ratio = 3/(2+3) = 0.60 > 0.40 → False
        assert doc_is_migrated(doc) is False

    def test_ratio_within_bound(self, tmp_path):
        doc = tmp_path / "ok.md"
        doc.write_text(
            textwrap.dedent("""\
            # Doc

            <!-- WIKI:GENERATED unit=a -->
            gen one
            gen two
            gen three
            gen four
            gen five
            <!-- /WIKI:GENERATED -->

            <!-- WIKI:HUMAN-OWNED reason="brief" -->
            one human line
            <!-- /WIKI:HUMAN-OWNED -->
        """)
        )
        # ratio = 1/(5+1) = 0.167 < 0.40 → True
        assert doc_is_migrated(doc) is True

    def test_unmigrated_content_detected(self, tmp_path):
        doc = tmp_path / "partial.md"
        doc.write_text(
            textwrap.dedent("""\
            # Doc

            <!-- WIKI:GENERATED unit=x -->
            body
            <!-- /WIKI:GENERATED -->

            This line is outside any fence and is substantive.
        """)
        )
        assert doc_is_migrated(doc) is False
