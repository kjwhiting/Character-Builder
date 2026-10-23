import tkinter as tk

import customtkinter as ctk
import pytest

import main
from src.database import seeds
from src.database.connection import DatabaseConnection
from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.export_service import ExportService
from src.ui import adjust_fields_view, app_window, card_view
from src.ui.tests.conftest import FakeMessageBox
from src.ui.tests.helpers import walk

pytestmark = pytest.mark.usefixtures("require_display")


class FakeFileDialog:
    def __init__(self):
        self.open_path = ""
        self.directory = ""

    def askopenfilename(self, **kwargs):
        return self.open_path

    def askdirectory(self, **kwargs):
        return self.directory


class Session:
    def __init__(self, app, dialogs, files, answers):
        self.app = app
        self.dialogs = dialogs
        self.files = files
        self.answers = answers

    def answer_names(self, *names):
        self.answers.clear()
        self.answers.extend(names)

    def field_id(self, category, name):
        for field in self.app._categories.list_fields(category):
            if field.name == name:
                return field.id
        raise AssertionError(f"{category}/{name} not found")

    def fill(self, category, name, text):
        widget, field_type = self.app.card._field_widgets[self.field_id(category, name)]
        if field_type == "text":
            widget.delete(0, "end")
            widget.insert(0, text)
        else:
            widget.delete("1.0", "end")
            widget.insert("1.0", text)

    def sidebar_names(self):
        return [entity.name for entity in self.app.sidebar.visible_entities()]

    def clipboard(self):
        return self.app.clipboard_get()


@pytest.fixture
def session(tmp_path, monkeypatch):
    dialogs, files, answers = FakeMessageBox(), FakeFileDialog(), []
    for module in (app_window, adjust_fields_view, card_view):
        monkeypatch.setattr(module, "messagebox", dialogs)
    monkeypatch.setattr(app_window, "filedialog", files)

    def next_name(*args, **kwargs):
        return answers.pop(0) if answers else None

    monkeypatch.setattr(app_window, "ask_name", next_name)
    monkeypatch.setattr(adjust_fields_view, "ask_name", next_name)

    install = tmp_path / "install"
    install.mkdir()
    app = main.create_app(install)
    app.withdraw()
    yield Session(app, dialogs, files, answers)
    try:
        app.shutdown()
        app.destroy()
    except tk.TclError:
        pass


def create_project(session, tmp_path, name="Saga"):
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    session.answer_names(name)
    session.files.directory = str(projects)
    session.app.invoke_menu("New Project...")
    return projects / name


def add_aria(session):
    app = session.app
    app.sidebar.add_button.invoke()
    app.card.name_entry.insert(0, "Aria")
    session.fill("Description", "Description", "A brave hero")
    session.fill("Relations", "Enemies", "Orc, Troll")
    session.fill("Favorites", "Color", "Teal")
    app.card.save()


def test_full_author_workflow_from_new_project_to_clipboard(session, tmp_path):
    app = session.app

    project_root = create_project(session, tmp_path)
    assert (project_root / "images").is_dir()
    assert app.database.path == (project_root / "Characters.sqlite").resolve()
    assert app.title() == "Character Builder - Characters"
    assert session.sidebar_names() == []

    add_aria(session)
    aria_id = app.card.entity_id
    assert session.sidebar_names() == ["Aria"]
    assert app.sidebar.selected_id == aria_id
    assert "Aria" in [w.cget("text") for w in _labels(app.card)]

    app.card.action_buttons["Duplicate"].invoke()
    copy_id = app.card.entity_id
    assert copy_id != aria_id
    assert session.sidebar_names() == ["Aria", "Aria (Copy)"]
    assert app.sidebar.selected_id == copy_id
    assert app._entities.get_values(copy_id) == app._entities.get_values(aria_id)

    app.invoke_menu("Adjust Fields...")
    adjust = app.adjust_window
    adjust.delete_category("Favorites")
    assert session.dialogs.kinds()[-1] == "warning"
    assert "still has" in session.dialogs.calls[-1][2]
    assert "Favorites" in app._categories.list_categories()

    session.answer_names("Scratch")
    adjust.add_category()
    adjust.delete_category("Scratch")
    assert "Scratch" not in app._categories.list_categories()

    for field in app._categories.list_fields("Favorites"):
        adjust.move_field(field.id, "Description")
    adjust.delete_category("Favorites")
    assert "Favorites" not in app._categories.list_categories()
    adjust.close()
    assert app.adjust_window is None
    assert not any("Favorites" in label for label in app.sidebar.filter_labels)

    app.select_entity(aria_id)
    app.card.action_buttons["Copy"].invoke()

    expected = (
        "Description\nDescription: A brave hero\nColor: Teal\n\n"
        "Relations\nEnemies: Orc, Troll"
    )
    assert session.clipboard() == expected
    assert app.card.action_buttons["Copy"].cget("text") == "Copied \u2713"

    app.shutdown()
    reopened = DatabaseConnection()
    reopened.open(project_root / "Characters.sqlite")
    connection = reopened.connection
    assert [e.name for e in EntityService(connection).list_entities()] == ["Aria", "Aria (Copy)"]
    assert ExportService(connection, lambda text: None).build_plain_text(aria_id) == expected
    assert "Favorites" not in CategoryService(connection).list_categories()
    reopened.close()


def test_project_profiles_keep_separate_data_when_switching(session, tmp_path):
    app = session.app
    project_root = create_project(session, tmp_path)
    add_aria(session)

    session.files.open_path = str(project_root / "Worldbuilding.sqlite")
    app.invoke_menu("Load Profile...")

    assert app.title() == "Character Builder - Worldbuilding"
    assert app.sidebar.add_button.cget("text") == "Add Place"
    assert session.sidebar_names() == []

    app.sidebar.add_button.invoke()
    app.card.name_entry.insert(0, "Old Mill")
    session.fill("Geography", "Landmarks", "Bridge\nWell")
    app.card.save()
    app.card.action_buttons["Copy"].invoke()
    assert session.clipboard() == "Geography\nLandmarks: Bridge, Well"

    session.files.open_path = str(project_root / "Characters.sqlite")
    app.invoke_menu("Load Profile...")

    assert session.sidebar_names() == ["Aria"]
    assert app.sidebar.add_button.cget("text") == "Add Character"


def test_missing_field_filter_finds_entries_to_complete(session, tmp_path):
    app = session.app
    create_project(session, tmp_path)
    add_aria(session)
    app.sidebar.add_button.invoke()
    app.card.name_entry.insert(0, "Bram")
    session.fill("Favorites", "Food", "Soup")
    app.card.save()

    app.sidebar.select_filter("Missing: Favorites / Color")

    assert session.sidebar_names() == ["Bram"]


def test_editing_cancelling_and_deleting_keep_everything_consistent(
    session, tmp_path
):
    app = session.app
    create_project(session, tmp_path)
    add_aria(session)
    aria_id = app.card.entity_id

    app.card.start_edit()
    session.fill("Favorites", "Color", "Crimson")
    app.card.cancel()
    assert app._entities.get_values(aria_id)[session.field_id("Favorites", "Color")] == "Teal"

    app.card.start_edit()
    app.card.name_entry.delete(0, "end")
    app.card.save()
    assert session.dialogs.kinds()[-1] == "warning"
    assert app.card.editing
    app.card.cancel()

    app.card.start_edit()
    app.card.delete()

    assert session.sidebar_names() == []
    assert app.sidebar.selected_id is None
    assert app.card.entity_id is None


def test_leaving_an_unsaved_edit_requires_confirmation(session, tmp_path):
    app = session.app
    create_project(session, tmp_path)
    add_aria(session)
    app.card.start_edit()
    session.dialogs.answer = False

    app.invoke_menu("Exit")

    assert app.database.is_open and app.card.editing

    session.dialogs.answer = True
    app.invoke_menu("Exit")

    assert not app.database.is_open


def _labels(widget):
    return [w for w in walk(widget) if isinstance(w, ctk.CTkLabel)]
