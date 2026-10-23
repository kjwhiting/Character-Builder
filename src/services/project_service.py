import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from src.database.connection import DatabaseConnection
from src.database.seeds import Template
from src.services.errors import InvalidNameError, ProjectCreationError, ProjectExistsError

IMAGES_DIRNAME = "images"
_FORBIDDEN_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class ProfileSpec:
    label: str
    filename: str


DEFAULT_PROFILES = (
    ProfileSpec("Characters", "Characters.sqlite"),
    ProfileSpec("Worldbuilding", "Worldbuilding.sqlite"),
)

DatabaseInitializer = Callable[[Path, ProfileSpec], None]


def make_initializer(templates: Mapping[str, Template]) -> DatabaseInitializer:
    def initialize(db_path: Path, profile: ProfileSpec) -> None:
        database = DatabaseConnection()
        try:
            database.open(db_path, create=True, template=templates.get(profile.label))
        finally:
            database.close()

    return initialize


@dataclass(frozen=True)
class Project:
    name: str
    root: Path
    images_dir: Path
    databases: Mapping[str, Path]


class ProjectService:
    def __init__(self, initializer: DatabaseInitializer,
                 profiles: Sequence[ProfileSpec] = DEFAULT_PROFILES):
        if not profiles:
            raise ValueError("At least one profile is required.")
        filenames = [profile.filename.lower() for profile in profiles]
        if len(set(filenames)) != len(filenames):
            raise ValueError("Profile filenames must be unique.")
        self._initializer = initializer
        self._profiles = tuple(profiles)

    def create_project(self, parent_dir: Path, name: str) -> Project:
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
            images_dir = root / IMAGES_DIRNAME
            images_dir.mkdir()
            databases = {}
            for profile in self._profiles:
                db_path = root / profile.filename
                self._initializer(db_path, profile)
                databases[profile.label] = db_path
        except Exception as exc:
            shutil.rmtree(root, ignore_errors=True)
            raise ProjectCreationError(f"Could not set up project '{cleaned}': {exc}") from exc

        return Project(name=cleaned, root=root, images_dir=images_dir, databases=databases)

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
