import tkinter as tk
from typing import Callable

import customtkinter as ctk

from src.services.collection_service import Collection
from src.ui import colors, scrolling, theme


class TabBar(ctk.CTkFrame):
    def __init__(self, master, on_select: Callable[[int], None], on_add: Callable[[], None],
                 on_rename: Callable[[int], None], on_adjust: Callable[[int], None],
                 on_delete: Callable[[int], None], on_trash: Callable[[], None],
                 on_color: Callable[[int], None]):
        super().__init__(master, corner_radius=0, fg_color=theme.SIDEBAR_BG, height=48)
        self._on_select = on_select
        self._on_add = on_add
        self._on_rename = on_rename
        self._on_adjust = on_adjust
        self._on_delete = on_delete
        self._on_trash = on_trash
        self._on_color = on_color
        self._tabs: dict[int, ctk.CTkButton] = {}
        self._active_id: int | None = None
        self._order: list[int] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)

        self._strip = scrolling.SmoothScrollableFrame(
            self, orientation="horizontal", fg_color="transparent", height=40,
            corner_radius=0, scrollbar_fg_color=theme.SIDEBAR_BG,
            scrollbar_button_color=theme.INPUT_BORDER, scrollbar_button_hover_color=theme.GOLD)
        self._strip.grid(row=0, column=0, sticky="ew", padx=(14, 4), pady=(6, 3))
        self.search_entry = theme.styled_entry(
            self, width=250, height=34, placeholder_text="Search all tabs (Ctrl+K)")
        self.search_entry.grid(row=0, column=1, padx=(8, 10), pady=(6, 3))
        self.add_button = theme.secondary_button(self, "+", self._on_add, width=40, height=34)
        self.add_button.grid(row=0, column=2, padx=(0, 10), pady=(6, 3))
        self.trash_button = theme.secondary_button(
            self, "Trash", self._on_trash, width=100, height=34)
        self.trash_button.grid(row=0, column=3, padx=(0, 14), pady=(6, 3))
        self.trash_button.grid_remove()
        self._strip.bind("<Configure>", lambda _event: self.after_idle(self._update_scrollbar))

        self._menu = tk.Menu(self, tearoff=False)

    def _update_scrollbar(self) -> None:
        try:
            canvas = self._strip._parent_canvas
            bounds = canvas.bbox("all")
            overflow = bounds is not None and (bounds[2] - bounds[0]) > canvas.winfo_width() + 2
            if overflow:
                self._strip._scrollbar.grid()
            else:
                self._strip._scrollbar.grid_remove()
        except (AttributeError, tk.TclError):
            pass

    @property
    def active_id(self) -> int | None:
        return self._active_id

    @property
    def tab_buttons(self) -> dict[int, ctk.CTkButton]:
        return dict(self._tabs)

    @property
    def tab_order(self) -> list[int]:
        return list(self._order)

    def set_tabs(self, collections: list[Collection], active_id: int | None) -> None:
        for child in self._strip.winfo_children():
            child.destroy()
        self._tabs = {}
        self._order = [c.id for c in collections]
        for column, collection in enumerate(collections):
            width = theme.font("label").measure(collection.label) + 40
            cell = ctk.CTkFrame(self._strip, fg_color="transparent", corner_radius=0)
            cell.grid(row=0, column=column, padx=2)
            tk.Frame(cell, height=3, bd=0, highlightthickness=0,
                     bg=colors.readable_on(collection.color, theme.SIDEBAR_BG, 3.0)).grid(
                row=1, column=0, sticky="ew", padx=6)
            button = ctk.CTkButton(
                cell, text=collection.label, height=34, width=width, corner_radius=4,
                fg_color="transparent", text_color=theme.TEXT_MUTED,
                hover_color=theme.HOVER_BG, font=theme.font("body"),
                command=lambda cid=collection.id: self._on_select(cid))
            button.grid(row=0, column=0)
            for sequence in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
                button.bind(sequence, self._popup_handler(collection.id))
            theme.make_focusable(button)
            self._tabs[collection.id] = button
        self.set_active(active_id)
        self.after_idle(self._update_scrollbar)

    def set_trash_count(self, count: int) -> None:
        if count > 0:
            self.trash_button.configure(text=f"Trash ({count})")
            self.trash_button.grid()
        else:
            self.trash_button.grid_remove()

    def set_active(self, collection_id: int | None) -> None:
        self._active_id = collection_id
        for cid, button in self._tabs.items():
            try:
                if cid == collection_id:
                    button.configure(fg_color=theme.BACKGROUND, text_color=theme.TEXT,
                                     hover_color=theme.BACKGROUND, font=theme.font("label"))
                else:
                    button.configure(fg_color="transparent", text_color=theme.TEXT_MUTED,
                                     hover_color=theme.HOVER_BG, font=theme.font("body"))
            except tk.TclError:
                pass

    def style_menu(self) -> None:
        self._menu.configure(
            tearoff=False, bg=theme.SURFACE, fg=theme.TEXT, activebackground=theme.SELECTION_BG,
            activeforeground=theme.TEXT, font=(theme.FONT_FAMILY, 12))

    def build_menu(self, collection_id: int) -> tk.Menu:
        self._menu.delete(0, "end")
        self.style_menu()
        self._menu.add_command(label="Rename...", command=lambda: self._on_rename(collection_id))
        self._menu.add_command(
            label="Adjust Fields...", command=lambda: self._on_adjust(collection_id))
        self._menu.add_command(
            label="Highlight Colour...", command=lambda: self._on_color(collection_id))
        self._menu.add_separator()
        self._menu.add_command(label="Delete Tab...", command=lambda: self._on_delete(collection_id))
        return self._menu

    def _popup_handler(self, collection_id):
        def handler(event=None):
            if event is None:
                return None
            return self._popup(event, collection_id)

        return handler

    def _popup(self, event, collection_id):
        menu = self.build_menu(collection_id)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
