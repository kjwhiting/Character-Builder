import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.services.term_index import Term, TermIndex
from src.ui import colors, theme

MAX_RESULTS = 8
DEBOUNCE_MS = 90
HIDE_DELAY_MS = 180


class GlobalSearch:
    def __init__(self, window, entry, get_index: Callable[[], TermIndex | None],
                 on_open: Callable[[int, int], None]):
        self._window = window
        self._entry = entry
        self._get_index = get_index
        self._on_open = on_open
        self._results: list[Term] = []
        self._rows: list[ctk.CTkFrame] = []
        self._selected = 0
        self._pending = None
        self._hide_job = None
        self._overlay = None

        entry.bind("<KeyRelease>", self._on_key)
        entry.bind("<Down>", lambda _event: self._move(1))
        entry.bind("<Up>", lambda _event: self._move(-1))
        entry.bind("<Return>", lambda _event: self.open_selected())
        entry.bind("<Escape>", lambda _event: self._dismiss())
        entry.bind("<FocusOut>", lambda _event: self._schedule_hide())
        entry.bind("<FocusIn>", lambda _event: self._cancel_hide())

    @property
    def results(self) -> list[Term]:
        return list(self._results)

    @property
    def visible(self) -> bool:
        return self._overlay is not None

    def focus(self) -> None:
        self._entry.focus_set()
        self._entry.select_range(0, "end")

    def set_query(self, text: str) -> None:
        self._entry.delete(0, "end")
        self._entry.insert(0, text)
        self.update_results()

    def update_results(self) -> None:
        query = self._entry.get().strip()
        index = self._get_index()
        if not query or index is None:
            self.hide()
            return
        self._results = index.search(query, MAX_RESULTS)
        self._selected = 0
        self._render(query)

    def open_selected(self) -> str:
        if self._results:
            self.choose(self._results[self._selected])
        return "break"

    def choose(self, term: Term) -> None:
        self._entry.delete(0, "end")
        self.hide()
        self._on_open(term.collection_id, term.entry_id)

    def hide(self) -> None:
        self._cancel_hide()
        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
        self._overlay = None
        self._rows = []
        self._results = []

    def _dismiss(self):
        self._entry.delete(0, "end")
        self.hide()
        return "break"

    def _on_key(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return
        if self._pending is not None:
            self._window.after_cancel(self._pending)
        self._pending = self._window.after(DEBOUNCE_MS, self.update_results)

    def _schedule_hide(self):
        self._cancel_hide()
        self._hide_job = self._window.after(HIDE_DELAY_MS, self.hide)

    def _cancel_hide(self):
        if self._hide_job is not None:
            try:
                self._window.after_cancel(self._hide_job)
            except tk.TclError:
                pass
            self._hide_job = None

    def _move(self, step):
        if not self._results:
            return "break"
        self._selected = (self._selected + step) % len(self._results)
        self._highlight()
        return "break"

    def _highlight(self):
        for index, row in enumerate(self._rows):
            try:
                row.configure(
                    fg_color=theme.SELECTION_BG if index == self._selected else "transparent")
            except tk.TclError:
                pass

    def _render(self, query):
        if self._overlay is not None:
            self._overlay.destroy()
        self._rows = []
        width = max(self._entry.winfo_width(), 340)
        x = self._entry.winfo_rootx() - self._window.winfo_rootx()
        x = max(8, min(x, self._window.winfo_width() - width - 8))
        y = self._entry.winfo_rooty() - self._window.winfo_rooty() + self._entry.winfo_height() + 4
        self._overlay = ctk.CTkFrame(
            self._window, fg_color=theme.SURFACE, border_width=1, border_color=theme.GOLD,
            corner_radius=6, width=width)
        self._overlay.place(x=x, y=y)
        self._overlay.lift()
        if not self._results:
            ctk.CTkLabel(self._overlay, text="No matches.", font=theme.font("note"),
                         text_color=theme.TEXT_MUTED).pack(padx=16, pady=14)
            return
        for index, term in enumerate(self._results):
            self._rows.append(self._build_row(term, width))
        self._highlight()

    def _build_row(self, term: Term, width):
        row = ctk.CTkFrame(self._overlay, fg_color="transparent", corner_radius=4, height=40)
        row.pack(fill="x", padx=6, pady=2)
        dot = colors.readable_on(term.color, theme.SURFACE, 3.0)
        ctk.CTkLabel(row, text="\u25CF", font=theme.font("small"), text_color=dot,
                     width=18).pack(side="left", padx=(8, 4), pady=8)
        shown = term.text if term.kind == "name" else f"{term.text}  ({term.entry_name})"
        name = ctk.CTkLabel(row, text=shown, font=theme.font("body"), text_color=theme.TEXT,
                            anchor="w")
        name.pack(side="left", pady=8)
        detail = ctk.CTkLabel(row, text=term.collection_label, font=theme.font("note"),
                              text_color=theme.TEXT_MUTED, anchor="e")
        detail.pack(side="right", padx=(12, 10), pady=8)
        for widget in (row, name, detail):
            widget.bind("<Button-1>", lambda _event, t=term: self.choose(t))
            widget.configure(cursor="hand2")
        return row
