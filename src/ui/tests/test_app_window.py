import tkinter as tk

import pytest

from src.database import seeds
from src.database.connection import DatabaseConnection
from src.ui import adjust_fields_view, app_window, card_view
from src.ui.adjust_fields_view import AdjustFieldsView
from src.ui.app_window import AppWindow, template_for_path
from src.ui.tests.helpers import label_texts


class FakeFileDialog:
    def __init__(self):
        self.open_path = ""
        self.directory = ""
        self.calls = []

    def askopenfilename(self, **kwargs):
        self.calls.append(("open", kwargs))
        return self.open_path

    def askdirectory(self, **kwargs):
        self.calls.append(("directory", kwargs))
        return self.directory


def make_profile(path, template):
    database = DatabaseConnection()
    database.open(path, create=True, template=template)
    database.close()
    return path


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def files():
    return FakeFileDialog()


@pytest.fixture
def app(workspace, dialogs, files, monkeypatch):
    monkeypatch.setattr(app_window, "messagebox", dialogs)
    monkeypatch.setattr(app_window, "filedialog", files)
    monkeypatch.setattr(adjust_fields_view, "messagebox", dialogs)
    monkeypatch.setattr(card_view, "messagebox", dialogs)
    database = DatabaseConnection()
    database.open(workspace / "Characters.sqlite", create=True, template=seeds.CHARACTER_TEMPLATE)
    try:
        window = AppWindow(database, settings_file=workspace / "last_profile.txt")
    except tk.TclError:
        database.close()
        pytest.skip("no display available")
    window.withdraw()
    yield window
    try:
        window.shutdown()
        window.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def name_answer(monkeypatch):
    def set_answer(value):
        monkeypatch.setattr(app_window, "ask_name", lambda *args, **kwargs: value)
        monkeypatch.setattr(adjust_fields_view, "ask_name", lambda *args, **kwargs: value)

    return set_answer


def add_entity(app, name, **values):
    return app._entities.create_entity(name, "Character", values=values)


def entity_names(app):
    return [entity.name for entity in app.sidebar.visible_entities()]


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Characters.sqlite", "characters"),
        ("Character.sqlite", "characters"),
        ("Worldbuilding.sqlite", "worldbuilding"),
        ("Places.sqlite", "worldbuilding"),
    ],
)
def test_template_for_path_matches_the_profile_kind(filename, expected):
    assert template_for_path(filename)["key"] == expected


def test_template_for_path_is_none_for_unknown_kinds_and_returns_copies():
    assert template_for_path("Factions.sqlite") is None
    first, second = template_for_path("Characters.sqlite"), template_for_path("Characters.sqlite")
    first["categories"].clear()
    assert second["categories"]


def test_window_assembles_sidebar_and_card_for_the_open_profile(app):
    app.update_idletasks()

    assert app.title() == "Character Builder - Characters"
    assert app.sidebar.add_button.cget("text") == "Add Character"
    assert app.card.entity_id is None
    assert any("Select a character" in text for text in label_texts(app.card))
    assert app.sidebar.winfo_manager() == "grid" and app.card.winfo_manager() == "grid"
    assert int(app.sidebar.grid_info()["column"]) < int(app.card.grid_info()["column"])


def test_file_menu_offers_the_three_actions_and_exit(app):
    assert app.menu_labels == ["New Project...", "Load Profile...", "Adjust Fields...", "Exit"]


def test_startup_remembers_the_profile(app, workspace):
    assert (workspace / "last_profile.txt").read_text() == str(app.database.path)


def test_selecting_an_entry_shows_its_card_and_highlights_it(app):
    first = add_entity(app, "Aria")
    second = add_entity(app, "Bram")
    app.sidebar.refresh()

    app.sidebar.entity_buttons[second].invoke()

    assert app.card.entity_id == second
    assert app.sidebar.selected_id == second
    assert "Bram" in label_texts(app.card)
    assert first != second


def test_add_button_opens_a_blank_form_for_the_profile_noun(app):
    app.sidebar.add_button.invoke()

    assert app.card.editing
    assert "New Character" in label_texts(app.card)


def test_saving_a_new_entry_lists_and_selects_it(app):
    app.sidebar.add_button.invoke()
    app.card.name_entry.insert(0, "Aria")

    app.card.save()

    assert entity_names(app) == ["Aria"]
    assert app.sidebar.selected_id == app.card.entity_id


def test_deleting_an_entry_clears_selection_and_list(app):
    entity_id = add_entity(app, "Aria")
    app.sidebar.refresh()
    app.select_entity(entity_id)
    app.card.start_edit()

    app.card.delete()

    assert entity_names(app) == []
    assert app.sidebar.selected_id is None
    assert app.card.entity_id is None


def test_duplicating_lists_both_and_selects_the_copy(app):
    entity_id = add_entity(app, "Aria")
    app.sidebar.refresh()
    app.select_entity(entity_id)

    app.card.action_buttons["Duplicate"].invoke()

    assert entity_names(app) == ["Aria", "Aria (Copy)"]
    assert app.sidebar.selected_id == app.card.entity_id != entity_id


def test_switching_entries_while_editing_asks_before_discarding(app, dialogs):
    first = add_entity(app, "Aria")
    second = add_entity(app, "Bram")
    app.sidebar.refresh()
    app.select_entity(first)
    app.card.start_edit()
    dialogs.answer = False

    app.select_entity(second)

    assert app.card.editing and app.card.entity_id == first
    assert dialogs.kinds() == ["askyesno"]

    dialogs.answer = True
    app.select_entity(second)

    assert not app.card.editing and app.card.entity_id == second


def test_add_while_editing_asks_before_discarding(app, dialogs):
    app.sidebar.add_button.invoke()
    dialogs.answer = False

    app.add_entity()

    assert dialogs.kinds() == ["askyesno"]
    assert app.card.editing


def test_load_profile_switches_data_labels_and_images_folder(app, workspace, files):
    add_entity(app, "Aria")
    other = make_profile(workspace / "Worldbuilding.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    files.open_path = str(other)

    app.invoke_menu("Load Profile...")

    assert app.database.path == other.resolve()
    assert app.title() == "Character Builder - Worldbuilding"
    assert app.sidebar.add_button.cget("text") == "Add Place"
    assert entity_names(app) == []
    assert app.card._images_dir == workspace / "images"
    assert (workspace / "last_profile.txt").read_text() == str(other.resolve())
    assert any("Geography" in label for label in app.sidebar.filter_labels)


def test_services_keep_working_after_a_profile_switch(app, workspace, files):
    other = make_profile(workspace / "Places.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    files.open_path = str(other)
    app.invoke_menu("Load Profile...")

    app.sidebar.add_button.invoke()
    app.card.name_entry.insert(0, "Old Mill")
    app.card.save()

    assert entity_names(app) == ["Old Mill"]


def test_data_is_kept_when_switching_back(app, workspace, files):
    add_entity(app, "Aria")
    original = app.database.path
    other = make_profile(workspace / "Places.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    files.open_path = str(other)
    app.invoke_menu("Load Profile...")

    files.open_path = str(original)
    app.invoke_menu("Load Profile...")

    assert entity_names(app) == ["Aria"]


def test_load_profile_cancelled_changes_nothing(app, files):
    sidebar = app.sidebar
    files.open_path = ""

    app.invoke_menu("Load Profile...")

    assert app.sidebar is sidebar


def test_loading_the_active_profile_keeps_the_current_views(app, files):
    sidebar = app.sidebar
    files.open_path = str(app.database.path)

    app.invoke_menu("Load Profile...")

    assert app.sidebar is sidebar


def test_loading_a_bad_file_reports_the_error_and_keeps_the_current_profile(
    app, workspace, files, dialogs
):
    add_entity(app, "Aria")
    bad = workspace / "notes.sqlite"
    bad.write_text("not a database")
    files.open_path = str(bad)
    original = app.database.path

    app.invoke_menu("Load Profile...")

    assert dialogs.kinds() == ["error"]
    assert app.database.path == original
    app.sidebar.refresh()
    assert entity_names(app) == ["Aria"]


def test_load_profile_while_editing_can_be_declined(app, workspace, files, dialogs):
    other = make_profile(workspace / "Places.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    files.open_path = str(other)
    app.add_entity()
    dialogs.answer = False
    original = app.database.path

    app.invoke_menu("Load Profile...")

    assert app.database.path == original
    assert files.calls == []


def test_new_project_creates_folder_and_opens_its_character_profile(
    app, workspace, files, name_answer
):
    name_answer("Saga")
    projects = workspace / "projects"
    projects.mkdir()
    files.directory = str(projects)

    app.invoke_menu("New Project...")

    root = projects / "Saga"
    assert (root / "images").is_dir()
    assert (root / "Characters.sqlite").is_file()
    assert (root / "Worldbuilding.sqlite").is_file()
    assert app.database.path == (root / "Characters.sqlite").resolve()
    assert app.card._images_dir == root / "images"
    assert "Relations" in [label.split(" / ")[0].replace("Missing: ", "")
                           for label in app.sidebar.filter_labels]


def test_new_project_name_cancelled_does_nothing(app, files, name_answer):
    name_answer(None)

    app.invoke_menu("New Project...")

    assert files.calls == []


def test_new_project_folder_cancelled_does_nothing(app, workspace, files, name_answer):
    name_answer("Saga")
    files.directory = ""

    app.invoke_menu("New Project...")

    assert not (workspace / "Saga").exists()


def test_new_project_with_existing_name_reports_the_problem(
    app, workspace, files, name_answer, dialogs
):
    name_answer("Saga")
    (workspace / "Saga").mkdir()
    files.directory = str(workspace)
    original = app.database.path

    app.invoke_menu("New Project...")

    assert dialogs.kinds() == ["error"]
    assert app.database.path == original


def test_new_project_with_invalid_name_reports_the_problem(
    app, workspace, files, name_answer, dialogs
):
    name_answer("bad/name")
    files.directory = str(workspace)

    app.invoke_menu("New Project...")

    assert dialogs.kinds() == ["error"]


def test_adjust_fields_opens_a_single_modal(app):
    app.invoke_menu("Adjust Fields...")
    first = app.adjust_window
    app.invoke_menu("Adjust Fields...")

    assert isinstance(first, AdjustFieldsView)
    assert app.adjust_window is first


def test_adjust_fields_is_blocked_while_editing(app, dialogs):
    app.add_entity()

    app.invoke_menu("Adjust Fields...")

    assert app.adjust_window is None
    assert dialogs.kinds() == ["info"]


def test_closing_adjust_fields_refreshes_sidebar_filters_and_card(app, name_answer):
    entity_id = add_entity(app, "Aria")
    app.sidebar.refresh()
    app.select_entity(entity_id)
    app.invoke_menu("Adjust Fields...")
    name_answer("Mascot")

    app.adjust_window.add_field("Favorites")
    app.adjust_window.close()

    assert "Missing: Favorites / Mascot" in app.sidebar.filter_labels
    assert app.adjust_window is None
    assert app.card.entity_id == entity_id


def test_closing_adjust_fields_without_changes_leaves_views_alone(app):
    sidebar = app.sidebar
    app.invoke_menu("Adjust Fields...")

    app.adjust_window.close()

    assert app.sidebar is sidebar


def test_switching_profiles_closes_the_adjust_window(app, workspace, files):
    app.invoke_menu("Adjust Fields...")
    other = make_profile(workspace / "Places.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    files.open_path = str(other)

    app.invoke_menu("Load Profile...")

    assert app.adjust_window is None


def test_exit_closes_the_database_and_the_window(app):
    app.invoke_menu("Exit")

    assert not app.database.is_open
    with pytest.raises(tk.TclError):
        app.winfo_exists()


def test_exit_while_editing_can_be_declined(app, dialogs):
    app.add_entity()
    dialogs.answer = False

    app.invoke_menu("Exit")

    assert app.database.is_open
    assert app.winfo_exists()


def test_closing_the_window_uses_the_same_exit_path(app):
    assert app.protocol("WM_DELETE_WINDOW")


def test_shutdown_is_safe_to_repeat(app):
    app.shutdown()
    app.shutdown()

    assert not app.database.is_open
