import tkinter as tk

import customtkinter as ctk

from src.ui import theme


def entry_summary(label: str, shown: int, total: int) -> str:
    noun = "entry" if total == 1 else "entries"
    if shown != total:
        return f"{label}: {shown} of {total} {noun}"
    return f"{label}: {total} {noun}"


class StatusBar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=0, fg_color=theme.SIDEBAR_BG, height=30)
        self.grid_columnconfigure(1, weight=1)
        self.grid_propagate(False)
        tk.Frame(self, height=1, bd=0, highlightthickness=0, bg=theme.BORDER).grid(
            row=0, column=0, columnspan=3, sticky="ew")
        self._summary = ctk.CTkLabel(
            self, text="", font=theme.font("small"), text_color=theme.TEXT_MUTED, anchor="w")
        self._summary.grid(row=1, column=0, sticky="w", padx=(16, 8), pady=(3, 3))
        self.right_area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, height=22)
        self.right_area.grid(row=1, column=2, sticky="e", padx=(8, 16))

    @property
    def summary_text(self) -> str:
        return self._summary.cget("text")

    def show_entries(self, label: str | None, shown: int = 0, total: int = 0) -> None:
        self._summary.configure(text="" if label is None else entry_summary(label, shown, total))
