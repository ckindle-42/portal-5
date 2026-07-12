"""Parser resilience tests (§4.4) — every documented edge case."""

from __future__ import annotations

from portal.platform.inference.tool_preselect.parser import (
    indices_to_tool_names,
    parse_ranked_indices,
)


class TestParseRankedIndices:
    def test_plain_newline_numbers(self):
        assert parse_ranked_indices("1\n2\n3", valid_max=5) == [1, 2, 3]

    def test_trailing_period(self):
        assert parse_ranked_indices("1.\n2.\n3.", valid_max=5) == [1, 2, 3]

    def test_parens_wrapped(self):
        assert parse_ranked_indices("(1)\n(2)\n(3)", valid_max=5) == [1, 2, 3]

    def test_trailing_paren(self):
        assert parse_ranked_indices("1)\n2)\n3)", valid_max=5) == [1, 2, 3]

    def test_number_with_tool_name_appended(self):
        assert parse_ranked_indices("1. run_bash\n2. web_search", valid_max=5) == [1, 2]

    def test_comma_separated(self):
        assert parse_ranked_indices("1, 2, 3", valid_max=5) == [1, 2, 3]

    def test_comma_and_newline_mixed(self):
        assert parse_ranked_indices("1, 2\n3", valid_max=5) == [1, 2, 3]

    def test_preamble_and_postamble(self):
        text = "Here are the 3 most relevant tools:\n1. web_search\n2. read_file\n3. write_file\nThanks!"
        assert parse_ranked_indices(text, valid_max=5) == [1, 2, 3]

    def test_out_of_range_discarded(self):
        assert parse_ranked_indices("1\n2\n99", valid_max=5) == [1, 2]

    def test_zero_discarded(self):
        assert parse_ranked_indices("0\n1\n2", valid_max=5) == [1, 2]

    def test_duplicates_discarded_first_occurrence_order(self):
        assert parse_ranked_indices("1\n2\n1\n3\n2", valid_max=5) == [1, 2, 3]

    def test_empty_input(self):
        assert parse_ranked_indices("", valid_max=5) == []

    def test_no_numbers_present(self):
        assert parse_ranked_indices("I cannot help with that request.", valid_max=5) == []

    def test_no_false_positive_inside_identifier(self):
        # "bash2" should not yield a spurious index 2
        assert parse_ranked_indices("run_bash2 seems relevant", valid_max=5) == []


class TestIndicesToToolNames:
    def test_maps_in_order(self):
        names = ["web_search", "read_file", "write_file"]
        assert indices_to_tool_names([2, 1], names) == ["read_file", "web_search"]

    def test_out_of_range_indices_dropped(self):
        names = ["web_search", "read_file"]
        assert indices_to_tool_names([1, 99, 2], names) == ["web_search", "read_file"]

    def test_empty_indices(self):
        assert indices_to_tool_names([], ["a", "b"]) == []
