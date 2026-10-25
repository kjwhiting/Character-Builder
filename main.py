import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from src.database.connection import DatabaseError, ProjectDatabase
from src.services.errors import ServiceError
from src.services.project_service import (
    DEFAULT_PROJECT_NAME,
    LAST_PROJECT_FILE_NAME,
    Project,
    ProjectService,
    recall_project,
)
from src.ui import theme
from src.ui.app_window import THEME_FILE_NAME, AppWindow, recall_theme


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def show_startup_error(message: str) -> None:
    window = tk.Tk()
    window.withdraw()
    try:
        messagebox.showerror("Worldbuilder can't start", message, parent=window)
    finally:
        window.destroy()


def choose_startup_project(base_dir: Path, service: ProjectService) -> Project:
    recalled = recall_project(base_dir / LAST_PROJECT_FILE_NAME)
    if recalled is not None:
        try:
            return service.locate_project(recalled)
        except ServiceError:
            pass
    default = base_dir / DEFAULT_PROJECT_NAME
    if default.exists():
        return service.locate_project(default)
    return service.create_project(base_dir, DEFAULT_PROJECT_NAME)


def create_app(base_dir: Path) -> AppWindow:
    theme.apply_palette(recall_theme(base_dir / THEME_FILE_NAME) or theme.DEFAULT_PALETTE)
    service = ProjectService()
    project = choose_startup_project(base_dir, service)
    database = ProjectDatabase()
    database.open(project.db_path)
    try:
        return AppWindow(
            database, project, settings_file=base_dir / LAST_PROJECT_FILE_NAME,
            project_service=service)
    except BaseException:
        database.close()
        raise


def main() -> int:
    try:
        app = create_app(application_dir())
    except (DatabaseError, ServiceError) as exc:
        show_startup_error(str(exc))
        return 1
    try:
        app.mainloop()
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
