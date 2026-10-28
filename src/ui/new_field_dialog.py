import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from src.services.category_service import CategoryService
from src.ui import theme
from src.ui.adjust_fields_view import FIELD_TYPE_LABELS, TYPE_FROM_LABEL

NEW_SECTION_LABEL = "+ New section..."


class NewFieldDialog(ctk.CTkToplevel):
    def __init__(self, master, categories: CategoryService):
        super().__init__(master)
        self.result = None
        self._categories = categories
        self._sections = categories.list_categories()

        self.title("Add Field")
        self.resizable(False, False)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=32, pady=22)
        self.add_button = theme.primary_button(row, "Add", self.ok, width=100)
        self.add_button.pack(side="left")
        theme.secondary_button(row, "Cancel", self.destroy, width=100).pack(side="left", padx=10)

        ctk.CTkLabel(self, text="Add a field", font=theme.font("heading"),
                     text_color=theme.TEXT, anchor="w").pack(padx=32, pady=(26, 2), anchor="w")
        ctk.CTkLabel(
            self, text="The field is added to every entry in this tab.",
            font=theme.font("note"), text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(padx=32, anchor="w")

        self._label("Section")
        self.section_box = theme.styled_combo(
            self, self._sections + [NEW_SECTION_LABEL], width=436, command=self._on_section)
        self.section_box.set(self._sections[-1] if self._sections else NEW_SECTION_LABEL)
        self.section_box.pack(padx=32)

        self.new_section_holder = ctk.CTkFrame(self, fg_color="transparent", height=0)
        self.new_section_holder.pack(fill="x", padx=32)
        self.new_section_label = ctk.CTkLabel(
            self.new_section_holder, text="New section name", font=theme.font("label"),
            text_color=theme.TEXT_MUTED, anchor="w")
        self.new_section_entry = theme.styled_entry(self.new_section_holder, width=436)
        self.new_section_entry.bind("<KeyRelease>", lambda _event: self._check())

        self._label("Field name")
        self.name_entry = theme.styled_entry(self, width=436)
        self.name_entry.pack(padx=32)
        self.name_entry.bind("<KeyRelease>", lambda _event: self._check())
        self.name_entry.bind("<Return>", lambda _event: self.ok())
        self.error_label = ctk.CTkLabel(self, text="", font=theme.font("note"),
                                        text_color=theme.DANGER, anchor="w")
        self.error_label.pack(padx=32, pady=(4, 0), anchor="w")

        self._label("Type")
        self.type_box = theme.styled_combo(
            self, list(FIELD_TYPE_LABELS.values()), width=436, command=self._on_type)
        self.type_box.set(FIELD_TYPE_LABELS["text"])
        self.type_box.pack(padx=32)

        self.options_holder = ctk.CTkFrame(self, fg_color="transparent", height=0)
        self.options_holder.pack(fill="x", padx=32)
        self.options_label = ctk.CTkLabel(
            self.options_holder, text="", font=theme.font("label"),
            text_color=theme.TEXT_MUTED, anchor="w")
        self.choices_box = theme.styled_textbox(self.options_holder, height=110, width=436)
        self.unit_entry = theme.styled_entry(self.options_holder, width=436,
                                             placeholder_text="cm, kg, years")

        if not self._sections:
            self.new_section_entry.insert(0, "Details")
        self._on_section(self.section_box.get())
        self._on_type(self.type_box.get())
        self.after(150, self._finish_setup)

    def _label(self, text):
        label = ctk.CTkLabel(self, text=text, font=theme.font("label"),
                             text_color=theme.TEXT_MUTED, anchor="w")
        label.pack(padx=32, pady=(14, 3), anchor="w")
        return label

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.name_entry.focus_set()
        except tk.TclError:
            pass

    @property
    def is_new_section(self) -> bool:
        return self.section_box.get() == NEW_SECTION_LABEL

    def _on_section(self, _value=None):
        if self.is_new_section:
            self.new_section_label.pack(pady=(14, 3), anchor="w")
            self.new_section_entry.pack()
        else:
            self.new_section_label.pack_forget()
            self.new_section_entry.pack_forget()
        self._check()

    def _on_type(self, _value=None):
        field_type = TYPE_FROM_LABEL[self.type_box.get()]
        for widget in (self.options_label, self.choices_box, self.unit_entry):
            widget.pack_forget()
        if field_type in ("choice", "multichoice"):
            self.options_label.configure(text="Choices, one per line")
            self.options_label.pack(pady=(14, 3), anchor="w")
            self.choices_box.pack()
        elif field_type == "number":
            self.options_label.configure(text="Unit shown after the number (optional)")
            self.options_label.pack(pady=(14, 3), anchor="w")
            self.unit_entry.pack()

    def _taken_names(self):
        if self.is_new_section:
            return set()
        return {f.name.lower() for f in self._categories.list_fields(self.section_box.get())}

    def _problem(self):
        name = self.name_entry.get().strip()
        if self.is_new_section:
            section = self.new_section_entry.get().strip()
            if section and section.lower() in {s.lower() for s in self._sections}:
                return "A section with that name already exists."
        if name and name.lower() in self._taken_names():
            return "That section already has a field with this name."
        return ""

    def _check(self):
        problem = self._problem()
        self.error_label.configure(text=problem)
        self.add_button.configure(state="disabled" if problem else "normal")

    def ok(self):
        name = self.name_entry.get().strip()
        section = (self.new_section_entry.get().strip() if self.is_new_section
                   else self.section_box.get())
        if not name or not section:
            messagebox.showwarning(
                "Missing information", "Please enter a section and a field name.", parent=self)
            return
        if self._problem():
            self._check()
            return
        field_type = TYPE_FROM_LABEL[self.type_box.get()]
        options = {}
        if field_type in ("choice", "multichoice"):
            options = {"choices": self.choices_box.get("1.0", "end-1c").splitlines()}
        elif field_type == "number":
            options = {"unit": self.unit_entry.get().strip()}
        self.result = {
            "category": section, "new_category": self.is_new_section,
            "name": name, "type": field_type, "options": options,
        }
        self.destroy()


def ask_new_field(parent, categories: CategoryService):
    dialog = NewFieldDialog(parent, categories)
    parent.wait_window(dialog)
    return dialog.result
