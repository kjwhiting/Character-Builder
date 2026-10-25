import sqlite3

_INSERT = """
INSERT INTO search_index (name, aliases, body, entry_id)
SELECT e.name,
       COALESCE((SELECT group_concat(alias, ' ') FROM aliases WHERE entry_id = e.id), ''),
       COALESCE((SELECT group_concat(value, ' ') FROM field_values WHERE entry_id = e.id), ''),
       e.id
FROM entries e
"""


def reindex_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM search_index WHERE entry_id = ?", (entry_id,))
    conn.execute(_INSERT + " WHERE e.id = ? AND e.deleted_at IS NULL", (entry_id,))


def reindex_collection(conn: sqlite3.Connection, collection_id: int) -> None:
    drop_collection(conn, collection_id)
    conn.execute(_INSERT + " WHERE e.collection_id = ? AND e.deleted_at IS NULL", (collection_id,))


def drop_entry(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM search_index WHERE entry_id = ?", (entry_id,))


def drop_collection(conn: sqlite3.Connection, collection_id: int) -> None:
    conn.execute(
        "DELETE FROM search_index WHERE entry_id IN "
        "(SELECT id FROM entries WHERE collection_id = ?)", (collection_id,))
