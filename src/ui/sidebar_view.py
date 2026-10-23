import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.services.category_service import CategoryService
from src.services.entity_service import Entity, EntityService
from src.ui import theme

ALL_ENTRIES_LABEL = "All entries"
TYPE_GLYPHS = {"Character": "\u2694", "Place": "\u2302"}
DEFAULT_GLYPH = "\u2022"


def missing_filter_label(field) -> str:
    return f"Missing: {field.category} / {field.name}"


class SidebarView(ctk.CTkFrame):
    def __init__(self, master, entities: EntityService, categories: CategoryService,
                 noun: str, profile_name: str, on_select: Callable[[int], None],
                 on_add: Callable[[], None], title: str = "Character Builder"):
        super().__init__(master, width=320, corner_radius=0, fg_color=theme.SIDEBAR_BG)
        self._entities = entities
        self._categories = categories
        self._on_select = on_select
        self._on_add = on_add
        self._filters: dict[str, int | None] = {ALL_ENTRIES_LABEL: None}
        self._filter_label = ALL_ENTRIES_LABEL
        self._selected_id: int | None = None
        self._buttons: dict[int, ctk.CTkButton] = {}

        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(self, text=title, font=theme.font("heading"), text_color=theme.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=24, pady=(30, 0))
        self._profile_label = ctk.CTkLabel(
            self, text=profile_name, font=theme.font("note"), text_color=theme.TEXT_MUTED,
            anchor="w")
        self._profile_label.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        theme.ornament(self).grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))

        self._search_var = tk.StringVar(master=self)
        self._search_var.trace_add("write", lambda *_args: self._render_list())
        self.search_entry = theme.styled_entry(
            self, height=40, textvariable=self._search_var, placeholder_text="Search...")
        self.search_entry.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.search_entry.bind("<Return>", lambda _event: self.open_first_match())

        self.filter_combo = theme.styled_combo(
            self, [ALL_ENTRIES_LABEL], height=36, command=self.select_filter)
        self.filter_combo.set(ALL_ENTRIES_LABEL)
        self.filter_combo.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 10))

        self.add_button = theme.primary_button(self, f"Add {noun}", self._on_add, height=40)
        self.add_button.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 14))

        self._list_frame = theme.scrollable(self, "transparent")
        self._list_frame.grid(row=6, column=0, sticky="nsew", padx=(14, 6), pady=(0, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

        self.refresh()

    @property
    def selected_id(self) -> int | None:
        return self._selected_id

    @property
    def filter_labels(self) -> list[str]:
        return list(self._filters)

    @property
    def entity_buttons(self) -> dict[int, ctk.CTkButton]:
        return dict(self._buttons)

    def set_profile(self, noun: str, profile_name: str) -> None:
        self.add_button.configure(text=f"Add {noun}")
        self._profile_label.configure(text=profile_name)

    def set_search_text(self, text: str) -> None:
        self._search_var.set(text)

    def select_filter(self, label: str) -> None:
        if label not in self._filters:
            label = ALL_ENTRIES_LABEL
        self._filter_label = label
        self.filter_combo.set(label)
        self._render_list()

    def set_selected(self, entity_id: int | None) -> None:
        self._selected_id = entity_id
        self._highlight()

    def refresh(self) -> None:
        self._reload_filters()
        self._render_list()

    def visible_entities(self) -> list[Entity]:
        found = self._entities.search_entities(self._search_var.get())
        missing_field_id = self._filters.get(self._filter_label)
        if missing_field_id is None:
            return found
        missing = {e.id for e in self._entities.get_entities_missing_field(missing_field_id)}
        return [entity for entity in found if entity.id in missing]

    def open_first_match(self) -> str:
        matches = self.visible_entities()
        if matches:
            self._on_select(matches[0].id)
        return "break"

    def _reload_filters(self) -> None:
        self._filters = {ALL_ENTRIES_LABEL: None}
        for field in self._categories.list_fields():
            self._filters[missing_filter_label(field)] = field.id
        if self._filter_label not in self._filters:
            self._filter_label = ALL_ENTRIES_LABEL
        self.filter_combo.configure(values=list(self._filters))
        self.filter_combo.set(self._filter_label)

    def _render_list(self) -> None:
        for child in self._list_frame.winfo_children():
            child.destroy()
        self._buttons = {}

        entities = self.visible_entities()
        if not entities:
            filtering = bool(self._search_var.get().strip()) or self._filter_label != ALL_ENTRIES_LABEL
            ctk.CTkLabel(
                self._list_frame, text="No matches." if filtering else "Nothing here yet.",
                font=theme.font("note"), text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, pady=24)
            return

        for row, entity in enumerate(entities):
            glyph = TYPE_GLYPHS.get(entity.type, DEFAULT_GLYPH)
            button = ctk.CTkButton(
                self._list_frame, text=f"{glyph}  {entity.name}", anchor="w", height=38,
                fg_color="transparent", text_color=theme.TEXT, hover_color=theme.HOVER_BG,
                font=theme.font("body"), corner_radius=4,
                command=lambda entity_id=entity.id: self._on_select(entity_id),
            )
            button.grid(row=row, column=0, sticky="ew", pady=1, padx=2)
            theme.make_focusable(button)
            self._buttons[entity.id] = button
        self._highlight()

    def _highlight(self) -> None:
        for entity_id, button in self._buttons.items():
            try:
                if entity_id == self._selected_id:
                    button.configure(fg_color=theme.SELECTION_BG, hover_color=theme.SELECTION_BG)
                else:
                    button.configure(fg_color="transparent", hover_color=theme.HOVER_BG)
            except tk.TclError:
                pass
