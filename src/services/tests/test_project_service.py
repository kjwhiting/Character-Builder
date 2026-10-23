import sqlite3

import pytest

from src.services.errors import InvalidNameError, ProjectCreationError, ProjectExistsError
from src.services.project_service import (
    DEFAULT_PROFILES,
    ProfileSpec,
    ProjectService,
    make_initializer,
)


def sqlite_initializer(db_path, profile):
    connection = sqlite3.connect(str(db_path))
    try:
        with connection:
            connection.execute("CREATE TABLE profile (label TEXT)")
            connection.execute("INSERT INTO profile VALUES (?)", (profile.label,))
    finally:
        connection.close()


@pytest.fixture
def service():
    return ProjectService(sqlite_initializer)


def test_creates_project_folder_with_images_subfolder(service, tmp_path):
    project = service.create_project(tmp_path, "My Saga")

    assert project.root == tmp_path / "My Saga"
    assert project.root.is_dir()
    assert project.images_dir == project.root / "images"
    assert project.images_dir.is_dir()


def test_creates_and_seeds_one_database_per_default_profile(service, tmp_path):
    project = service.create_project(tmp_path, "My Saga")

    assert set(project.databases) == {profile.label for profile in DEFAULT_PROFILES}
    for profile in DEFAULT_PROFILES:
        path = project.databases[profile.label]
        assert path == project.root / profile.filename
        connection = sqlite3.connect(str(path))
        try:
            assert connection.execute("SELECT label FROM profile").fetchone() == (profile.label,)
        finally:
            connection.close()


def test_initializer_receives_each_profile_in_order(tmp_path):
    received = []

    def recording(db_path, profile):
        received.append((db_path.name, profile.label))
        db_path.touch()

    ProjectService(recording).create_project(tmp_path, "Saga")

    assert received == [("Characters.sqlite", "Characters"), ("Worldbuilding.sqlite", "Worldbuilding")]


def test_custom_profiles_replace_the_defaults(tmp_path):
    profiles = [ProfileSpec("Factions", "factions.sqlite")]

    project = ProjectService(sqlite_initializer, profiles).create_project(tmp_path, "Saga")

    assert list(project.databases) == ["Factions"]
    assert sorted(p.name for p in project.root.iterdir()) == ["factions.sqlite", "images"]


def test_project_name_is_trimmed(service, tmp_path):
    project = service.create_project(tmp_path, "  Saga  ")

    assert project.name == "Saga"
    assert (tmp_path / "Saga").is_dir()


def test_existing_folder_is_never_touched(service, tmp_path):
    existing = tmp_path / "Saga"
    existing.mkdir()
    (existing / "notes.txt").write_text("keep me")

    with pytest.raises(ProjectExistsError):
        service.create_project(tmp_path, "Saga")

    assert [p.name for p in existing.iterdir()] == ["notes.txt"]


def test_existing_file_with_same_name_blocks_creation(service, tmp_path):
    (tmp_path / "Saga").write_text("a file")

    with pytest.raises(ProjectExistsError):
        service.create_project(tmp_path, "Saga")

    assert (tmp_path / "Saga").read_text() == "a file"


@pytest.mark.parametrize(
    "name", ["", "   ", ".", "..", "bad/name", "bad\\name", "what?", "a:b", "ends.", 'q"q', "a*b"]
)
def test_invalid_names_are_rejected_before_anything_is_created(service, tmp_path, name):
    with pytest.raises(InvalidNameError):
        service.create_project(tmp_path, name)

    assert list(tmp_path.iterdir()) == []


def test_missing_parent_folder_is_reported(service, tmp_path):
    with pytest.raises(ProjectCreationError):
        service.create_project(tmp_path / "nowhere", "Saga")

    assert list(tmp_path.iterdir()) == []


def test_failed_seeding_removes_the_partial_project(tmp_path):
    def failing_on_second(db_path, profile):
        if profile.label == "Worldbuilding":
            raise sqlite3.OperationalError("disk full")
        db_path.touch()

    service = ProjectService(failing_on_second)

    with pytest.raises(ProjectCreationError) as caught:
        service.create_project(tmp_path, "Saga")

    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    assert not (tmp_path / "Saga").exists()


def test_service_requires_at_least_one_profile():
    with pytest.raises(ValueError):
        ProjectService(sqlite_initializer, profiles=[])


def test_service_rejects_profiles_sharing_a_filename():
    profiles = [ProfileSpec("A", "same.sqlite"), ProfileSpec("B", "SAME.sqlite")]

    with pytest.raises(ValueError):
        ProjectService(sqlite_initializer, profiles)


TEMPLATE = {
    "categories": [
        {"name": "Basics", "fields": [{"name": "Age", "type": "text"},
                                      {"name": "Notes", "type": "textarea"}]},
    ]
}


def read_layout(db_path):
    connection = sqlite3.connect(str(db_path))
    try:
        categories = [r[0] for r in connection.execute("SELECT name FROM categories")]
        fields = [r[0] for r in connection.execute("SELECT name FROM fields ORDER BY sort_order")]
    finally:
        connection.close()
    return categories, fields


def test_make_initializer_creates_a_seeded_profile_database(tmp_path):
    initializer = make_initializer({"Characters": TEMPLATE})

    project = ProjectService(initializer).create_project(tmp_path, "Saga")

    assert read_layout(project.databases["Characters"]) == (["Basics"], ["Age", "Notes"])


def test_make_initializer_leaves_profiles_without_a_template_empty(tmp_path):
    initializer = make_initializer({"Characters": TEMPLATE})

    project = ProjectService(initializer).create_project(tmp_path, "Saga")

    assert read_layout(project.databases["Worldbuilding"]) == ([], [])


def test_make_initializer_releases_the_database_file(tmp_path):
    initializer = make_initializer({})
    path = tmp_path / "x.sqlite"

    initializer(path, ProfileSpec("Characters", "x.sqlite"))
    path.unlink()

    assert not path.exists()
