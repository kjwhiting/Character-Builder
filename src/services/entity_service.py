import sqlite3
from dataclasses import dataclass

from src.services.errors import EntityNotFoundError, FieldNotFoundError, InvalidNameError


@dataclass(frozen=True)
class Entity:
    id: int
    name: str
    type: str
    image: str


def _like_pattern(query):
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _require_text(value, label):
    cleaned = (value or "").strip()
    if not cleaned:
        raise InvalidNameError(f"{label} cannot be empty.")
    return cleaned


class EntityService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create_entity(self, name: str, entity_type: str, image: str = "",
                      values: dict[int, str] | None = None) -> int:
        cleaned_name = _require_text(name, "Name")
        cleaned_type = _require_text(entity_type, "Type")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO entities (name, type, image) VALUES (?, ?, ?)",
                (cleaned_name, cleaned_type, image.strip()),
            )
            self._write_values(cursor.lastrowid, values or {})
        return cursor.lastrowid

    def get_entity(self, entity_id: int) -> Entity:
        row = self._conn.execute(
            "SELECT id, name, type, image FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            raise EntityNotFoundError(f"Entity {entity_id} does not exist.")
        return Entity(*row)

    def get_values(self, entity_id: int) -> dict[int, str]:
        rows = self._conn.execute(
            "SELECT field_id, value FROM field_values WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def update_entity(self, entity_id: int, name: str, entity_type: str, image: str = "",
                      values: dict[int, str] | None = None) -> None:
        cleaned_name = _require_text(name, "Name")
        cleaned_type = _require_text(entity_type, "Type")
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE entities SET name = ?, type = ?, image = ? WHERE id = ?",
                (cleaned_name, cleaned_type, image.strip(), entity_id),
            )
            if cursor.rowcount == 0:
                raise EntityNotFoundError(f"Entity {entity_id} does not exist.")
            self._write_values(entity_id, values or {})

    def delete_entity(self, entity_id: int) -> None:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            if cursor.rowcount == 0:
                raise EntityNotFoundError(f"Entity {entity_id} does not exist.")

    def list_entities(self) -> list[Entity]:
        rows = self._conn.execute(
            "SELECT id, name, type, image FROM entities ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [Entity(*row) for row in rows]

    def search_entities(self, query: str = "") -> list[Entity]:
        query = (query or "").strip()
        if not query:
            return self.list_entities()
        pattern = _like_pattern(query)
        rows = self._conn.execute(
            """
            SELECT DISTINCT e.id, e.name, e.type, e.image
            FROM entities e
            LEFT JOIN field_values v ON v.entity_id = e.id
            WHERE e.name LIKE ? ESCAPE '\\'
               OR e.type LIKE ? ESCAPE '\\'
               OR v.value LIKE ? ESCAPE '\\'
            ORDER BY e.name COLLATE NOCASE, e.id
            """,
            (pattern, pattern, pattern),
        ).fetchall()
        return [Entity(*row) for row in rows]

    def get_entities_missing_field(self, field_id: int) -> list[Entity]:
        self._require_fields([field_id])
        rows = self._conn.execute(
            """
            SELECT e.id, e.name, e.type, e.image
            FROM entities e
            WHERE NOT EXISTS (
                SELECT 1 FROM field_values v
                WHERE v.entity_id = e.id AND v.field_id = ? AND TRIM(v.value) <> ''
            )
            ORDER BY e.name COLLATE NOCASE, e.id
            """,
            (field_id,),
        ).fetchall()
        return [Entity(*row) for row in rows]

    def duplicate_entity(self, entity_id: int, new_name: str | None = None) -> int:
        source = self.get_entity(entity_id)
        name = f"{source.name} (Copy)" if new_name is None else _require_text(new_name, "Name")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO entities (name, type, image) VALUES (?, ?, ?)",
                (name, source.type, source.image),
            )
            self._conn.execute(
                "INSERT INTO field_values (entity_id, field_id, value) "
                "SELECT ?, field_id, value FROM field_values WHERE entity_id = ?",
                (cursor.lastrowid, entity_id),
            )
        return cursor.lastrowid

    def _write_values(self, entity_id, values):
        self._require_fields(values.keys())
        for field_id, value in values.items():
            if (value or "").strip():
                self._conn.execute(
                    "INSERT INTO field_values (entity_id, field_id, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(entity_id, field_id) DO UPDATE SET value = excluded.value",
                    (entity_id, field_id, value),
                )
            else:
                self._conn.execute(
                    "DELETE FROM field_values WHERE entity_id = ? AND field_id = ?",
                    (entity_id, field_id),
                )

    def _require_fields(self, field_ids):
        wanted = set(field_ids)
        if not wanted:
            return
        marks = ",".join("?" * len(wanted))
        found = {
            row[0]
            for row in self._conn.execute(
                f"SELECT id FROM fields WHERE id IN ({marks})", list(wanted)
            )
        }
        missing = wanted - found
        if missing:
            raise FieldNotFoundError(f"Unknown field id(s): {sorted(missing)}")
