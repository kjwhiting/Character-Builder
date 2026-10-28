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
from src.ui.field_layout import SectionGrid, is_full_width
from src.ui.image_preview import ImagePreview
from src.ui.new_field_dialog import ask_new_field

HEADER_IMAGE_SIDE = 180
PREVIEW_IMAGE_SIDE = 720
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


def columns_for_width(width: int) -> int:
    if width < 640:
        return 1
    if width < 900:
        return 2
    return 3


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
        self._wrap_labels: list[tuple[ctk.CTkLabel, int, int, bool]] = []
        self._grids: list[SectionGrid] = []
        self._columns = 2
        self._reflow_job = None
        self._collapsed: set[str] = set()
        self._form_collapsed: set[str] = set()
        self._initial_signature: tuple | None = None
        self._preview_ref = None
        self._field_widgets: dict[int, tuple[tk.Widget, str]] = {}
        self.action_buttons: dict[str, ctk.CTkButton] = {}
        self.name_entry = None
        self.image_entry = None
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
        header = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        header.grid(row=row, column=0, sticky="ew", padx=(0, 18), pady=(0, 4))
        image = load_image(self._images_dir, entity.image, max_side=HEADER_IMAGE_SIDE)
        text_column = 0
        reserve = 130
        if image is not None:
            self._image_ref = image
            mount = ctk.CTkFrame(header, fg_color=theme.BACKGROUND, border_width=2,
                                 border_color=theme.GOLD, corner_radius=2)
            mount.grid(row=0, column=0, sticky="nw", padx=(0, 20))
            picture = ctk.CTkLabel(mount, text="", image=image, cursor="hand2")
            picture.pack(padx=5, pady=5)
            picture.bind("<Button-1>", lambda _event, e=entity: self.preview_image(e))
            text_column = 1
            reserve += HEADER_IMAGE_SIDE + 40
        header.grid_columnconfigure(text_column, weight=1)
        text = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        text.grid(row=0, column=text_column, sticky="w")
        ctk.CTkLabel(text, text=f"  {self._noun}  ", font=theme.font("small"),
                     text_color=theme.TEXT, fg_color=theme.SELECTION_BG,
                     corner_radius=10, height=22).pack(anchor="w", pady=(2, 6))
        title = ctk.CTkLabel(text, text=entity.name, font=theme.font("title"),
                             text_color=theme.TEXT, anchor="w", justify="left", wraplength=640)
        title.pack(anchor="w")
        self._wrap_labels.append((title, reserve, 230, False))
        if entity.image and image is None:
            ctk.CTkLabel(text, text=f"(image not found: images/{entity.image})",
                         text_color=theme.TEXT_MUTED, font=theme.font("note")).pack(
                anchor="w", pady=(6, 0))
        row += 1

        self._show_sections(body, row, entity_id)

    def start_edit(self) -> None:
        if self._entity_id is None:
            return
        entity = self._entities.get_entity(self._entity_id)
        self._build_form(
            self._entity_id,
            {"name": entity.name, "image": entity.image,
             "values": self._entities.get_values(entity.id)},
        )

    def start_new(self) -> None:
        self._build_form(None, {"name": "", "image": "", "values": {}})

    def collect_form(self) -> dict:
        values = {}
        for field_id, (widget, _field_type) in self._field_widgets.items():
            values[field_id] = field_inputs.read_input(widget).strip()
        return {
            "name": self.name_entry.get().strip(),
            "image": self.image_entry.get().strip(),
            "values": values,
        }

    def save(self) -> None:
        if not self._editing:
            return
        data = self.collect_form()
        try:
            if self._edit_id is None:
                entity_id = self._entities.create_entity(
                    data["name"], data["image"], data["values"])
            else:
                entity_id = self._edit_id
                self._entities.update_entity(
                    entity_id, data["name"], data["image"], data["values"])
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
        all_fields = self._categories.list_fields()
        for field in all_fields:
            value = (values.get(field.id) or "").strip()
            if value or field.show_empty:
                groups.setdefault(field.category, []).append((field, value))
        if not groups:
            hint = ("No details yet. Press Edit to add some." if all_fields else
                    f"This tab has no fields yet. Use + Add field to choose what to track "
                    f"for each {self._noun.lower()}.")
            ctk.CTkLabel(body, text=hint, justify="left", wraplength=560, anchor="w",
                         text_color=theme.TEXT_MUTED, font=theme.font("note")).grid(
                row=row, column=0, sticky="w", pady=(18, 6))
            row += 1
        for category, items in groups.items():
            row = self._add_section(
                body, row, category, lambda section, items=items: self._fill_view(section, items),
                self._collapsed)
        self._add_field_button(body, row)

    def _add_section(self, body, row, category, fill, collapsed):
        section = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        grid = SectionGrid(section)
        self._grids.append(grid)
        header = theme.section_header(
            body, category, collapsed=category in collapsed,
            on_toggle=lambda: self._toggle_section(collapsed, category, header, section))
        header.grid(row=row, column=0, sticky="ew", pady=(14, 4), padx=(0, 18))
        section.grid(row=row + 1, column=0, sticky="ew", padx=(0, 18))
        if category in collapsed:
            section.grid_remove()
        fill(grid)
        grid.reflow(self._columns)
        return row + 2

    def _toggle_section(self, collapsed, category, header, section):
        if category in collapsed:
            collapsed.discard(category)
            section.grid()
            header.marker_label.configure(text="\u25BE")
        else:
            collapsed.add(category)
            section.grid_remove()
            header.marker_label.configure(text="\u25B8")

    def _add_field_button(self, body, row):
        theme.secondary_button(body, "+ Add field", self.add_field, width=140, height=34).grid(
            row=row, column=0, sticky="w", pady=(18, 6))

    def _fill_view(self, grid, items):
        for field, value in items:
            full = is_full_width(field.field_type, field.full_width)
            grid.add(self._view_cell(grid.frame, field, value, full), full)

    def _view_cell(self, section, field, value, full):
        cell = ctk.CTkFrame(section, fg_color="transparent", corner_radius=0)
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
        self._wrap_labels.append((label, 150 if full else 190, 140, not full))
        return cell

    def preview_image(self, entity) -> None:
        large = load_image(self._images_dir, entity.image, max_side=PREVIEW_IMAGE_SIDE)
        if large is not None:
            self._preview_ref = large
            ImagePreview(self, large, entity.name)

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
        self._form_collapsed.discard(result["category"])
        if self._editing:
            preset = self.collect_form()
            self._build_form(self._edit_id, preset, keep_state=True)
        elif self._entity_id is not None:
            self.show_entity(self._entity_id)
        self.after(120, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            self._body_frame._parent_canvas.yview_moveto(1.0)
        except (AttributeError, tk.TclError):
            pass

    def _build_form(self, entity_id, preset, keep_state=False):
        self._editing = True
        self._edit_id = entity_id
        self._clear()
        if not keep_state:
            self._form_collapsed = self._initial_collapsed(entity_id, preset)

        bar = self._topbar()
        theme.primary_button(bar, "Save", self.save).pack(side="left")
        theme.secondary_button(bar, "Cancel", self.request_cancel).pack(side="left", padx=10)
        ctk.CTkLabel(
            bar, text=f"New {self._noun.lower()}" if entity_id is None else "Editing",
            font=theme.font("note"), text_color=theme.TEXT_MUTED).pack(side="left", padx=(14, 0))
        if entity_id is not None:
            theme.secondary_button(bar, "Delete", self.delete, danger=True).pack(side="right")

        body = self._body()
        row = 0
        top = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        top.grid(row=row, column=0, sticky="ew", padx=(0, 18))
        top.grid_columnconfigure(0, weight=3, uniform="top")
        top.grid_columnconfigure(1, weight=2, uniform="top")
        name_cell = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        name_cell.grid(row=0, column=0, sticky="ew", padx=(0, 18))
        self._cell_label(name_cell, "Name")
        self.name_entry = theme.styled_entry(name_cell)
        self.name_entry.insert(0, preset["name"])
        self.name_entry.pack(fill="x")
        image_cell = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        image_cell.grid(row=0, column=1, sticky="ew")
        self._cell_label(image_cell, "Image  (in ./images/)")
        image_row = ctk.CTkFrame(image_cell, fg_color="transparent", corner_radius=0)
        image_row.pack(fill="x")
        image_row.grid_columnconfigure(0, weight=1)
        self.image_entry = theme.styled_entry(image_row, placeholder_text="hero.png")
        self.image_entry.insert(0, preset["image"])
        self.image_entry.grid(row=0, column=0, sticky="ew")
        theme.secondary_button(image_row, "Browse...", self.browse_image, width=96).grid(
            row=0, column=1, padx=(8, 0))
        row += 1

        by_category: dict[str, list] = {}
        for field in self._categories.list_fields():
            by_category.setdefault(field.category, []).append(field)
        if not by_category:
            ctk.CTkLabel(
                body, text=f"No fields yet. Add the ones you want to track for each "
                           f"{self._noun.lower()} below.",
                font=theme.font("note"), text_color=theme.TEXT_MUTED, anchor="w",
                justify="left", wraplength=560,
            ).grid(row=row, column=0, sticky="w", pady=(18, 0))
            row += 1
        for category, fields in by_category.items():
            row = self._add_section(
                body, row, category,
                lambda grid, fields=fields: self._fill_form(grid, fields, preset),
                self._form_collapsed)
        self._add_field_button(body, row)

        if not keep_state:
            self._initial_signature = self._signature(self.collect_form())
        self.after(50, self._focus_name)

    @staticmethod
    def _cell_label(parent, text, suffix=""):
        ctk.CTkLabel(parent, text=text + suffix, font=theme.font("label"),
                     text_color=theme.TEXT_MUTED, anchor="w").pack(anchor="w", pady=(0, 3))

    def _initial_collapsed(self, entity_id, preset):
        if entity_id is None:
            return set()
        filled = {fid for fid, value in preset["values"].items() if (value or "").strip()}
        collapsed = set()
        for category in self._categories.list_categories():
            fields = self._categories.list_fields(category)
            if fields and not any(f.id in filled for f in fields):
                collapsed.add(category)
        return collapsed

    @staticmethod
    def _signature(data):
        values = tuple(sorted((fid, v.strip()) for fid, v in data["values"].items() if v.strip()))
        return (data["name"].strip(), data["image"].strip(), values)

    @property
    def is_dirty(self) -> bool:
        if not self._editing or self._initial_signature is None:
            return False
        return self._signature(self.collect_form()) != self._initial_signature

    def request_cancel(self) -> bool:
        if not self._editing:
            return True
        if self.is_dirty:
            confirmed = messagebox.askyesno(
                "Discard changes?", "You have unsaved changes. Discard them?", parent=self)
            if not confirmed:
                return False
        self.cancel()
        return True

    def _fill_form(self, grid, fields, preset):
        for field in fields:
            cell = ctk.CTkFrame(grid.frame, fg_color="transparent", corner_radius=0)
            self._cell_label(cell, field.name, field_inputs.field_hint(field))
            widget = field_inputs.build_input(cell, field, preset["values"].get(field.id, "") or "")
            stretch = isinstance(widget, (ctk.CTkTextbox, ctk.CTkEntry))
            widget.pack(fill="x" if stretch else None, anchor="w")
            self._field_widgets[field.id] = (widget, field.field_type)
            grid.add(cell, is_full_width(field.field_type, field.full_width))

    def _focus_name(self):
        try:
            self.name_entry.focus_set()
        except (tk.TclError, AttributeError):
            pass

    def _clear(self):
        for child in self.winfo_children():
            child.destroy()
        self._wrap_labels = []
        self._grids = []
        self._field_widgets = {}
        self.action_buttons = {}
        self.name_entry = None
        self.image_entry = None

    def _topbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 8))
        return bar

    def _body(self):
        card = ctk.CTkFrame(self, **theme.CARD_STYLE)
        card.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        body = theme.scrollable(card, theme.SURFACE)
        body.grid(row=0, column=0, sticky="nsew", padx=(26, 10), pady=(14, 10))
        body.grid_columnconfigure(0, weight=1)
        self._body_frame = body
        if self.winfo_width() > 1:
            self._columns = columns_for_width(self.winfo_width())
        self.after(60, lambda: self._apply_wraps(self.winfo_width()))
        return body

    def _on_resize(self, event):
        self._apply_wraps(event.width)
        columns = columns_for_width(event.width)
        if columns != self._columns:
            if self._reflow_job is not None:
                self.after_cancel(self._reflow_job)
            self._reflow_job = self.after(80, lambda: self._reflow(columns))

    def _reflow(self, columns):
        self._reflow_job = None
        self._columns = columns
        for grid in self._grids:
            try:
                grid.reflow(columns)
            except tk.TclError:
                pass
        self._apply_wraps(self.winfo_width())

    def _apply_wraps(self, width):
        if width <= 1:
            return
        for label, reserve, minimum, half in self._wrap_labels:
            divisor = self._columns if half else 1
            try:
                label.configure(wraplength=max(minimum, (width - reserve) // divisor))
            except tk.TclError:
                pass
