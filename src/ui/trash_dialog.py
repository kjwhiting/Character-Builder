import tkinter as tk
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from src.services.trash_service import RETENTION_DAYS, TrashItem, TrashService
from src.ui import theme


class TrashDialog(ctk.CTkToplevel):
    def __init__(self, master, trash: TrashService, on_changed: Callable[[], None] | None = None):
        super().__init__(master)
        self._trash = trash
        self._on_changed = on_changed or (lambda: None)
        self._changed = False

        self.title("Trash")
        self.geometry("720x560")
        self.minsize(560, 420)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Trash", font=theme.font("title"), text_color=theme.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=34, pady=(28, 4))
        ctk.CTkLabel(
            self,
            text=(f"Deleted tabs and entries stay here for {RETENTION_DAYS} days. "
                  "Restore them, or delete them permanently."),
            font=theme.font("note"), text_color=theme.TEXT_MUTED, anchor="w", justify="left",
            wraplength=640,
        ).grid(row=1, column=0, sticky="ew", padx=34, pady=(0, 12))

        panel = ctk.CTkFrame(self, **theme.CARD_STYLE)
        panel.grid(row=2, column=0, sticky="nsew", padx=34, pady=4)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self._list = theme.scrollable(panel, theme.SURFACE)
        self._list.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=12)
        self._list.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=34, pady=(14, 28))
        self.empty_button = theme.secondary_button(
            footer, "Empty Trash", self.empty, width=140, danger=True)
        self.empty_button.pack(side="left")
        theme.primary_button(footer, "Close", self.close, width=120).pack(side="right")

        self._render()
        self.after(150, self._finish_setup)

    def items(self) -> list[TrashItem]:
        return self._trash.list_items()

    def restore(self, kind: str, item_id: int) -> None:
        self._trash.restore(kind, item_id)
        self._after_change()

    def delete_forever(self, kind: str, item_id: int) -> None:
        item = next((i for i in self.items() if i.kind == kind and i.id == item_id), None)
        name = item.label if item else "this item"
        confirmed = messagebox.askyesno(
            "Delete permanently?",
            f"Permanently delete \u201c{name}\u201d? This can't be undone.", parent=self)
        if not confirmed:
            return
        self._trash.delete_forever(kind, item_id)
        self._after_change()

    def empty(self) -> None:
        count = len(self.items())
        if count == 0:
            return
        noun = "item" if count == 1 else "items"
        confirmed = messagebox.askyesno(
            "Empty Trash?",
            f"Permanently delete all {count} {noun} in the Trash? This can't be undone.",
            parent=self)
        if not confirmed:
            return
        self._trash.empty_trash()
        self._after_change()

    def close(self) -> None:
        changed = self._changed
        self.destroy()
        if changed:
            self._on_changed()

    def _after_change(self) -> None:
        self._changed = True
        self._render()

    def _finish_setup(self) -> None:
        try:
            self.lift()
            self.grab_set()
        except tk.TclError:
            pass

    def _render(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        items = self.items()
        self.empty_button.configure(state="normal" if items else "disabled")
        if not items:
            ctk.CTkLabel(self._list, text="The Trash is empty.", font=theme.font("note"),
                         text_color=theme.TEXT_MUTED).grid(row=0, column=0, pady=40)
            return
        for row, item in enumerate(items):
            frame = ctk.CTkFrame(self._list, fg_color=theme.BACKGROUND, border_width=1,
                                 border_color=theme.BORDER, corner_radius=0)
            frame.grid(row=row, column=0, sticky="ew", pady=3)
            frame.grid_columnconfigure(0, weight=1)
            text = ctk.CTkFrame(frame, fg_color="transparent")
            text.grid(row=0, column=0, sticky="w", padx=14, pady=8)
            ctk.CTkLabel(text, text=item.label, font=theme.font("label"), text_color=theme.TEXT,
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(text, text=f"{item.detail}  |  deleted {item.deleted_at[:10]}",
                         font=theme.font("note"), text_color=theme.TEXT_MUTED,
                         anchor="w").pack(anchor="w")
            theme.primary_button(
                frame, "Restore", lambda i=item: self.restore(i.kind, i.id),
                width=96, height=34).grid(row=0, column=1, padx=4, pady=8)
            theme.secondary_button(
                frame, "Delete", lambda i=item: self.delete_forever(i.kind, i.id),
                width=84, height=34, danger=True).grid(row=0, column=2, padx=(4, 10), pady=8)
