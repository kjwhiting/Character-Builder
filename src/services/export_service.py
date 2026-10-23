import sqlite3
from typing import Callable

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.errors import NothingToExportError

ClipboardWriter = Callable[[str], None]


class TkClipboard:
    def __init__(self, widget):
        self._widget = widget

    def __call__(self, text: str) -> None:
        self._widget.clipboard_clear()
        self._widget.clipboard_append(text)
        self._widget.update()


def _format_value(raw, field_type):
    text = (raw or "").strip()
    if field_type == "list":
        return ", ".join(item.strip() for item in text.splitlines() if item.strip())
    return text


class ExportService:
    def __init__(self, conn: sqlite3.Connection, clipboard: ClipboardWriter):
        self._entities = EntityService(conn)
        self._categories = CategoryService(conn)
        self._clipboard = clipboard

    def build_plain_text(self, entity_id: int) -> str:
        self._entities.get_entity(entity_id)
        values = self._entities.get_values(entity_id)
        groups: dict[str, list[str]] = {}
        for field in self._categories.list_fields():
            value = _format_value(values.get(field.id), field.field_type)
            if value:
                groups.setdefault(field.category, []).append(f"{field.name}: {value}")
        return "\n\n".join("\n".join([category, *lines]) for category, lines in groups.items())

    def copy_entity(self, entity_id: int) -> str:
        text = self.build_plain_text(entity_id)
        if not text:
            raise NothingToExportError("This entry has no filled-in fields to copy.")
        self._clipboard(text)
        return text
