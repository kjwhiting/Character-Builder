import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.services.entity_service import Entity, EntityService
from src.ui import theme


class SidebarView(ctk.CTkFrame):
    def __init__(self, master, entities: EntityService, title: str, noun: str,
                 on_select: Callable[[int], None], on_add: Callable[[], None]):
        super().__init__(master, width=320, corner_radius=0, fg_color=theme.SIDEBAR_BG)
        self._entities = entities
        self._on_select = on_select
        self._on_add = on_add
        self._selected_id: int | None = None
        self._buttons: dict[int, ctk.CTkButton] = {}

        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        self._title_label = ctk.CTkLabel(
            self, text=title, font=theme.font("heading"), text_color=theme.TEXT, anchor="w")
        self._title_label.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 0))
        self._count_label = ctk.CTkLabel(
            self, text="", font=theme.font("note"), text_color=theme.TEXT_MUTED, anchor="w")
        self._count_label.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        theme.ornament(self).grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))

        self.search_entry = theme.styled_entry(self, height=40, placeholder_text="Search...")
        self.search_entry.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.search_entry.bind("<Return>", lambda _event: self.open_first_match())
        for sequence in ("<KeyRelease>", "<<Paste>>", "<<Cut>>"):
            self.search_entry.bind(sequence, lambda _event: self.after_idle(self._render_list))

        self.add_button = theme.primary_button(self, f"Add {noun}", self._on_add, height=40)
        self.add_button.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 14))

        self._list_frame = theme.scrollable(self, "transparent")
        self._list_frame.grid(row=5, column=0, sticky="nsew", padx=(14, 6), pady=(0, 16))
        self._list_frame.grid_columnconfigure(0, weight=1)

        self.refresh()

    @property
    def selected_id(self) -> int | None:
        return self._selected_id

    @property
    def entity_buttons(self) -> dict[int, ctk.CTkButton]:
        return dict(self._buttons)

    def set_texts(self, title: str, noun: str) -> None:
        self._title_label.configure(text=title)
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

        total = len(self._entities.list_entities())
        self._count_label.configure(text=f"{total} {'entry' if total == 1 else 'entries'}")
        entities = self.visible_entities()
        if not entities:
            searching = bool(self.search_entry.get().strip())
            ctk.CTkLabel(
                self._list_frame, text="No matches." if searching else "Nothing here yet.",
                font=theme.font("note"), text_color=theme.TEXT_MUTED,
            ).grid(row=0, column=0, pady=24)
            return

        for row, entity in enumerate(entities):
            button = ctk.CTkButton(
                self._list_frame, text=entity.name, anchor="w", height=38,
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
