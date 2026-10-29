import re

import pytest

from src.services.category_service import CategoryService
from src.services.collection_service import CollectionService, new_uuid
from src.services.entity_service import EntityService
from src.services.errors import (
    CollectionNotFoundError,
    DuplicateCollectionError,
    InvalidColorError,
    InvalidNameError,
    InvalidOrderError,
)


def labels(collections):
    return [c.label for c in collections.list_collections()]


class TestAddingATab:
    def test_a_new_tab_is_listed_with_its_name_and_entry_noun(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        assert (tab.label, tab.entry_noun) == ("Magic", "Spell")
        assert labels(collections) == ["Magic"]

    def test_tabs_keep_the_order_they_were_added_in(self, collections):
        for name in ("Zebra", "Apple", "Mango"):
            collections.add_collection(name, "Thing")

        assert labels(collections) == ["Zebra", "Apple", "Mango"]

    def test_each_new_tab_takes_the_next_sort_position(self, collections):
        first = collections.add_collection("One", "Thing")
        second = collections.add_collection("Two", "Thing")

        assert (first.sort_order, second.sort_order) == (0, 1)

    def test_names_are_trimmed(self, collections):
        tab = collections.add_collection("  Magic  ", "  Spell ")

        assert (tab.label, tab.entry_noun) == ("Magic", "Spell")

    def test_a_blank_tab_name_is_rejected(self, collections):
        with pytest.raises(InvalidNameError):
            collections.add_collection("   ", "Spell")

    def test_a_blank_entry_noun_is_rejected(self, collections):
        with pytest.raises(InvalidNameError):
            collections.add_collection("Magic", "")

    def test_a_tab_name_that_already_exists_is_rejected_ignoring_case(self, collections):
        collections.add_collection("Magic", "Spell")

        with pytest.raises(DuplicateCollectionError):
            collections.add_collection("MAGIC", "Spell")

    def test_a_rejected_tab_leaves_the_list_unchanged(self, collections):
        collections.add_collection("Magic", "Spell")

        with pytest.raises(DuplicateCollectionError):
            collections.add_collection("magic", "Spell")

        assert labels(collections) == ["Magic"]

    def test_a_new_tab_starts_with_no_categories_or_fields(self, collections, connection):
        tab = collections.add_collection("Magic", "Spell")

        assert CategoryService(connection, tab.id).list_categories() == []
        assert CategoryService(connection, tab.id).list_fields() == []

    def test_a_tab_can_be_given_a_highlight_colour_when_created(self, collections):
        tab = collections.add_collection("Magic", "Spell", color="#123456")

        assert tab.color == "#123456"

    def test_without_a_colour_the_template_colour_is_used(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        assert tab.color == "#8FB3C8"


class TestTabKeys:
    def test_the_key_is_a_lowercase_slug_of_the_name(self, collections):
        assert collections.add_collection("My Big World!", "Thing").key == "my-big-world"

    def test_two_names_that_slug_alike_get_distinct_keys(self, collections):
        first = collections.add_collection("My Tab", "Thing")
        second = collections.add_collection("my-tab!", "Thing")

        assert (first.key, second.key) == ("my-tab", "my-tab-2")

    def test_a_name_without_letters_or_digits_still_gets_a_key(self, collections):
        assert collections.add_collection("!!!", "Thing").key == "tab"


class TestTemplates:
    def test_a_template_creates_its_categories_fields_and_options(self, collections, connection):
        template = {
            "key": "custom", "label": "Custom", "entry_noun": "Thing", "color": "#ABCDEF",
            "categories": [
                {"name": "Basics", "fields": [
                    {"name": "Height", "type": "number", "options": {"unit": "cm"}},
                    {"name": "Notes", "type": "textarea"},
                ]},
                {"name": "Extra", "fields": [{"name": "Tag", "type": "text"}]},
            ],
        }

        tab = collections.add_from_template(template)
        categories = CategoryService(connection, tab.id)

        assert categories.list_categories() == ["Basics", "Extra"]
        assert [(f.name, f.field_type) for f in categories.list_fields()] == [
            ("Height", "number"), ("Notes", "textarea"), ("Tag", "text")]
        assert categories.list_fields("Basics")[0].options == {"unit": "cm"}
        assert tab.color == "#ABCDEF"

    def test_the_label_and_noun_can_override_the_template(self, collections):
        template = {"key": "t", "label": "Template", "entry_noun": "Thing",
                    "color": "#111111", "categories": []}

        tab = collections.add_from_template(template, label="Mine", entry_noun="Item")

        assert (tab.label, tab.entry_noun) == ("Mine", "Item")


class TestRenamingAndEditing:
    def test_a_tab_can_be_renamed(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        renamed = collections.rename_collection(tab.id, "Sorcery")

        assert renamed.label == "Sorcery"
        assert labels(collections) == ["Sorcery"]

    def test_renaming_keeps_the_tab_key(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        assert collections.rename_collection(tab.id, "Sorcery").key == tab.key

    def test_a_tab_cannot_take_the_name_of_another_tab(self, collections):
        collections.add_collection("Magic", "Spell")
        other = collections.add_collection("Places", "Place")

        with pytest.raises(DuplicateCollectionError):
            collections.rename_collection(other.id, "magic")

    def test_a_tab_can_change_only_the_case_of_its_own_name(self, collections):
        tab = collections.add_collection("magic", "Spell")

        assert collections.rename_collection(tab.id, "Magic").label == "Magic"

    def test_a_blank_new_name_is_rejected(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        with pytest.raises(InvalidNameError):
            collections.rename_collection(tab.id, " ")

    def test_the_entry_noun_can_be_changed(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        assert collections.set_entry_noun(tab.id, "Charm").entry_noun == "Charm"

    def test_renaming_a_missing_tab_is_an_error(self, collections):
        with pytest.raises(CollectionNotFoundError):
            collections.rename_collection(999, "Anything")


class TestHighlightColour:
    def test_a_colour_is_stored_in_uppercase(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        assert collections.set_color(tab.id, "#a1b2c3").color == "#A1B2C3"

    @pytest.mark.parametrize("bad", ["red", "#12345", "#GGGGGG", "123456", "", None])
    def test_anything_but_a_six_digit_hex_colour_is_rejected(self, collections, bad):
        tab = collections.add_collection("Magic", "Spell")

        with pytest.raises(InvalidColorError):
            collections.set_color(tab.id, bad)

    def test_a_rejected_colour_leaves_the_old_one(self, collections):
        tab = collections.add_collection("Magic", "Spell", color="#111111")

        with pytest.raises(InvalidColorError):
            collections.set_color(tab.id, "nope")

        assert collections.get_collection(tab.id).color == "#111111"


class TestReordering:
    def test_tabs_can_be_put_in_a_new_order(self, collections):
        ids = [collections.add_collection(n, "Thing").id for n in ("A", "B", "C")]

        collections.reorder_collections([ids[2], ids[0], ids[1]])

        assert labels(collections) == ["C", "A", "B"]

    @pytest.mark.parametrize("bad_order", [lambda ids: ids[:-1], lambda ids: ids + [ids[0]],
                                           lambda ids: ids + [999]])
    def test_an_order_that_misses_or_repeats_a_tab_is_rejected(self, collections, bad_order):
        ids = [collections.add_collection(n, "Thing").id for n in ("A", "B", "C")]

        with pytest.raises(InvalidOrderError):
            collections.reorder_collections(bad_order(ids))

        assert labels(collections) == ["A", "B", "C"]


class TestTrashingATab:
    def test_a_trashed_tab_disappears_from_the_list(self, collections):
        tab = collections.add_collection("Magic", "Spell")
        collections.add_collection("Places", "Place")

        collections.trash_collection(tab.id)

        assert labels(collections) == ["Places"]

    def test_a_trashed_tab_can_no_longer_be_fetched(self, collections):
        tab = collections.add_collection("Magic", "Spell")

        collections.trash_collection(tab.id)

        with pytest.raises(CollectionNotFoundError):
            collections.get_collection(tab.id)

    def test_trashing_keeps_the_entries_inside_for_a_later_restore(self, collections, connection):
        tab = collections.add_collection("Magic", "Spell")
        EntityService(connection, tab.id).create_entity("Fireball")

        collections.trash_collection(tab.id)

        stored = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        assert stored == 1

    def test_trashing_removes_the_entries_from_the_search_index(self, collections, connection):
        tab = collections.add_collection("Magic", "Spell")
        EntityService(connection, tab.id).create_entity("Fireball")

        collections.trash_collection(tab.id)

        assert connection.execute("SELECT COUNT(*) FROM search_index").fetchone()[0] == 0

    def test_the_name_of_a_trashed_tab_can_be_used_again(self, collections):
        tab = collections.add_collection("Magic", "Spell")
        collections.trash_collection(tab.id)

        again = collections.add_collection("Magic", "Spell")

        assert again.id != tab.id

    def test_trashing_a_missing_tab_is_an_error(self, collections):
        with pytest.raises(CollectionNotFoundError):
            collections.trash_collection(123)


class TestCountingEntries:
    def test_entries_are_counted_per_tab(self, collections, connection):
        magic = collections.add_collection("Magic", "Spell")
        places = collections.add_collection("Places", "Place")
        EntityService(connection, magic.id).create_entity("Fireball")
        EntityService(connection, magic.id).create_entity("Frost")
        EntityService(connection, places.id).create_entity("Mill")

        assert collections.count_entries(magic.id) == 2
        assert collections.count_entries(places.id) == 1

    def test_trashed_entries_are_not_counted(self, collections, connection):
        magic = collections.add_collection("Magic", "Spell")
        entities = EntityService(connection, magic.id)
        keep = entities.create_entity("Fireball")
        gone = entities.create_entity("Frost")
        entities.delete_entity(gone)

        assert collections.count_entries(magic.id) == 1
        assert keep


class TestIdentifiers:
    def test_new_identifiers_look_like_uuids_and_never_repeat(self):
        first, second = new_uuid(), new_uuid()

        assert re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", first)
        assert first != second

    def test_the_service_can_be_built_from_a_bare_connection(self, connection):
        assert CollectionService(connection).list_collections() == []
