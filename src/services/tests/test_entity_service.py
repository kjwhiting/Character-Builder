import pytest

from src.services.entity_service import EntityService
from src.services.errors import EntityNotFoundError, FieldNotFoundError, InvalidNameError, InvalidValueError


def names(entities):
    return [e.name for e in entities.list_entities()]


class TestCreatingEntries:
    def test_an_entry_is_stored_with_its_name_and_image(self, entities):
        entry = entities.get_entity(entities.create_entity(" Aria Vale ", " aria.png "))

        assert (entry.name, entry.image) == ("Aria Vale", "aria.png")

    def test_an_entry_gets_a_unique_permanent_identifier(self, entities):
        first = entities.get_entity(entities.create_entity("A"))
        second = entities.get_entity(entities.create_entity("B"))

        assert first.uuid and second.uuid and first.uuid != second.uuid

    def test_a_blank_name_is_rejected(self, entities):
        with pytest.raises(InvalidNameError):
            entities.create_entity("   ")

        assert names(entities) == []

    def test_two_entries_may_share_a_name(self, entities):
        entities.create_entity("Aria")
        entities.create_entity("Aria")

        assert names(entities) == ["Aria", "Aria"]

    def test_values_are_stored_under_their_fields(self, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Hometown"].id: "Reed Hollow"})

        assert entities.get_values(entry) == {fields["Hometown"].id: "Reed Hollow"}

    def test_blank_values_are_not_stored(self, entities, fields):
        entry = entities.create_entity("Aria", values={
            fields["Hometown"].id: "Reed Hollow", fields["Summary"].id: "   "})

        assert entities.get_values(entry) == {fields["Hometown"].id: "Reed Hollow"}

    def test_a_value_for_an_unknown_field_is_rejected(self, entities, fields):
        with pytest.raises(FieldNotFoundError):
            entities.create_entity("Aria", values={9999: "x"})

    def test_a_failed_save_leaves_nothing_behind(self, entities, fields):
        with pytest.raises(FieldNotFoundError):
            entities.create_entity("Aria", values={fields["Age"].id: "30", 9999: "x"})

        assert names(entities) == []

    def test_a_value_for_a_field_in_another_tab_is_rejected(self, connection, entities, places):
        other = field_in_another_tab(connection, places)

        with pytest.raises(FieldNotFoundError):
            entities.create_entity("Aria", values={other.id: "x"})


def field_in_another_tab(connection, tab):
    from src.services.category_service import CategoryService

    service = CategoryService(connection, tab.id)
    service.add_category("Basics")
    return service.add_field("Basics", "Terrain")


class TestValueRules:
    def test_a_number_field_accepts_whole_and_decimal_numbers(self, entities, fields):
        first = entities.create_entity("A", values={fields["Age"].id: "29"})
        second = entities.create_entity("B", values={fields["Height"].id: " 172.5 "})

        assert entities.get_values(first) == {fields["Age"].id: "29"}
        assert entities.get_values(second) == {fields["Height"].id: "172.5"}

    def test_a_number_field_rejects_text_and_names_the_field(self, entities, fields):
        with pytest.raises(InvalidValueError, match="Height must be a number"):
            entities.create_entity("A", values={fields["Height"].id: "tall"})

    def test_a_checked_checkbox_is_stored_as_true(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Alive"].id: "TRUE"})

        assert entities.get_values(entry) == {fields["Alive"].id: "true"}

    def test_an_unchecked_checkbox_stores_nothing(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Alive"].id: ""})

        assert entities.get_values(entry) == {}

    def test_anything_but_true_in_a_checkbox_stores_nothing(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Alive"].id: "yes please"})

        assert entities.get_values(entry) == {}

    def test_list_items_are_trimmed_and_blank_lines_dropped(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Tags"].id: " one \n\n two\n  \n"})

        assert entities.get_values(entry) == {fields["Tags"].id: "one\ntwo"}

    def test_multichoice_selections_are_stored_one_per_line(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Traits"].id: "Brave\n Shy "})

        assert entities.get_values(entry) == {fields["Traits"].id: "Brave\nShy"}

    def test_a_paragraph_keeps_its_inner_line_breaks(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Summary"].id: " Line one\nLine two "})

        assert entities.get_values(entry) == {fields["Summary"].id: "Line one\nLine two"}


class TestUpdatingEntries:
    def test_the_name_and_image_can_change(self, entities):
        entry = entities.create_entity("Aria", "old.png")

        entities.update_entity(entry, "Aria Vale", "new.png")

        updated = entities.get_entity(entry)
        assert (updated.name, updated.image) == ("Aria Vale", "new.png")

    def test_a_blank_new_name_is_rejected(self, entities):
        entry = entities.create_entity("Aria")

        with pytest.raises(InvalidNameError):
            entities.update_entity(entry, "")

        assert entities.get_entity(entry).name == "Aria"

    def test_values_are_replaced_for_the_fields_given(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Hometown"].id: "Old"})

        entities.update_entity(entry, "A", values={fields["Hometown"].id: "New"})

        assert entities.get_values(entry) == {fields["Hometown"].id: "New"}

    def test_a_blank_value_clears_a_field(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Hometown"].id: "Old"})

        entities.update_entity(entry, "A", values={fields["Hometown"].id: ""})

        assert entities.get_values(entry) == {}

    def test_fields_not_mentioned_keep_their_values(self, entities, fields):
        entry = entities.create_entity("A", values={fields["Hometown"].id: "Old"})

        entities.update_entity(entry, "A", values={fields["Summary"].id: "Hello"})

        assert entities.get_values(entry) == {
            fields["Hometown"].id: "Old", fields["Summary"].id: "Hello"}

    def test_a_failed_update_changes_nothing(self, entities, fields):
        entry = entities.create_entity("Aria")

        with pytest.raises(FieldNotFoundError):
            entities.update_entity(entry, "Renamed", values={9999: "x"})

        assert entities.get_entity(entry).name == "Aria"

    def test_an_invalid_number_on_update_changes_nothing(self, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Age"].id: "30"})

        with pytest.raises(InvalidValueError):
            entities.update_entity(entry, "Aria II", values={fields["Age"].id: "old"})

        assert entities.get_entity(entry).name == "Aria"
        assert entities.get_values(entry) == {fields["Age"].id: "30"}

    def test_updating_a_missing_entry_is_an_error(self, entities):
        with pytest.raises(EntityNotFoundError):
            entities.update_entity(999, "Name")


class TestListingAndSearching:
    def test_entries_are_listed_alphabetically_ignoring_case(self, entities):
        for name in ("zed", "Bram", "aria"):
            entities.create_entity(name)

        assert names(entities) == ["aria", "Bram", "zed"]

    def test_a_blank_search_lists_everything(self, entities):
        entities.create_entity("Aria")
        entities.create_entity("Bram")

        assert [e.name for e in entities.search_entities("   ")] == ["Aria", "Bram"]

    def test_search_matches_part_of_a_name_ignoring_case(self, entities):
        entities.create_entity("Aria Vale")
        entities.create_entity("Bram")

        assert [e.name for e in entities.search_entities("VALE")] == ["Aria Vale"]

    def test_search_matches_text_inside_field_values(self, entities, fields):
        entities.create_entity("Aria", values={fields["Summary"].id: "Lives by the river"})
        entities.create_entity("Bram")

        assert [e.name for e in entities.search_entities("river")] == ["Aria"]

    def test_search_matches_alternate_names(self, entities):
        entities.create_entity("Aria Vale", aliases=["the Captain"])

        assert [e.name for e in entities.search_entities("captain")] == ["Aria Vale"]

    def test_an_entry_matching_in_several_places_is_listed_once(self, entities, fields):
        entities.create_entity("Teal", values={fields["Hometown"].id: "Teal Bay"},
                               aliases=["Teal One"])

        assert len(entities.search_entities("teal")) == 1

    def test_percent_and_underscore_in_a_search_are_taken_literally(self, entities, fields):
        entities.create_entity("Plain")
        entities.create_entity("Odd", values={fields["Summary"].id: "100% sure_thing"})

        assert [e.name for e in entities.search_entities("100%")] == ["Odd"]
        assert [e.name for e in entities.search_entities("e_t")] == ["Odd"]
        assert entities.search_entities("%") == [entities.get_entity(
            entities.search_entities("%")[0].id)]

    def test_a_search_with_no_match_returns_nothing(self, entities):
        entities.create_entity("Aria")

        assert entities.search_entities("dragon") == []


class TestEachTabKeepsItsOwnEntries:
    def test_entries_do_not_appear_in_other_tabs(self, connection, entities, places):
        entities.create_entity("Aria")
        other = EntityService(connection, places.id)
        other.create_entity("Old Mill")

        assert names(entities) == ["Aria"]
        assert names(other) == ["Old Mill"]

    def test_an_entry_cannot_be_read_through_another_tab(self, connection, entities, places):
        entry = entities.create_entity("Aria")
        other = EntityService(connection, places.id)

        with pytest.raises(EntityNotFoundError):
            other.get_entity(entry)

    def test_an_entry_cannot_be_changed_or_deleted_through_another_tab(
        self, connection, entities, places
    ):
        entry = entities.create_entity("Aria")
        other = EntityService(connection, places.id)

        with pytest.raises(EntityNotFoundError):
            other.update_entity(entry, "Hijacked")
        with pytest.raises(EntityNotFoundError):
            other.delete_entity(entry)

        assert entities.get_entity(entry).name == "Aria"

    def test_search_never_crosses_tabs(self, connection, entities, places):
        entities.create_entity("Aria")
        EntityService(connection, places.id).create_entity("Aria Bay")

        assert [e.name for e in entities.search_entities("aria")] == ["Aria"]


class TestDeletingEntries:
    def test_a_deleted_entry_disappears_from_lists_and_search(self, entities):
        entry = entities.create_entity("Aria")

        entities.delete_entity(entry)

        assert names(entities) == []
        assert entities.search_entities("aria") == []

    def test_a_deleted_entry_can_no_longer_be_opened(self, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)

        with pytest.raises(EntityNotFoundError):
            entities.get_entity(entry)

    def test_deleting_keeps_the_data_so_the_trash_can_restore_it(self, connection, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Hometown"].id: "Reed"})

        entities.delete_entity(entry)

        stored = connection.execute("SELECT value FROM field_values WHERE entry_id = ?",
                                    (entry,)).fetchone()[0]
        assert stored == "Reed"

    def test_a_deleted_entry_cannot_be_deleted_or_updated_again(self, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)

        with pytest.raises(EntityNotFoundError):
            entities.delete_entity(entry)
        with pytest.raises(EntityNotFoundError):
            entities.update_entity(entry, "Back")

    def test_deleting_a_missing_entry_is_an_error(self, entities):
        with pytest.raises(EntityNotFoundError):
            entities.delete_entity(999)


class TestDuplicatingEntries:
    def test_a_copy_is_named_after_the_original(self, entities):
        entry = entities.create_entity("Aria")

        copy = entities.get_entity(entities.duplicate_entity(entry))

        assert copy.name == "Aria (Copy)"

    def test_a_copy_can_be_given_its_own_name(self, entities):
        entry = entities.create_entity("Aria")

        assert entities.get_entity(entities.duplicate_entity(entry, "  Twin ")).name == "Twin"

    def test_a_blank_copy_name_creates_nothing(self, entities):
        entry = entities.create_entity("Aria")

        with pytest.raises(InvalidNameError):
            entities.duplicate_entity(entry, " ")

        assert names(entities) == ["Aria"]

    def test_a_copy_has_the_same_image_values_and_alternate_names(self, entities, fields):
        entry = entities.create_entity(
            "Aria", "aria.png", {fields["Age"].id: "30", fields["Tags"].id: "a\nb"},
            aliases=["Cap"])

        copy = entities.duplicate_entity(entry)

        assert entities.get_entity(copy).image == "aria.png"
        assert entities.get_values(copy) == entities.get_values(entry)
        assert entities.get_aliases(copy) == ["Cap"]

    def test_a_copy_has_its_own_identifier(self, entities):
        entry = entities.create_entity("Aria")

        copy = entities.duplicate_entity(entry)

        assert entities.get_entity(copy).uuid != entities.get_entity(entry).uuid

    def test_changing_the_copy_leaves_the_original_alone(self, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Age"].id: "30"})
        copy = entities.duplicate_entity(entry)

        entities.update_entity(copy, "Copy", values={fields["Age"].id: "99"})

        assert entities.get_values(entry) == {fields["Age"].id: "30"}

    def test_deleting_the_original_leaves_the_copy(self, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Age"].id: "30"})
        copy = entities.duplicate_entity(entry)

        entities.delete_entity(entry)

        assert entities.get_values(copy) == {fields["Age"].id: "30"}

    def test_duplicating_a_missing_entry_is_an_error(self, entities):
        with pytest.raises(EntityNotFoundError):
            entities.duplicate_entity(999)


class TestAlternateNames:
    def test_alternate_names_are_kept_in_the_order_given(self, entities):
        entry = entities.create_entity("Aria Vale", aliases=["the Captain", "Aria"])

        assert entities.get_aliases(entry) == ["the Captain", "Aria"]

    def test_blanks_duplicates_and_the_entrys_own_name_are_dropped(self, entities):
        entry = entities.create_entity(
            "Aria Vale", aliases=["Aria", " ", "aria", "ARIA VALE", "Cap"])

        assert entities.get_aliases(entry) == ["Aria", "Cap"]

    def test_updating_with_a_list_replaces_the_alternate_names(self, entities):
        entry = entities.create_entity("Aria", aliases=["A"])

        entities.update_entity(entry, "Aria", aliases=["B", "C"])

        assert entities.get_aliases(entry) == ["B", "C"]

    def test_updating_with_an_empty_list_clears_them(self, entities):
        entry = entities.create_entity("Aria", aliases=["A"])

        entities.update_entity(entry, "Aria", aliases=[])

        assert entities.get_aliases(entry) == []

    def test_updating_without_the_argument_leaves_them_alone(self, entities):
        entry = entities.create_entity("Aria", aliases=["A"])

        entities.update_entity(entry, "Aria II")

        assert entities.get_aliases(entry) == ["A"]

    def test_an_entry_with_none_reports_an_empty_list(self, entities):
        assert entities.get_aliases(entities.create_entity("Aria")) == []
