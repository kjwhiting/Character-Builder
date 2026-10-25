import sqlite3
from typing import Callable

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.value_format import format_value

ClipboardWriter = Callable[[str], None]


class TkClipboard:
    def __init__(self, widget):
        self._widget = widget

    def __call__(self, text: str) -> None:
        self._widget.clipboard_clear()
        self._widget.clipboard_append(text)
        self._widget.update()


class ExportService:
    def __init__(self, conn: sqlite3.Connection, collection_id: int, clipboard: ClipboardWriter):
        self._entities = EntityService(conn, collection_id)
        self._categories = CategoryService(conn, collection_id)
        self._clipboard = clipboard

    def build_plain_text(self, entity_id: int) -> str:
        self._entities.get_entity(entity_id)
        values = self._entities.get_values(entity_id)
        groups: dict[str, list[str]] = {}
        for field in self._categories.list_fields():
            value = format_value(field.field_type, field.options, values.get(field.id))
            groups.setdefault(field.category, []).append(f"{field.name}: {value}".rstrip())
        return "\n\n".join("\n".join([category, *lines]) for category, lines in groups.items())

    def copy_entity(self, entity_id: int) -> str:
        text = self.build_plain_text(entity_id)
        self._clipboard(text)
        return text
