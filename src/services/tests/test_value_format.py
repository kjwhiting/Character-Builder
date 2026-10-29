import pytest

from src.services.value_format import CHECKBOX_TRUE, format_value, split_lines


class TestSplittingLines:
    def test_lines_are_trimmed_and_blank_ones_dropped(self):
        assert split_lines(" a \n\n  b\n   \nc ") == ["a", "b", "c"]

    @pytest.mark.parametrize("empty", [None, "", "   \n  "])
    def test_nothing_in_gives_an_empty_list(self, empty):
        assert split_lines(empty) == []


class TestFormattingValues:
    def test_text_is_trimmed(self):
        assert format_value("text", {}, "  hello ") == "hello"

    def test_a_paragraph_keeps_its_line_breaks(self):
        assert format_value("textarea", {}, "one\ntwo") == "one\ntwo"

    def test_list_items_are_joined_with_commas(self):
        assert format_value("list", {}, "a\n\n b \nc") == "a, b, c"

    def test_multichoice_selections_are_joined_with_commas(self):
        assert format_value("multichoice", {}, "Brave\nShy") == "Brave, Shy"

    def test_a_choice_is_shown_as_it_was_picked(self):
        assert format_value("choice", {"choices": ["Hero"]}, "Hero") == "Hero"

    def test_a_checked_checkbox_reads_yes(self):
        assert format_value("checkbox", {}, CHECKBOX_TRUE) == "Yes"

    @pytest.mark.parametrize("unchecked", ["", None, "false", "no"])
    def test_anything_else_in_a_checkbox_reads_no(self, unchecked):
        assert format_value("checkbox", {}, unchecked) == "No"

    def test_a_number_is_followed_by_its_unit(self):
        assert format_value("number", {"unit": "cm"}, "172") == "172 cm"

    def test_a_number_without_a_unit_is_shown_plainly(self):
        assert format_value("number", {}, "172") == "172"

    def test_an_empty_number_stays_empty_even_with_a_unit(self):
        assert format_value("number", {"unit": "cm"}, "") == ""

    @pytest.mark.parametrize("field_type", ["text", "list", "choice", "multichoice", "number"])
    def test_empty_values_format_to_nothing(self, field_type):
        assert format_value(field_type, {}, None) == ""
