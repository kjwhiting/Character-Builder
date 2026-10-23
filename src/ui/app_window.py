import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.database.connection import (
    DatabaseConnection,
    ProfileError,
    profile_noun,
    remember_profile,
)
from src.database.seeds import TEMPLATES, Template, get_template
from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.errors import ServiceError
from src.services.export_service import ExportService, TkClipboard
from src.services.project_service import (
    IMAGES_DIRNAME,
    ProjectService,
    make_initializer,
)
from src.ui import theme
from src.ui.adjust_fields_view import AdjustFieldsView, ask_name
from src.ui.card_view import CardView
from src.ui.sidebar_view import SidebarView

APP_TITLE = "Character Builder"
THEME_FILE_NAME = "theme.txt"
THEME_LABELS = {"dark": "Dark Theme", "light": "Light Theme"}
PROFILE_FILETYPES = [("SQLite profiles", "*.sqlite *.sqlite3 *.db"), ("All files", "*.*")]


def template_for_path(path) -> Template | None:
    noun = profile_noun(path)
    for template in TEMPLATES.values():
        if template["entity_type"] == noun:
            return get_template(template["key"])
    return None


def recall_theme(theme_file) -> str | None:
    try:
        name = Path(theme_file).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name if name in theme.PALETTES else None


def remember_theme(theme_file, name: str) -> bool:
    try:
        Path(theme_file).write_text(name, encoding="utf-8")
    except OSError:
        return False
    return True


class AppWindow(ctk.CTk):
    def __init__(self, database: DatabaseConnection, settings_file: Path | None = None,
                 project_service: ProjectService | None = None):
        super().__init__()
        self._db = database
        self._settings_file = Path(settings_file) if settings_file else None
        self._theme_file = (self._settings_file.with_name(THEME_FILE_NAME)
                            if self._settings_file else None)
        self._projects = project_service or ProjectService(make_initializer())
        self._adjust_window: AdjustFieldsView | None = None
        self._entities: EntityService | None = None
        self._categories: CategoryService | None = None
        self._exporter: ExportService | None = None
        self.sidebar: SidebarView | None = None
        self.card: CardView | None = None

        self.geometry("1280x860")
        self.minsize(980, 640)
        self.configure(fg_color=theme.BACKGROUND)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_menu()
        self.protocol("WM_DELETE_WINDOW", self.exit_app)
        self._build_views()
        self._remember_profile()

    @property
    def database(self) -> DatabaseConnection:
        return self._db

    @property
    def adjust_window(self) -> AdjustFieldsView | None:
        window = self._adjust_window
        if window is None:
            return None
        try:
            return window if window.winfo_exists() else None
        except tk.TclError:
            return None

    @property
    def menu_labels(self) -> list[str]:
        return self._entry_labels(self.file_menu)

    @property
    def view_menu_labels(self) -> list[str]:
        return self._entry_labels(self.view_menu)

    def invoke_menu(self, label: str) -> None:
        for menu in (self.file_menu, self.view_menu):
            for position in range(menu.index("end") + 1):
                if (menu.type(position) in ("command", "radiobutton")
                        and menu.entrycget(position, "label") == label):
                    menu.invoke(position)
                    return
        raise KeyError(label)

    def set_theme(self, name: str) -> None:
        if name not in theme.PALETTES:
            raise KeyError(name)
        if name == theme.current_palette():
            self._theme_var.set(name)
            return
        if not self._confirm_discard():
            self._theme_var.set(theme.current_palette())
            return
        selected = self.card.entity_id
        self._close_adjust_window()
        theme.apply_palette(name)
        self._theme_var.set(name)
        self.configure(fg_color=theme.BACKGROUND)
        self._style_menus()
        self._build_views()
        if selected is not None:
            self.card.show_entity(selected)
            self.sidebar.set_selected(self.card.entity_id)
        if self._theme_file is not None:
            remember_theme(self._theme_file, name)

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        name = ask_name(self, "New Project", "Project name")
        if not name:
            return
        parent = filedialog.askdirectory(
            parent=self, title="Choose where to create the project",
            initialdir=str(self._db.path.parent.parent))
        if not parent:
            return
        try:
            project = self._projects.create_project(Path(parent), name)
        except ServiceError as exc:
            messagebox.showerror("Can't create project", str(exc), parent=self)
            return
        self.open_profile(next(iter(project.databases.values())))

    def load_profile(self) -> None:
        if not self._confirm_discard():
            return
        chosen = filedialog.askopenfilename(
            parent=self, title="Load Profile", initialdir=str(self._db.path.parent),
            filetypes=PROFILE_FILETYPES)
        if chosen:
            self.open_profile(Path(chosen))

    def adjust_fields(self) -> None:
        if self.card.editing:
            messagebox.showinfo(
                "Finish editing first",
                "Save or cancel the entry you are editing before adjusting fields.",
                parent=self)
            return
        existing = self.adjust_window
        if existing is not None:
            existing.lift()
            existing.focus_force()
            return
        self._adjust_window = AdjustFieldsView(
            self, self._categories, on_changed=self._fields_changed)

    def open_profile(self, path) -> bool:
        path = Path(path)
        try:
            changed = self._db.switch_profile(path, template=template_for_path(path))
        except ProfileError as exc:
            messagebox.showerror("Can't open profile", str(exc), parent=self)
            return False
        if changed:
            self._close_adjust_window()
            self._build_views()
            self._remember_profile()
        return True

    def select_entity(self, entity_id: int) -> None:
        if not self._confirm_discard():
            return
        self.card.show_entity(entity_id)
        self.sidebar.set_selected(self.card.entity_id)

    def add_entity(self) -> None:
        if not self._confirm_discard():
            return
        self.card.start_new()

    def exit_app(self) -> None:
        if not self._confirm_discard():
            return
        self.shutdown()
        self.destroy()

    def shutdown(self) -> None:
        self._close_adjust_window()
        self._db.close()

    def _build_menu(self) -> None:
        self._menubar = tk.Menu(self)
        self.file_menu = tk.Menu(self._menubar)
        self.file_menu.add_command(label="New Project...", command=self.new_project)
        self.file_menu.add_command(label="Load Profile...", command=self.load_profile)
        self.file_menu.add_command(label="Adjust Fields...", command=self.adjust_fields)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.exit_app)
        self._menubar.add_cascade(label="File", menu=self.file_menu)

        self._theme_var = tk.StringVar(master=self, value=theme.current_palette())
        self.view_menu = tk.Menu(self._menubar)
        for name, label in THEME_LABELS.items():
            self.view_menu.add_radiobutton(
                label=label, value=name, variable=self._theme_var,
                command=lambda: self.set_theme(self._theme_var.get()))
        self._menubar.add_cascade(label="View", menu=self.view_menu)

        self._style_menus()
        self.configure(menu=self._menubar)

    def _style_menus(self) -> None:
        style = {
            "bg": theme.SURFACE, "fg": theme.TEXT,
            "activebackground": theme.SELECTION_BG, "activeforeground": theme.TEXT,
            "font": (theme.FONT_FAMILY, 12),
        }
        self._menubar.configure(**style)
        for menu in (self.file_menu, self.view_menu):
            menu.configure(tearoff=False, **style)
        self.view_menu.configure(selectcolor=theme.TEXT)

    @staticmethod
    def _entry_labels(menu) -> list[str]:
        return [menu.entrycget(position, "label")
                for position in range(menu.index("end") + 1)
                if menu.type(position) in ("command", "radiobutton")]

    def _build_views(self) -> None:
        for view in (self.sidebar, self.card):
            if view is not None:
                view.destroy()

        connection = self._db.connection
        path = self._db.path
        noun = profile_noun(path)
        self._entities = EntityService(connection)
        self._categories = CategoryService(connection)
        self._exporter = ExportService(connection, TkClipboard(self))

        self.sidebar = SidebarView(
            self, self._entities, self._categories, noun=noun, profile_name=path.stem,
            on_select=self.select_entity, on_add=self.add_entity, title=APP_TITLE)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.card = CardView(
            self, self._entities, self._categories, self._exporter,
            images_dir=path.parent / IMAGES_DIRNAME, noun=noun,
            on_saved=self._entity_saved, on_deleted=self._entity_deleted,
            on_duplicated=self._entity_duplicated)
        self.card.grid(row=0, column=1, sticky="nsew")
        self.title(f"{APP_TITLE} - {path.stem}")

    def _entity_saved(self, entity_id: int) -> None:
        self.sidebar.refresh()
        self.sidebar.set_selected(entity_id)

    def _entity_deleted(self, _entity_id: int) -> None:
        self.sidebar.set_selected(None)
        self.sidebar.refresh()

    def _entity_duplicated(self, entity_id: int) -> None:
        self.sidebar.refresh()
        self.sidebar.set_selected(entity_id)

    def _fields_changed(self) -> None:
        self.sidebar.refresh()
        if self.card.entity_id is not None and not self.card.editing:
            self.card.show_entity(self.card.entity_id)

    def _confirm_discard(self) -> bool:
        if not self.card.editing:
            return True
        return messagebox.askyesno(
            "Discard changes?", "You have unsaved changes. Discard them?", parent=self)

    def _close_adjust_window(self) -> None:
        window = self.adjust_window
        self._adjust_window = None
        if window is not None:
            window.destroy()

    def _remember_profile(self) -> None:
        if self._settings_file is not None:
            remember_profile(self._settings_file, self._db.path)
