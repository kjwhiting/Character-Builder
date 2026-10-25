import sqlite3
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from src.services.category_service import CategoryService
from src.services.collection_service import Collection
from src.services.entity_service import EntityService
from src.services.export_service import ClipboardWriter, ExportService
from src.ui import theme
from src.ui.card_view import CardView
from src.ui.sidebar_view import SidebarView


class TabPage(ctk.CTkFrame):
    def __init__(self, master, connection: sqlite3.Connection, collection: Collection,
                 images_dir: Path, clipboard: ClipboardWriter,
                 on_trash_changed: Callable[[], None] | None = None,
                 on_terms_changed: Callable[[], None] | None = None):
        super().__init__(master, corner_radius=0, fg_color=theme.BACKGROUND)
        self.collection = collection
        self._on_trash_changed = on_trash_changed or (lambda: None)
        self._on_terms_changed = on_terms_changed or (lambda: None)
        self.entities = EntityService(connection, collection.id)
        self.categories = CategoryService(connection, collection.id)
        self.exporter = ExportService(connection, collection.id, clipboard)

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = SidebarView(
            self, self.entities, title=collection.label, noun=collection.entry_noun,
            on_select=self.select_entity, on_add=self.add_entity)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.card = CardView(
            self, self.entities, self.categories, self.exporter,
            images_dir=images_dir, noun=collection.entry_noun,
            on_saved=self._saved, on_deleted=self._deleted, on_duplicated=self._duplicated)
        self.card.grid(row=0, column=1, sticky="nsew")

    @property
    def editing(self) -> bool:
        return self.card.editing

    @property
    def selected_entity_id(self) -> int | None:
        return self.card.entity_id

    def update_collection(self, collection: Collection) -> None:
        self.collection = collection
        self.sidebar.set_texts(collection.label, collection.entry_noun)
        self.card.set_noun(collection.entry_noun)

    def select_entity(self, entity_id: int) -> None:
        if not self.confirm_discard():
            return
        self.card.show_entity(entity_id)
        self.sidebar.set_selected(self.card.entity_id)

    def add_entity(self) -> None:
        if not self.confirm_discard():
            return
        self.card.start_new()

    def confirm_discard(self) -> bool:
        if not self.card.editing:
            return True
        return messagebox.askyesno(
            "Discard changes?", "You have unsaved changes. Discard them?", parent=self)

    def fields_changed(self) -> None:
        self.sidebar.refresh()
        if self.card.entity_id is not None and not self.card.editing:
            self.card.show_entity(self.card.entity_id)

    def _saved(self, entity_id: int) -> None:
        self.sidebar.refresh()
        self.sidebar.set_selected(entity_id)
        self._on_terms_changed()

    def _deleted(self, _entity_id: int) -> None:
        self.sidebar.set_selected(None)
        self.sidebar.refresh()
        self._on_trash_changed()
        self._on_terms_changed()

    def _duplicated(self, entity_id: int) -> None:
        self.sidebar.refresh()
        self.sidebar.set_selected(entity_id)
        self._on_terms_changed()
