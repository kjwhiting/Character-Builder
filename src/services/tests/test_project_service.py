from pathlib import Path

import pytest

from src.database.connection import ProjectDatabase
from src.services.category_service import CategoryService
from src.services.collection_service import CollectionService
from src.services.errors import (
    InvalidNameError,
    InvalidProjectError,
    ProjectCreationError,
    ProjectExistsError,
)
from src.services.project_service import (
    DEFAULT_PROJECT_NAME,
    IMAGES_DIRNAME,
    LAST_PROJECT_FILE_NAME,
    PROJECT_DB_NAME,
    ProjectService,
    recall_project,
    remember_project,
)


@pytest.fixture
def service():
    return ProjectService()


class TestCreatingAProject:
    def test_a_project_is_a_folder_with_a_database_and_an_images_folder(self, service, tmp_path):
        project = service.create_project(tmp_path, "Saga")

        assert project.root == (tmp_path / "Saga").resolve()
        assert (project.root / PROJECT_DB_NAME).is_file()
        assert (project.root / IMAGES_DIRNAME).is_dir()
        assert project.db_path == project.root / PROJECT_DB_NAME
        assert project.images_dir == project.root / IMAGES_DIRNAME

    def test_the_project_takes_its_name_from_the_folder(self, service, tmp_path):
        assert service.create_project(tmp_path, "Saga").name == "Saga"

    def test_the_name_is_trimmed(self, service, tmp_path):
        service.create_project(tmp_path, "  Saga  ")

        assert (tmp_path / "Saga").is_dir()

    def test_it_starts_with_six_tabs_in_a_fixed_order(self, service, tmp_path):
        project = service.create_project(tmp_path, "Saga")

        with ProjectDatabase() as database:
            database.open(project.db_path)
            tabs = CollectionService(database.connection).list_collections()

        assert [t.label for t in tabs] == [
            "Characters", "Magic", "Places", "Items", "Events", "Dictionary"]
        assert [t.entry_noun for t in tabs] == [
            "Character", "Spell", "Place", "Item", "Event", "Word"]

    def test_every_starter_tab_has_its_own_colour(self, service, tmp_path):
        project = service.create_project(tmp_path, "Saga")

        with ProjectDatabase() as database:
            database.open(project.db_path)
            tabs = CollectionService(database.connection).list_collections()

        assert len({t.color for t in tabs}) == 6

    def test_starter_tabs_have_no_fields_for_the_creator_to_decide(self, service, tmp_path):
        project = service.create_project(tmp_path, "Saga")

        with ProjectDatabase() as database:
            database.open(project.db_path)
            tab = CollectionService(database.connection).list_collections()[0]

            assert CategoryService(database.connection, tab.id).list_fields() == []

    def test_the_default_project_name_is_my_world(self):
        assert DEFAULT_PROJECT_NAME == "My World"


class TestRefusingBadRequests:
    @pytest.mark.parametrize("name", [
        "", "   ", ".", "..", "ends.", "bad/name", "bad\\name", "what?", "a:b", 'q"q', "a*b",
        "a<b", "a>b", "a|b", "tab\tname"])
    def test_names_a_folder_cannot_have_are_rejected_before_anything_is_created(
        self, service, tmp_path, name
    ):
        with pytest.raises(InvalidNameError):
            service.create_project(tmp_path, name)

        assert list(tmp_path.iterdir()) == []

    def test_an_existing_folder_is_never_touched(self, service, tmp_path):
        existing = tmp_path / "Saga"
        existing.mkdir()
        (existing / "notes.txt").write_text("keep me")

        with pytest.raises(ProjectExistsError):
            service.create_project(tmp_path, "Saga")

        assert [p.name for p in existing.iterdir()] == ["notes.txt"]

    def test_an_existing_file_with_that_name_blocks_creation(self, service, tmp_path):
        (tmp_path / "Saga").write_text("a file")

        with pytest.raises(ProjectExistsError):
            service.create_project(tmp_path, "Saga")

        assert (tmp_path / "Saga").read_text() == "a file"

    def test_a_missing_parent_folder_is_reported(self, service, tmp_path):
        with pytest.raises(ProjectCreationError, match="does not exist"):
            service.create_project(tmp_path / "nowhere", "Saga")

    def test_a_folder_that_cannot_be_made_is_reported(self, service, tmp_path, monkeypatch):
        def refuse(self, *args, **kwargs):
            raise PermissionError("read-only")

        monkeypatch.setattr(Path, "mkdir", refuse)

        with pytest.raises(ProjectCreationError, match="Could not create project folder"):
            service.create_project(tmp_path, "Saga")

    def test_a_failure_halfway_removes_the_partial_project(self, service, tmp_path, monkeypatch):
        def explode(self, *args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(CollectionService, "add_from_template", explode)

        with pytest.raises(ProjectCreationError, match="disk full"):
            service.create_project(tmp_path, "Saga")

        assert list(tmp_path.iterdir()) == []


class TestFindingAProject:
    def test_a_project_folder_is_recognised(self, service, tmp_path):
        created = service.create_project(tmp_path, "Saga")

        assert service.locate_project(created.root) == created

    def test_a_folder_without_a_project_database_is_refused(self, service, tmp_path):
        (tmp_path / "Plain").mkdir()

        with pytest.raises(InvalidProjectError, match="not a Worldbuilder project"):
            service.locate_project(tmp_path / "Plain")

    def test_a_path_that_is_not_a_folder_is_refused(self, service, tmp_path):
        (tmp_path / "file.txt").write_text("x")

        with pytest.raises(InvalidProjectError):
            service.locate_project(tmp_path / "file.txt")

    def test_a_missing_path_is_refused(self, service, tmp_path):
        with pytest.raises(InvalidProjectError):
            service.locate_project(tmp_path / "gone")


class TestRememberingTheLastProject:
    def test_the_last_project_folder_can_be_recalled(self, service, tmp_path):
        project = service.create_project(tmp_path, "Saga")
        settings = tmp_path / LAST_PROJECT_FILE_NAME

        assert remember_project(settings, project.root) is True
        assert recall_project(settings) == project.root

    def test_nothing_is_recalled_before_anything_was_remembered(self, tmp_path):
        assert recall_project(tmp_path / LAST_PROJECT_FILE_NAME) is None

    def test_an_empty_settings_file_recalls_nothing(self, tmp_path):
        settings = tmp_path / LAST_PROJECT_FILE_NAME
        settings.write_text("")

        assert recall_project(settings) is None

    def test_a_remembered_folder_that_no_longer_holds_a_project_is_ignored(self, service, tmp_path):
        project = service.create_project(tmp_path, "Saga")
        settings = tmp_path / LAST_PROJECT_FILE_NAME
        remember_project(settings, project.root)
        (project.root / PROJECT_DB_NAME).unlink()

        assert recall_project(settings) is None

    def test_remembering_into_an_unwritable_place_reports_failure(self, tmp_path):
        assert remember_project(tmp_path / "missing" / "settings.txt", tmp_path) is False
