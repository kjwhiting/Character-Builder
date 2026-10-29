import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import ProjectDatabase  # noqa: E402
from src.services.category_service import CategoryService  # noqa: E402
from src.services.collection_service import CollectionService  # noqa: E402
from src.services.entity_service import EntityService  # noqa: E402


@pytest.fixture
def database(tmp_path):
    project_database = ProjectDatabase()
    project_database.open(tmp_path / "project.sqlite", create=True)
    yield project_database
    project_database.close()


@pytest.fixture
def connection(database):
    return database.connection


@pytest.fixture
def collections(connection):
    return CollectionService(connection)


@pytest.fixture
def characters(collections):
    return collections.add_collection("Characters", "Character")


@pytest.fixture
def places(collections):
    return collections.add_collection("Places", "Place")


@pytest.fixture
def categories(connection, characters):
    return CategoryService(connection, characters.id)


@pytest.fixture
def entities(connection, characters):
    return EntityService(connection, characters.id)


@pytest.fixture
def fields(categories):
    created = {}
    categories.add_category("Basics")
    for name, field_type, options in [
        ("Age", "number", {"unit": "years"}),
        ("Height", "number", {"unit": "cm"}),
        ("Alive", "checkbox", None),
        ("Role", "choice", {"choices": ["Hero", "Villain"]}),
    ]:
        created[name] = categories.add_field("Basics", name, field_type, options)
    categories.add_category("Notes")
    for name, field_type, options in [
        ("Summary", "textarea", None),
        ("Tags", "list", None),
        ("Traits", "multichoice", {"choices": ["Brave", "Shy", "Loud"]}),
        ("Hometown", "text", None),
    ]:
        created[name] = categories.add_field("Notes", name, field_type, options)
    return created


@pytest.fixture
def values_of(entities):
    def read(entity_id):
        return entities.get_values(entity_id)

    return read
