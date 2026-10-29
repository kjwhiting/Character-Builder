import sqlite3

import pytest

from src.database.connection import (
    SCHEMA_VERSION,
    DatabaseError,
    NoActiveProjectError,
    ProjectDatabase,
)

EXPECTED_TABLES = {
    "project_meta", "collections", "categories", "fields", "entries", "aliases",
    "field_values", "search_index",
}


def table_names(connection):
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def make_collection(connection, key="characters", label="Characters"):
    cursor = connection.execute(
        "INSERT INTO collections (key, label, entry_noun) VALUES (?, ?, 'Entry')", (key, label))
    return cursor.lastrowid


def make_category(connection, collection_id, name="Basics"):
    cursor = connection.execute(
        "INSERT INTO categories (collection_id, name) VALUES (?, ?)", (collection_id, name))
    return cursor.lastrowid


def make_field(connection, collection_id, category_id, name="Age", field_type="text"):
    cursor = connection.execute(
        "INSERT INTO fields (collection_id, category_id, name, field_type) VALUES (?, ?, ?, ?)",
        (collection_id, category_id, name, field_type))
    return cursor.lastrowid


def make_entry(connection, collection_id, uuid="u1", name="Aria"):
    cursor = connection.execute(
        "INSERT INTO entries (uuid, collection_id, name) VALUES (?, ?, ?)",
        (uuid, collection_id, name))
    return cursor.lastrowid


class TestOpeningAProject:
    def test_a_new_database_file_is_created_with_the_full_schema(self, tmp_path):
        path = tmp_path / "project.sqlite"
        with ProjectDatabase() as database:
            database.open(path, create=True)

            assert path.is_file()
            assert EXPECTED_TABLES <= table_names(database.connection)

    def test_a_new_database_records_the_current_schema_version(self, database):
        version = database.connection.execute("PRAGMA user_version").fetchone()[0]
        stored = database.connection.execute(
            "SELECT value FROM project_meta WHERE key = 'schema_version'").fetchone()[0]

        assert version == SCHEMA_VERSION == int(stored)

    def test_opening_a_missing_file_without_create_is_an_error(self, tmp_path):
        with pytest.raises(DatabaseError, match="not found"):
            ProjectDatabase().open(tmp_path / "absent.sqlite")

    def test_a_path_inside_a_missing_folder_cannot_be_created(self, tmp_path):
        with pytest.raises(DatabaseError, match="Could not open"):
            ProjectDatabase().open(tmp_path / "no" / "such" / "p.sqlite", create=True)

    def test_an_existing_project_reopens_with_its_data(self, tmp_path):
        path = tmp_path / "project.sqlite"
        with ProjectDatabase() as first:
            first.open(path, create=True)
            with first.connection:
                make_collection(first.connection)

        with ProjectDatabase() as second:
            second.open(path)

            count = second.connection.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
            assert count == 1

    def test_rows_can_be_read_by_column_name(self, database):
        with database.connection:
            make_collection(database.connection)

        row = database.connection.execute("SELECT label FROM collections").fetchone()

        assert row["label"] == "Characters"

    def test_foreign_keys_are_enforced(self, database):
        enabled = database.connection.execute("PRAGMA foreign_keys").fetchone()[0]

        assert enabled == 1

    def test_the_resolved_path_is_reported(self, database, tmp_path):
        assert database.path == (tmp_path / "project.sqlite").resolve()

    def test_a_database_reports_when_it_is_open(self, tmp_path):
        database = ProjectDatabase()
        assert not database.is_open

        database.open(tmp_path / "p.sqlite", create=True)
        assert database.is_open

        database.close()
        assert not database.is_open


class TestClosing:
    def test_the_connection_is_unavailable_after_closing(self, tmp_path):
        database = ProjectDatabase()
        database.open(tmp_path / "p.sqlite", create=True)
        database.close()

        with pytest.raises(NoActiveProjectError):
            database.connection

    def test_the_path_is_unavailable_after_closing(self, tmp_path):
        database = ProjectDatabase()
        database.open(tmp_path / "p.sqlite", create=True)
        database.close()

        with pytest.raises(NoActiveProjectError):
            database.path

    def test_closing_twice_is_harmless(self, tmp_path):
        database = ProjectDatabase()
        database.open(tmp_path / "p.sqlite", create=True)

        database.close()
        database.close()

        assert not database.is_open

    def test_using_the_connection_before_opening_is_an_error(self):
        with pytest.raises(NoActiveProjectError):
            ProjectDatabase().connection

    def test_leaving_a_with_block_closes_the_database(self, tmp_path):
        with ProjectDatabase() as database:
            database.open(tmp_path / "p.sqlite", create=True)

        assert not database.is_open

    def test_the_old_connection_stops_working_once_closed(self, tmp_path):
        database = ProjectDatabase()
        database.open(tmp_path / "p.sqlite", create=True)
        old = database.connection
        database.close()

        with pytest.raises(sqlite3.ProgrammingError):
            old.execute("SELECT 1")


class TestSwitchingProjects:
    def test_opening_another_project_replaces_the_current_one(self, tmp_path):
        with ProjectDatabase() as database:
            database.open(tmp_path / "a.sqlite", create=True)
            database.open(tmp_path / "b.sqlite", create=True)

            assert database.path == (tmp_path / "b.sqlite").resolve()

    def test_the_previous_connection_is_closed_after_a_successful_switch(self, tmp_path):
        with ProjectDatabase() as database:
            database.open(tmp_path / "a.sqlite", create=True)
            old = database.connection
            database.open(tmp_path / "b.sqlite", create=True)

            with pytest.raises(sqlite3.ProgrammingError):
                old.execute("SELECT 1")

    def test_a_failed_switch_keeps_the_current_project_open(self, tmp_path):
        bad = tmp_path / "bad.sqlite"
        bad.write_text("not a database at all")
        with ProjectDatabase() as database:
            database.open(tmp_path / "good.sqlite", create=True)

            with pytest.raises(DatabaseError):
                database.open(bad)

            assert database.path == (tmp_path / "good.sqlite").resolve()
            assert database.connection.execute("SELECT 1").fetchone()[0] == 1


class TestRejectingFilesThatAreNotProjects:
    def test_a_text_file_is_not_a_readable_database(self, tmp_path):
        path = tmp_path / "notes.sqlite"
        path.write_text("just some notes")

        with pytest.raises(DatabaseError, match="not a readable database"):
            ProjectDatabase().open(path)

    def test_a_foreign_sqlite_database_is_not_a_worldbuilder_project(self, tmp_path):
        path = tmp_path / "other.sqlite"
        other = sqlite3.connect(path)
        other.execute("CREATE TABLE recipes (name TEXT)")
        other.commit()
        other.close()

        with pytest.raises(DatabaseError, match="not a Worldbuilder project"):
            ProjectDatabase().open(path)

    def test_a_project_from_a_newer_version_is_refused(self, tmp_path):
        path = tmp_path / "future.sqlite"
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE collections (id INTEGER)")
        raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        raw.commit()
        raw.close()

        with pytest.raises(DatabaseError, match="schema version"):
            ProjectDatabase().open(path)

    def test_a_refused_file_is_left_untouched(self, tmp_path):
        path = tmp_path / "other.sqlite"
        other = sqlite3.connect(path)
        other.execute("CREATE TABLE recipes (name TEXT)")
        other.commit()
        other.close()

        with pytest.raises(DatabaseError):
            ProjectDatabase().open(path)

        check = sqlite3.connect(path)
        tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master")}
        check.close()
        assert tables == {"recipes"}


class TestSchemaRules:
    def test_a_field_type_outside_the_supported_list_is_rejected(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)

            with pytest.raises(sqlite3.IntegrityError):
                make_field(connection, collection, category, field_type="rainbow")

    @pytest.mark.parametrize("field_type", [
        "text", "textarea", "list", "choice", "multichoice", "checkbox", "number"])
    def test_every_supported_field_type_is_accepted(self, database, field_type):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)

            assert make_field(connection, collection, category, field_type=field_type)

    def test_a_category_that_still_has_fields_cannot_be_deleted(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            make_field(connection, collection, category)

        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                connection.execute("DELETE FROM categories WHERE id = ?", (category,))

    def test_an_empty_category_can_be_deleted(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            connection.execute("DELETE FROM categories WHERE id = ?", (category,))

    def test_a_field_cannot_sit_in_a_category_from_another_tab(self, database):
        connection = database.connection
        with connection:
            first = make_collection(connection, "a", "A")
            second = make_collection(connection, "b", "B")
            category = make_category(connection, first)

            with pytest.raises(sqlite3.IntegrityError):
                make_field(connection, second, category)

    def test_two_categories_in_one_tab_cannot_share_a_name_in_any_case(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            make_category(connection, collection, "Basics")

            with pytest.raises(sqlite3.IntegrityError):
                make_category(connection, collection, "BASICS")

    def test_different_tabs_can_reuse_a_category_name(self, database):
        connection = database.connection
        with connection:
            first = make_collection(connection, "a", "A")
            second = make_collection(connection, "b", "B")
            make_category(connection, first, "Basics")
            make_category(connection, second, "Basics")

    def test_two_fields_in_one_category_cannot_share_a_name(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            make_field(connection, collection, category, "Age")

            with pytest.raises(sqlite3.IntegrityError):
                make_field(connection, collection, category, "age")

    def test_entry_identifiers_are_unique(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            make_entry(connection, collection, uuid="same")

            with pytest.raises(sqlite3.IntegrityError):
                make_entry(connection, collection, uuid="same", name="Other")

    def test_tab_keys_are_unique(self, database):
        connection = database.connection
        with connection:
            make_collection(connection, "characters", "Characters")

            with pytest.raises(sqlite3.IntegrityError):
                make_collection(connection, "characters", "Other")

    def test_new_fields_hide_when_empty_and_use_automatic_width(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            field = make_field(connection, collection, category)

        row = connection.execute(
            "SELECT show_empty, full_width FROM fields WHERE id = ?", (field,)).fetchone()
        assert tuple(row) == (0, 0)

    def test_new_entries_start_without_a_deleted_marker(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            entry = make_entry(connection, collection)

        deleted = connection.execute(
            "SELECT deleted_at FROM entries WHERE id = ?", (entry,)).fetchone()[0]
        assert deleted is None


class TestCascadingDeletes:
    def test_deleting_a_tab_removes_everything_inside_it(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            field = make_field(connection, collection, category)
            entry = make_entry(connection, collection)
            connection.execute(
                "INSERT INTO field_values (entry_id, field_id, value) VALUES (?, ?, 'x')",
                (entry, field))
            connection.execute("INSERT INTO aliases (entry_id, alias) VALUES (?, 'Al')", (entry,))

        with connection:
            connection.execute("DELETE FROM collections WHERE id = ?", (collection,))

        for table in ("categories", "fields", "entries", "field_values", "aliases"):
            count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, table

    def test_deleting_an_entry_removes_its_values_and_aliases(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            field = make_field(connection, collection, category)
            entry = make_entry(connection, collection)
            connection.execute(
                "INSERT INTO field_values (entry_id, field_id, value) VALUES (?, ?, 'x')",
                (entry, field))
            connection.execute("INSERT INTO aliases (entry_id, alias) VALUES (?, 'Al')", (entry,))

        with connection:
            connection.execute("DELETE FROM entries WHERE id = ?", (entry,))

        assert connection.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0] == 0

    def test_deleting_a_field_removes_the_values_stored_under_it(self, database):
        connection = database.connection
        with connection:
            collection = make_collection(connection)
            category = make_category(connection, collection)
            field = make_field(connection, collection, category)
            entry = make_entry(connection, collection)
            connection.execute(
                "INSERT INTO field_values (entry_id, field_id, value) VALUES (?, ?, 'x')",
                (entry, field))

        with connection:
            connection.execute("DELETE FROM fields WHERE id = ?", (field,))

        assert connection.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1
