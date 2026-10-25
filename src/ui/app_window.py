import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.database.connection import DatabaseError, ProjectDatabase
from src.services.collection_service import CollectionService
from src.services.errors import ServiceError
from src.services.export_service import TkClipboard
from src.services.project_service import Project, ProjectService, remember_project
from src.services.term_index import TermIndex
from src.services.trash_service import RETENTION_DAYS, TrashService
from src.ui import theme
from src.ui.adjust_fields_view import AdjustFieldsView, ask_name
from src.ui.color_dialog import ask_color
from src.ui.global_search import GlobalSearch
from src.ui.new_tab_dialog import ask_new_tab
from src.ui.tab_bar import TabBar
from src.ui.tab_page import TabPage
from src.ui.trash_dialog import TrashDialog

APP_TITLE = "Worldbuilder"
THEME_FILE_NAME = "theme.txt"
THEME_LABELS = {"dark": "Dark Theme", "light": "Light Theme"}


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
    def __init__(self, database: ProjectDatabase, project: Project,
                 settings_file: Path | None = None,
                 project_service: ProjectService | None = None):
        super().__init__()
        self._db = database
        self._project = project
        self._settings_file = Path(settings_file) if settings_file else None
        self._theme_file = (self._settings_file.with_name(THEME_FILE_NAME)
                            if self._settings_file else None)
        self._projects = project_service or ProjectService()
        self._collections: CollectionService | None = None
        self._pages: dict[int, TabPage] = {}
        self._active_id: int | None = None
        self._adjust_window: AdjustFieldsView | None = None
        self._adjust_for: int | None = None
        self.terms: TermIndex | None = None
        self.global_search: GlobalSearch | None = None
        self.tab_bar: TabBar | None = None
        self._content: ctk.CTkFrame | None = None
        self._empty_label: ctk.CTkLabel | None = None

        self.geometry("1360x900")
        self.minsize(1040, 660)
        self.configure(fg_color=theme.BACKGROUND)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_menu()
        self._build_chrome()
        self._load_project_views()
        self.protocol("WM_DELETE_WINDOW", self.exit_app)
        self._bind_tab_keys()
        self._remember_project()

    @property
    def database(self) -> ProjectDatabase:
        return self._db

    @property
    def project(self) -> Project:
        return self._project

    @property
    def active_id(self) -> int | None:
        return self._active_id

    @property
    def active_page(self) -> TabPage | None:
        return self._pages.get(self._active_id) if self._active_id is not None else None

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

    def page_for(self, collection_id: int) -> TabPage:
        page = self._pages.get(collection_id)
        if page is None:
            collection = self._collections.get_collection(collection_id)
            page = TabPage(
                self._content, self._db.connection, collection, self._project.images_dir,
                TkClipboard(self), on_trash_changed=self._update_trash_count,
                on_terms_changed=self.refresh_terms)
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()
            self._pages[collection_id] = page
        return page

    def refresh_terms(self) -> None:
        if self.terms is not None:
            self.terms.refresh()

    def open_entry(self, collection_id: int, entity_id: int) -> None:
        self.select_tab(collection_id)
        self.page_for(collection_id).select_entity(entity_id)

    def focus_search(self) -> None:
        self.global_search.focus()

    def change_color(self, collection_id: int) -> None:
        collection = self._collections.get_collection(collection_id)
        chosen = ask_color(self, collection.label, collection.color)
        if not chosen:
            return
        try:
            self._collections.set_color(collection_id, chosen)
        except ServiceError as exc:
            messagebox.showerror("Can't change colour", str(exc), parent=self)
            return
        self.refresh_terms()
        self._refresh_tab_bar(self._active_id)

    def select_tab(self, collection_id: int) -> None:
        if collection_id == self._active_id:
            return
        self._show(collection_id)

    def next_tab(self, offset: int = 1) -> None:
        order = self.tab_bar.tab_order
        if not order:
            return
        index = order.index(self._active_id) if self._active_id in order else -1
        self.select_tab(order[(index + offset) % len(order)])

    def add_tab(self) -> None:
        answer = ask_new_tab(self, taken=[c.label for c in self._collections.list_collections()])
        if not answer:
            return
        label, noun, template_key = answer
        try:
            created = self._collections.add_collection(label, noun, template_key)
        except ServiceError as exc:
            messagebox.showerror("Can't add tab", str(exc), parent=self)
            return
        self._refresh_tab_bar(created.id)
        self._show(created.id)
        self.refresh_terms()

    def rename_tab(self, collection_id: int) -> None:
        current = self._collections.get_collection(collection_id)
        others = [c.label for c in self._collections.list_collections() if c.id != collection_id]
        name = ask_name(self, "Rename Tab", "Tab name", current.label, taken=others)
        if not name:
            return
        try:
            renamed = self._collections.rename_collection(collection_id, name)
        except ServiceError as exc:
            messagebox.showerror("Can't rename tab", str(exc), parent=self)
            return
        if collection_id in self._pages:
            self._pages[collection_id].update_collection(renamed)
        self._refresh_tab_bar(self._active_id)
        self.refresh_terms()

    def delete_tab(self, collection_id: int) -> None:
        collection = self._collections.get_collection(collection_id)
        count = self._collections.count_entries(collection_id)
        noun = "entry" if count == 1 else "entries"
        confirmed = messagebox.askyesno(
            "Move tab to Trash?",
            f"Move the tab \u201c{collection.label}\u201d and its {count} {noun} to the Trash? "
            f"You can restore it from the Trash for {RETENTION_DAYS} days.",
            parent=self)
        if not confirmed:
            return
        order = self.tab_bar.tab_order
        neighbour = None
        if collection_id in order:
            index = order.index(collection_id)
            others = [cid for cid in order if cid != collection_id]
            neighbour = others[min(index, len(others) - 1)] if others else None
        if self._adjust_for == collection_id:
            self._close_adjust_window()
        self._collections.trash_collection(collection_id)
        self.refresh_terms()
        self._update_trash_count()
        page = self._pages.pop(collection_id, None)
        if page is not None:
            page.destroy()
        if self._active_id == collection_id:
            self._active_id = None
        target = self._active_id if self._active_id is not None else neighbour
        self._refresh_tab_bar(target)
        self._show(target)

    def adjust_fields(self, collection_id: int | None = None) -> None:
        collection_id = self._active_id if collection_id is None else collection_id
        if collection_id is None:
            return
        page = self.page_for(collection_id)
        if page.editing:
            messagebox.showinfo(
                "Finish editing first",
                "Save or cancel the entry you are editing before adjusting fields.",
                parent=self)
            return
        existing = self.adjust_window
        if existing is not None and self._adjust_for == collection_id:
            existing.lift()
            existing.focus_force()
            return
        self._close_adjust_window()
        self._adjust_for = collection_id
        self._adjust_window = AdjustFieldsView(
            self, page.categories, on_changed=page.fields_changed,
            heading=f"Adjust Fields: {page.collection.label}")

    def open_trash(self) -> None:
        TrashDialog(self, TrashService(self._db.connection), on_changed=self._trash_changed)

    def new_project(self) -> None:
        if not self._confirm_discard_all():
            return
        name = ask_name(self, "New Project", "Project name")
        if not name:
            return
        parent = filedialog.askdirectory(
            parent=self, title="Choose where to create the project",
            initialdir=str(self._project.root.parent))
        if not parent:
            return
        try:
            created = self._projects.create_project(Path(parent), name)
        except ServiceError as exc:
            messagebox.showerror("Can't create project", str(exc), parent=self)
            return
        self.open_project(created.root, confirm=False)

    def load_project(self) -> None:
        if not self._confirm_discard_all():
            return
        folder = filedialog.askdirectory(
            parent=self, title="Load Project", initialdir=str(self._project.root.parent))
        if folder:
            self.open_project(Path(folder), confirm=False)

    def open_project(self, folder, confirm: bool = True) -> bool:
        if confirm and not self._confirm_discard_all():
            return False
        try:
            project = self._projects.locate_project(folder)
            if project.root == self._project.root:
                return True
            self._db.open(project.db_path)
        except (ServiceError, DatabaseError) as exc:
            messagebox.showerror("Can't open project", str(exc), parent=self)
            return False
        self._close_adjust_window()
        self._project = project
        self._load_project_views()
        self._remember_project()
        return True

    def set_theme(self, name: str) -> None:
        if name not in theme.PALETTES:
            raise KeyError(name)
        if name == theme.current_palette():
            self._theme_var.set(name)
            return
        if not self._confirm_discard_all():
            self._theme_var.set(theme.current_palette())
            return
        active = self._active_id
        selected = {cid: page.selected_entity_id for cid, page in self._pages.items()}
        self._close_adjust_window()
        theme.apply_palette(name)
        self._theme_var.set(name)
        self.configure(fg_color=theme.BACKGROUND)
        self._style_menus()
        self._build_chrome()
        self._load_project_views(active_id=active)
        for collection_id, entity_id in selected.items():
            if entity_id is not None and collection_id in self._collections_by_id():
                page = self.page_for(collection_id)
                page.card.show_entity(entity_id)
                page.sidebar.set_selected(page.card.entity_id)
        if self._theme_file is not None:
            remember_theme(self._theme_file, name)

    def exit_app(self) -> None:
        if not self._confirm_discard_all():
            return
        self.shutdown()
        self.destroy()

    def shutdown(self) -> None:
        self._close_adjust_window()
        self._db.close()

    def _collections_by_id(self):
        return {c.id: c for c in self._collections.list_collections()}

    def _build_menu(self) -> None:
        self._menubar = tk.Menu(self)
        self.file_menu = tk.Menu(self._menubar)
        self.file_menu.add_command(label="New Project...", command=self.new_project)
        self.file_menu.add_command(label="Load Project...", command=self.load_project)
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

    def _build_chrome(self) -> None:
        for widget in (self.tab_bar, self._content):
            if widget is not None:
                widget.destroy()
        self._pages = {}
        self._active_id = None
        self.tab_bar = TabBar(
            self, on_select=self.select_tab, on_add=self.add_tab, on_rename=self.rename_tab,
            on_adjust=self.adjust_fields, on_delete=self.delete_tab, on_trash=self.open_trash,
            on_color=self.change_color)
        self.tab_bar.grid(row=0, column=0, sticky="ew")
        self.global_search = GlobalSearch(
            self, self.tab_bar.search_entry, lambda: self.terms, self.open_entry)
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color=theme.BACKGROUND)
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)
        self._empty_label = ctk.CTkLabel(
            self._content, text="No tabs yet.\nClick + above to add one.",
            font=theme.font("placeholder"), text_color=theme.TEXT_MUTED, justify="center")
        self._empty_label.grid(row=0, column=0)

    def _bind_tab_keys(self) -> None:
        for sequence in ("<Control-k>", "<Control-K>"):
            self.bind(sequence, lambda _event: (self.focus_search(), "break")[1])
        self.bind("<Control-Tab>", lambda _event: (self.next_tab(1), "break")[1])
        for sequence in ("<Control-ISO_Left_Tab>", "<Control-Shift-Tab>"):
            try:
                self.bind(sequence, lambda _event: (self.next_tab(-1), "break")[1])
            except tk.TclError:
                pass

    def _load_project_views(self, active_id: int | None = None) -> None:
        for page in self._pages.values():
            page.destroy()
        self._pages = {}
        self._active_id = None
        TrashService(self._db.connection).purge_expired()
        self._collections = CollectionService(self._db.connection)
        self.terms = TermIndex(self._db.connection)
        collections = self._collections.list_collections()
        ids = [c.id for c in collections]
        target = active_id if active_id in ids else (ids[0] if ids else None)
        self.tab_bar.set_tabs(collections, target)
        self._show(target)
        self._update_trash_count()
        self.title(f"{APP_TITLE} - {self._project.name}")

    def _update_trash_count(self) -> None:
        self.tab_bar.set_trash_count(TrashService(self._db.connection).count())

    def _trash_changed(self) -> None:
        collections = self._collections.list_collections()
        ids = [c.id for c in collections]
        active = self._active_id if self._active_id in ids else (ids[0] if ids else None)
        self._refresh_tab_bar(active)
        if active != self._active_id:
            self._show(active)
        for page in self._pages.values():
            page.fields_changed()
        self.refresh_terms()
        self._update_trash_count()

    def _refresh_tab_bar(self, active_id: int | None) -> None:
        self.tab_bar.set_tabs(self._collections.list_collections(), active_id)

    def _show(self, collection_id: int | None) -> None:
        current = self.active_page
        if current is not None:
            current.grid_remove()
        self._active_id = collection_id
        self.tab_bar.set_active(collection_id)
        if collection_id is None:
            self._empty_label.grid()
            return
        self._empty_label.grid_remove()
        self.page_for(collection_id).grid()

    def _confirm_discard_all(self) -> bool:
        if not any(page.editing for page in self._pages.values()):
            return True
        return messagebox.askyesno(
            "Discard changes?", "You have unsaved changes. Discard them?", parent=self)

    def _close_adjust_window(self) -> None:
        window = self.adjust_window
        self._adjust_window = None
        self._adjust_for = None
        if window is not None:
            window.destroy()

    def _remember_project(self) -> None:
        if self._settings_file is not None:
            remember_project(self._settings_file, self._project.root)
