import sqlite3
from dataclasses import dataclass

from src.database.seeds import FIELD_TYPE_TEXTAREA, FIELD_TYPES
from src.services.errors import (
    CategoryNotEmptyError,
    CategoryNotFoundError,
    DuplicateCategoryError,
    DuplicateFieldError,
    FieldNotFoundError,
    InvalidFieldTypeError,
    InvalidNameError,
    InvalidOrderError,
)

_FIELD_SELECT = """
    SELECT f.id, COALESCE(c.name, f.category), f.name, f.field_type, f.sort_order
    FROM fields f
    LEFT JOIN categories c ON c.name = f.category
"""
_FIELD_ORDER = " ORDER BY COALESCE(c.sort_order, 1000000), f.category, f.sort_order, f.id"


@dataclass(frozen=True)
class Field:
    id: int
    category: str
    name: str
    field_type: str
    sort_order: int


def _clean_name(name, label):
    cleaned = (name or "").strip()
    if not cleaned:
        raise InvalidNameError(f"{label} name cannot be empty.")
    return cleaned


class CategoryService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_categories(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM categories ORDER BY sort_order, id"
        ).fetchall()
        return [row[0] for row in rows]

    def add_category(self, name: str) -> str:
        cleaned = _clean_name(name, "Category")
        if self._find_category(cleaned) is not None:
            raise DuplicateCategoryError(f"Category '{cleaned}' already exists.")
        with self._conn:
            top = self._conn.execute("SELECT MAX(sort_order) FROM categories").fetchone()[0]
            self._conn.execute(
                "INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                (cleaned, 0 if top is None else top + 1),
            )
        return cleaned

    def rename_category(self, old_name: str, new_name: str) -> str:
        current = self._require_category(old_name)
        cleaned = _clean_name(new_name, "Category")
        clash = self._find_category(cleaned)
        if clash is not None and clash.lower() != current.lower():
            raise DuplicateCategoryError(f"Category '{cleaned}' already exists.")
        with self._conn:
            self._conn.execute("UPDATE categories SET name = ? WHERE name = ?", (cleaned, current))
            self._conn.execute("UPDATE fields SET category = ? WHERE category = ?", (cleaned, current))
        return cleaned

    def delete_category(self, name: str) -> None:
        current = self._require_category(name)
        assigned = self.count_fields(current)
        if assigned:
            raise CategoryNotEmptyError(
                f"Category '{current}' still has {assigned} field(s) assigned to it. "
                "Move or delete them first."
            )
        with self._conn:
            self._conn.execute("DELETE FROM categories WHERE name = ?", (current,))

    def reorder_categories(self, ordered_names: list[str]) -> None:
        resolved = [self._require_category(name) for name in ordered_names]
        if sorted(resolved) != sorted(self.list_categories()):
            raise InvalidOrderError("Reordering must list every category exactly once.")
        with self._conn:
            for position, name in enumerate(resolved):
                self._conn.execute(
                    "UPDATE categories SET sort_order = ? WHERE name = ?", (position, name)
                )

    def count_fields(self, category: str) -> int:
        current = self._require_category(category)
        return self._conn.execute(
            "SELECT COUNT(*) FROM fields WHERE category = ?", (current,)
        ).fetchone()[0]

    def list_fields(self, category: str | None = None) -> list[Field]:
        if category is None:
            rows = self._conn.execute(_FIELD_SELECT + _FIELD_ORDER).fetchall()
        else:
            current = self._require_category(category)
            rows = self._conn.execute(
                _FIELD_SELECT + " WHERE f.category = ?" + _FIELD_ORDER, (current,)
            ).fetchall()
        return [Field(*row) for row in rows]

    def get_field(self, field_id: int) -> Field:
        row = self._conn.execute(_FIELD_SELECT + " WHERE f.id = ?", (field_id,)).fetchone()
        if row is None:
            raise FieldNotFoundError(f"Field {field_id} does not exist.")
        return Field(*row)

    def add_field(self, category: str, name: str, field_type: str = "text") -> Field:
        current = self._require_category(category)
        cleaned = _clean_name(name, "Field")
        self._require_field_type(field_type)
        if self._field_name_taken(current, cleaned):
            raise DuplicateFieldError(f"'{current}' already has a field named '{cleaned}'.")
        with self._conn:
            top = self._conn.execute(
                "SELECT MAX(sort_order) FROM fields WHERE category = ?", (current,)
            ).fetchone()[0]
            cursor = self._conn.execute(
                "INSERT INTO fields (category, name, multiline, field_type, sort_order) "
                "VALUES (?, ?, ?, ?, ?)",
                (current, cleaned, int(field_type == FIELD_TYPE_TEXTAREA), field_type,
                 0 if top is None else top + 1),
            )
        return self.get_field(cursor.lastrowid)

    def rename_field(self, field_id: int, new_name: str) -> Field:
        field = self.get_field(field_id)
        cleaned = _clean_name(new_name, "Field")
        if self._field_name_taken(field.category, cleaned, exclude_id=field_id):
            raise DuplicateFieldError(
                f"'{field.category}' already has a field named '{cleaned}'."
            )
        with self._conn:
            self._conn.execute("UPDATE fields SET name = ? WHERE id = ?", (cleaned, field_id))
        return self.get_field(field_id)

    def change_field_type(self, field_id: int, field_type: str) -> Field:
        self.get_field(field_id)
        self._require_field_type(field_type)
        with self._conn:
            self._conn.execute(
                "UPDATE fields SET field_type = ?, multiline = ? WHERE id = ?",
                (field_type, int(field_type == FIELD_TYPE_TEXTAREA), field_id),
            )
        return self.get_field(field_id)

    def count_field_values(self, field_id: int) -> int:
        self.get_field(field_id)
        return self._conn.execute(
            "SELECT COUNT(*) FROM field_values WHERE field_id = ?", (field_id,)
        ).fetchone()[0]

    def delete_field(self, field_id: int) -> None:
        field = self.get_field(field_id)
        remaining = [f.id for f in self.list_fields(field.category) if f.id != field_id]
        with self._conn:
            self._conn.execute("DELETE FROM field_values WHERE field_id = ?", (field_id,))
            self._conn.execute("DELETE FROM fields WHERE id = ?", (field_id,))
            self._renumber(remaining)

    def move_field(self, field_id: int, target_category: str, position: int | None = None) -> Field:
        field = self.get_field(field_id)
        target = self._require_category(target_category)
        same_category = target == field.category
        if not same_category and self._field_name_taken(target, field.name, exclude_id=field_id):
            raise DuplicateFieldError(f"'{target}' already has a field named '{field.name}'.")

        source_order = [f.id for f in self.list_fields(field.category) if f.id != field_id]
        target_order = source_order if same_category else [f.id for f in self.list_fields(target)]
        index = len(target_order) if position is None else max(0, min(position, len(target_order)))
        target_order.insert(index, field_id)

        with self._conn:
            if not same_category:
                self._conn.execute("UPDATE fields SET category = ? WHERE id = ?", (target, field_id))
                self._renumber(source_order)
            self._renumber(target_order)
        return self.get_field(field_id)

    def reorder_fields(self, category: str, ordered_field_ids: list[int]) -> None:
        current = self._require_category(category)
        existing = [f.id for f in self.list_fields(current)]
        if sorted(ordered_field_ids) != sorted(existing):
            raise InvalidOrderError(
                f"Reordering must list every field in '{current}' exactly once."
            )
        with self._conn:
            self._renumber(ordered_field_ids)

    def _renumber(self, ordered_field_ids):
        for position, field_id in enumerate(ordered_field_ids):
            self._conn.execute(
                "UPDATE fields SET sort_order = ? WHERE id = ?", (position, field_id)
            )

    def _find_category(self, name):
        row = self._conn.execute("SELECT name FROM categories WHERE name = ?", (name,)).fetchone()
        return None if row is None else row[0]

    def _require_category(self, name):
        found = self._find_category((name or "").strip())
        if found is None:
            raise CategoryNotFoundError(f"Category '{name}' does not exist.")
        return found

    def _field_name_taken(self, category, name, exclude_id=None):
        row = self._conn.execute(
            "SELECT 1 FROM fields WHERE category = ? AND name = ? AND id IS NOT ?",
            (category, name, exclude_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _require_field_type(field_type):
        if field_type not in FIELD_TYPES:
            raise InvalidFieldTypeError(
                f"Field type must be one of {', '.join(FIELD_TYPES)}; got '{field_type}'."
            )
