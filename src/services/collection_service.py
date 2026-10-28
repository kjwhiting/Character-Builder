import json
import re
import sqlite3
import uuid
from dataclasses import dataclass

from src.database.seeds import Template, get_template
from src.services import search_index
from src.services.errors import (
    CollectionNotFoundError,
    DuplicateCollectionError,
    InvalidColorError,
    InvalidNameError,
    InvalidOrderError,
)

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


@dataclass(frozen=True)
class Collection:
    id: int
    key: str
    label: str
    entry_noun: str
    color: str | None
    sort_order: int


def _clean(value, label):
    cleaned = (value or "").strip()
    if not cleaned:
        raise InvalidNameError(f"{label} cannot be empty.")
    return cleaned


def _slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "tab"


class CollectionService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_collections(self) -> list[Collection]:
        rows = self._conn.execute(
            "SELECT id, key, label, entry_noun, color, sort_order FROM collections "
            "WHERE deleted_at IS NULL ORDER BY sort_order, id"
        ).fetchall()
        return [Collection(*row) for row in rows]

    def get_collection(self, collection_id: int) -> Collection:
        row = self._conn.execute(
            "SELECT id, key, label, entry_noun, color, sort_order FROM collections "
            "WHERE id = ? AND deleted_at IS NULL",
            (collection_id,),
        ).fetchone()
        if row is None:
            raise CollectionNotFoundError(f"Tab {collection_id} does not exist.")
        return Collection(*row)

    def add_collection(self, label: str, entry_noun: str, template_key: str = "blank",
                       color: str | None = None) -> Collection:
        template = get_template(template_key)
        return self.add_from_template(template, label=label, entry_noun=entry_noun, color=color)

    def add_from_template(self, template: Template, label: str | None = None,
                          entry_noun: str | None = None, color: str | None = None) -> Collection:
        cleaned_label = _clean(label if label is not None else template["label"], "Tab name")
        cleaned_noun = _clean(
            entry_noun if entry_noun is not None else template["entry_noun"], "Entry name")
        if self._label_taken(cleaned_label):
            raise DuplicateCollectionError(f"A tab named '{cleaned_label}' already exists.")
        key = self._unique_key(_slug(cleaned_label))
        with self._conn:
            top = self._conn.execute("SELECT MAX(sort_order) FROM collections").fetchone()[0]
            collection_id = self._conn.execute(
                "INSERT INTO collections (key, label, entry_noun, color, sort_order) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, cleaned_label, cleaned_noun, color or template.get("color"),
                 0 if top is None else top + 1),
            ).lastrowid
            for category_order, category in enumerate(template["categories"]):
                category_id = self._conn.execute(
                    "INSERT INTO categories (collection_id, name, sort_order) VALUES (?, ?, ?)",
                    (collection_id, category["name"], category_order),
                ).lastrowid
                for field_order, field in enumerate(category["fields"]):
                    options = field.get("options")
                    self._conn.execute(
                        "INSERT INTO fields (collection_id, category_id, name, field_type, "
                        "options, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                        (collection_id, category_id, field["name"], field["type"],
                         json.dumps(options) if options else None, field_order),
                    )
        return self.get_collection(collection_id)

    def rename_collection(self, collection_id: int, label: str) -> Collection:
        self.get_collection(collection_id)
        cleaned = _clean(label, "Tab name")
        if self._label_taken(cleaned, exclude_id=collection_id):
            raise DuplicateCollectionError(f"A tab named '{cleaned}' already exists.")
        with self._conn:
            self._conn.execute(
                "UPDATE collections SET label = ? WHERE id = ?", (cleaned, collection_id))
        return self.get_collection(collection_id)

    def set_entry_noun(self, collection_id: int, entry_noun: str) -> Collection:
        self.get_collection(collection_id)
        cleaned = _clean(entry_noun, "Entry name")
        with self._conn:
            self._conn.execute(
                "UPDATE collections SET entry_noun = ? WHERE id = ?", (cleaned, collection_id))
        return self.get_collection(collection_id)

    def set_color(self, collection_id: int, color: str) -> Collection:
        self.get_collection(collection_id)
        if not _HEX_COLOR.fullmatch(color or ""):
            raise InvalidColorError("Color must look like #RRGGBB.")
        with self._conn:
            self._conn.execute(
                "UPDATE collections SET color = ? WHERE id = ?", (color.upper(), collection_id))
        return self.get_collection(collection_id)

    def count_entries(self, collection_id: int) -> int:
        self.get_collection(collection_id)
        return self._conn.execute(
            "SELECT COUNT(*) FROM entries WHERE collection_id = ? AND deleted_at IS NULL",
            (collection_id,)
        ).fetchone()[0]

    def trash_collection(self, collection_id: int) -> None:
        self.get_collection(collection_id)
        with self._conn:
            self._conn.execute(
                "UPDATE collections SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (collection_id,))
            search_index.drop_collection(self._conn, collection_id)

    def reorder_collections(self, ordered_ids: list[int]) -> None:
        existing = [c.id for c in self.list_collections()]
        if sorted(ordered_ids) != sorted(existing):
            raise InvalidOrderError("Reordering must list every tab exactly once.")
        with self._conn:
            for position, collection_id in enumerate(ordered_ids):
                self._conn.execute(
                    "UPDATE collections SET sort_order = ? WHERE id = ?",
                    (position, collection_id))

    def _label_taken(self, label, exclude_id=None):
        row = self._conn.execute(
            "SELECT 1 FROM collections WHERE label = ? COLLATE NOCASE AND id IS NOT ? "
            "AND deleted_at IS NULL",
            (label, exclude_id),
        ).fetchone()
        return row is not None

    def _unique_key(self, base):
        key, counter = base, 2
        while self._conn.execute(
            "SELECT 1 FROM collections WHERE key = ?", (key,)
        ).fetchone():
            key = f"{base}-{counter}"
            counter += 1
        return key


def new_uuid() -> str:
    return str(uuid.uuid4())
