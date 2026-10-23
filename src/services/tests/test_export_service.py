import pytest

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.errors import EntityNotFoundError, NothingToExportError
from src.services.export_service import ExportService, TkClipboard


@pytest.fixture
def copied():
    return []


@pytest.fixture
def entities(conn):
    return EntityService(conn)


@pytest.fixture
def export(conn, copied):
    return ExportService(conn, clipboard=copied.append)


def test_formats_each_category_followed_by_its_field_lines(entities, export, catalog):
    entity_id = entities.create_entity(
        "Aria", "Character",
        values={catalog["Description"]: "A brave hero", catalog["Best friend"]: "Mira"},
    )

    assert export.build_plain_text(entity_id) == (
        "Description\nDescription: A brave hero\n\nRelations\nBest friend: Mira"
    )


def test_omits_empty_fields_and_categories_with_nothing_filled(entities, export, catalog):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    assert export.build_plain_text(entity_id) == "Favorites\nColor: Teal"


def test_whitespace_only_values_count_as_empty(entities, export, catalog, conn):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    with conn:
        conn.execute(
            "INSERT INTO field_values (entity_id, field_id, value) VALUES (?, ?, ?)",
            (entity_id, catalog["Food"], "   \n "),
        )

    assert export.build_plain_text(entity_id) == "Favorites\nColor: Teal"


def test_list_fields_are_joined_with_commas(entities, export, catalog):
    entity_id = entities.create_entity(
        "Aria", "Character", values={catalog["Enemies"]: "Orc\n\n  Troll \nGoblin"}
    )

    assert export.build_plain_text(entity_id) == "Relations\nEnemies: Orc, Troll, Goblin"


def test_textarea_values_keep_inner_line_breaks(entities, export, catalog):
    entity_id = entities.create_entity(
        "Aria", "Character", values={catalog["Description"]: "Line one\nLine two"}
    )

    assert export.build_plain_text(entity_id) == "Description\nDescription: Line one\nLine two"


def test_categories_follow_display_order(conn, entities, export, catalog):
    entity_id = entities.create_entity(
        "Aria", "Character",
        values={catalog["Description"]: "Hero", catalog["Color"]: "Teal"},
    )
    CategoryService(conn).reorder_categories(["Favorites", "Relations", "Description"])

    assert export.build_plain_text(entity_id) == (
        "Favorites\nColor: Teal\n\nDescription\nDescription: Hero"
    )


def test_fields_follow_display_order_within_a_category(conn, entities, export, catalog):
    entity_id = entities.create_entity(
        "Aria", "Character", values={catalog["Color"]: "Teal", catalog["Food"]: "Soup"}
    )
    CategoryService(conn).reorder_fields("Favorites", [catalog["Food"], catalog["Color"]])

    assert export.build_plain_text(entity_id) == "Favorites\nFood: Soup\nColor: Teal"


def test_entity_with_no_values_produces_empty_text(entities, export, catalog):
    entity_id = entities.create_entity("Aria", "Character")

    assert export.build_plain_text(entity_id) == ""


def test_unknown_entity_raises(export, catalog):
    with pytest.raises(EntityNotFoundError):
        export.build_plain_text(999)


def test_copy_pushes_text_to_clipboard_and_returns_it(entities, export, copied, catalog):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    returned = export.copy_entity(entity_id)

    assert returned == "Favorites\nColor: Teal"
    assert copied == ["Favorites\nColor: Teal"]


def test_copy_with_nothing_to_export_raises_and_leaves_clipboard_alone(
    entities, export, copied, catalog
):
    entity_id = entities.create_entity("Aria", "Character")

    with pytest.raises(NothingToExportError):
        export.copy_entity(entity_id)
    assert copied == []


def test_tk_clipboard_clears_appends_then_updates():
    calls = []

    class FakeWidget:
        def clipboard_clear(self):
            calls.append(("clear",))

        def clipboard_append(self, text):
            calls.append(("append", text))

        def update(self):
            calls.append(("update",))

    TkClipboard(FakeWidget())("hello")

    assert calls == [("clear",), ("append", "hello"), ("update",)]
