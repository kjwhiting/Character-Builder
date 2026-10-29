FIELD_TYPES_SQL = "'text', 'textarea', 'list', 'choice', 'multichoice', 'checkbox', 'number'"

V1_SCHEMA = f"""
CREATE TABLE project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
    entry_noun TEXT NOT NULL, color TEXT, sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE, sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (collection_id, name), UNIQUE (id, collection_id)
);
CREATE TABLE fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL, name TEXT NOT NULL COLLATE NOCASE,
    field_type TEXT NOT NULL DEFAULT 'text' CHECK (field_type IN ({FIELD_TYPES_SQL})),
    options TEXT, sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (category_id, name),
    FOREIGN KEY (category_id, collection_id) REFERENCES categories(id, collection_id)
);
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT NOT NULL UNIQUE,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    name TEXT NOT NULL, image TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    alias TEXT NOT NULL COLLATE NOCASE, UNIQUE (entry_id, alias)
);
CREATE TABLE field_values (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    value TEXT NOT NULL, PRIMARY KEY (entry_id, field_id)
);
CREATE VIRTUAL TABLE search_index USING fts5(
    name, aliases, body, entry_id UNINDEXED, tokenize = 'unicode61 remove_diacritics 2'
);
"""

V2_SCHEMA = V1_SCHEMA.replace(
    "color TEXT, sort_order INTEGER NOT NULL DEFAULT 0\n);",
    "color TEXT, sort_order INTEGER NOT NULL DEFAULT 0, deleted_at TEXT\n);",
).replace(
    "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);",
    "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT\n);",
)

SAMPLE_ROWS = """
INSERT INTO project_meta (key, value) VALUES ('schema_version', '{version}');
INSERT INTO collections (key, label, entry_noun, color, sort_order)
    VALUES ('characters', 'Characters', 'Character', '#E0A458', 0);
INSERT INTO categories (collection_id, name, sort_order) VALUES (1, 'Basics', 0);
INSERT INTO fields (collection_id, category_id, name, field_type, options, sort_order)
    VALUES (1, 1, 'Height', 'number', '{{"unit": "cm"}}', 0);
INSERT INTO entries (uuid, collection_id, name) VALUES ('uuid-aria', 1, 'Aria Vale');
INSERT INTO field_values (entry_id, field_id, value) VALUES (1, 1, '172');
INSERT INTO aliases (entry_id, alias) VALUES (1, 'the Captain');
"""
