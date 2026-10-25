import sqlite3
from dataclasses import dataclass

from src.services import search_index
from src.services.errors import TrashItemNotFoundError

KIND_TAB = "tab"
KIND_ENTRY = "entry"
RETENTION_DAYS = 30


@dataclass(frozen=True)
class TrashItem:
    kind: str
    id: int
    label: str
    detail: str
    deleted_at: str


class TrashService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_items(self) -> list[TrashItem]:
        tabs = self._conn.execute(
            """
            SELECT c.id, c.label, c.deleted_at,
                   (SELECT COUNT(*) FROM entries e
                    WHERE e.collection_id = c.id AND e.deleted_at IS NULL)
            FROM collections c WHERE c.deleted_at IS NOT NULL
            """
        ).fetchall()
        entries = self._conn.execute(
            """
            SELECT e.id, e.name, e.deleted_at, c.label
            FROM entries e JOIN collections c ON c.id = e.collection_id
            WHERE e.deleted_at IS NOT NULL AND c.deleted_at IS NULL
            """
        ).fetchall()
        items = [
            TrashItem(KIND_TAB, row[0], row[1],
                      f"Tab with {row[3]} {'entry' if row[3] == 1 else 'entries'}", row[2])
            for row in tabs
        ] + [
            TrashItem(KIND_ENTRY, row[0], row[1], f"Entry from {row[3]}", row[2])
            for row in entries
        ]
        return sorted(items, key=lambda item: item.deleted_at, reverse=True)

    def count(self) -> int:
        return len(self.list_items())

    def restore(self, kind: str, item_id: int) -> str:
        if kind == KIND_TAB:
            return self._restore_tab(item_id)
        if kind == KIND_ENTRY:
            return self._restore_entry(item_id)
        raise TrashItemNotFoundError(f"Unknown trash item kind '{kind}'.")

    def delete_forever(self, kind: str, item_id: int) -> None:
        with self._conn:
            if kind == KIND_TAB:
                self._require_trashed("collections", item_id)
                search_index.drop_collection(self._conn, item_id)
                self._conn.execute("DELETE FROM collections WHERE id = ?", (item_id,))
            elif kind == KIND_ENTRY:
                self._require_trashed("entries", item_id)
                search_index.drop_entry(self._conn, item_id)
                self._conn.execute("DELETE FROM entries WHERE id = ?", (item_id,))
            else:
                raise TrashItemNotFoundError(f"Unknown trash item kind '{kind}'.")

    def empty_trash(self) -> int:
        items = self.list_items()
        for item in items:
            self.delete_forever(item.kind, item.id)
        return len(items)

    def purge_expired(self, days: int = RETENTION_DAYS) -> int:
        cutoff = f"-{int(days)} days"
        expired_tabs = self._conn.execute(
            "SELECT id FROM collections WHERE deleted_at IS NOT NULL "
            "AND deleted_at < datetime('now', ?)", (cutoff,)).fetchall()
        expired_entries = self._conn.execute(
            "SELECT id FROM entries WHERE deleted_at IS NOT NULL "
            "AND deleted_at < datetime('now', ?)", (cutoff,)).fetchall()
        for row in expired_entries:
            self.delete_forever(KIND_ENTRY, row[0])
        for row in expired_tabs:
            self.delete_forever(KIND_TAB, row[0])
        return len(expired_tabs) + len(expired_entries)

    def _restore_tab(self, collection_id):
        row = self._require_trashed("collections", collection_id)
        label = row[0]
        candidate, counter = label, 1
        while self._label_taken(candidate):
            counter += 1
            candidate = f"{label} (restored)" if counter == 2 else f"{label} (restored {counter - 1})"
        with self._conn:
            self._conn.execute(
                "UPDATE collections SET deleted_at = NULL, label = ? WHERE id = ?",
                (candidate, collection_id))
            search_index.reindex_collection(self._conn, collection_id)
        return candidate

    def _restore_entry(self, entry_id):
        row = self._conn.execute(
            "SELECT e.name FROM entries e JOIN collections c ON c.id = e.collection_id "
            "WHERE e.id = ? AND e.deleted_at IS NOT NULL AND c.deleted_at IS NULL",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise TrashItemNotFoundError(f"Entry {entry_id} is not in the Trash.")
        with self._conn:
            self._conn.execute("UPDATE entries SET deleted_at = NULL WHERE id = ?", (entry_id,))
            search_index.reindex_entry(self._conn, entry_id)
        return row[0]

    def _require_trashed(self, table, item_id):
        column = "label" if table == "collections" else "name"
        row = self._conn.execute(
            f"SELECT {column} FROM {table} WHERE id = ? AND deleted_at IS NOT NULL", (item_id,)
        ).fetchone()
        if row is None:
            raise TrashItemNotFoundError(f"Item {item_id} is not in the Trash.")
        return row

    def _label_taken(self, label):
        return self._conn.execute(
            "SELECT 1 FROM collections WHERE label = ? COLLATE NOCASE AND deleted_at IS NULL",
            (label,),
        ).fetchone() is not None
