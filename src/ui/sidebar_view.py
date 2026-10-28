import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.services.entity_service import Entity, EntityService
from src.ui import theme


class SidebarView(ctk.CTkFrame):
    def __init__(self, master, entities: EntityService, noun: str,
                 on_select: Callable[[int], None], on_add: Callable[[], None],
                 on_counts_changed: Callable[[int, int], None] | None = None):
        super().__init__(master, width=290, corner_radius=0, fg_color=theme.SIDEBAR_BG)
        self._entities = entities
        self._on_select = on_select
        self._on_add = on_add
        self._on_counts_changed = on_counts_changed or (lambda shown, total: None)
        self._selected_id: int | None = None
        self._buttons: dict[int, ctk.CTkButton] = {}
        self.shown_count = 0
        self.total_count = 0

        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.search_entry = theme.styled_entry(self, height=36, placeholder_text="Search...")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        self.search_entry.bind("<Return>", lambda _event: self.open_first_match())
        for sequence in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
            self.search_entry.bind(sequence, lambda _event: self.after_idle(self._render_list))

        self.add_button = theme.primary_button(self, f"Add {noun}", self._on_add, height=36)
        self.add_button.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._list_frame = theme.scrollable(self, "transparent")
        self._list_frame.grid(row=2, column=0, sticky="nsew", padx=(10, 4), pady=(0, 8))
        self._list_frame.grid_columnconfigure(0, weight=1)

        self.refresh()

    @property
    def selected_id(self) -> int | None:
        return self._selected_id

    @property
    def entity_buttons(self) -> dict[int, ctk.CTkButton]:
        return dict(self._buttons)

    def set_noun(self, noun: str) -> None:
        self.add_button.configure(text=f"Add {noun}")

    def set_search_text(self, text: str) -> None:
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, text)
        self._render_list()

    def set_selected(self, entity_id: int | None) -> None:
        self._selected_id = entity_id
        self._highlight()

    def refresh(self) -> None:
        self._render_list()

    def visible_entities(self) -> list[Entity]:
        return self._entities.search_entities(self.search_entry.get())

    def open_first_match(self) -> str:
        matches = self.visible_entities()
        if matches:
            self._on_select(matches[0].id)
        return "break"

    def _render_list(self) -> None:
        for child in self._list_frame.winfo_children():
            child.destroy()
        self._buttons = {}

        self.total_count = len(self._entities.list_entities())
        entities = self.visible_entities()
        self.shown_count = len(entities)
        self._on_counts_changed(self.shown_count, self.total_count)
        if not entities:
            searching = bool(self.search_entry.get().strip())
            ctk.CTkLabel(
                self._list_frame, text="No matches." if searching else "Nothing here yet.",
                font=theme.font("note"), text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, pady=24)
            return

        for row, entity in enumerate(entities):
            button = ctk.CTkButton(
                self._list_frame, text=entity.name, anchor="w", height=34,
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
                    button.configure(fg_color=theme.SELECTION_BG, hover_color=theme.SELECTION_BG,
                                     font=theme.font("label"))
                else:
                    button.configure(fg_color="transparent", hover_color=theme.HOVER_BG,
                                     font=theme.font("body"))
            except tk.TclError:
                pass
