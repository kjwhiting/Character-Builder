import pytest

from src.services.category_service import CategoryService, normalize_options
from src.services.errors import (
    CategoryNotEmptyError,
    CategoryNotFoundError,
    DuplicateCategoryError,
    DuplicateFieldError,
    FieldNotFoundError,
    InvalidFieldTypeError,
    InvalidNameError,
    InvalidOrderError,
)


def field_names(categories, category=None):
    return [f.name for f in categories.list_fields(category)]


class TestSections:
    def test_a_new_tab_has_no_sections(self, categories):
        assert categories.list_categories() == []

    def test_sections_are_listed_in_the_order_they_were_added(self, categories):
        for name in ("Basics", "Notes", "Extra"):
            categories.add_category(name)

        assert categories.list_categories() == ["Basics", "Notes", "Extra"]

    def test_section_names_are_trimmed(self, categories):
        assert categories.add_category("  Basics ") == "Basics"

    def test_a_blank_section_name_is_rejected(self, categories):
        with pytest.raises(InvalidNameError):
            categories.add_category("  ")

    def test_a_section_name_in_use_is_rejected_ignoring_case(self, categories):
        categories.add_category("Basics")

        with pytest.raises(DuplicateCategoryError):
            categories.add_category("BASICS")

    def test_two_tabs_can_have_sections_with_the_same_name(self, connection, categories, places):
        categories.add_category("Basics")

        CategoryService(connection, places.id).add_category("Basics")

        assert CategoryService(connection, places.id).list_categories() == ["Basics"]

    def test_a_section_can_be_renamed_and_keeps_its_fields(self, categories, fields):
        categories.rename_category("Notes", "Details")

        assert categories.list_categories() == ["Basics", "Details"]
        assert field_names(categories, "Details") == ["Summary", "Tags", "Traits", "Hometown"]

    def test_a_section_cannot_take_another_sections_name(self, categories, fields):
        with pytest.raises(DuplicateCategoryError):
            categories.rename_category("Notes", "basics")

    def test_a_section_can_change_only_the_case_of_its_name(self, categories, fields):
        categories.rename_category("Notes", "NOTES")

        assert categories.list_categories() == ["Basics", "NOTES"]

    def test_renaming_a_missing_section_is_an_error(self, categories):
        with pytest.raises(CategoryNotFoundError):
            categories.rename_category("Nope", "Other")

    def test_sections_can_be_reordered(self, categories, fields):
        categories.reorder_categories(["Notes", "Basics"])

        assert categories.list_categories() == ["Notes", "Basics"]

    def test_fields_follow_their_sections_when_reordered(self, categories, fields):
        categories.reorder_categories(["Notes", "Basics"])

        assert field_names(categories)[:2] == ["Summary", "Tags"]

    @pytest.mark.parametrize("bad", [["Basics"], ["Basics", "Notes", "Notes"], ["Basics", "Ghost"]])
    def test_a_reordering_that_misses_or_repeats_a_section_is_rejected(
        self, categories, fields, bad
    ):
        with pytest.raises((InvalidOrderError, CategoryNotFoundError)):
            categories.reorder_categories(bad)

        assert categories.list_categories() == ["Basics", "Notes"]


class TestDeletingASection:
    def test_a_section_with_fields_cannot_be_deleted(self, categories, fields):
        with pytest.raises(CategoryNotEmptyError, match="still has 4 field"):
            categories.delete_category("Basics")

        assert "Basics" in categories.list_categories()

    def test_the_refusal_leaves_every_field_in_place(self, categories, fields):
        with pytest.raises(CategoryNotEmptyError):
            categories.delete_category("Basics")

        assert len(categories.list_fields()) == 8

    def test_an_empty_section_can_be_deleted(self, categories):
        categories.add_category("Scratch")

        categories.delete_category("scratch")

        assert categories.list_categories() == []

    def test_a_section_can_be_deleted_once_its_fields_move_elsewhere(self, categories, fields):
        for field in categories.list_fields("Basics"):
            categories.move_field(field.id, "Notes")

        categories.delete_category("Basics")

        assert categories.list_categories() == ["Notes"]

    def test_a_section_can_be_deleted_once_its_fields_are_deleted(self, categories, fields):
        for field in categories.list_fields("Basics"):
            categories.delete_field(field.id)

        categories.delete_category("Basics")

        assert categories.list_categories() == ["Notes"]

    def test_deleting_a_missing_section_is_an_error(self, categories):
        with pytest.raises(CategoryNotFoundError):
            categories.delete_category("Ghost")

    def test_fields_in_a_section_can_be_counted(self, categories, fields):
        assert categories.count_fields("Basics") == 4


class TestAddingFields:
    def test_a_field_appears_at_the_end_of_its_section(self, categories):
        categories.add_category("Basics")
        categories.add_field("Basics", "Age", "number")

        added = categories.add_field("Basics", "Height", "number")

        assert field_names(categories, "Basics") == ["Age", "Height"]
        assert added.sort_order == 1

    def test_a_field_remembers_its_type_and_section(self, categories):
        categories.add_category("Basics")

        field = categories.add_field("Basics", "Alive", "checkbox")

        assert (field.category, field.name, field.field_type) == ("Basics", "Alive", "checkbox")

    def test_the_default_type_is_text(self, categories):
        categories.add_category("Basics")

        assert categories.add_field("Basics", "Hometown").field_type == "text"

    def test_a_new_field_hides_when_empty_and_uses_automatic_width(self, categories):
        categories.add_category("Basics")

        field = categories.add_field("Basics", "Hometown")

        assert (field.show_empty, field.full_width) == (False, False)

    def test_choices_are_trimmed_and_deduplicated_ignoring_case(self, categories):
        categories.add_category("Basics")

        field = categories.add_field(
            "Basics", "Role", "choice", {"choices": [" Hero ", "hero", "", "Villain"]})

        assert field.options == {"choices": ["Hero", "Villain"]}

    def test_a_number_field_keeps_its_unit(self, categories):
        categories.add_category("Basics")

        field = categories.add_field("Basics", "Height", "number", {"unit": " cm "})

        assert field.options == {"unit": "cm"}

    def test_options_are_dropped_for_types_that_do_not_use_them(self, categories):
        categories.add_category("Basics")

        field = categories.add_field("Basics", "Hometown", "text", {"unit": "cm"})

        assert field.options == {}

    def test_a_field_name_in_use_is_rejected_ignoring_case(self, categories, fields):
        with pytest.raises(DuplicateFieldError):
            categories.add_field("Basics", "age")

    def test_two_sections_can_each_have_a_field_with_the_same_name(self, categories, fields):
        categories.add_field("Notes", "Age")

        assert field_names(categories).count("Age") == 2

    def test_an_unsupported_type_is_rejected(self, categories):
        categories.add_category("Basics")

        with pytest.raises(InvalidFieldTypeError):
            categories.add_field("Basics", "Colour", "rainbow")

    def test_a_blank_field_name_is_rejected(self, categories):
        categories.add_category("Basics")

        with pytest.raises(InvalidNameError):
            categories.add_field("Basics", " ")

    def test_adding_to_a_missing_section_is_an_error(self, categories):
        with pytest.raises(CategoryNotFoundError):
            categories.add_field("Ghost", "Name")


class TestListingFields:
    def test_fields_come_back_by_section_order_then_field_order(self, categories, fields):
        assert field_names(categories) == [
            "Age", "Height", "Alive", "Role", "Summary", "Tags", "Traits", "Hometown"]

    def test_fields_can_be_listed_for_one_section(self, categories, fields):
        assert field_names(categories, "Notes") == ["Summary", "Tags", "Traits", "Hometown"]

    def test_a_field_can_be_fetched_by_id(self, categories, fields):
        assert categories.get_field(fields["Height"].id).name == "Height"

    def test_a_missing_field_is_an_error(self, categories):
        with pytest.raises(FieldNotFoundError):
            categories.get_field(999)

    def test_a_field_from_another_tab_is_not_visible(self, connection, fields, places):
        other = CategoryService(connection, places.id)

        with pytest.raises(FieldNotFoundError):
            other.get_field(fields["Age"].id)

    def test_listing_never_mixes_in_fields_from_another_tab(self, connection, fields, places):
        other = CategoryService(connection, places.id)
        other.add_category("Basics")
        other.add_field("Basics", "Terrain")

        assert field_names(other) == ["Terrain"]


class TestRenamingAndRetypingFields:
    def test_a_field_can_be_renamed(self, categories, fields):
        assert categories.rename_field(fields["Age"].id, " Years old ").name == "Years old"

    def test_a_field_cannot_take_a_name_used_in_its_section(self, categories, fields):
        with pytest.raises(DuplicateFieldError):
            categories.rename_field(fields["Age"].id, "height")

    def test_a_field_can_change_only_the_case_of_its_name(self, categories, fields):
        assert categories.rename_field(fields["Age"].id, "AGE").name == "AGE"

    def test_a_blank_name_is_rejected(self, categories, fields):
        with pytest.raises(InvalidNameError):
            categories.rename_field(fields["Age"].id, "")

    def test_switching_between_choice_and_multichoice_keeps_the_options(self, categories, fields):
        changed = categories.change_field_type(fields["Role"].id, "multichoice")

        assert changed.options == {"choices": ["Hero", "Villain"]}

    def test_switching_to_a_type_without_options_clears_them(self, categories, fields):
        changed = categories.change_field_type(fields["Role"].id, "text")

        assert changed.options == {}

    def test_switching_from_number_to_choice_clears_the_unit(self, categories, fields):
        changed = categories.change_field_type(fields["Age"].id, "choice")

        assert changed.options == {}

    def test_an_unsupported_type_is_rejected(self, categories, fields):
        with pytest.raises(InvalidFieldTypeError):
            categories.change_field_type(fields["Age"].id, "rainbow")

    def test_retyping_a_missing_field_is_an_error(self, categories):
        with pytest.raises(FieldNotFoundError):
            categories.change_field_type(999, "text")


class TestFieldOptions:
    def test_choices_can_be_replaced(self, categories, fields):
        changed = categories.set_field_options(
            fields["Role"].id, {"choices": ["Ally", "Foe", "ally"]})

        assert changed.options == {"choices": ["Ally", "Foe"]}

    def test_clearing_all_choices_leaves_no_options(self, categories, fields):
        assert categories.set_field_options(fields["Role"].id, {"choices": []}).options == {}

    def test_a_unit_can_be_changed_or_removed(self, categories, fields):
        assert categories.set_field_options(fields["Age"].id, {"unit": "yrs"}).options == {
            "unit": "yrs"}
        assert categories.set_field_options(fields["Age"].id, {"unit": ""}).options == {}

    def test_options_are_ignored_for_plain_text_fields(self, categories, fields):
        changed = categories.set_field_options(fields["Hometown"].id, {"choices": ["a"]})

        assert changed.options == {}


class TestNormalizingOptions:
    def test_choice_options_keep_the_first_spelling_of_each_choice(self):
        assert normalize_options("choice", {"choices": ["Red", "RED", "Blue"]}) == {
            "choices": ["Red", "Blue"]}

    def test_choice_options_accept_non_string_entries(self):
        assert normalize_options("multichoice", {"choices": [1, 2]}) == {"choices": ["1", "2"]}

    def test_missing_options_normalize_to_nothing(self):
        assert normalize_options("choice", None) == {}
        assert normalize_options("number", {}) == {}

    def test_text_fields_never_keep_options(self):
        assert normalize_options("text", {"unit": "cm", "choices": ["a"]}) == {}


class TestDisplaySettings:
    def test_a_field_can_be_set_to_show_even_when_empty(self, categories, fields):
        assert categories.set_field_display(fields["Age"].id, show_empty=True).show_empty is True

    def test_a_field_can_be_set_to_full_width(self, categories, fields):
        assert categories.set_field_display(fields["Age"].id, full_width=True).full_width is True

    def test_changing_one_setting_leaves_the_other(self, categories, fields):
        categories.set_field_display(fields["Age"].id, show_empty=True, full_width=True)

        changed = categories.set_field_display(fields["Age"].id, show_empty=False)

        assert (changed.show_empty, changed.full_width) == (False, True)


class TestDeletingFields:
    def test_the_values_stored_under_a_field_are_counted(self, categories, entities, fields):
        entities.create_entity("A", values={fields["Age"].id: "1"})
        entities.create_entity("B", values={fields["Age"].id: "2"})

        assert categories.count_field_values(fields["Age"].id) == 2

    def test_deleting_a_field_removes_it_and_its_values(self, categories, entities, fields):
        entry = entities.create_entity("A", values={fields["Age"].id: "1",
                                                    fields["Height"].id: "170"})

        categories.delete_field(fields["Age"].id)

        assert entities.get_values(entry) == {fields["Height"].id: "170"}
        assert "Age" not in field_names(categories)

    def test_the_remaining_fields_close_the_gap(self, categories, fields):
        categories.delete_field(fields["Age"].id)

        assert [(f.name, f.sort_order) for f in categories.list_fields("Basics")] == [
            ("Height", 0), ("Alive", 1), ("Role", 2)]

    def test_deleting_a_missing_field_is_an_error(self, categories):
        with pytest.raises(FieldNotFoundError):
            categories.delete_field(999)


class TestMovingFields:
    def test_a_field_can_move_to_the_end_of_another_section(self, categories, fields):
        moved = categories.move_field(fields["Age"].id, "Notes")

        assert moved.category == "Notes"
        assert field_names(categories, "Notes")[-1] == "Age"

    def test_both_sections_are_renumbered_after_a_move(self, categories, fields):
        categories.move_field(fields["Age"].id, "Notes")

        assert [f.sort_order for f in categories.list_fields("Basics")] == [0, 1, 2]
        assert [f.sort_order for f in categories.list_fields("Notes")] == [0, 1, 2, 3, 4]

    def test_a_field_can_move_to_a_chosen_position(self, categories, fields):
        categories.move_field(fields["Age"].id, "Notes", 1)

        assert field_names(categories, "Notes") == ["Summary", "Age", "Tags", "Traits", "Hometown"]

    def test_a_position_past_either_end_is_clamped(self, categories, fields):
        categories.move_field(fields["Age"].id, "Notes", 99)
        assert field_names(categories, "Notes")[-1] == "Age"

        categories.move_field(fields["Height"].id, "Notes", -5)
        assert field_names(categories, "Notes")[0] == "Height"

    def test_a_field_can_move_within_its_own_section(self, categories, fields):
        categories.move_field(fields["Role"].id, "Basics", 0)

        assert field_names(categories, "Basics") == ["Role", "Age", "Height", "Alive"]

    def test_moving_keeps_the_values_already_entered(self, categories, entities, fields):
        entry = entities.create_entity("A", values={fields["Age"].id: "30"})

        categories.move_field(fields["Age"].id, "Notes")

        assert entities.get_values(entry) == {fields["Age"].id: "30"}

    def test_a_name_clash_in_the_target_section_blocks_the_move(self, categories, fields):
        categories.add_field("Notes", "Age")

        with pytest.raises(DuplicateFieldError):
            categories.move_field(fields["Age"].id, "Notes")

        assert "Age" in field_names(categories, "Basics")

    def test_moving_to_a_missing_section_is_an_error(self, categories, fields):
        with pytest.raises(CategoryNotFoundError):
            categories.move_field(fields["Age"].id, "Ghost")


class TestReorderingFields:
    def test_fields_can_be_put_in_a_new_order(self, categories, fields):
        ids = [fields[n].id for n in ("Alive", "Role", "Height", "Age")]

        categories.reorder_fields("Basics", ids)

        assert field_names(categories, "Basics") == ["Alive", "Role", "Height", "Age"]

    def test_the_order_must_list_exactly_the_sections_fields(self, categories, fields):
        with pytest.raises(InvalidOrderError):
            categories.reorder_fields("Basics", [fields["Age"].id, fields["Summary"].id])

        assert field_names(categories, "Basics") == ["Age", "Height", "Alive", "Role"]
