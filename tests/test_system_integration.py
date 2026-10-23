import sqlite3

import pytest

from src.database import seeds
from src.database.connection import DatabaseConnection, NoActiveProfileError
from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.errors import CategoryNotEmptyError, FieldNotFoundError
from src.services.export_service import ExportService
from src.services.project_service import ProjectService, make_initializer


def open_profile(path, template=seeds.CHARACTER_TEMPLATE):
    database = DatabaseConnection()
    database.open(path, create=True, template=template)
    return database


class Stack:
    def __init__(self, database):
        connection = database.connection
        self.categories = CategoryService(connection)
        self.entities = EntityService(connection)
        self.copied = []
        self.export = ExportService(connection, self.copied.append)
        self.connection = connection

    def field_id(self, category, name):
        for field in self.categories.list_fields(category):
            if field.name == name:
                return field.id
        raise AssertionError(f"{category}/{name} not found")


@pytest.fixture
def database(tmp_path):
    db = open_profile(tmp_path / "Characters.sqlite")
    yield db
    db.close()


@pytest.fixture
def stack(database):
    return Stack(database)


def template_layout(template):
    return [(c["name"], [f["name"] for f in c["fields"]]) for c in template["categories"]]


def live_layout(stack):
    return [(name, [f.name for f in stack.categories.list_fields(name)])
            for name in stack.categories.list_categories()]


def row_count(stack, table):
    return stack.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_seeded_profile_exposes_the_template_through_the_category_service(stack):
    assert live_layout(stack) == template_layout(seeds.CHARACTER_TEMPLATE)


def test_seeded_field_types_follow_the_template(stack):
    expected = {
        (c["name"], f["name"]): f["type"]
        for c in seeds.CHARACTER_TEMPLATE["categories"] for f in c["fields"]
    }
    actual = {(f.category, f.name): f.field_type for f in stack.categories.list_fields()}

    assert actual == expected


def test_every_database_field_type_is_accepted_by_the_real_schema(stack):
    for index, field_type in enumerate(seeds.FIELD_TYPES):
        field = stack.categories.add_field("Favorites", f"Extra {index}", field_type)
        assert field.field_type == field_type


def test_entities_and_values_survive_closing_and_reopening(tmp_path):
    first = open_profile(tmp_path / "Characters.sqlite")
    stack = Stack(first)
    color = stack.field_id("Favorites", "Color")
    entity_id = stack.entities.create_entity("Aria", "Character", values={color: "Teal"})
    first.close()

    second = DatabaseConnection()
    second.open(tmp_path / "Characters.sqlite")
    reopened = Stack(second)

    assert reopened.entities.get_entity(entity_id).name == "Aria"
    assert reopened.entities.get_values(entity_id) == {color: "Teal"}
    second.close()


def test_deleting_an_entity_cascades_to_its_values_in_the_real_schema(stack):
    color = stack.field_id("Favorites", "Color")
    entity_id = stack.entities.create_entity("Aria", "Character", values={color: "Teal"})

    stack.entities.delete_entity(entity_id)

    assert row_count(stack, "field_values") == 0


def test_deleting_a_field_removes_its_values_but_keeps_other_fields(stack):
    color = stack.field_id("Favorites", "Color")
    food = stack.field_id("Favorites", "Food")
    entity_id = stack.entities.create_entity(
        "Aria", "Character", values={color: "Teal", food: "Soup"})

    stack.categories.delete_field(color)

    assert stack.entities.get_values(entity_id) == {food: "Soup"}


def test_failed_save_leaves_the_real_database_untouched(stack):
    with pytest.raises(FieldNotFoundError):
        stack.entities.create_entity("Aria", "Character", values={99999: "x"})

    assert row_count(stack, "entities") == 0
    assert row_count(stack, "field_values") == 0


def test_export_follows_template_order_and_skips_empty_fields(stack):
    values = {
        stack.field_id("Description", "Description"): "A brave hero",
        stack.field_id("Relations", "Enemies"): "Orc, Troll",
        stack.field_id("Favorites", "Color"): "Teal",
    }
    entity_id = stack.entities.create_entity("Aria", "Character", values=values)

    assert stack.export.build_plain_text(entity_id) == (
        "Description\nDescription: A brave hero\n\n"
        "Relations\nEnemies: Orc, Troll\n\n"
        "Favorites\nColor: Teal"
    )


def test_export_of_a_worldbuilding_profile_joins_list_fields(tmp_path):
    database = open_profile(tmp_path / "Worldbuilding.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    stack = Stack(database)
    landmarks = stack.field_id("Geography", "Landmarks")
    entity_id = stack.entities.create_entity(
        "Old Mill", "Place", values={landmarks: "Bridge\nWell\n"})

    assert stack.export.build_plain_text(entity_id) == "Geography\nLandmarks: Bridge, Well"
    database.close()


def test_a_duplicate_exports_exactly_like_its_original(stack):
    values = {
        stack.field_id("Description", "Description"): "A brave hero",
        stack.field_id("Favorites", "Food"): "Soup",
    }
    original = stack.entities.create_entity("Aria", "Character", values=values)

    copy_id = stack.entities.duplicate_entity(original)

    assert stack.export.build_plain_text(copy_id) == stack.export.build_plain_text(original)
    assert stack.entities.get_entity(copy_id).name == "Aria (Copy)"


def test_copy_entity_sends_the_export_to_the_clipboard_writer(stack):
    entity_id = stack.entities.create_entity(
        "Aria", "Character", values={stack.field_id("Favorites", "Color"): "Teal"})

    text = stack.export.copy_entity(entity_id)

    assert stack.copied == [text] == ["Favorites\nColor: Teal"]


def test_missing_field_filter_and_search_use_the_same_stored_values(stack):
    color = stack.field_id("Favorites", "Color")
    stack.entities.create_entity("Aria", "Character", values={color: "Teal"})
    stack.entities.create_entity("Bram", "Character")

    assert [e.name for e in stack.entities.get_entities_missing_field(color)] == ["Bram"]
    assert [e.name for e in stack.entities.search_entities("teal")] == ["Aria"]


def test_category_with_fields_cannot_be_deleted_in_the_real_database(stack):
    with pytest.raises(CategoryNotEmptyError):
        stack.categories.delete_category("Favorites")

    assert "Favorites" in stack.categories.list_categories()
    assert row_count(stack, "fields") == sum(
        len(c["fields"]) for c in seeds.CHARACTER_TEMPLATE["categories"])


def test_emptied_category_deletion_survives_reopening_the_profile(tmp_path):
    path = tmp_path / "Characters.sqlite"
    first = open_profile(path)
    stack = Stack(first)
    for field in stack.categories.list_fields("Favorites"):
        stack.categories.move_field(field.id, "Description")
    stack.categories.delete_category("Favorites")
    first.close()

    second = DatabaseConnection()
    second.open(path)
    reopened = Stack(second)

    assert "Favorites" not in reopened.categories.list_categories()
    assert len(reopened.categories.list_fields("Description")) == 7
    second.close()


def test_added_category_and_reordering_persist_and_change_export_order(tmp_path):
    path = tmp_path / "Characters.sqlite"
    first = open_profile(path)
    stack = Stack(first)
    stack.categories.reorder_categories(
        ["Favorites", "Relations", "Description", "Dances", "Musical Contributions"])
    stack.categories.add_category("Titles")
    stack.categories.add_field("Titles", "Rank")
    entity_id = stack.entities.create_entity("Aria", "Character", values={
        stack.field_id("Description", "Description"): "Hero",
        stack.field_id("Favorites", "Color"): "Teal",
        stack.field_id("Titles", "Rank"): "Captain",
    })
    first.close()

    second = DatabaseConnection()
    second.open(path)
    reopened = Stack(second)

    assert reopened.categories.list_categories()[:3] == ["Favorites", "Relations", "Description"]
    assert reopened.categories.list_categories()[-1] == "Titles"
    assert reopened.export.build_plain_text(entity_id) == (
        "Favorites\nColor: Teal\n\nDescription\nDescription: Hero\n\nTitles\nRank: Captain"
    )
    second.close()


def test_profiles_are_isolated_and_old_services_stop_working_after_a_switch(tmp_path):
    database = open_profile(tmp_path / "Characters.sqlite")
    old = Stack(database)
    old.entities.create_entity("Aria", "Character")
    other = open_profile(tmp_path / "Worldbuilding.sqlite", seeds.WORLDBUILDING_TEMPLATE)
    other.close()

    database.switch_profile(tmp_path / "Worldbuilding.sqlite")
    new = Stack(database)

    assert new.entities.list_entities() == []
    assert "Geography" in new.categories.list_categories()
    with pytest.raises(sqlite3.ProgrammingError):
        old.entities.list_entities()
    database.close()


def test_connection_is_unavailable_once_the_database_is_closed(tmp_path):
    database = open_profile(tmp_path / "Characters.sqlite")
    database.close()

    with pytest.raises(NoActiveProfileError):
        database.connection


def test_project_service_builds_independent_seeded_profiles_that_services_can_use(tmp_path):
    project = ProjectService(make_initializer()).create_project(tmp_path, "Saga")
    characters = DatabaseConnection()
    characters.open(project.databases["Characters"])
    worlds = DatabaseConnection()
    worlds.open(project.databases["Worldbuilding"])
    character_stack, world_stack = Stack(characters), Stack(worlds)

    character_stack.entities.create_entity("Aria", "Character")

    assert [e.name for e in character_stack.entities.list_entities()] == ["Aria"]
    assert world_stack.entities.list_entities() == []
    assert live_layout(character_stack) == template_layout(seeds.CHARACTER_TEMPLATE)
    assert live_layout(world_stack) == template_layout(seeds.WORLDBUILDING_TEMPLATE)
    assert project.images_dir.is_dir()
    characters.close()
    worlds.close()
