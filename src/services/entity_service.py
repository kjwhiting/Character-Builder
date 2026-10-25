import sqlite3
from dataclasses import dataclass

from src.database.seeds import (
    FIELD_TYPE_CHECKBOX,
    FIELD_TYPE_LIST,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_NUMBER,
)
from src.services import search_index
from src.services.collection_service import new_uuid
from src.services.value_format import CHECKBOX_TRUE, split_lines
from src.services.errors import (
    EntityNotFoundError,
    FieldNotFoundError,
    InvalidNameError,
    InvalidValueError,
)


@dataclass(frozen=True)
class Entity:
    id: int
    uuid: str
    name: str
    image: str


_ENTITY_COLUMNS = "e.id, e.uuid, e.name, e.image"


def _like_pattern(query):
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _require_name(value):
    cleaned = (value or "").strip()
    if not cleaned:
        raise InvalidNameError("Name cannot be empty.")
    return cleaned


class EntityService:
    def __init__(self, conn: sqlite3.Connection, collection_id: int):
        self._conn = conn
        self._collection_id = collection_id

    def create_entity(self, name: str, image: str = "",
                      values: dict[int, str] | None = None,
                      aliases: list[str] | None = None) -> int:
        cleaned = _require_name(name)
        with self._conn:
            entity_id = self._conn.execute(
                "INSERT INTO entries (uuid, collection_id, name, image) VALUES (?, ?, ?, ?)",
                (new_uuid(), self._collection_id, cleaned, image.strip()),
            ).lastrowid
            self._write_values(entity_id, values or {})
            if aliases:
                self._write_aliases(entity_id, cleaned, aliases)
            search_index.reindex_entry(self._conn, entity_id)
        return entity_id

    def get_entity(self, entity_id: int) -> Entity:
        row = self._conn.execute(
            f"SELECT {_ENTITY_COLUMNS} FROM entries e "
            "WHERE e.id = ? AND e.collection_id = ? AND e.deleted_at IS NULL",
            (entity_id, self._collection_id),
        ).fetchone()
        if row is None:
            raise EntityNotFoundError(f"Entry {entity_id} does not exist.")
        return Entity(*row)

    def get_values(self, entity_id: int) -> dict[int, str]:
        rows = self._conn.execute(
            "SELECT field_id, value FROM field_values WHERE entry_id = ?", (entity_id,)
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def get_aliases(self, entity_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT a.alias FROM aliases a JOIN entries e ON e.id = a.entry_id "
            "WHERE a.entry_id = ? AND e.collection_id = ? ORDER BY a.id",
            (entity_id, self._collection_id),
        ).fetchall()
        return [row[0] for row in rows]

    def update_entity(self, entity_id: int, name: str, image: str = "",
                      values: dict[int, str] | None = None,
                      aliases: list[str] | None = None) -> None:
        cleaned = _require_name(name)
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE entries SET name = ?, image = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND collection_id = ? AND deleted_at IS NULL",
                (cleaned, image.strip(), entity_id, self._collection_id),
            )
            if cursor.rowcount == 0:
                raise EntityNotFoundError(f"Entry {entity_id} does not exist.")
            self._write_values(entity_id, values or {})
            if aliases is not None:
                self._write_aliases(entity_id, cleaned, aliases)
            search_index.reindex_entry(self._conn, entity_id)

    def delete_entity(self, entity_id: int) -> None:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE entries SET deleted_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND collection_id = ? AND deleted_at IS NULL",
                (entity_id, self._collection_id),
            )
            if cursor.rowcount == 0:
                raise EntityNotFoundError(f"Entry {entity_id} does not exist.")
            search_index.drop_entry(self._conn, entity_id)

    def list_entities(self) -> list[Entity]:
        rows = self._conn.execute(
            f"SELECT {_ENTITY_COLUMNS} FROM entries e "
            "WHERE e.collection_id = ? AND e.deleted_at IS NULL "
            "ORDER BY e.name COLLATE NOCASE, e.id",
            (self._collection_id,),
        ).fetchall()
        return [Entity(*row) for row in rows]

    def search_entities(self, query: str = "") -> list[Entity]:
        query = (query or "").strip()
        if not query:
            return self.list_entities()
        pattern = _like_pattern(query)
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT {_ENTITY_COLUMNS}
            FROM entries e
            LEFT JOIN aliases a ON a.entry_id = e.id
            LEFT JOIN field_values v ON v.entry_id = e.id
            WHERE e.collection_id = ? AND e.deleted_at IS NULL
              AND (e.name LIKE ? ESCAPE '\\'
                   OR a.alias LIKE ? ESCAPE '\\'
                   OR v.value LIKE ? ESCAPE '\\')
            ORDER BY e.name COLLATE NOCASE, e.id
            """,
            (self._collection_id, pattern, pattern, pattern),
        ).fetchall()
        return [Entity(*row) for row in rows]

    def duplicate_entity(self, entity_id: int, new_name: str | None = None) -> int:
        source = self.get_entity(entity_id)
        name = f"{source.name} (Copy)" if new_name is None else _require_name(new_name)
        with self._conn:
            new_id = self._conn.execute(
                "INSERT INTO entries (uuid, collection_id, name, image) VALUES (?, ?, ?, ?)",
                (new_uuid(), self._collection_id, name, source.image),
            ).lastrowid
            self._conn.execute(
                "INSERT INTO field_values (entry_id, field_id, value) "
                "SELECT ?, field_id, value FROM field_values WHERE entry_id = ?",
                (new_id, entity_id),
            )
            self._conn.execute(
                "INSERT INTO aliases (entry_id, alias) SELECT ?, alias FROM aliases "
                "WHERE entry_id = ?",
                (new_id, entity_id),
            )
            search_index.reindex_entry(self._conn, new_id)
        return new_id

    def _write_aliases(self, entity_id, name, aliases):
        seen = {name.lower()}
        kept = []
        for alias in aliases:
            cleaned = (alias or "").strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                kept.append(cleaned)
        self._conn.execute("DELETE FROM aliases WHERE entry_id = ?", (entity_id,))
        for alias in kept:
            self._conn.execute(
                "INSERT INTO aliases (entry_id, alias) VALUES (?, ?)", (entity_id, alias))

    def _write_values(self, entity_id, values):
        types = self._field_types(values.keys())
        for field_id, raw in values.items():
            value = self._normalize(types[field_id][0], types[field_id][1], raw)
            if value:
                self._conn.execute(
                    "INSERT INTO field_values (entry_id, field_id, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(entry_id, field_id) DO UPDATE SET value = excluded.value",
                    (entity_id, field_id, value),
                )
            else:
                self._conn.execute(
                    "DELETE FROM field_values WHERE entry_id = ? AND field_id = ?",
                    (entity_id, field_id),
                )

    @staticmethod
    def _normalize(field_name, field_type, raw):
        text = (raw or "").strip()
        if not text:
            return ""
        if field_type == FIELD_TYPE_CHECKBOX:
            return CHECKBOX_TRUE if text.lower() == CHECKBOX_TRUE else ""
        if field_type == FIELD_TYPE_NUMBER:
            try:
                float(text)
            except ValueError:
                raise InvalidValueError(f"{field_name} must be a number.") from None
            return text
        if field_type in (FIELD_TYPE_LIST, FIELD_TYPE_MULTICHOICE):
            return "\n".join(split_lines(text))
        return text

    def _field_types(self, field_ids):
        wanted = set(field_ids)
        if not wanted:
            return {}
        marks = ",".join("?" * len(wanted))
        found = {
            row[0]: (row[1], row[2])
            for row in self._conn.execute(
                f"SELECT id, name, field_type FROM fields "
                f"WHERE collection_id = ? AND id IN ({marks})",
                [self._collection_id, *wanted],
            )
        }
        missing = wanted - set(found)
        if missing:
            raise FieldNotFoundError(f"Unknown field id(s): {sorted(missing)}")
        return found
