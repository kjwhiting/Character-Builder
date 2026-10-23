import pytest

from src.services.category_service import CategoryService
from src.services.errors import (
    CategoryNotEmptyError,
    CategoryNotFoundError,
    DuplicateCategoryError,
    DuplicateFieldError,
    FieldNotFoundError,
    InvalidFieldTypeError,
    InvalidNameError,
    InvalidOrderError,
)


@pytest.fixture
def categories(conn):
    return CategoryService(conn)


def field_names(categories, category):
    return [field.name for field in categories.list_fields(category)]


def test_lists_categories_in_display_order(categories, catalog):
    assert categories.list_categories() == ["Description", "Relations", "Favorites"]


def test_add_category_appends_at_the_end(categories, catalog):
    assert categories.add_category("  Dances ") == "Dances"
    assert categories.list_categories()[-1] == "Dances"


def test_add_category_rejects_duplicates_ignoring_case(categories, catalog):
    with pytest.raises(DuplicateCategoryError):
        categories.add_category("favorites")


def test_add_category_rejects_blank_names(categories, catalog):
    with pytest.raises(InvalidNameError):
        categories.add_category("   ")


def test_rename_category_carries_its_fields_along(categories, catalog):
    categories.rename_category("Favorites", "Likes")

    assert "Likes" in categories.list_categories()
    assert field_names(categories, "Likes") == ["Color", "Food"]
    with pytest.raises(CategoryNotFoundError):
        categories.list_fields("Favorites")


def test_rename_category_allows_changing_only_the_case(categories, catalog):
    categories.rename_category("Favorites", "FAVORITES")

    assert categories.list_categories()[-1] == "FAVORITES"
    assert field_names(categories, "FAVORITES") == ["Color", "Food"]


def test_rename_category_rejects_name_of_another_category(categories, catalog):
    with pytest.raises(DuplicateCategoryError):
        categories.rename_category("Favorites", "relations")


def test_delete_category_is_blocked_while_fields_are_assigned(categories, catalog):
    with pytest.raises(CategoryNotEmptyError):
        categories.delete_category("Favorites")

    assert "Favorites" in categories.list_categories()
    assert field_names(categories, "Favorites") == ["Color", "Food"]


def test_delete_category_removes_an_empty_category(categories, catalog):
    categories.add_category("Dances")

    categories.delete_category("dances")

    assert "Dances" not in categories.list_categories()


def test_delete_category_succeeds_after_its_fields_are_moved_out(categories, catalog):
    for field in categories.list_fields("Favorites"):
        categories.move_field(field.id, "Description")

    categories.delete_category("Favorites")

    assert "Favorites" not in categories.list_categories()
    assert field_names(categories, "Description") == ["Description", "Color", "Food"]


def test_delete_category_succeeds_after_its_fields_are_deleted(categories, catalog):
    for field in categories.list_fields("Favorites"):
        categories.delete_field(field.id)

    categories.delete_category("Favorites")

    assert "Favorites" not in categories.list_categories()


def test_delete_unknown_category_raises(categories, catalog):
    with pytest.raises(CategoryNotFoundError):
        categories.delete_category("Nope")


def test_reorder_categories_applies_the_new_order(categories, catalog):
    categories.reorder_categories(["Favorites", "Description", "Relations"])

    assert categories.list_categories() == ["Favorites", "Description", "Relations"]


@pytest.mark.parametrize(
    "order",
    [["Favorites", "Description"], ["Favorites", "Description", "Relations", "Relations"]],
)
def test_reorder_categories_requires_every_category_exactly_once(categories, catalog, order):
    with pytest.raises(InvalidOrderError):
        categories.reorder_categories(order)

    assert categories.list_categories() == ["Description", "Relations", "Favorites"]


def test_count_fields(categories, catalog):
    assert categories.count_fields("Favorites") == 2


def test_add_field_appends_with_next_sort_order(categories, catalog):
    field = categories.add_field("Favorites", "Animal", "list")

    assert (field.category, field.name, field.field_type, field.sort_order) == (
        "Favorites", "Animal", "list", 2,
    )
    assert field_names(categories, "Favorites") == ["Color", "Food", "Animal"]


def test_add_field_to_empty_category_starts_at_zero(categories, catalog):
    categories.add_category("Dances")

    assert categories.add_field("Dances", "Free form").sort_order == 0


def test_add_field_rejects_duplicate_name_ignoring_case(categories, catalog):
    with pytest.raises(DuplicateFieldError):
        categories.add_field("Favorites", "color")


def test_add_field_rejects_unknown_type(categories, catalog):
    with pytest.raises(InvalidFieldTypeError):
        categories.add_field("Favorites", "Animal", "number")


def test_add_field_rejects_unknown_category(categories, catalog):
    with pytest.raises(CategoryNotFoundError):
        categories.add_field("Nope", "Animal")


def test_rename_field(categories, catalog):
    field = categories.rename_field(catalog["Color"], "Favorite color")

    assert field.name == "Favorite color"


def test_rename_field_rejects_name_used_in_same_category(categories, catalog):
    with pytest.raises(DuplicateFieldError):
        categories.rename_field(catalog["Color"], "Food")


def test_rename_field_to_its_own_name_with_new_case_is_allowed(categories, catalog):
    assert categories.rename_field(catalog["Color"], "COLOR").name == "COLOR"


def test_delete_field_removes_saved_values_and_closes_the_gap(categories, conn, catalog):
    with conn:
        conn.execute("INSERT INTO entities (name) VALUES ('Aria')")
        conn.execute(
            "INSERT INTO field_values (entity_id, field_id, value) VALUES (1, ?, 'Teal')",
            (catalog["Color"],),
        )
    assert categories.count_field_values(catalog["Color"]) == 1

    categories.delete_field(catalog["Color"])

    assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0
    remaining = categories.list_fields("Favorites")
    assert [(f.name, f.sort_order) for f in remaining] == [("Food", 0)]


def test_unknown_field_raises(categories, catalog):
    with pytest.raises(FieldNotFoundError):
        categories.get_field(999)


def test_move_field_to_end_of_another_category_renumbers_both(categories, catalog):
    moved = categories.move_field(catalog["Color"], "Relations")

    assert moved.category == "Relations"
    assert [(f.name, f.sort_order) for f in categories.list_fields("Relations")] == [
        ("Best friend", 0), ("Enemies", 1), ("Color", 2),
    ]
    assert [(f.name, f.sort_order) for f in categories.list_fields("Favorites")] == [("Food", 0)]


def test_move_field_to_specific_position(categories, catalog):
    categories.move_field(catalog["Color"], "Relations", position=1)

    assert field_names(categories, "Relations") == ["Best friend", "Color", "Enemies"]


def test_move_field_clamps_out_of_range_positions(categories, catalog):
    categories.move_field(catalog["Color"], "Relations", position=99)
    assert field_names(categories, "Relations") == ["Best friend", "Enemies", "Color"]

    categories.move_field(catalog["Food"], "Relations", position=-5)
    assert field_names(categories, "Relations")[0] == "Food"


def test_move_field_within_its_own_category_reorders_it(categories, catalog):
    categories.move_field(catalog["Food"], "Favorites", position=0)

    assert [(f.name, f.sort_order) for f in categories.list_fields("Favorites")] == [
        ("Food", 0), ("Color", 1),
    ]


def test_move_field_keeps_saved_values(categories, conn, catalog):
    with conn:
        conn.execute("INSERT INTO entities (name) VALUES ('Aria')")
        conn.execute(
            "INSERT INTO field_values (entity_id, field_id, value) VALUES (1, ?, 'Teal')",
            (catalog["Color"],),
        )

    categories.move_field(catalog["Color"], "Relations")

    value = conn.execute(
        "SELECT value FROM field_values WHERE field_id = ?", (catalog["Color"],)
    ).fetchone()[0]
    assert value == "Teal"


def test_move_field_blocked_by_name_clash_changes_nothing(categories, catalog):
    categories.add_field("Relations", "Color")

    with pytest.raises(DuplicateFieldError):
        categories.move_field(catalog["Color"], "Relations")

    assert field_names(categories, "Favorites") == ["Color", "Food"]
    assert field_names(categories, "Relations") == ["Best friend", "Enemies", "Color"]


def test_move_field_to_unknown_category_raises(categories, catalog):
    with pytest.raises(CategoryNotFoundError):
        categories.move_field(catalog["Color"], "Nope")


def test_reorder_fields_applies_the_new_order(categories, catalog):
    categories.reorder_fields("Favorites", [catalog["Food"], catalog["Color"]])

    assert field_names(categories, "Favorites") == ["Food", "Color"]


def test_reorder_fields_requires_exactly_the_categorys_fields(categories, catalog):
    with pytest.raises(InvalidOrderError):
        categories.reorder_fields("Favorites", [catalog["Food"], catalog["Enemies"]])

    assert field_names(categories, "Favorites") == ["Color", "Food"]


def test_change_field_type_updates_type_and_multiline_flag(categories, conn, catalog):
    field = categories.change_field_type(catalog["Color"], "textarea")

    assert field.field_type == "textarea"
    assert conn.execute(
        "SELECT multiline FROM fields WHERE id = ?", (catalog["Color"],)
    ).fetchone()[0] == 1
    assert categories.change_field_type(catalog["Color"], "text").field_type == "text"


def test_change_field_type_rejects_unknown_type_and_field(categories, catalog):
    with pytest.raises(InvalidFieldTypeError):
        categories.change_field_type(catalog["Color"], "number")
    with pytest.raises(FieldNotFoundError):
        categories.change_field_type(999, "text")
