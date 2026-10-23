import sqlite3
import sys

import customtkinter as ctk
import pytest

import main
from src.database import seeds
from src.database.connection import (
    LAST_PROFILE_FILE_NAME,
    DatabaseConnection,
    remember_profile,
)
from src.ui import theme
from src.ui.app_window import THEME_FILE_NAME, AppWindow

pytestmark = pytest.mark.usefixtures("require_display")


@pytest.fixture
def started(tmp_path):
    windows = []

    def start(base_dir=None):
        window = main.create_app(base_dir or tmp_path)
        window.withdraw()
        windows.append(window)
        return window

    yield start
    for window in windows:
        try:
            window.shutdown()
            window.destroy()
        except Exception:
            pass


def category_names(database_path):
    connection = sqlite3.connect(str(database_path))
    try:
        return [row[0] for row in connection.execute("SELECT name FROM categories ORDER BY sort_order, id")]
    finally:
        connection.close()


def test_application_dir_is_the_folder_holding_main():
    assert main.application_dir() == main.Path(main.__file__).resolve().parent


def test_application_dir_follows_the_executable_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "CharacterBuilder.exe"))

    assert main.application_dir() == tmp_path.resolve()


def test_first_launch_creates_and_seeds_the_default_character_profile(started, tmp_path):
    window = started()

    assert isinstance(window, AppWindow)
    assert window.database.is_open
    assert window.database.path.parent == tmp_path.resolve()
    assert category_names(window.database.path) == [
        category["name"] for category in seeds.CHARACTER_TEMPLATE["categories"]
    ]
    assert window.sidebar.add_button.cget("text") == "Add Character"


def test_launch_records_the_profile_for_next_time(started, tmp_path):
    window = started()

    assert (tmp_path / LAST_PROFILE_FILE_NAME).read_text() == str(window.database.path)


def test_second_launch_reopens_the_remembered_profile(started, tmp_path):
    other = tmp_path / "Worldbuilding.sqlite"
    seeded = DatabaseConnection()
    seeded.open(other, create=True, template=seeds.WORLDBUILDING_TEMPLATE)
    seeded.close()
    remember_profile(tmp_path / LAST_PROFILE_FILE_NAME, other)

    window = started()

    assert window.database.path == other.resolve()
    assert window.sidebar.add_button.cget("text") == "Add Place"
    assert not (tmp_path / "Character.sqlite").exists()


def test_create_app_uses_the_dark_appearance(started):
    started()

    assert ctk.get_appearance_mode() == "Dark"


def test_unreadable_profile_raises_before_any_window_exists(tmp_path):
    (tmp_path / "Character.sqlite").write_text("not a database")

    with pytest.raises(main.ProfileError):
        main.create_app(tmp_path)


def test_main_runs_the_event_loop_then_closes_the_database(monkeypatch, tmp_path):
    created = []
    real_create = main.create_app

    def create(base_dir):
        window = real_create(base_dir)
        window.withdraw()
        created.append(window)
        return window

    loops = []
    monkeypatch.setattr(main, "application_dir", lambda: tmp_path)
    monkeypatch.setattr(main, "create_app", create)
    monkeypatch.setattr(AppWindow, "mainloop", lambda self, n=0: loops.append(self))

    assert main.main() == 0

    assert loops == created
    assert not created[0].database.is_open
    created[0].destroy()


def test_main_reports_startup_failures_and_returns_an_error_code(monkeypatch, tmp_path):
    (tmp_path / "Character.sqlite").write_text("not a database")
    shown = []
    monkeypatch.setattr(main, "application_dir", lambda: tmp_path)
    monkeypatch.setattr(main, "show_startup_error", shown.append)

    assert main.main() == 1

    assert len(shown) == 1 and shown[0]


def test_remembered_light_theme_is_applied_at_launch(started, tmp_path):
    (tmp_path / THEME_FILE_NAME).write_text("light")

    window = started()

    assert theme.current_palette() == "light"
    assert ctk.get_appearance_mode() == "Light"
    assert window.cget("fg_color") == theme.PALETTES["light"]["BACKGROUND"]


def test_unrecognised_saved_theme_falls_back_to_dark(started, tmp_path):
    (tmp_path / THEME_FILE_NAME).write_text("neon")

    started()

    assert theme.current_palette() == "dark"


def test_choosing_light_in_the_menu_persists_to_the_next_launch(started, tmp_path):
    first = started()
    first.invoke_menu("Light Theme")
    first.shutdown()
    first.destroy()

    second = started()

    assert theme.current_palette() == "light"
    assert second._theme_var.get() == "light"
