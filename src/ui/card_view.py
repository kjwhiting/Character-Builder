import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
from PIL import Image

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.errors import EntityNotFoundError, ServiceError
from src.services.value_format import format_value, split_lines
from src.services.export_service import ExportService
from src.ui import field_inputs, theme
from src.ui.field_layout import is_full_width, plan_layout
from src.ui.new_field_dialog import ask_new_field

IMAGE_FILETYPES = [("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")]


def load_image(images_dir: Path, filename: str, max_side: int = 320):
    if not filename:
        return None
    path = Path(images_dir) / Path(filename).name
    if not path.is_file():
        return None
    try:
        picture = Image.open(path)
        picture.load()
    except (OSError, ValueError):
        return None
    width, height = picture.size
    scale = min(max_side / width, max_side / height, 2.0)
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return ctk.CTkImage(light_image=picture, dark_image=picture, size=size)


def import_image(source: Path, images_dir: Path) -> str:
    source = Path(source)
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    destination = images_dir / source.name
    if destination.exists() and source.resolve() == destination.resolve():
        return destination.name
    counter = 1
    while destination.exists():
        destination = images_dir / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    shutil.copy2(source, destination)
    return destination.name


def _reset_button_text(button, text):
    try:
        button.configure(text=text)
    except tk.TclError:
        pass


class CardView(ctk.CTkFrame):
    def __init__(self, master, entities: EntityService, categories: CategoryService,
                 exporter: ExportService, images_dir: Path, noun: str = "Character",
                 on_saved: Callable[[int], None] | None = None,
                 on_deleted: Callable[[int], None] | None = None,
                 on_duplicated: Callable[[int], None] | None = None):
        super().__init__(master, corner_radius=0, fg_color=theme.BACKGROUND)
        self._entities = entities
        self._categories = categories
        self._exporter = exporter
        self._images_dir = Path(images_dir)
        self._noun = noun
        self._on_saved = on_saved or (lambda entity_id: None)
        self._on_deleted = on_deleted or (lambda entity_id: None)
        self._on_duplicated = on_duplicated or (lambda entity_id: None)

        self._entity_id: int | None = None
        self._edit_id: int | None = None
        self._editing = False
        self._image_ref = None
        self._wrap_labels: list[tuple[ctk.CTkLabel, int, int, int]] = []
        self._collapsed: set[str] = set()
        self._field_widgets: dict[int, tuple[tk.Widget, str]] = {}
        self.action_buttons: dict[str, ctk.CTkButton] = {}
        self.name_entry = None
        self.image_entry = None
        self.aliases_box = None
        self._body_frame = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.bind("<Configure>", self._on_resize)
        self.show_empty()

    @property
    def editing(self) -> bool:
        return self._editing

    @property
    def entity_id(self) -> int | None:
        return self._entity_id

    def set_noun(self, noun: str) -> None:
        self._noun = noun

    def show_empty(self) -> None:
        self._editing = False
        self._edit_id = None
        self._entity_id = None
        self._clear()
        holder = ctk.CTkFrame(self, fg_color=theme.BACKGROUND)
        holder.grid(row=0, column=0, rowspan=2, sticky="nsew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(holder, fg_color="transparent")
        inner.grid(row=0, column=0)
        theme.ornament(inner).pack(fill="x", padx=40, pady=(0, 18))
        article = "an" if self._noun[:1].lower() in "aeiou" else "a"
        ctk.CTkLabel(
            inner,
            text=f"Select {article} {self._noun.lower()} on the left,\n"
                 f"or click \u201cAdd {self._noun}\u201d to begin.",
            font=theme.font("placeholder"), text_color=theme.TEXT_MUTED, justify="center",
        ).pack()
        theme.ornament(inner).pack(fill="x", padx=40, pady=(18, 0))

    def show_entity(self, entity_id: int) -> None:
        try:
            entity = self._entities.get_entity(entity_id)
        except EntityNotFoundError:
            self.show_empty()
            return
        self._editing = False
        self._edit_id = None
        self._entity_id = entity_id
        self._clear()

        bar = self._topbar()
        self.action_buttons = {
            "Copy": theme.secondary_button(bar, "Copy", self.copy_to_clipboard),
            "Edit": theme.primary_button(bar, "Edit", self.start_edit),
            "Duplicate": theme.secondary_button(bar, "Duplicate", self.duplicate, width=110),
        }
        for index, button in enumerate(self.action_buttons.values()):
            button.pack(side="left", padx=(0 if index == 0 else 10, 0))

        body = self._body()
        row = 0
        image = load_image(self._images_dir, entity.image)
        if image is not None:
            self._image_ref = image
            mount = ctk.CTkFrame(body, fg_color=theme.BACKGROUND, border_width=2,
                                 border_color=theme.GOLD, corner_radius=2)
            mount.grid(row=row, column=0, sticky="w", pady=(2, 20))
            ctk.CTkLabel(mount, text="", image=image).pack(padx=6, pady=6)
            row += 1
        elif entity.image:
            ctk.CTkLabel(body, text=f"(image not found: images/{entity.image})",
                         text_color=theme.TEXT_MUTED, font=theme.font("note")).grid(
                row=row, column=0, sticky="w", pady=(4, 8))
            row += 1

        ctk.CTkLabel(body, text=f"  {self._noun}  ", font=theme.font("small"),
                     text_color=theme.TEXT, fg_color=theme.SELECTION_BG,
                     corner_radius=10, height=22).grid(row=row, column=0, sticky="w", pady=(0, 8))
        row += 1
        title = ctk.CTkLabel(body, text=entity.name, font=theme.font("title"),
                             text_color=theme.TEXT, anchor="w", justify="left", wraplength=640)
        title.grid(row=row, column=0, sticky="w")
        self._wrap_labels.append((title, 130, 230, 1))
        row += 1
        aliases = self._entities.get_aliases(entity_id)
        if aliases:
            alias_label = ctk.CTkLabel(
                body, text="Also known as: " + ", ".join(aliases), font=theme.font("note"),
                text_color=theme.TEXT_MUTED, anchor="w", justify="left", wraplength=640)
            alias_label.grid(row=row, column=0, sticky="w", pady=(2, 0))
            self._wrap_labels.append((alias_label, 130, 230, 1))
            row += 1
        theme.ornament(body).grid(row=row, column=0, sticky="ew", pady=(10, 2), padx=(0, 18))
        row += 1

        self._show_sections(body, row, entity_id)

    def start_edit(self) -> None:
        if self._entity_id is None:
            return
        entity = self._entities.get_entity(self._entity_id)
        self._build_form(
            self._entity_id,
            {"name": entity.name, "image": entity.image,
             "aliases": self._entities.get_aliases(entity.id),
             "values": self._entities.get_values(entity.id)},
        )

    def start_new(self) -> None:
        self._build_form(None, {"name": "", "image": "", "aliases": [], "values": {}})

    def collect_form(self) -> dict:
        values = {}
        for field_id, (widget, _field_type) in self._field_widgets.items():
            values[field_id] = field_inputs.read_input(widget).strip()
        return {
            "name": self.name_entry.get().strip(),
            "image": self.image_entry.get().strip(),
            "aliases": [line.strip() for line in
                        self.aliases_box.get("1.0", "end-1c").splitlines() if line.strip()],
            "values": values,
        }

    def save(self) -> None:
        if not self._editing:
            return
        data = self.collect_form()
        try:
            if self._edit_id is None:
                entity_id = self._entities.create_entity(
                    data["name"], data["image"], data["values"], data["aliases"])
            else:
                entity_id = self._edit_id
                self._entities.update_entity(
                    entity_id, data["name"], data["image"], data["values"], data["aliases"])
        except ServiceError as exc:
            messagebox.showwarning("Can't save", str(exc), parent=self)
            self.name_entry.focus_set()
            return
        self.show_entity(entity_id)
        self._on_saved(entity_id)

    def cancel(self) -> None:
        if not self._editing:
            return
        if self._entity_id is not None:
            self.show_entity(self._entity_id)
        else:
            self.show_empty()

    def delete(self) -> None:
        if not self._editing or self._edit_id is None:
            return
        entity = self._entities.get_entity(self._edit_id)
        confirmed = messagebox.askyesno(
            "Move to Trash?",
            f"Move \u201c{entity.name}\u201d to the Trash? "
            "You can restore it from the Trash for 30 days.",
            parent=self)
        if not confirmed:
            return
        self._entities.delete_entity(entity.id)
        self.show_empty()
        self._on_deleted(entity.id)

    def duplicate(self) -> None:
        if self._entity_id is None:
            return
        try:
            new_id = self._entities.duplicate_entity(self._entity_id)
        except ServiceError as exc:
            messagebox.showwarning("Can't duplicate", str(exc), parent=self)
            return
        self.show_entity(new_id)
        self._on_duplicated(new_id)

    def copy_to_clipboard(self) -> None:
        if self._entity_id is None:
            return
        try:
            self._exporter.copy_entity(self._entity_id)
        except ServiceError as exc:
            messagebox.showwarning("Can't copy", str(exc), parent=self)
            return
        button = self.action_buttons["Copy"]
        button.configure(text="Copied \u2713")
        self.after(1500, lambda: _reset_button_text(button, "Copy"))

    def browse_image(self) -> None:
        start = self._images_dir if self._images_dir.exists() else Path.home()
        chosen = filedialog.askopenfilename(
            parent=self, title="Choose an image", initialdir=str(start),
            filetypes=IMAGE_FILETYPES)
        if not chosen:
            return
        try:
            filename = import_image(Path(chosen), self._images_dir)
        except OSError as exc:
            messagebox.showerror("Couldn't copy image", str(exc), parent=self)
            return
        self.image_entry.delete(0, "end")
        self.image_entry.insert(0, filename)

    def _show_sections(self, body, row, entity_id):
        values = self._entities.get_values(entity_id)
        groups: dict[str, list] = {}
        for field in self._categories.list_fields():
            value = (values.get(field.id) or "").strip()
            if value or field.show_empty:
                groups.setdefault(field.category, []).append((field, value))
        if not groups:
            ctk.CTkLabel(body, text="No details yet. Press Edit to add some.",
                         text_color=theme.TEXT_MUTED, font=theme.font("note")).grid(
                row=row, column=0, sticky="w", pady=(18, 6))
            row += 1
        for category, items in groups.items():
            row = self._add_section(
                body, row, category, lambda section, items=items: self._fill_view(section, items))
        self._add_field_button(body, row)

    def _add_section(self, body, row, category, fill):
        section = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        section.grid_columnconfigure(0, weight=1, uniform="cells")
        section.grid_columnconfigure(1, weight=1, uniform="cells")
        header = theme.section_header(
            body, category, collapsed=category in self._collapsed,
            on_toggle=lambda: self._toggle_section(category, header, section))
        header.grid(row=row, column=0, sticky="ew", pady=(20, 6), padx=(0, 18))
        section.grid(row=row + 1, column=0, sticky="ew", padx=(0, 18))
        if category in self._collapsed:
            section.grid_remove()
        fill(section)
        return row + 2

    def _toggle_section(self, category, header, section):
        if category in self._collapsed:
            self._collapsed.discard(category)
            section.grid()
            header.marker_label.configure(text="\u25BE")
        else:
            self._collapsed.add(category)
            section.grid_remove()
            header.marker_label.configure(text="\u25B8")

    def _add_field_button(self, body, row):
        theme.secondary_button(body, "+ Add field", self.add_field, width=140).grid(
            row=row, column=0, sticky="w", pady=(26, 10))

    def _fill_view(self, section, items):
        widths = [is_full_width(field.field_type, field.full_width) for field, _ in items]
        for index, grid_row, column, span in plan_layout(widths):
            field, value = items[index]
            self._view_cell(section, field, value, grid_row, column, span)

    def _view_cell(self, section, field, value, grid_row, column, span):
        cell = ctk.CTkFrame(section, fg_color="transparent", corner_radius=0)
        cell.grid(row=grid_row, column=column, columnspan=span, sticky="ew", pady=5,
                  padx=(0, 18) if column == 0 and span == 1 else (0, 0))
        ctk.CTkLabel(cell, text=field.name, font=theme.font("label"),
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w")
        if field.field_type == "list":
            shown = "\n".join("\u2022 " + item for item in split_lines(value))
        else:
            shown = format_value(field.field_type, field.options, value)
        empty = not shown or (not value and field.field_type != "checkbox")
        label = ctk.CTkLabel(
            cell, text="Not set" if empty and not shown else shown,
            font=theme.font("note" if empty else "body"),
            text_color=theme.TEXT_MUTED if empty else theme.TEXT,
            anchor="w", justify="left", wraplength=300)
        label.pack(anchor="w", fill="x")
        self._wrap_labels.append((label, 150 if span == 2 else 190, 140, 1 if span == 2 else 2))

    def add_field(self) -> None:
        result = ask_new_field(self, self._categories)
        if not result:
            return
        created_section = False
        try:
            if result["new_category"]:
                self._categories.add_category(result["category"])
                created_section = True
            self._categories.add_field(
                result["category"], result["name"], result["type"], result["options"])
        except ServiceError as exc:
            if created_section:
                try:
                    self._categories.delete_category(result["category"])
                except ServiceError:
                    pass
            messagebox.showwarning("Can't add field", str(exc), parent=self)
            return
        self._collapsed.discard(result["category"])
        if self._editing:
            preset = self.collect_form()
            self._build_form(self._edit_id, preset)
        elif self._entity_id is not None:
            self.show_entity(self._entity_id)
        self.after(120, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            self._body_frame._parent_canvas.yview_moveto(1.0)
        except (AttributeError, tk.TclError):
            pass

    def _build_form(self, entity_id, preset):
        self._editing = True
        self._edit_id = entity_id
        self._clear()

        bar = self._topbar()
        theme.primary_button(bar, "Save", self.save).pack(side="left")
        theme.secondary_button(bar, "Cancel", self.cancel).pack(side="left", padx=10)
        if entity_id is not None:
            theme.secondary_button(bar, "Delete", self.delete, danger=True).pack(side="right")

        body = self._body()
        row = 0
        heading = f"New {self._noun}" if entity_id is None else "Edit"
        ctk.CTkLabel(body, text=heading, font=theme.font("heading"), text_color=theme.TEXT,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=(2, 4))
        row += 1
        theme.ornament(body).grid(row=row, column=0, sticky="ew", padx=(0, 18), pady=(0, 6))
        row += 1

        row = self._form_label(body, row, "Name", top=8)
        self.name_entry = theme.styled_entry(body)
        self.name_entry.insert(0, preset["name"])
        self.name_entry.grid(row=row, column=0, sticky="ew", padx=(0, 18))
        row += 1

        row = self._form_label(body, row, "Also known as  (one per line)", top=10)
        self.aliases_box = theme.styled_textbox(body, height=64)
        self.aliases_box.insert("1.0", "\n".join(preset.get("aliases", [])))
        field_inputs.make_tabbable(self.aliases_box)
        self.aliases_box.grid(row=row, column=0, sticky="ew", padx=(0, 18))
        row += 1

        row = self._form_label(body, row, "Image filename (in ./images/)", top=10)
        image_row = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        image_row.grid(row=row, column=0, sticky="ew", padx=(0, 18))
        image_row.grid_columnconfigure(0, weight=1)
        self.image_entry = theme.styled_entry(image_row, placeholder_text="hero.png")
        self.image_entry.insert(0, preset["image"])
        self.image_entry.grid(row=0, column=0, sticky="ew")
        theme.secondary_button(image_row, "Browse...", self.browse_image, width=110).grid(
            row=0, column=1, padx=(10, 0))
        row += 1

        by_category: dict[str, list] = {}
        for field in self._categories.list_fields():
            by_category.setdefault(field.category, []).append(field)
        for category, fields in by_category.items():
            row = self._add_section(
                body, row, category,
                lambda section, fields=fields: self._fill_form(section, fields, preset))
        self._add_field_button(body, row)

        self.after(50, self._focus_name)

    def _fill_form(self, section, fields, preset):
        widths = [is_full_width(field.field_type, field.full_width) for field in fields]
        for index, grid_row, column, span in plan_layout(widths):
            field = fields[index]
            cell = ctk.CTkFrame(section, fg_color="transparent", corner_radius=0)
            cell.grid(row=grid_row, column=column, columnspan=span, sticky="ew", pady=5,
                      padx=(0, 18) if column == 0 and span == 1 else (0, 0))
            ctk.CTkLabel(cell, text=field.name + field_inputs.field_hint(field),
                         font=theme.font("label"), text_color=theme.TEXT_MUTED,
                         anchor="w").pack(anchor="w", pady=(0, 3))
            widget = field_inputs.build_input(cell, field, preset["values"].get(field.id, "") or "")
            stretch = isinstance(widget, (ctk.CTkTextbox, ctk.CTkEntry))
            widget.pack(fill="x" if stretch else None, anchor="w")
            self._field_widgets[field.id] = (widget, field.field_type)

    def _form_label(self, parent, row, text, top):
        ctk.CTkLabel(parent, text=text, font=theme.font("label"), text_color=theme.TEXT_MUTED,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=(top, 3))
        return row + 1

    def _focus_name(self):
        try:
            self.name_entry.focus_set()
        except (tk.TclError, AttributeError):
            pass

    def _clear(self):
        for child in self.winfo_children():
            child.destroy()
        self._wrap_labels = []
        self._field_widgets = {}
        self.action_buttons = {}
        self.name_entry = None
        self.image_entry = None
        self.aliases_box = None

    def _topbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew", padx=30, pady=(28, 12))
        return bar

    def _body(self):
        card = ctk.CTkFrame(self, **theme.CARD_STYLE)
        card.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 30))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        body = theme.scrollable(card, theme.SURFACE)
        body.grid(row=0, column=0, sticky="nsew", padx=(32, 12), pady=(20, 14))
        body.grid_columnconfigure(0, weight=1)
        self._body_frame = body
        self.after(60, lambda: self._apply_wraps(self.winfo_width()))
        return body

    def _on_resize(self, event):
        self._apply_wraps(event.width)

    def _apply_wraps(self, width):
        if width <= 1:
            return
        for label, reserve, minimum, divisor in self._wrap_labels:
            try:
                label.configure(wraplength=max(minimum, (width - reserve) // divisor))
            except tk.TclError:
                pass
