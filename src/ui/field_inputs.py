import tkinter as tk

import customtkinter as ctk

from src.database.seeds import (
    FIELD_TYPE_CHECKBOX,
    FIELD_TYPE_CHOICE,
    FIELD_TYPE_LIST,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXTAREA,
)
from src.services.category_service import Field
from src.services.value_format import CHECKBOX_TRUE, split_lines
from src.ui import theme

NONE_LABEL = "(none)"
CHOICE_COLUMNS = 3


def make_tabbable(textbox) -> None:
    def forward(event):
        event.widget.tk_focusNext().focus_set()
        return "break"

    def backward(event):
        event.widget.tk_focusPrev().focus_set()
        return "break"

    textbox.bind("<Tab>", forward)
    for sequence in ("<Shift-Tab>", "<ISO_Left_Tab>"):
        try:
            textbox.bind(sequence, backward)
        except tk.TclError:
            pass


class CheckboxInput(ctk.CTkFrame):
    def __init__(self, master, value: str):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._var = tk.BooleanVar(master=self, value=(value or "").strip() == CHECKBOX_TRUE)
        self.box = ctk.CTkCheckBox(
            self, text="Yes", variable=self._var, font=theme.font("body"),
            text_color=theme.TEXT, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            border_color=theme.INPUT_BORDER, checkmark_color=theme.TEXT_ON_ACCENT)
        self.box.pack(anchor="w")

    def set_checked(self, checked: bool) -> None:
        self._var.set(checked)

    def get(self) -> str:
        return CHECKBOX_TRUE if self._var.get() else ""


class NumberInput(ctk.CTkFrame):
    def __init__(self, master, value: str, unit: str):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.entry = theme.styled_entry(self, width=160)
        self.entry.insert(0, value)
        self.entry.pack(side="left")
        if unit:
            ctk.CTkLabel(self, text=unit, font=theme.font("body"),
                         text_color=theme.TEXT_MUTED).pack(side="left", padx=(10, 0))

    def get(self) -> str:
        return self.entry.get().strip()


class ChoiceInput(ctk.CTkFrame):
    def __init__(self, master, value: str, choices: list[str]):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        shown = [NONE_LABEL] + list(choices)
        if value and value not in choices:
            shown.append(value)
        self.combo = theme.styled_combo(self, shown, width=280)
        self.combo.set(value if value else NONE_LABEL)
        self.combo.pack(anchor="w")

    def set_value(self, value: str) -> None:
        self.combo.set(value if value else NONE_LABEL)

    def get(self) -> str:
        current = self.combo.get()
        return "" if current == NONE_LABEL else current


class MultiChoiceInput(ctk.CTkFrame):
    def __init__(self, master, value: str, choices: list[str]):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        selected = split_lines(value)
        options = list(choices) + [item for item in selected if item not in choices]
        self._vars: dict[str, tk.BooleanVar] = {}
        if not options:
            ctk.CTkLabel(self, text="No options yet. Add them in Adjust Fields.",
                         font=theme.font("note"), text_color=theme.TEXT_MUTED).pack(anchor="w")
            return
        for index, option in enumerate(options):
            var = tk.BooleanVar(master=self, value=option in selected)
            self._vars[option] = var
            ctk.CTkCheckBox(
                self, text=option, variable=var, font=theme.font("body"),
                text_color=theme.TEXT, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                border_color=theme.INPUT_BORDER, checkmark_color=theme.TEXT_ON_ACCENT,
            ).grid(row=index // CHOICE_COLUMNS, column=index % CHOICE_COLUMNS,
                   sticky="w", padx=(0, 22), pady=3)

    def set_selected(self, values: list[str]) -> None:
        for option, var in self._vars.items():
            var.set(option in values)

    def get(self) -> str:
        return "\n".join(option for option, var in self._vars.items() if var.get())


def build_input(parent, field: Field, value: str):
    value = value or ""
    options = field.options or {}
    if field.field_type in (FIELD_TYPE_TEXTAREA, FIELD_TYPE_LIST):
        widget = theme.styled_textbox(
            parent, height=130 if field.field_type == FIELD_TYPE_TEXTAREA else 96)
        widget.insert("1.0", value)
        make_tabbable(widget)
        return widget
    if field.field_type == FIELD_TYPE_NUMBER:
        return NumberInput(parent, value, options.get("unit", ""))
    if field.field_type == FIELD_TYPE_CHOICE:
        return ChoiceInput(parent, value, options.get("choices", []))
    if field.field_type == FIELD_TYPE_MULTICHOICE:
        return MultiChoiceInput(parent, value, options.get("choices", []))
    if field.field_type == FIELD_TYPE_CHECKBOX:
        return CheckboxInput(parent, value)
    widget = theme.styled_entry(parent)
    widget.insert(0, value)
    return widget


def read_input(widget) -> str:
    if isinstance(widget, ctk.CTkTextbox):
        return widget.get("1.0", "end-1c")
    return widget.get()


def field_hint(field: Field) -> str:
    if field.field_type == FIELD_TYPE_LIST:
        return "  (one per line)"
    if field.field_type == FIELD_TYPE_MULTICHOICE:
        return "  (choose any)"
    return ""
