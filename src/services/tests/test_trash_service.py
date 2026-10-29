import pytest

from src.services.errors import TrashItemNotFoundError
from src.services.trash_service import KIND_ENTRY, KIND_TAB, TrashService


@pytest.fixture
def trash(connection):
    return TrashService(connection)


def indexed(connection):
    return connection.execute("SELECT COUNT(*) FROM search_index").fetchone()[0]


def age(connection, table, days, item_id):
    connection.execute(
        f"UPDATE {table} SET deleted_at = datetime('now', ?) WHERE id = ?",
        (f"-{days} days", item_id))
    connection.commit()


class TestWhatIsInTheTrash:
    def test_a_fresh_project_has_an_empty_trash(self, trash):
        assert trash.list_items() == []
        assert trash.count() == 0

    def test_a_deleted_entry_is_listed_with_the_tab_it_came_from(self, trash, entities):
        entities.delete_entity(entities.create_entity("Aria"))

        [item] = trash.list_items()

        assert (item.kind, item.label, item.detail) == (KIND_ENTRY, "Aria", "Entry from Characters")

    def test_a_deleted_tab_is_listed_with_its_entry_count(self, trash, collections, characters,
                                                           entities):
        entities.create_entity("Aria")
        entities.create_entity("Bram")
        collections.trash_collection(characters.id)

        [item] = trash.list_items()

        assert (item.kind, item.label, item.detail) == (KIND_TAB, "Characters", "Tab with 2 entries")

    def test_a_tab_with_one_entry_uses_the_singular(self, trash, collections, characters, entities):
        entities.create_entity("Aria")
        collections.trash_collection(characters.id)

        assert trash.list_items()[0].detail == "Tab with 1 entry"

    def test_entries_inside_a_trashed_tab_are_not_listed_separately(
        self, trash, collections, characters, entities
    ):
        entities.delete_entity(entities.create_entity("Aria"))
        collections.trash_collection(characters.id)

        assert [i.kind for i in trash.list_items()] == [KIND_TAB]

    def test_the_most_recently_deleted_item_comes_first(self, connection, trash, entities):
        old = entities.create_entity("Old")
        new = entities.create_entity("New")
        entities.delete_entity(old)
        entities.delete_entity(new)
        age(connection, "entries", 5, old)

        assert [i.label for i in trash.list_items()] == ["New", "Old"]


class TestRestoring:
    def test_a_restored_entry_comes_back_with_its_values(self, trash, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Hometown"].id: "Reed"})
        entities.delete_entity(entry)

        name = trash.restore(KIND_ENTRY, entry)

        assert name == "Aria"
        assert entities.get_entity(entry).name == "Aria"
        assert entities.get_values(entry) == {fields["Hometown"].id: "Reed"}
        assert trash.count() == 0

    def test_a_restored_entry_is_searchable_again(self, connection, trash, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)
        assert indexed(connection) == 0

        trash.restore(KIND_ENTRY, entry)

        assert indexed(connection) == 1

    def test_a_restored_tab_brings_back_its_entries(self, trash, collections, characters, entities):
        entities.create_entity("Aria")
        collections.trash_collection(characters.id)

        trash.restore(KIND_TAB, characters.id)

        assert [c.label for c in collections.list_collections()] == ["Characters"]
        assert [e.name for e in entities.list_entities()] == ["Aria"]

    def test_a_restored_tab_makes_its_entries_searchable_again(
        self, connection, trash, collections, characters, entities
    ):
        entities.create_entity("Aria")
        collections.trash_collection(characters.id)

        trash.restore(KIND_TAB, characters.id)

        assert indexed(connection) == 1

    def test_entries_deleted_before_their_tab_stay_deleted_after_the_tab_returns(
        self, trash, collections, characters, entities
    ):
        entities.create_entity("Keep")
        gone = entities.create_entity("Gone")
        entities.delete_entity(gone)
        collections.trash_collection(characters.id)

        trash.restore(KIND_TAB, characters.id)

        assert [e.name for e in entities.list_entities()] == ["Keep"]
        assert [i.label for i in trash.list_items()] == ["Gone"]

    def test_a_tab_whose_name_is_now_taken_returns_with_a_restored_suffix(
        self, trash, collections, characters
    ):
        collections.trash_collection(characters.id)
        collections.add_collection("Characters", "Character")

        name = trash.restore(KIND_TAB, characters.id)

        assert name == "Characters (restored)"

    def test_the_suffix_is_numbered_when_that_name_is_taken_too(self, trash, collections):
        first = collections.add_collection("Magic", "Spell")
        collections.trash_collection(first.id)
        collections.add_collection("Magic", "Spell")
        second = collections.add_collection("Magic (restored)", "Spell")
        assert second

        assert trash.restore(KIND_TAB, first.id) == "Magic (restored 2)"

    def test_an_entry_cannot_be_restored_into_a_trashed_tab(
        self, trash, collections, characters, entities
    ):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)
        collections.trash_collection(characters.id)

        with pytest.raises(TrashItemNotFoundError):
            trash.restore(KIND_ENTRY, entry)

    def test_restoring_something_that_is_not_in_the_trash_is_an_error(self, trash, entities):
        entry = entities.create_entity("Aria")

        with pytest.raises(TrashItemNotFoundError):
            trash.restore(KIND_ENTRY, entry)
        with pytest.raises(TrashItemNotFoundError):
            trash.restore(KIND_TAB, 999)

    def test_an_unknown_kind_is_an_error(self, trash):
        with pytest.raises(TrashItemNotFoundError):
            trash.restore("folder", 1)
        with pytest.raises(TrashItemNotFoundError):
            trash.delete_forever("folder", 1)


class TestDeletingForGood:
    def test_an_entry_deleted_forever_is_gone_with_its_data(self, connection, trash, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Hometown"].id: "Reed"})
        entities.delete_entity(entry)

        trash.delete_forever(KIND_ENTRY, entry)

        assert connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0

    def test_a_tab_deleted_forever_takes_everything_inside_it(
        self, connection, trash, collections, characters, entities, fields
    ):
        entities.create_entity("Aria", values={fields["Hometown"].id: "Reed"})
        collections.trash_collection(characters.id)

        trash.delete_forever(KIND_TAB, characters.id)

        for table in ("collections", "categories", "fields", "entries", "field_values"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert indexed(connection) == 0

    def test_only_trashed_items_can_be_deleted_forever(self, trash, entities, characters):
        entry = entities.create_entity("Aria")

        with pytest.raises(TrashItemNotFoundError):
            trash.delete_forever(KIND_ENTRY, entry)
        with pytest.raises(TrashItemNotFoundError):
            trash.delete_forever(KIND_TAB, characters.id)

    def test_emptying_the_trash_removes_everything_and_reports_how_many(
        self, trash, collections, places, entities
    ):
        entities.delete_entity(entities.create_entity("Aria"))
        collections.trash_collection(places.id)

        removed = trash.empty_trash()

        assert removed == 2
        assert trash.count() == 0

    def test_emptying_an_empty_trash_removes_nothing(self, trash):
        assert trash.empty_trash() == 0


class TestExpiry:
    def test_items_older_than_thirty_days_are_purged(self, connection, trash, entities):
        old = entities.create_entity("Old")
        recent = entities.create_entity("Recent")
        entities.delete_entity(old)
        entities.delete_entity(recent)
        age(connection, "entries", 45, old)

        purged = trash.purge_expired()

        assert purged == 1
        assert [i.label for i in trash.list_items()] == ["Recent"]

    def test_an_item_just_inside_the_window_is_kept(self, connection, trash, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)
        age(connection, "entries", 29, entry)

        assert trash.purge_expired() == 0

    def test_old_tabs_are_purged_with_their_contents(self, connection, trash, collections, places):
        collections.trash_collection(places.id)
        age(connection, "collections", 40, places.id)

        assert trash.purge_expired() == 1
        assert connection.execute("SELECT COUNT(*) FROM collections").fetchone()[0] == 0

    def test_the_retention_period_can_be_shortened(self, connection, trash, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)
        age(connection, "entries", 3, entry)

        assert trash.purge_expired(days=2) == 1

    def test_nothing_is_purged_from_a_clean_project(self, trash, entities):
        entities.create_entity("Aria")

        assert trash.purge_expired() == 0
