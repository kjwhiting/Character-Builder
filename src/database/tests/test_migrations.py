import sqlite3

import pytest

from src.database.connection import SCHEMA_VERSION, ProjectDatabase
from src.database.tests.legacy_schemas import SAMPLE_ROWS, V1_SCHEMA, V2_SCHEMA
from src.services.category_service import CategoryService
from src.services.collection_service import CollectionService
from src.services.entity_service import EntityService
from src.services.trash_service import TrashService


def build_legacy_project(path, schema, version):
    raw = sqlite3.connect(path)
    raw.executescript(schema)
    raw.executescript(SAMPLE_ROWS.format(version=version))
    raw.execute(f"PRAGMA user_version = {version}")
    raw.commit()
    raw.close()
    return path


def column_names(connection, table):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


@pytest.fixture
def version_one_project(tmp_path):
    return build_legacy_project(tmp_path / "v1.sqlite", V1_SCHEMA, 1)


@pytest.fixture
def version_two_project(tmp_path):
    return build_legacy_project(tmp_path / "v2.sqlite", V2_SCHEMA, 2)


class TestUpgradingFromVersionOne:
    def test_the_file_is_brought_up_to_the_current_version(self, version_one_project):
        with ProjectDatabase() as database:
            database.open(version_one_project)

            version = database.connection.execute("PRAGMA user_version").fetchone()[0]
            stored = database.connection.execute(
                "SELECT value FROM project_meta WHERE key = 'schema_version'").fetchone()[0]
            assert version == SCHEMA_VERSION
            assert stored == str(SCHEMA_VERSION)

    def test_tabs_and_entries_can_be_trashed_after_the_upgrade(self, version_one_project):
        with ProjectDatabase() as database:
            database.open(version_one_project)

            assert "deleted_at" in column_names(database.connection, "collections")
            assert "deleted_at" in column_names(database.connection, "entries")

    def test_fields_gain_the_display_settings_with_safe_defaults(self, version_one_project):
        with ProjectDatabase() as database:
            database.open(version_one_project)

            row = database.connection.execute(
                "SELECT show_empty, full_width FROM fields").fetchone()
            assert tuple(row) == (0, 0)

    def test_existing_data_survives_the_upgrade(self, version_one_project):
        with ProjectDatabase() as database:
            database.open(version_one_project)
            tab = CollectionService(database.connection).list_collections()[0]
            categories = CategoryService(database.connection, tab.id)
            entities = EntityService(database.connection, tab.id)
            entry = entities.list_entities()[0]

            assert (tab.label, tab.entry_noun, tab.color) == ("Characters", "Character", "#E0A458")
            assert categories.list_fields()[0].options == {"unit": "cm"}
            assert entry.name == "Aria Vale"
            assert entities.get_values(entry.id) == {1: "172"}
            assert entities.get_aliases(entry.id) == ["the Captain"]

    def test_the_upgraded_project_supports_the_trash(self, version_one_project):
        with ProjectDatabase() as database:
            database.open(version_one_project)
            tab = CollectionService(database.connection).list_collections()[0]
            entities = EntityService(database.connection, tab.id)

            entities.delete_entity(entities.list_entities()[0].id)

            assert TrashService(database.connection).count() == 1

    def test_reopening_an_upgraded_file_changes_nothing_further(self, version_one_project):
        with ProjectDatabase() as database:
            database.open(version_one_project)
        with ProjectDatabase() as database:
            database.open(version_one_project)

            assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 3


class TestUpgradingFromVersionTwo:
    def test_the_file_is_brought_up_to_the_current_version(self, version_two_project):
        with ProjectDatabase() as database:
            database.open(version_two_project)

            assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 3

    def test_fields_gain_the_display_settings(self, version_two_project):
        with ProjectDatabase() as database:
            database.open(version_two_project)

            assert "show_empty" in column_names(database.connection, "fields")
            assert "full_width" in column_names(database.connection, "fields")

    def test_the_display_settings_can_be_changed_after_the_upgrade(self, version_two_project):
        with ProjectDatabase() as database:
            database.open(version_two_project)
            tab = CollectionService(database.connection).list_collections()[0]
            categories = CategoryService(database.connection, tab.id)
            field = categories.list_fields()[0]

            changed = categories.set_field_display(field.id, show_empty=True, full_width=True)

            assert (changed.show_empty, changed.full_width) == (True, True)

    def test_existing_data_survives_the_upgrade(self, version_two_project):
        with ProjectDatabase() as database:
            database.open(version_two_project)
            tab = CollectionService(database.connection).list_collections()[0]
            entities = EntityService(database.connection, tab.id)

            assert [e.name for e in entities.list_entities()] == ["Aria Vale"]

    def test_deleted_markers_already_in_the_file_are_kept(self, tmp_path):
        path = build_legacy_project(tmp_path / "v2.sqlite", V2_SCHEMA, 2)
        raw = sqlite3.connect(path)
        raw.execute("UPDATE entries SET deleted_at = '2026-01-01 00:00:00'")
        raw.commit()
        raw.close()

        with ProjectDatabase() as database:
            database.open(path)

            row = database.connection.execute("SELECT deleted_at FROM entries").fetchone()
            assert row[0] == "2026-01-01 00:00:00"
