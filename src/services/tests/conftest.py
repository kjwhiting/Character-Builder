import sqlite3

import pytest

SCHEMA_SQL = """
CREATE TABLE entities (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT NOT NULL,
    type   TEXT NOT NULL DEFAULT 'Character',
    image  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE fields (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL COLLATE NOCASE,
    name       TEXT NOT NULL COLLATE NOCASE,
    multiline  INTEGER NOT NULL DEFAULT 0,
    field_type TEXT NOT NULL DEFAULT 'text',
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (category, name)
);
CREATE TABLE field_values (
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    field_id  INTEGER NOT NULL REFERENCES fields(id)   ON DELETE CASCADE,
    value     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (entity_id, field_id)
);
CREATE TABLE categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sort_order INTEGER NOT NULL DEFAULT 0
);
"""

CATALOG = [
    ("Description", [("Description", "textarea")]),
    ("Relations", [("Best friend", "text"), ("Enemies", "list")]),
    ("Favorites", [("Color", "text"), ("Food", "text")]),
]


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_SQL)
    yield connection
    connection.close()


@pytest.fixture
def catalog(conn):
    field_ids = {}
    with conn:
        for category_order, (category, fields) in enumerate(CATALOG):
            conn.execute(
                "INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                (category, category_order),
            )
            for field_order, (name, field_type) in enumerate(fields):
                cursor = conn.execute(
                    "INSERT INTO fields (category, name, multiline, field_type, sort_order) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (category, name, int(field_type == "textarea"), field_type, field_order),
                )
                field_ids[name] = cursor.lastrowid
    return field_ids
