import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.database.connection import ProjectDatabase
from src.database.seeds import DEFAULT_PROJECT_TEMPLATE_KEYS, get_template
from src.services.collection_service import CollectionService
from src.services.errors import (
    InvalidNameError,
    InvalidProjectError,
    ProjectCreationError,
    ProjectExistsError,
)

PROJECT_DB_NAME = "project.sqlite"
IMAGES_DIRNAME = "images"
DEFAULT_PROJECT_NAME = "My World"
LAST_PROJECT_FILE_NAME = "last_project.txt"
_FORBIDDEN_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class Project:
    name: str
    root: Path
    db_path: Path
    images_dir: Path


class ProjectService:
    def create_project(self, parent_dir, name: str) -> Project:
        cleaned = self._validate_name(name)
        parent = Path(parent_dir)
        if not parent.is_dir():
            raise ProjectCreationError(f"Parent folder does not exist: {parent}")
        root = parent / cleaned
        if root.exists():
            raise ProjectExistsError(f"A file or folder named '{cleaned}' already exists here.")
        try:
            root.mkdir()
        except OSError as exc:
            raise ProjectCreationError(f"Could not create project folder: {exc}") from exc

        try:
            (root / IMAGES_DIRNAME).mkdir()
            with ProjectDatabase() as database:
                database.open(root / PROJECT_DB_NAME, create=True)
                collections = CollectionService(database.connection)
                for key in DEFAULT_PROJECT_TEMPLATE_KEYS:
                    collections.add_from_template(get_template(key))
        except Exception as exc:
            shutil.rmtree(root, ignore_errors=True)
            raise ProjectCreationError(f"Could not set up project '{cleaned}': {exc}") from exc
        return self.locate_project(root)

    def locate_project(self, folder) -> Project:
        root = Path(folder).resolve()
        db_path = root / PROJECT_DB_NAME
        if not root.is_dir() or not db_path.is_file():
            raise InvalidProjectError(
                f"'{root.name}' is not a Worldbuilder project (no {PROJECT_DB_NAME} found).")
        return Project(name=root.name, root=root, db_path=db_path,
                       images_dir=root / IMAGES_DIRNAME)

    @staticmethod
    def _validate_name(name):
        cleaned = (name or "").strip()
        if not cleaned:
            raise InvalidNameError("Project name cannot be empty.")
        if cleaned in (".", "..") or cleaned.endswith("."):
            raise InvalidNameError("Project name cannot be '.', '..', or end with a period.")
        if _FORBIDDEN_NAME_CHARS.search(cleaned):
            raise InvalidNameError('Project name cannot contain any of < > : " / \\ | ? * .')
        return cleaned


def remember_project(settings_file, folder) -> bool:
    try:
        Path(settings_file).write_text(str(Path(folder).resolve()), encoding="utf-8")
    except OSError:
        return False
    return True


def recall_project(settings_file) -> Path | None:
    try:
        text = Path(settings_file).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    folder = Path(text) if text else None
    if folder is not None and (folder / PROJECT_DB_NAME).is_file():
        return folder
    return None
