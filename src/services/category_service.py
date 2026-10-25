import json
import sqlite3
from dataclasses import dataclass, field as dataclass_field

from src.database.seeds import (
    FIELD_TYPE_CHOICE,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPES,
)
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
    SELECT f.id, c.name, f.name, f.field_type, f.options, f.sort_order,
           f.show_empty, f.full_width
    FROM fields f
    JOIN categories c ON c.id = f.category_id
"""
_FIELD_ORDER = " ORDER BY c.sort_order, c.id, f.sort_order, f.id"


@dataclass(frozen=True)
class Field:
    id: int
    category: str
    name: str
    field_type: str
    options: dict = dataclass_field(default_factory=dict)
    sort_order: int = 0
    show_empty: bool = False
    full_width: bool = False


def _field_from_row(row):
    options = json.loads(row[4]) if row[4] else {}
    return Field(row[0], row[1], row[2], row[3], options, row[5], bool(row[6]), bool(row[7]))


def normalize_options(field_type: str, options: dict | None) -> dict:
    options = options or {}
    if field_type in (FIELD_TYPE_CHOICE, FIELD_TYPE_MULTICHOICE):
        seen, choices = set(), []
        for choice in options.get("choices", []):
            cleaned = str(choice).strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                choices.append(cleaned)
        return {"choices": choices} if choices else {}
    if field_type == FIELD_TYPE_NUMBER:
        unit = str(options.get("unit", "")).strip()
        return {"unit": unit} if unit else {}
    return {}


def _clean_name(name, label):
    cleaned = (name or "").strip()
    if not cleaned:
        raise InvalidNameError(f"{label} name cannot be empty.")
    return cleaned


class CategoryService:
    def __init__(self, conn: sqlite3.Connection, collection_id: int):
        self._conn = conn
        self._collection_id = collection_id

    def list_categories(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM categories WHERE collection_id = ? ORDER BY sort_order, id",
            (self._collection_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def add_category(self, name: str) -> str:
        cleaned = _clean_name(name, "Category")
        if self._find_category(cleaned) is not None:
            raise DuplicateCategoryError(f"Category '{cleaned}' already exists.")
        with self._conn:
            top = self._conn.execute(
                "SELECT MAX(sort_order) FROM categories WHERE collection_id = ?",
                (self._collection_id,),
            ).fetchone()[0]
            self._conn.execute(
                "INSERT INTO categories (collection_id, name, sort_order) VALUES (?, ?, ?)",
                (self._collection_id, cleaned, 0 if top is None else top + 1),
            )
        return cleaned

    def rename_category(self, old_name: str, new_name: str) -> str:
        current = self._require_category(old_name)
        cleaned = _clean_name(new_name, "Category")
        clash = self._find_category(cleaned)
        if clash is not None and clash[1].lower() != current[1].lower():
            raise DuplicateCategoryError(f"Category '{cleaned}' already exists.")
        with self._conn:
            self._conn.execute(
                "UPDATE categories SET name = ? WHERE id = ?", (cleaned, current[0]))
        return cleaned

    def delete_category(self, name: str) -> None:
        category_id, current = self._require_category(name)
        assigned = self.count_fields(current)
        if assigned:
            raise CategoryNotEmptyError(
                f"Category '{current}' still has {assigned} field(s) assigned to it. "
                "Move or delete them first."
            )
        with self._conn:
            self._conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))

    def reorder_categories(self, ordered_names: list[str]) -> None:
        resolved = [self._require_category(name) for name in ordered_names]
        if sorted(item[1] for item in resolved) != sorted(self.list_categories()):
            raise InvalidOrderError("Reordering must list every category exactly once.")
        with self._conn:
            for position, (category_id, _name) in enumerate(resolved):
                self._conn.execute(
                    "UPDATE categories SET sort_order = ? WHERE id = ?", (position, category_id))

    def count_fields(self, category: str) -> int:
        category_id, _name = self._require_category(category)
        return self._conn.execute(
            "SELECT COUNT(*) FROM fields WHERE category_id = ?", (category_id,)
        ).fetchone()[0]

    def list_fields(self, category: str | None = None) -> list[Field]:
        if category is None:
            rows = self._conn.execute(
                _FIELD_SELECT + " WHERE f.collection_id = ?" + _FIELD_ORDER,
                (self._collection_id,),
            ).fetchall()
        else:
            category_id, _name = self._require_category(category)
            rows = self._conn.execute(
                _FIELD_SELECT + " WHERE f.category_id = ?" + _FIELD_ORDER, (category_id,)
            ).fetchall()
        return [_field_from_row(row) for row in rows]

    def get_field(self, field_id: int) -> Field:
        row = self._conn.execute(
            _FIELD_SELECT + " WHERE f.id = ? AND f.collection_id = ?",
            (field_id, self._collection_id),
        ).fetchone()
        if row is None:
            raise FieldNotFoundError(f"Field {field_id} does not exist.")
        return _field_from_row(row)

    def add_field(self, category: str, name: str, field_type: str = "text",
                  options: dict | None = None) -> Field:
        category_id, current = self._require_category(category)
        cleaned = _clean_name(name, "Field")
        self._require_field_type(field_type)
        if self._field_name_taken(category_id, cleaned):
            raise DuplicateFieldError(f"'{current}' already has a field named '{cleaned}'.")
        with self._conn:
            top = self._conn.execute(
                "SELECT MAX(sort_order) FROM fields WHERE category_id = ?", (category_id,)
            ).fetchone()[0]
            cursor = self._conn.execute(
                "INSERT INTO fields (collection_id, category_id, name, field_type, options, "
                "sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                (self._collection_id, category_id, cleaned, field_type,
                 self._encode_options(field_type, options), 0 if top is None else top + 1),
            )
        return self.get_field(cursor.lastrowid)

    def rename_field(self, field_id: int, new_name: str) -> Field:
        field = self.get_field(field_id)
        cleaned = _clean_name(new_name, "Field")
        category_id, _name = self._require_category(field.category)
        if self._field_name_taken(category_id, cleaned, exclude_id=field_id):
            raise DuplicateFieldError(
                f"'{field.category}' already has a field named '{cleaned}'.")
        with self._conn:
            self._conn.execute("UPDATE fields SET name = ? WHERE id = ?", (cleaned, field_id))
        return self.get_field(field_id)

    def change_field_type(self, field_id: int, field_type: str) -> Field:
        field = self.get_field(field_id)
        self._require_field_type(field_type)
        kept = {}
        if {field.field_type, field_type} <= {FIELD_TYPE_CHOICE, FIELD_TYPE_MULTICHOICE}:
            kept = field.options
        with self._conn:
            self._conn.execute(
                "UPDATE fields SET field_type = ?, options = ? WHERE id = ?",
                (field_type, self._encode_options(field_type, kept), field_id))
        return self.get_field(field_id)

    def set_field_options(self, field_id: int, options: dict) -> Field:
        field = self.get_field(field_id)
        with self._conn:
            self._conn.execute(
                "UPDATE fields SET options = ? WHERE id = ?",
                (self._encode_options(field.field_type, options), field_id))
        return self.get_field(field_id)

    def set_field_display(self, field_id: int, show_empty: bool | None = None,
                          full_width: bool | None = None) -> Field:
        field = self.get_field(field_id)
        new_show = field.show_empty if show_empty is None else show_empty
        new_wide = field.full_width if full_width is None else full_width
        with self._conn:
            self._conn.execute(
                "UPDATE fields SET show_empty = ?, full_width = ? WHERE id = ?",
                (int(new_show), int(new_wide), field_id))
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
        target_id, target = self._require_category(target_category)
        same_category = target == field.category
        if not same_category and self._field_name_taken(target_id, field.name, exclude_id=field_id):
            raise DuplicateFieldError(f"'{target}' already has a field named '{field.name}'.")

        source_order = [f.id for f in self.list_fields(field.category) if f.id != field_id]
        target_order = source_order if same_category else [f.id for f in self.list_fields(target)]
        index = len(target_order) if position is None else max(0, min(position, len(target_order)))
        target_order.insert(index, field_id)

        with self._conn:
            if not same_category:
                self._conn.execute(
                    "UPDATE fields SET category_id = ? WHERE id = ?", (target_id, field_id))
                self._renumber(source_order)
            self._renumber(target_order)
        return self.get_field(field_id)

    def reorder_fields(self, category: str, ordered_field_ids: list[int]) -> None:
        _category_id, current = self._require_category(category)
        existing = [f.id for f in self.list_fields(current)]
        if sorted(ordered_field_ids) != sorted(existing):
            raise InvalidOrderError(
                f"Reordering must list every field in '{current}' exactly once.")
        with self._conn:
            self._renumber(ordered_field_ids)

    def _renumber(self, ordered_field_ids):
        for position, field_id in enumerate(ordered_field_ids):
            self._conn.execute(
                "UPDATE fields SET sort_order = ? WHERE id = ?", (position, field_id))

    def _find_category(self, name):
        row = self._conn.execute(
            "SELECT id, name FROM categories WHERE collection_id = ? AND name = ?",
            (self._collection_id, name),
        ).fetchone()
        return None if row is None else (row[0], row[1])

    def _require_category(self, name):
        found = self._find_category((name or "").strip())
        if found is None:
            raise CategoryNotFoundError(f"Category '{name}' does not exist.")
        return found

    def _field_name_taken(self, category_id, name, exclude_id=None):
        row = self._conn.execute(
            "SELECT 1 FROM fields WHERE category_id = ? AND name = ? AND id IS NOT ?",
            (category_id, name, exclude_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _encode_options(field_type, options):
        normalized = normalize_options(field_type, options)
        return json.dumps(normalized) if normalized else None

    @staticmethod
    def _require_field_type(field_type):
        if field_type not in FIELD_TYPES:
            raise InvalidFieldTypeError(
                f"Field type must be one of {', '.join(FIELD_TYPES)}; got '{field_type}'.")
