import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from src.database.connection import (
    LAST_PROFILE_FILE_NAME,
    DatabaseConnection,
    ProfileError,
    resolve_startup_profile,
)
from src.ui import theme
from src.ui.app_window import THEME_FILE_NAME, AppWindow, recall_theme, template_for_path


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def show_startup_error(message: str) -> None:
    window = tk.Tk()
    window.withdraw()
    try:
        messagebox.showerror("Character Builder can't start", message, parent=window)
    finally:
        window.destroy()


def create_app(base_dir: Path) -> AppWindow:
    theme.apply_palette(recall_theme(base_dir / THEME_FILE_NAME) or theme.DEFAULT_PALETTE)
    database = DatabaseConnection()
    path = resolve_startup_profile(base_dir)
    database.open(path, create=True, template=template_for_path(path))
    try:
        return AppWindow(database, settings_file=base_dir / LAST_PROFILE_FILE_NAME)
    except BaseException:
        database.close()
        raise


def main() -> int:
    try:
        app = create_app(application_dir())
    except ProfileError as exc:
        show_startup_error(str(exc))
        return 1
    try:
        app.mainloop()
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
