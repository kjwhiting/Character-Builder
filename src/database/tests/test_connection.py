"""Tests for database/connection.py: schema, constraints, profiles and transactions.

Every test uses pytest's ``tmp_path`` so real profile files are never touched.
"""

import hashlib
import sqlite3

import pytest

from database import seeds
from database.connection import (
    DEFAULT_PROFILE_NAME,
    LAST_PROFILE_FILE_NAME,
    LEGACY_PROFILE_NAME,
    SCHEMA_VERSION,
    DatabaseConnection,
    NoActiveProfileError,
    ProfileError,
    initialize_schema,
    is_blank,
    profile_noun,
    recall_profile,
    remember_profile,
    resolve_startup_profile,
    seed_if_blank,
    validate_profile_file,
)


# --------------------------------------------------------------------------- #
# Helpers and fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def db(tmp_path):
    """An open, empty profile (no template) that is closed after the test."""
    manager = DatabaseConnection()
    manager.open(tmp_path / "test.sqlite", create=True)
    yield manager
    manager.close()


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def add_entity(conn, name="Aria"):
    return conn.execute("INSERT INTO entities (name) VALUES (?)", (name,)).lastrowid


def add_field(conn, category="Relations", name="Enemies", **extra):
    columns = ["category", "name"] + list(extra)
    marks = ", ".join("?" * len(columns))
    sql = f"INSERT INTO fields ({', '.join(columns)}) VALUES ({marks})"
    return conn.execute(sql, [category, name] + list(extra.values())).lastrowid


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_legacy_profile(path):
    """A profile as the first version of the app wrote it: no field_type, no categories."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'Character', image TEXT NOT NULL DEFAULT '');
        CREATE TABLE fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL COLLATE NOCASE, name TEXT NOT NULL COLLATE NOCASE,
            multiline INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE (category, name));
        CREATE TABLE field_values (
            entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            field_id  INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
            value TEXT NOT NULL DEFAULT '', PRIMARY KEY (entity_id, field_id));
        INSERT INTO entities (name) VALUES ('Old Hero');
        INSERT INTO fields (category, name, multiline, sort_order) VALUES
            ('Overview', 'Description', 1, 0),
            ('Relations', 'Best Friend', 0, 100),
            ('Dances', 'Style', 0, 200);
        INSERT INTO field_values VALUES (1, 1, 'A knight'), (1, 2, 'Tomas');
    """)
    conn.commit()
    conn.close()


def make_foreign_database(path):
    """A SQLite file that belongs to some other application."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    conn.execute("INSERT INTO users (email) VALUES ('someone@example.com')")
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Schema and constraints
# --------------------------------------------------------------------------- #
class TestSchema:
    def test_creates_all_tables(self, db):
        assert {"entities", "fields", "field_values", "categories"} <= table_names(db.connection)

    def test_records_the_schema_version(self, db):
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    def test_foreign_keys_are_enforced(self, db):
        assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_initialize_schema_can_run_twice(self, db):
        initialize_schema(db.connection)
        initialize_schema(db.connection)
        assert {"entities", "fields", "field_values", "categories"} <= table_names(db.connection)

    def test_initialize_schema_refuses_a_newer_file_without_touching_it(self, tmp_path):
        raw = sqlite3.connect(tmp_path / "future.sqlite")
        raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        with pytest.raises(ProfileError, match="newer version"):
            initialize_schema(raw)
        assert table_names(raw) == set()
        raw.close()

    def test_deleting_an_entity_deletes_its_values(self, db):
        conn = db.connection
        entity_id, field_id = add_entity(conn), add_field(conn)
        conn.execute("INSERT INTO field_values VALUES (?, ?, 'Vex')", (entity_id, field_id))
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0

    def test_deleting_a_field_deletes_its_values_but_not_the_entity(self, db):
        conn = db.connection
        entity_id, field_id = add_entity(conn), add_field(conn)
        conn.execute("INSERT INTO field_values VALUES (?, ?, 'Vex')", (entity_id, field_id))
        conn.execute("DELETE FROM fields WHERE id = ?", (field_id,))
        assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 1

    def test_a_value_must_point_at_a_real_entity_and_field(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.connection.execute("INSERT INTO field_values VALUES (999, 999, 'x')")

    def test_an_entity_needs_a_name(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.connection.execute("INSERT INTO entities (name) VALUES (NULL)")

    def test_field_names_are_unique_per_category_ignoring_case(self, db):
        conn = db.connection
        add_field(conn, "Relations", "Enemies")
        with pytest.raises(sqlite3.IntegrityError):
            add_field(conn, "relations", "ENEMIES")

    def test_the_same_field_name_is_allowed_in_different_categories(self, db):
        conn = db.connection
        add_field(conn, "Relations", "Notes")
        add_field(conn, "Favorites", "Notes")
        assert conn.execute("SELECT COUNT(*) FROM fields").fetchone()[0] == 2

    def test_category_names_are_unique_ignoring_case(self, db):
        conn = db.connection
        conn.execute("INSERT INTO categories (name) VALUES ('Dances')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO categories (name) VALUES ('DANCES')")

    def test_field_type_defaults_to_text(self, db):
        field_id = add_field(db.connection)
        row = db.connection.execute("SELECT field_type FROM fields WHERE id = ?",
                                    (field_id,)).fetchone()
        assert row["field_type"] == "text"

    @pytest.mark.parametrize("field_type", seeds.FIELD_TYPES)
    def test_every_supported_field_type_is_accepted(self, db, field_type):
        add_field(db.connection, name=f"as {field_type}", field_type=field_type)

    def test_an_unsupported_field_type_is_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            add_field(db.connection, field_type="checkbox")


# --------------------------------------------------------------------------- #
# Opening files made by earlier versions of the app
# --------------------------------------------------------------------------- #
class TestUpgradingOlderFiles:
    @pytest.fixture
    def legacy_db(self, tmp_path):
        path = tmp_path / "old.sqlite"
        make_legacy_profile(path)
        manager = DatabaseConnection()
        manager.open(path)
        yield manager
        manager.close()

    def test_existing_entries_and_values_are_kept(self, legacy_db):
        conn = legacy_db.connection
        assert conn.execute("SELECT name FROM entities").fetchone()["name"] == "Old Hero"
        values = {r["value"] for r in conn.execute("SELECT value FROM field_values")}
        assert values == {"A knight", "Tomas"}

    def test_multiline_fields_become_textarea_fields(self, legacy_db):
        rows = legacy_db.connection.execute("SELECT name, field_type FROM fields").fetchall()
        assert {r["name"]: r["field_type"] for r in rows} == {
            "Description": "textarea", "Best Friend": "text", "Style": "text"}

    def test_categories_keep_their_original_order(self, legacy_db):
        rows = legacy_db.connection.execute(
            "SELECT name FROM categories ORDER BY sort_order").fetchall()
        assert [r["name"] for r in rows] == ["Overview", "Relations", "Dances"]

    def test_the_upgraded_file_enforces_field_types_too(self, legacy_db):
        with pytest.raises(sqlite3.IntegrityError):
            add_field(legacy_db.connection, "Overview", "Bad", field_type="checkbox")

    def test_the_version_is_stamped(self, legacy_db):
        assert legacy_db.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    def test_opening_again_changes_nothing(self, tmp_path):
        path = tmp_path / "old.sqlite"
        make_legacy_profile(path)
        for _ in range(3):
            with DatabaseConnection() as manager:
                manager.open(path)
                conn = manager.connection
                assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 3
                assert conn.execute("SELECT COUNT(*) FROM fields").fetchone()[0] == 3

    def test_a_file_from_a_newer_version_is_refused_and_left_alone(self, tmp_path):
        path = tmp_path / "future.sqlite"
        with DatabaseConnection() as manager:
            manager.open(path, create=True)
        raw = sqlite3.connect(path)
        raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        raw.commit()
        raw.close()
        before = file_hash(path)

        with pytest.raises(ProfileError, match="newer version"):
            DatabaseConnection().open(path)
        assert file_hash(path) == before


# --------------------------------------------------------------------------- #
# Starter templates
# --------------------------------------------------------------------------- #
class TestSeeding:
    def open_with(self, tmp_path, template, name="seeded.sqlite"):
        manager = DatabaseConnection()
        manager.open(tmp_path / name, create=True, template=template)
        return manager

    def test_a_new_profile_gets_the_template_categories_in_order(self, tmp_path):
        with self.open_with(tmp_path, seeds.CHARACTER_TEMPLATE) as manager:
            rows = manager.connection.execute(
                "SELECT name FROM categories ORDER BY sort_order").fetchall()
            assert [r["name"] for r in rows] == [
                c["name"] for c in seeds.CHARACTER_TEMPLATE["categories"]]

    def test_a_new_profile_gets_the_template_fields_in_order(self, tmp_path):
        with self.open_with(tmp_path, seeds.CHARACTER_TEMPLATE) as manager:
            rows = manager.connection.execute(
                "SELECT category, name, field_type FROM fields ORDER BY sort_order").fetchall()
            expected = [(c["name"], f["name"], f["type"])
                        for c in seeds.CHARACTER_TEMPLATE["categories"] for f in c["fields"]]
            assert [tuple(r) for r in rows] == expected

    def test_the_multiline_column_stays_in_step_with_the_type(self, tmp_path):
        with self.open_with(tmp_path, seeds.CHARACTER_TEMPLATE) as manager:
            rows = manager.connection.execute("SELECT field_type, multiline FROM fields")
            for row in rows:
                assert row["multiline"] == (1 if row["field_type"] == "textarea" else 0)

    def test_without_a_template_the_profile_stays_empty(self, db):
        assert is_blank(db.connection)

    def test_a_profile_that_has_data_is_never_seeded(self, tmp_path):
        path = tmp_path / "used.sqlite"
        with DatabaseConnection() as manager:
            manager.open(path, create=True)
            add_field(manager.connection, "Mine", "Only field")
            manager.connection.commit()
        with DatabaseConnection() as manager:
            manager.open(path, template=seeds.CHARACTER_TEMPLATE)
            count = manager.connection.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
            assert count == 1

    def test_deleted_fields_do_not_come_back_on_the_next_launch(self, tmp_path):
        path = tmp_path / "pruned.sqlite"
        with DatabaseConnection() as manager:
            manager.open(path, create=True, template=seeds.CHARACTER_TEMPLATE)
            add_entity(manager.connection)
            manager.connection.execute("DELETE FROM fields")
            manager.connection.commit()
        with DatabaseConnection() as manager:
            manager.open(path, template=seeds.CHARACTER_TEMPLATE)
            assert manager.connection.execute("SELECT COUNT(*) FROM fields").fetchone()[0] == 0

    def test_seed_if_blank_reports_whether_it_seeded(self, db):
        assert seed_if_blank(db.connection, seeds.WORLDBUILDING_TEMPLATE) is True
        assert seed_if_blank(db.connection, seeds.WORLDBUILDING_TEMPLATE) is False

    def test_seeding_leaves_the_shared_template_unchanged(self, tmp_path):
        snapshot = seeds.get_template("characters")
        with self.open_with(tmp_path, seeds.CHARACTER_TEMPLATE):
            pass
        assert seeds.CHARACTER_TEMPLATE == snapshot

    def test_the_worldbuilding_template_seeds_too(self, tmp_path):
        with self.open_with(tmp_path, seeds.WORLDBUILDING_TEMPLATE) as manager:
            count = manager.connection.execute("SELECT COUNT(*) FROM fields").fetchone()[0]
            expected = sum(len(c["fields"]) for c in seeds.WORLDBUILDING_TEMPLATE["categories"])
            assert count == expected


# --------------------------------------------------------------------------- #
# Checking a file before opening it
# --------------------------------------------------------------------------- #
class TestProfileValidation:
    def test_a_missing_file_is_rejected(self, tmp_path):
        with pytest.raises(ProfileError, match="doesn't exist"):
            validate_profile_file(tmp_path / "nope.sqlite")

    def test_a_folder_is_rejected(self, tmp_path):
        with pytest.raises(ProfileError, match="folder"):
            validate_profile_file(tmp_path)

    def test_a_text_file_is_rejected(self, tmp_path):
        path = tmp_path / "notes.sqlite"
        path.write_text("definitely not a database")
        with pytest.raises(ProfileError, match="isn't a SQLite"):
            validate_profile_file(path)

    def test_a_damaged_database_is_rejected(self, tmp_path):
        path = tmp_path / "damaged.sqlite"
        path.write_bytes(b"SQLite format 3\x00" + b"\xff" * 200)
        with pytest.raises(ProfileError):
            validate_profile_file(path)

    def test_an_empty_file_is_accepted(self, tmp_path):
        path = tmp_path / "empty.sqlite"
        path.write_bytes(b"")
        validate_profile_file(path)

    def test_a_database_with_no_tables_is_accepted(self, tmp_path):
        path = tmp_path / "blank.sqlite"
        sqlite3.connect(path).close()
        validate_profile_file(path)

    def test_a_real_profile_is_accepted(self, tmp_path):
        with DatabaseConnection() as manager:
            manager.open(tmp_path / "real.sqlite", create=True)
        validate_profile_file(tmp_path / "real.sqlite")

    def test_another_applications_database_is_rejected(self, tmp_path):
        path = tmp_path / "other.sqlite"
        make_foreign_database(path)
        with pytest.raises(ProfileError, match="wasn't made by Character Builder"):
            validate_profile_file(path)

    def test_another_applications_database_is_never_modified(self, tmp_path):
        path = tmp_path / "other.sqlite"
        make_foreign_database(path)
        before = file_hash(path)
        with pytest.raises(ProfileError):
            DatabaseConnection().open(path)
        assert file_hash(path) == before


# --------------------------------------------------------------------------- #
# Opening, closing and the connection lifecycle
# --------------------------------------------------------------------------- #
class TestLifecycle:
    def test_a_new_manager_has_no_profile(self):
        manager = DatabaseConnection()
        assert manager.is_open is False
        assert manager.path is None

    def test_using_the_connection_before_opening_raises(self):
        with pytest.raises(NoActiveProfileError):
            DatabaseConnection().connection

    def test_open_with_create_makes_the_file(self, tmp_path):
        path = tmp_path / "made.sqlite"
        with DatabaseConnection() as manager:
            returned = manager.open(path, create=True)
            assert path.is_file()
            assert manager.is_open
            assert manager.path == path.resolve() == returned

    def test_open_without_create_refuses_a_missing_file(self, tmp_path):
        path = tmp_path / "missing.sqlite"
        with pytest.raises(ProfileError, match="doesn't exist"):
            DatabaseConnection().open(path)
        assert not path.exists()

    def test_create_needs_the_folder_to_exist(self, tmp_path):
        with pytest.raises(ProfileError, match="doesn't exist"):
            DatabaseConnection().open(tmp_path / "no_such_folder" / "a.sqlite", create=True)

    def test_rows_can_be_read_by_column_name(self, db):
        assert db.connection.execute("SELECT 7 AS answer").fetchone()["answer"] == 7

    def test_close_releases_the_profile(self, tmp_path):
        manager = DatabaseConnection()
        manager.open(tmp_path / "a.sqlite", create=True)
        manager.close()
        assert manager.is_open is False
        assert manager.path is None
        with pytest.raises(NoActiveProfileError):
            manager.connection

    def test_close_can_be_called_twice(self, db):
        db.close()
        db.close()

    def test_the_context_manager_closes_on_exit(self, tmp_path):
        with DatabaseConnection() as manager:
            manager.open(tmp_path / "a.sqlite", create=True)
        assert manager.is_open is False

    def test_data_survives_closing_and_reopening(self, tmp_path):
        path = tmp_path / "keep.sqlite"
        with DatabaseConnection() as manager:
            manager.open(path, create=True)
            add_entity(manager.connection, "Aria")
            manager.connection.commit()
        with DatabaseConnection() as manager:
            manager.open(path)
            assert manager.connection.execute("SELECT name FROM entities").fetchone()[0] == "Aria"


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
class TestTransactions:
    def names_seen_by_another_connection(self, manager):
        other = sqlite3.connect(manager.path)
        try:
            return {row[0] for row in other.execute("SELECT name FROM entities")}
        finally:
            other.close()

    def test_commits_when_the_block_finishes(self, db):
        with db.transaction() as conn:
            add_entity(conn, "Aria")
        assert self.names_seen_by_another_connection(db) == {"Aria"}

    def test_rolls_back_when_the_block_raises(self, db):
        with pytest.raises(RuntimeError, match="boom"):
            with db.transaction() as conn:
                add_entity(conn, "Aria")
                raise RuntimeError("boom")
        assert self.names_seen_by_another_connection(db) == set()
        assert db.connection.in_transaction is False

    def test_a_failing_statement_undoes_the_earlier_ones(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                add_entity(conn, "Aria")
                conn.execute("INSERT INTO entities (name) VALUES (NULL)")
        assert self.names_seen_by_another_connection(db) == set()

    def test_nested_blocks_join_the_outer_transaction(self, db):
        with db.transaction():
            with db.transaction() as conn:
                add_entity(conn, "Inner")
            add_entity(db.connection, "Outer")
        assert self.names_seen_by_another_connection(db) == {"Inner", "Outer"}

    def test_a_failure_after_a_nested_block_undoes_the_nested_work(self, db):
        with pytest.raises(RuntimeError):
            with db.transaction():
                with db.transaction() as conn:
                    add_entity(conn, "Inner")
                raise RuntimeError("late failure")
        assert self.names_seen_by_another_connection(db) == set()

    def test_the_connection_is_usable_after_a_rollback(self, db):
        with pytest.raises(RuntimeError):
            with db.transaction() as conn:
                add_entity(conn, "Lost")
                raise RuntimeError("boom")
        with db.transaction() as conn:
            add_entity(conn, "Kept")
        assert self.names_seen_by_another_connection(db) == {"Kept"}

    def test_needs_an_open_profile(self):
        with pytest.raises(NoActiveProfileError):
            with DatabaseConnection().transaction():
                pass


# --------------------------------------------------------------------------- #
# File > Load Profile
# --------------------------------------------------------------------------- #
class TestSwitchProfile:
    @pytest.fixture
    def two_profiles(self, tmp_path):
        """An open manager on characters.sqlite, plus the path of places.sqlite."""
        places = tmp_path / "places.sqlite"
        with DatabaseConnection() as other:
            other.open(places, create=True)
            add_entity(other.connection, "Elmora")
            other.connection.commit()
        manager = DatabaseConnection()
        manager.open(tmp_path / "characters.sqlite", create=True)
        add_entity(manager.connection, "Aria")
        manager.connection.commit()
        yield manager, places
        manager.close()

    def entity_names(self, manager):
        return [r[0] for r in manager.connection.execute("SELECT name FROM entities")]

    def test_switching_changes_the_active_profile_and_its_data(self, two_profiles):
        manager, places = two_profiles
        assert self.entity_names(manager) == ["Aria"]
        assert manager.switch_profile(places) is True
        assert manager.path == places.resolve()
        assert self.entity_names(manager) == ["Elmora"]

    def test_switching_back_shows_the_first_profiles_data_again(self, two_profiles):
        manager, places = two_profiles
        first = manager.path
        manager.switch_profile(places)
        manager.switch_profile(first)
        assert self.entity_names(manager) == ["Aria"]

    def test_the_previous_connection_is_closed(self, two_profiles):
        manager, places = two_profiles
        old_connection = manager.connection
        manager.switch_profile(places)
        with pytest.raises(sqlite3.ProgrammingError):
            old_connection.execute("SELECT 1")

    def test_switching_to_the_active_profile_does_nothing(self, two_profiles):
        manager, _places = two_profiles
        connection = manager.connection
        assert manager.switch_profile(manager.path) is False
        assert manager.connection is connection

    def test_a_missing_file_keeps_the_current_profile(self, two_profiles, tmp_path):
        manager, _places = two_profiles
        original = manager.path
        with pytest.raises(ProfileError, match="doesn't exist"):
            manager.switch_profile(tmp_path / "ghost.sqlite")
        assert manager.path == original
        assert self.entity_names(manager) == ["Aria"]

    def test_an_invalid_file_keeps_the_current_profile(self, two_profiles, tmp_path):
        manager, _places = two_profiles
        bad = tmp_path / "bad.sqlite"
        bad.write_text("not a database")
        with pytest.raises(ProfileError):
            manager.switch_profile(bad)
        assert self.entity_names(manager) == ["Aria"]

    def test_another_applications_database_is_refused_without_changes(self, two_profiles,
                                                                       tmp_path):
        manager, _places = two_profiles
        foreign = tmp_path / "foreign.sqlite"
        make_foreign_database(foreign)
        before = file_hash(foreign)
        with pytest.raises(ProfileError):
            manager.switch_profile(foreign)
        assert file_hash(foreign) == before
        assert self.entity_names(manager) == ["Aria"]

    def test_an_empty_file_is_set_up_with_the_given_template(self, two_profiles, tmp_path):
        manager, _places = two_profiles
        fresh = tmp_path / "fresh.sqlite"
        fresh.write_bytes(b"")
        manager.switch_profile(fresh, template=seeds.WORLDBUILDING_TEMPLATE)
        names = [r[0] for r in manager.connection.execute(
            "SELECT name FROM categories ORDER BY sort_order")]
        assert names == [c["name"] for c in seeds.WORLDBUILDING_TEMPLATE["categories"]]

    def test_an_empty_file_stays_empty_without_a_template(self, two_profiles, tmp_path):
        manager, _places = two_profiles
        fresh = tmp_path / "fresh.sqlite"
        fresh.write_bytes(b"")
        manager.switch_profile(fresh)
        assert is_blank(manager.connection)

    def test_switching_with_nothing_open_simply_opens(self, tmp_path):
        path = tmp_path / "a.sqlite"
        with DatabaseConnection() as seed:
            seed.open(path, create=True)
        manager = DatabaseConnection()
        assert manager.switch_profile(path) is True
        assert manager.path == path.resolve()
        manager.close()


# --------------------------------------------------------------------------- #
# Naming: "Add Character", "Add Place", ...
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("filename, expected", [
    ("characters.sqlite", "Character"),
    ("Characters.db", "Character"),
    ("Character.sqlite", "Character"),
    ("my_characters.sqlite", "Character"),
    ("places.sqlite", "Place"),
    ("Places.SQLITE", "Place"),
    ("locations.db", "Place"),
    ("Worldbuilding.sqlite", "Place"),
    ("factions.sqlite", "Faction"),
    ("cities.sqlite", "City"),
    ("boxes.sqlite", "Box"),
    ("glass.sqlite", "Glass"),
    ("my_magic_items.sqlite", "My Magic Item"),
    ("database.sqlite", "Entry"),
    ("db.sqlite", "Entry"),
    ("untitled.sqlite", "Entry"),
])
def test_profile_noun(filename, expected):
    assert profile_noun(filename) == expected


def test_profile_noun_ignores_the_folder():
    assert profile_noun("/home/me/places/database.sqlite") == "Entry"


# --------------------------------------------------------------------------- #
# Which profile opens at launch
# --------------------------------------------------------------------------- #
class TestStartupProfile:
    def make_profile(self, path):
        with DatabaseConnection() as manager:
            manager.open(path, create=True)

    def test_a_fresh_folder_uses_character_sqlite(self, tmp_path):
        assert resolve_startup_profile(tmp_path) == (tmp_path / DEFAULT_PROFILE_NAME).resolve()

    def test_an_existing_character_file_is_used(self, tmp_path):
        self.make_profile(tmp_path / DEFAULT_PROFILE_NAME)
        assert resolve_startup_profile(tmp_path).name == DEFAULT_PROFILE_NAME

    def test_the_first_versions_file_is_used_until_character_sqlite_exists(self, tmp_path):
        self.make_profile(tmp_path / LEGACY_PROFILE_NAME)
        assert resolve_startup_profile(tmp_path).name == LEGACY_PROFILE_NAME

    def test_character_sqlite_wins_when_both_exist(self, tmp_path):
        self.make_profile(tmp_path / LEGACY_PROFILE_NAME)
        self.make_profile(tmp_path / DEFAULT_PROFILE_NAME)
        assert resolve_startup_profile(tmp_path).name == DEFAULT_PROFILE_NAME

    def test_an_unusable_first_versions_file_is_ignored(self, tmp_path):
        (tmp_path / LEGACY_PROFILE_NAME).write_text("not a database")
        assert resolve_startup_profile(tmp_path).name == DEFAULT_PROFILE_NAME

    def test_the_last_loaded_profile_comes_first(self, tmp_path):
        self.make_profile(tmp_path / LEGACY_PROFILE_NAME)
        places = tmp_path / "places.sqlite"
        self.make_profile(places)
        assert remember_profile(tmp_path / LAST_PROFILE_FILE_NAME, places) is True
        assert resolve_startup_profile(tmp_path) == places.resolve()

    def test_a_remembered_file_that_vanished_is_ignored(self, tmp_path):
        remember_profile(tmp_path / LAST_PROFILE_FILE_NAME, tmp_path / "gone.sqlite")
        assert resolve_startup_profile(tmp_path).name == DEFAULT_PROFILE_NAME

    def test_a_remembered_file_that_is_no_longer_valid_is_ignored(self, tmp_path):
        broken = tmp_path / "broken.sqlite"
        broken.write_text("not a database")
        remember_profile(tmp_path / LAST_PROFILE_FILE_NAME, broken)
        assert resolve_startup_profile(tmp_path).name == DEFAULT_PROFILE_NAME

    def test_remember_and_recall_round_trip(self, tmp_path):
        profile = tmp_path / "places.sqlite"
        self.make_profile(profile)
        settings = tmp_path / LAST_PROFILE_FILE_NAME
        remember_profile(settings, profile)
        assert recall_profile(settings) == profile.resolve()

    def test_recall_without_a_settings_file_returns_none(self, tmp_path):
        assert recall_profile(tmp_path / LAST_PROFILE_FILE_NAME) is None

    def test_an_empty_settings_file_returns_none(self, tmp_path):
        settings = tmp_path / LAST_PROFILE_FILE_NAME
        settings.write_text("   \n")
        assert recall_profile(settings) is None

    def test_remember_reports_failure_instead_of_raising(self, tmp_path):
        assert remember_profile(tmp_path / "no_folder" / LAST_PROFILE_FILE_NAME,
                                tmp_path / "x.sqlite") is False
