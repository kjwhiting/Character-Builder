import tkinter as tk
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from src.services.category_service import CategoryService, Field
from src.services.errors import ServiceError
from src.ui import theme
from src.ui.field_layout import ALWAYS_FULL_TYPES


FIELD_TYPE_LABELS = {
    "text": "Text",
    "textarea": "Paragraph",
    "list": "List",
    "choice": "Choice",
    "multichoice": "Multi-choice",
    "checkbox": "Checkbox",
    "number": "Number",
}
TYPE_FROM_LABEL = {label: key for key, label in FIELD_TYPE_LABELS.items()}


def options_summary(field: Field) -> str:
    if field.field_type in ("choice", "multichoice"):
        count = len(field.options.get("choices", []))
        return f"Options ({count})" if count else "Add options"
    if field.field_type == "number":
        unit = field.options.get("unit", "")
        return f"Unit: {unit}" if unit else "Set unit"
    return ""


def find_drop_target(y, blocks):
    for block_index, block in enumerate(blocks):
        if y < block["header_bottom"]:
            return block_index, 0
        rows = block["rows"]
        if not rows:
            if y < block["end"]:
                return block_index, 0
            continue
        for row_index, (top, bottom) in enumerate(rows):
            if y < (top + bottom) / 2:
                return block_index, row_index
        if y < block["end"]:
            return block_index, len(rows)
    if not blocks:
        return None
    return len(blocks) - 1, len(blocks[-1]["rows"])


def drop_line_y(target, blocks):
    block_index, row_index = target
    block = blocks[block_index]
    if row_index < len(block["rows"]):
        return block["rows"][row_index][0]
    if block["rows"]:
        return block["rows"][-1][1]
    return block["header_bottom"]


class NameDialog(ctk.CTkToplevel):
    def __init__(self, master, title, prompt, initial="", taken=()):
        super().__init__(master)
        self.result = None
        self._taken = {name.strip().lower() for name in taken}
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(self, text=prompt, font=theme.font("subheading"), text_color=theme.TEXT,
                     anchor="w").pack(padx=32, pady=(30, 10), anchor="w")
        self.entry = theme.styled_entry(self, width=396)
        self.entry.pack(padx=32)
        if initial:
            self.entry.insert(0, initial)
        self.entry.bind("<Return>", lambda _event: self.ok())
        self.entry.bind("<KeyRelease>", lambda _event: self._check())
        self.error_label = ctk.CTkLabel(self, text="", font=theme.font("note"),
                                        text_color=theme.DANGER, anchor="w")
        self.error_label.pack(padx=32, pady=(6, 0), anchor="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=32, pady=18)
        self.ok_button = theme.primary_button(row, "OK", self.ok, width=100)
        self.ok_button.pack(side="left")
        theme.secondary_button(row, "Cancel", self.destroy, width=100).pack(side="left", padx=10)
        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.entry.focus_set()
        except tk.TclError:
            pass

    def is_taken(self, value: str) -> bool:
        return value.strip().lower() in self._taken

    def _check(self):
        value = self.entry.get()
        if value.strip() and self.is_taken(value):
            self.error_label.configure(text="That name is already in use.")
            self.ok_button.configure(state="disabled")
        else:
            self.error_label.configure(text="")
            self.ok_button.configure(state="normal")

    def ok(self):
        value = self.entry.get().strip()
        if not value:
            messagebox.showwarning("Name required", "Please enter a name.", parent=self)
            return
        if self.is_taken(value):
            self._check()
            return
        self.result = value
        self.destroy()


def ask_name(parent, title, prompt, initial="", taken=()):
    dialog = NameDialog(parent, title, prompt, initial, taken)
    parent.wait_window(dialog)
    return dialog.result


class FieldOptionsDialog(ctk.CTkToplevel):
    def __init__(self, master, field: Field):
        super().__init__(master)
        self.result = None
        self._field = field
        self._is_number = field.field_type == "number"
        self.title(f"Options: {field.name}")
        self.resizable(False, False)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        prompt = ("Unit shown after the number (optional)" if self._is_number
                  else "Choices, one per line")
        ctk.CTkLabel(self, text=prompt, font=theme.font("subheading"), text_color=theme.TEXT,
                     anchor="w").pack(padx=32, pady=(28, 10), anchor="w")
        if self._is_number:
            self.input = theme.styled_entry(self, width=396, placeholder_text="cm, kg, years")
            self.input.insert(0, field.options.get("unit", ""))
        else:
            self.input = theme.styled_textbox(self, height=220, width=396)
            self.input.insert("1.0", "\n".join(field.options.get("choices", [])))
        self.input.pack(padx=32)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=32, pady=20)
        theme.primary_button(row, "Save", self.save, width=100).pack(side="left")
        theme.secondary_button(row, "Cancel", self.destroy, width=100).pack(side="left", padx=10)
        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.input.focus_set()
        except tk.TclError:
            pass

    def save(self):
        if self._is_number:
            self.result = {"unit": self.input.get().strip()}
        else:
            self.result = {"choices": self.input.get("1.0", "end-1c").splitlines()}
        self.destroy()


def ask_field_options(parent, field: Field):
    dialog = FieldOptionsDialog(parent, field)
    parent.wait_window(dialog)
    return dialog.result


class AdjustFieldsView(ctk.CTkToplevel):
    TYPE_WIDTH = 150
    OPTIONS_WIDTH = 120
    DISPLAY_WIDTH = 90
    DELETE_WIDTH = 84

    def __init__(self, master, categories: CategoryService,
                 on_changed: Callable[[], None] | None = None, heading: str = "Adjust Fields"):
        super().__init__(master)
        self._categories = categories
        self._on_changed = on_changed or (lambda: None)
        self._layout: list[dict] = []
        self._dirty = False
        self._busy = False
        self._drag: dict | None = None

        self.title(heading)
        self.geometry("1020x760")
        self.minsize(760, 500)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self, text=heading, font=theme.font("title"),
                     text_color=theme.TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=34, pady=(28, 4))
        theme.ornament(self).grid(row=1, column=0, sticky="ew", padx=34, pady=(0, 8))
        ctk.CTkLabel(
            self,
            text=("Drag the \u2261 handle to reorder a field or move it to another category. "
                  "Changes are saved as you make them. Deleting a field also deletes its saved "
                  "values for every entry. A category can only be deleted when it has no fields."),
            font=theme.font("note"), text_color=theme.TEXT_MUTED, anchor="w", justify="left",
            wraplength=820,
        ).grid(row=2, column=0, sticky="ew", padx=34, pady=(0, 12))

        panel = ctk.CTkFrame(self, **theme.CARD_STYLE)
        panel.grid(row=3, column=0, sticky="nsew", padx=34, pady=4)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self._list = theme.scrollable(panel, theme.SURFACE)
        self._list.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=12)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=34, pady=(14, 28))
        theme.secondary_button(footer, "+ Add Category", self.add_category, width=170).pack(
            side="left")
        theme.primary_button(footer, "Done", self.close, width=120).pack(side="right")

        self._render()
        self.after(150, self._finish_setup)

    def snapshot(self) -> list[tuple[str, list[str]]]:
        return [(block["name"], [field.name for field in block["fields"]])
                for block in self._layout]

    def add_category(self) -> None:
        name = ask_name(self, "Add Category", "New category name",
                        taken=self._categories.list_categories())
        self._regrab()
        if name:
            self._apply(lambda: self._categories.add_category(name))

    def rename_category(self, category: str) -> None:
        others = [c for c in self._categories.list_categories() if c != category]
        name = ask_name(self, "Rename Category", f"New name for \u201c{category}\u201d",
                        initial=category, taken=others)
        self._regrab()
        if name:
            self._apply(lambda: self._categories.rename_category(category, name))

    def delete_category(self, category: str) -> None:
        self._apply(lambda: self._categories.delete_category(category))

    def move_category(self, category: str, offset: int) -> None:
        names = self._categories.list_categories()
        index = names.index(category)
        target = max(0, min(len(names) - 1, index + offset))
        if target == index:
            return
        names.insert(target, names.pop(index))
        self._apply(lambda: self._categories.reorder_categories(names))

    def add_field(self, category: str) -> None:
        taken = [f.name for f in self._categories.list_fields(category)]
        name = ask_name(self, "Add Field", f"New field name in \u201c{category}\u201d",
                        taken=taken)
        self._regrab()
        if name:
            self._apply(lambda: self._categories.add_field(category, name))

    def rename_field(self, field_id: int, new_name: str) -> None:
        self._apply(lambda: self._categories.rename_field(field_id, new_name))

    def change_field_type(self, field_id: int, field_type: str) -> None:
        self._apply(lambda: self._categories.change_field_type(field_id, field_type))

    def set_display(self, field_id: int, show_empty: bool | None = None,
                    full_width: bool | None = None) -> None:
        self._apply(lambda: self._categories.set_field_display(field_id, show_empty, full_width))

    def edit_options(self, field_id: int) -> None:
        field = self._categories.get_field(field_id)
        result = ask_field_options(self, field)
        self._regrab()
        if result is not None:
            self._apply(lambda: self._categories.set_field_options(field_id, result))

    def delete_field(self, field_id: int) -> None:
        field = self._categories.get_field(field_id)
        count = self._categories.count_field_values(field_id)
        detail = f" and {count} saved value{'s' if count != 1 else ''}" if count else ""
        confirmed = messagebox.askyesno(
            "Delete field?",
            f"Permanently delete \u201c{field.name}\u201d{detail}? This can't be undone.",
            parent=self)
        if confirmed:
            self._apply(lambda: self._categories.delete_field(field_id))

    def move_field(self, field_id: int, category: str, position: int | None = None) -> None:
        self._apply(lambda: self._categories.move_field(field_id, category, position))

    def drop_field(self, field_id: int, target: tuple[int, int]) -> None:
        block_index, row_index = target
        source = self._locate(field_id)
        if source is None:
            return
        source_block, source_index = source
        if block_index == source_block and row_index > source_index:
            row_index -= 1
        if block_index == source_block and row_index == source_index:
            self._render()
            return
        self.move_field(field_id, self._layout[block_index]["name"], row_index)

    def close(self) -> None:
        changed = self._dirty
        self.destroy()
        if changed:
            self._on_changed()

    def _apply(self, action) -> bool:
        self._busy = True
        try:
            action()
        except ServiceError as exc:
            messagebox.showwarning("Can't make that change", str(exc), parent=self)
            self._render()
            return False
        finally:
            self._busy = False
        self._dirty = True
        self._render()
        return True

    def _locate(self, field_id):
        for block_index, block in enumerate(self._layout):
            for index, field in enumerate(block["fields"]):
                if field.id == field_id:
                    return block_index, index
        return None

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _regrab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _render(self):
        try:
            scroll_position = self._list._parent_canvas.yview()[0]
        except (AttributeError, tk.TclError):
            scroll_position = 0.0

        for child in self._list.winfo_children():
            child.destroy()
        self._layout = []

        for index, name in enumerate(self._categories.list_categories()):
            fields = self._categories.list_fields(name)
            header = self._build_header(index, name, len(fields))
            rows = [self._build_row(field) for field in fields]
            if not fields:
                ctk.CTkLabel(self._list, text="No fields yet. Drag one here or add one below.",
                             font=theme.font("note"), text_color=theme.TEXT_MUTED,
                             anchor="w").pack(fill="x", padx=16, pady=6)
            theme.secondary_button(
                self._list, "+ Add Field", lambda c=name: self.add_field(c),
                width=128, height=32).pack(anchor="w", padx=46, pady=(6, 0))
            self._layout.append({"name": name, "fields": fields, "header": header, "rows": rows})

        try:
            self.update_idletasks()
            self._list._parent_canvas.yview_moveto(scroll_position)
        except (AttributeError, tk.TclError):
            pass

    def _build_header(self, index, name, count):
        header = ctk.CTkFrame(self._list, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", pady=(26 if index else 4, 4))
        header.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(header, text="\u25C6", font=theme.font("small"),
                     text_color=theme.GOLD).grid(row=0, column=0, padx=(8, 8))
        ctk.CTkLabel(header, text=name.upper(), font=theme.font("subheading"),
                     text_color=theme.EMPHASIS, anchor="w").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(header, text=f"{count} field{'s' if count != 1 else ''}",
                     font=theme.font("note"), text_color=theme.TEXT_MUTED,
                     anchor="w").grid(row=0, column=2, sticky="w", padx=14)
        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.grid(row=0, column=3, padx=(0, 4))
        theme.secondary_button(controls, "\u25B2", lambda c=name: self.move_category(c, -1),
                               width=34, height=32).pack(side="left", padx=2)
        theme.secondary_button(controls, "\u25BC", lambda c=name: self.move_category(c, 1),
                               width=34, height=32).pack(side="left", padx=2)
        theme.secondary_button(controls, "Rename", lambda c=name: self.rename_category(c),
                               width=90, height=32).pack(side="left", padx=2)
        theme.secondary_button(controls, "Delete Category",
                               lambda c=name: self.delete_category(c),
                               width=150, height=32, danger=True).pack(side="left", padx=2)
        tk.Frame(header, height=1, bd=0, highlightthickness=0, bg=theme.GOLD).grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        return header

    def _build_row(self, field: Field):
        frame = ctk.CTkFrame(self._list, fg_color=theme.BACKGROUND, border_width=1,
                             border_color=theme.BORDER, corner_radius=0)
        frame.pack(fill="x", pady=3)
        frame.grid_columnconfigure(1, weight=1)

        handle = tk.Label(frame, text="\u2261", font=(theme.FONT_FAMILY, 20),
                          bg=theme.BACKGROUND, fg=theme.ACCENT, cursor="fleur", padx=10)
        handle.grid(row=0, column=0, pady=6)
        handle.bind("<ButtonPress-1>", lambda event, f=field: self._drag_start(event, f, frame, handle))
        handle.bind("<B1-Motion>", self._drag_motion)
        handle.bind("<ButtonRelease-1>", self._drag_end)

        entry = theme.styled_entry(frame, height=34)
        entry.insert(0, field.name)
        entry.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        entry.bind("<Return>", lambda _event, f=field, e=entry: self._commit_rename(f, e))
        entry.bind("<FocusOut>", lambda _event, f=field, e=entry: self._commit_rename(f, e))

        combo = theme.styled_combo(
            frame, list(FIELD_TYPE_LABELS.values()), height=34, width=self.TYPE_WIDTH,
            command=lambda label, f=field: self.change_field_type(f.id, TYPE_FROM_LABEL[label]))
        combo.set(FIELD_TYPE_LABELS.get(field.field_type, field.field_type))
        combo.grid(row=0, column=2, padx=4, pady=6)

        summary = options_summary(field)
        if summary:
            theme.secondary_button(
                frame, summary, lambda f=field: self.edit_options(f.id),
                width=self.OPTIONS_WIDTH, height=34).grid(row=0, column=3, padx=4, pady=6)
        else:
            ctk.CTkLabel(frame, text="", width=self.OPTIONS_WIDTH).grid(
                row=0, column=3, padx=4, pady=6)

        display = theme.secondary_button(
            frame, "Display", lambda: None, width=self.DISPLAY_WIDTH, height=34)
        display.configure(command=lambda f=field, b=display: self._show_display_menu(f, b))
        display.grid(row=0, column=4, padx=4, pady=6)

        theme.secondary_button(
            frame, "Delete", lambda f=field: self.delete_field(f.id),
            width=self.DELETE_WIDTH, height=34, danger=True).grid(
            row=0, column=5, padx=(4, 10), pady=6)
        return frame

    def _show_display_menu(self, field: Field, button) -> None:
        menu = tk.Menu(self, tearoff=False, bg=theme.SURFACE, fg=theme.TEXT,
                       activebackground=theme.SELECTION_BG, activeforeground=theme.TEXT,
                       selectcolor=theme.TEXT, font=(theme.FONT_FAMILY, 12))
        show_var = tk.BooleanVar(master=self, value=field.show_empty)
        menu.add_checkbutton(
            label="Show when empty", variable=show_var,
            command=lambda: self.set_display(field.id, show_empty=show_var.get()))
        if field.field_type in ALWAYS_FULL_TYPES:
            menu.add_checkbutton(
                label="Full width (always for this type)",
                variable=tk.BooleanVar(master=self, value=True), state="disabled")
        else:
            wide_var = tk.BooleanVar(master=self, value=field.full_width)
            menu.add_checkbutton(
                label="Full width", variable=wide_var,
                command=lambda: self.set_display(field.id, full_width=wide_var.get()))
        try:
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            menu.grab_release()

    def _commit_rename(self, field, entry):
        if self._busy:
            return
        try:
            new_name = entry.get().strip()
        except tk.TclError:
            return
        if new_name != field.name:
            self.rename_field(field.id, new_name)

    def _blocks(self):
        count = len(self._layout)
        blocks = []
        for index, block in enumerate(self._layout):
            header = block["header"]
            next_top = (self._layout[index + 1]["header"].winfo_rooty()
                        if index + 1 < count else float("inf"))
            blocks.append({
                "header_bottom": header.winfo_rooty() + header.winfo_height(),
                "rows": [(row.winfo_rooty(), row.winfo_rooty() + row.winfo_height())
                         for row in block["rows"]],
                "end": next_top,
            })
        return blocks

    def _drag_start(self, _event, field, frame, handle):
        line = tk.Frame(self._list, bg=theme.EMPHASIS, height=4)
        self._drag = {"field": field, "target": None, "line": line}
        try:
            frame.configure(fg_color=theme.DRAG_BG)
            handle.configure(bg=theme.DRAG_BG)
        except tk.TclError:
            pass

    def _autoscroll(self, y):
        try:
            canvas = self._list._parent_canvas
            top = canvas.winfo_rooty()
            bottom = top + canvas.winfo_height()
            if y < top + 36:
                canvas.yview_scroll(-1, "units")
            elif y > bottom - 36:
                canvas.yview_scroll(1, "units")
        except (AttributeError, tk.TclError):
            pass

    def _drag_motion(self, event):
        if self._drag is None:
            return
        self._autoscroll(event.y_root)
        blocks = self._blocks()
        target = find_drop_target(event.y_root, blocks)
        self._drag["target"] = target
        line = self._drag["line"]
        if target is None:
            line.place_forget()
            return
        y = drop_line_y(target, blocks) - self._list.winfo_rooty()
        line.place(x=0, y=max(0, y - 2), relwidth=1.0, height=4)
        line.lift()

    def _drag_end(self, _event):
        drag, self._drag = self._drag, None
        if drag is None:
            return
        try:
            drag["line"].destroy()
        except tk.TclError:
            pass
        if drag["target"] is None:
            self._render()
            return
        self.drop_field(drag["field"].id, drag["target"])
