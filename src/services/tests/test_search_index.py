from src.services import search_index


def indexed(connection, query):
    rows = connection.execute(
        "SELECT entry_id FROM search_index WHERE search_index MATCH ?", (query,)).fetchall()
    return sorted(row[0] for row in rows)


class TestKeepingTheIndexCurrent:
    def test_a_new_entry_is_searchable_by_name(self, connection, entities):
        entry = entities.create_entity("Aria")

        assert indexed(connection, "Aria") == [entry]

    def test_field_values_are_searchable(self, connection, entities, fields):
        entry = entities.create_entity("Aria", values={fields["Summary"].id: "lantern bearer"})

        assert indexed(connection, "lantern") == [entry]

    def test_alternate_names_are_searchable(self, connection, entities):
        entry = entities.create_entity("Aria Vale", aliases=["Captain"])

        assert indexed(connection, "Captain") == [entry]

    def test_a_rename_replaces_the_old_name(self, connection, entities):
        entry = entities.create_entity("Aria")

        entities.update_entity(entry, "Zora")

        assert indexed(connection, "Aria") == []
        assert indexed(connection, "Zora") == [entry]

    def test_changed_values_replace_the_old_ones(self, connection, entities, fields):
        entry = entities.create_entity("A", values={fields["Summary"].id: "alpha"})

        entities.update_entity(entry, "A", values={fields["Summary"].id: "omega"})

        assert indexed(connection, "alpha") == []
        assert indexed(connection, "omega") == [entry]

    def test_an_entry_is_indexed_exactly_once(self, connection, entities):
        entry = entities.create_entity("Aria")
        entities.update_entity(entry, "Aria")
        entities.update_entity(entry, "Aria")

        count = connection.execute("SELECT COUNT(*) FROM search_index").fetchone()[0]
        assert count == 1

    def test_accents_are_ignored_when_searching(self, connection, entities):
        entry = entities.create_entity("Élan")

        assert indexed(connection, "elan") == [entry]

    def test_a_duplicate_is_indexed_too(self, connection, entities):
        entry = entities.create_entity("Aria")
        copy = entities.duplicate_entity(entry)

        assert indexed(connection, "Aria") == sorted([entry, copy])


class TestRemovingFromTheIndex:
    def test_a_deleted_entry_leaves_the_index(self, connection, entities):
        entry = entities.create_entity("Aria")

        entities.delete_entity(entry)

        assert indexed(connection, "Aria") == []

    def test_dropping_an_entry_removes_only_that_entry(self, connection, entities):
        keep = entities.create_entity("Aria")
        drop = entities.create_entity("Aria Two")

        search_index.drop_entry(connection, drop)

        assert indexed(connection, "Aria") == [keep]

    def test_dropping_a_tab_removes_all_of_its_entries(self, connection, characters, entities):
        entities.create_entity("Aria")
        entities.create_entity("Bram")

        search_index.drop_collection(connection, characters.id)

        assert connection.execute("SELECT COUNT(*) FROM search_index").fetchone()[0] == 0


class TestRebuilding:
    def test_reindexing_an_entry_restores_it(self, connection, entities):
        entry = entities.create_entity("Aria")
        search_index.drop_entry(connection, entry)

        search_index.reindex_entry(connection, entry)

        assert indexed(connection, "Aria") == [entry]

    def test_a_deleted_entry_is_not_reindexed(self, connection, entities):
        entry = entities.create_entity("Aria")
        entities.delete_entity(entry)

        search_index.reindex_entry(connection, entry)

        assert indexed(connection, "Aria") == []

    def test_reindexing_a_tab_covers_every_live_entry(self, connection, characters, entities):
        first = entities.create_entity("Aria")
        second = entities.create_entity("Bram")
        gone = entities.create_entity("Cleo")
        entities.delete_entity(gone)
        search_index.drop_collection(connection, characters.id)

        search_index.reindex_collection(connection, characters.id)

        assert indexed(connection, "Aria OR Bram OR Cleo") == sorted([first, second])
