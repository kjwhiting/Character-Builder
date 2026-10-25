from __future__ import annotations

import sqlite3
from pathlib import Path

from src.database.seeds import FIELD_TYPES

SCHEMA_VERSION = 3

_FIELD_TYPE_LIST = ", ".join(f"'{field_type}'" for field_type in FIELD_TYPES)

SCHEMA_SQL = f"""
CREATE TABLE project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE collections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,
    label      TEXT NOT NULL,
    entry_noun TEXT NOT NULL,
    color      TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT
);

CREATE TABLE categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    name          TEXT NOT NULL COLLATE NOCASE,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (collection_id, name),
    UNIQUE (id, collection_id)
);

CREATE TABLE fields (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    category_id   INTEGER NOT NULL,
    name          TEXT NOT NULL COLLATE NOCASE,
    field_type    TEXT NOT NULL DEFAULT 'text' CHECK (field_type IN ({_FIELD_TYPE_LIST})),
    options       TEXT,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    show_empty    INTEGER NOT NULL DEFAULT 0,
    full_width    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (category_id, name),
    FOREIGN KEY (category_id, collection_id) REFERENCES categories(id, collection_id)
);

CREATE TABLE entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid          TEXT NOT NULL UNIQUE,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    image         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at    TEXT
);
CREATE INDEX idx_entries_deleted ON entries(deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX idx_entries_collection_name ON entries(collection_id, name COLLATE NOCASE);
CREATE INDEX idx_entries_name ON entries(name COLLATE NOCASE);

CREATE TABLE aliases (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    alias    TEXT NOT NULL COLLATE NOCASE,
    UNIQUE (entry_id, alias)
);
CREATE INDEX idx_aliases_alias ON aliases(alias);

CREATE TABLE field_values (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES fields(id)  ON DELETE CASCADE,
    value    TEXT NOT NULL,
    PRIMARY KEY (entry_id, field_id)
);
CREATE INDEX idx_field_values_field ON field_values(field_id);

CREATE VIRTUAL TABLE search_index USING fts5(
    name, aliases, body,
    entry_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


class DatabaseError(Exception):
    pass


class NoActiveProjectError(DatabaseError):
    pass


class ProjectDatabase:
    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        self._path: Path | None = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    @property
    def path(self) -> Path:
        if self._path is None:
            raise NoActiveProjectError("No project database is open.")
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise NoActiveProjectError("No project database is open.")
        return self._conn

    def open(self, path, create: bool = False) -> None:
        resolved = Path(path).resolve()
        if not resolved.exists() and not create:
            raise DatabaseError(f"Project database not found: {resolved}")
        connection = self._connect(resolved)
        try:
            self._prepare(connection, resolved)
        except BaseException:
            connection.close()
            raise
        previous = self._conn
        self._conn = connection
        self._path = resolved
        if previous is not None:
            previous.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        self._path = None

    def __enter__(self) -> "ProjectDatabase":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(str(path), timeout=10)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Could not open {path}: {exc}") from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _prepare(connection: sqlite3.Connection, path: Path) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise DatabaseError(f"{path.name} is not a readable database: {exc}") from exc

        if version == 0 and tables == 0:
            with connection:
                connection.executescript(SCHEMA_SQL)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.execute(
                    "INSERT INTO project_meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            return
        if version == 1:
            with connection:
                connection.execute("ALTER TABLE collections ADD COLUMN deleted_at TEXT")
                connection.execute("ALTER TABLE entries ADD COLUMN deleted_at TEXT")
                connection.execute(
                    "CREATE INDEX idx_entries_deleted ON entries(deleted_at) "
                    "WHERE deleted_at IS NOT NULL")
                connection.execute("UPDATE project_meta SET value = '2' WHERE key = 'schema_version'")
                connection.execute("PRAGMA user_version = 2")
            version = 2
        if version == 2:
            with connection:
                connection.execute(
                    "ALTER TABLE fields ADD COLUMN show_empty INTEGER NOT NULL DEFAULT 0")
                connection.execute(
                    "ALTER TABLE fields ADD COLUMN full_width INTEGER NOT NULL DEFAULT 0")
                connection.execute("UPDATE project_meta SET value = '3' WHERE key = 'schema_version'")
                connection.execute("PRAGMA user_version = 3")
            version = 3
        if version != SCHEMA_VERSION:
            raise DatabaseError(
                f"{path.name} is not a Worldbuilder project database "
                f"(schema version {version}, expected {SCHEMA_VERSION})."
            )
