import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from src.ui import theme


def _singular(label: str) -> str:
    text = label.strip()
    if text.lower().endswith("ies") and len(text) > 3:
        return text[:-3] + "y"
    if text.lower().endswith("s") and not text.lower().endswith("ss") and len(text) > 1:
        return text[:-1]
    return text


class NewTabDialog(ctk.CTkToplevel):
    def __init__(self, master, taken=()):
        super().__init__(master)
        self.result = None
        self._noun_touched = False
        self._taken = {name.strip().lower() for name in taken}

        self.title("Add Tab")
        self.resizable(False, False)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(self, text="Add a tab", font=theme.font("heading"), text_color=theme.TEXT,
                     anchor="w").pack(padx=32, pady=(26, 6), anchor="w")

        self._label("Tab name")
        self.name_entry = theme.styled_entry(self, width=436)
        self.name_entry.pack(padx=32)
        self.name_entry.bind("<KeyRelease>", self._on_name_typed)
        self.name_entry.bind("<Return>", lambda _event: self.ok())
        self.error_label = ctk.CTkLabel(self, text="", font=theme.font("note"),
                                        text_color=theme.DANGER, anchor="w")
        self.error_label.pack(padx=32, pady=(4, 0), anchor="w")

        self._label("Each entry is called")
        self.noun_entry = theme.styled_entry(self, width=436)
        self.noun_entry.pack(padx=32)
        self.noun_entry.bind("<KeyRelease>", self._mark_noun_touched)
        self.noun_entry.bind("<Return>", lambda _event: self.ok())

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=32, pady=26)
        self.add_button = theme.primary_button(row, "Add", self.ok, width=100)
        self.add_button.pack(side="left")
        theme.secondary_button(row, "Cancel", self.destroy, width=100).pack(side="left", padx=10)
        self.after(150, self._finish_setup)

    def _label(self, text):
        ctk.CTkLabel(self, text=text, font=theme.font("label"), text_color=theme.TEXT_MUTED,
                     anchor="w").pack(padx=32, pady=(14, 3), anchor="w")

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.name_entry.focus_set()
        except tk.TclError:
            pass

    def is_taken(self, label: str) -> bool:
        return label.strip().lower() in self._taken

    def _on_name_typed(self, _event=None):
        self._suggest_noun()
        label = self.name_entry.get()
        if label.strip() and self.is_taken(label):
            self.error_label.configure(text="A tab with that name already exists.")
            self.add_button.configure(state="disabled")
        else:
            self.error_label.configure(text="")
            self.add_button.configure(state="normal")

    def _suggest_noun(self, _event=None):
        if self._noun_touched:
            return
        self.noun_entry.delete(0, "end")
        self.noun_entry.insert(0, _singular(self.name_entry.get()))

    def _mark_noun_touched(self, _event=None):
        self._noun_touched = True

    def ok(self):
        label = self.name_entry.get().strip()
        noun = self.noun_entry.get().strip()
        if not label or not noun:
            messagebox.showwarning(
                "Missing information", "Please enter a tab name and what each entry is called.",
                parent=self)
            return
        if self.is_taken(label):
            self._on_name_typed()
            return
        self.result = (label, noun)
        self.destroy()


def ask_new_tab(parent, taken=()):
    dialog = NewTabDialog(parent, taken)
    parent.wait_window(dialog)
    return dialog.result
