import pytest

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.ui import adjust_fields_view
from src.ui.adjust_fields_view import AdjustFieldsView, drop_line_y, find_drop_target
from src.ui.tests.helpers import find_buttons, label_texts


@pytest.fixture
def categories(conn):
    return CategoryService(conn)


@pytest.fixture
def changes():
    return []


@pytest.fixture
def view(root, categories, catalog, changes, dialogs, monkeypatch):
    monkeypatch.setattr(adjust_fields_view, "messagebox", dialogs)
    window = AdjustFieldsView(root, categories, on_changed=lambda: changes.append(1))
    return window


@pytest.fixture
def answer_name(monkeypatch):
    def set_answer(value):
        monkeypatch.setattr(adjust_fields_view, "ask_name", lambda *args, **kwargs: value)

    return set_answer


BLOCKS = [
    {"header_bottom": 40, "rows": [(40, 80), (80, 120)], "end": 160},
    {"header_bottom": 200, "rows": [], "end": 240},
    {"header_bottom": 280, "rows": [(280, 320)], "end": float("inf")},
]


@pytest.mark.parametrize(
    "y, expected",
    [
        (10, (0, 0)),
        (50, (0, 0)),
        (70, (0, 1)),
        (110, (0, 2)),
        (130, (0, 2)),
        (190, (1, 0)),
        (210, (1, 0)),
        (250, (2, 0)),
        (285, (2, 0)),
        (310, (2, 1)),
        (9999, (2, 1)),
    ],
)
def test_find_drop_target(y, expected):
    assert find_drop_target(y, BLOCKS) == expected


def test_find_drop_target_without_categories_is_none():
    assert find_drop_target(50, []) is None


@pytest.mark.parametrize(
    "target, expected",
    [((0, 0), 40), ((0, 1), 80), ((0, 2), 120), ((1, 0), 200), ((2, 1), 320)],
)
def test_drop_line_y(target, expected):
    assert drop_line_y(target, BLOCKS) == expected


def test_renders_every_category_with_its_fields_in_order(view):
    assert view.snapshot() == [
        ("Description", ["Description"]),
        ("Relations", ["Best friend", "Enemies"]),
        ("Favorites", ["Color", "Food"]),
    ]
    texts = label_texts(view)
    assert "RELATIONS" in texts and "2 fields" in texts and "1 field" in texts


def test_every_category_has_management_buttons(view):
    assert len(find_buttons(view, "Delete Category")) == 3
    assert len(find_buttons(view, "Rename")) == 3
    assert len(find_buttons(view, "+ Add Field")) == 3
    assert len(find_buttons(view, "Delete")) == 5


def test_add_category_appends_a_new_empty_category(view, answer_name, categories):
    answer_name("Dances")

    view.add_category()

    assert view.snapshot()[-1] == ("Dances", [])
    assert "No fields yet. Drag one here or add one below." in label_texts(view)


def test_add_category_cancelled_changes_nothing(view, answer_name, categories, changes):
    answer_name(None)

    view.add_category()

    assert categories.list_categories() == ["Description", "Relations", "Favorites"]


def test_add_duplicate_category_warns_and_changes_nothing(view, answer_name, dialogs):
    answer_name("favorites")

    view.add_category()

    assert dialogs.kinds() == ["warning"]
    assert "already exists" in dialogs.calls[0][2]
    assert len(view.snapshot()) == 3


def test_delete_category_with_fields_is_blocked_with_an_explanation(view, dialogs):
    view.delete_category("Favorites")

    assert dialogs.kinds() == ["warning"]
    assert "still has 2 field(s)" in dialogs.calls[0][2]
    assert [name for name, _ in view.snapshot()] == ["Description", "Relations", "Favorites"]


def test_delete_category_button_on_a_populated_category_is_blocked(view, dialogs):
    find_buttons(view, "Delete Category")[2].invoke()

    assert dialogs.kinds() == ["warning"]
    assert len(view.snapshot()) == 3


def test_delete_empty_category_removes_it(view, answer_name, dialogs):
    answer_name("Dances")
    view.add_category()

    view.delete_category("Dances")

    assert dialogs.kinds() == []
    assert [name for name, _ in view.snapshot()] == ["Description", "Relations", "Favorites"]


def test_category_can_be_deleted_after_its_fields_move_out(view, categories, catalog, dialogs):
    view.move_field(catalog["Color"], "Description")
    view.move_field(catalog["Food"], "Description")

    view.delete_category("Favorites")

    assert dialogs.kinds() == []
    assert view.snapshot() == [
        ("Description", ["Description", "Color", "Food"]),
        ("Relations", ["Best friend", "Enemies"]),
    ]


def test_rename_category_keeps_its_fields(view, answer_name):
    answer_name("Likes")

    view.rename_category("Favorites")

    assert view.snapshot()[-1] == ("Likes", ["Color", "Food"])


def test_move_category_up_and_down(view):
    view.move_category("Favorites", -1)
    assert [n for n, _ in view.snapshot()] == ["Description", "Favorites", "Relations"]

    view.move_category("Description", 1)
    assert [n for n, _ in view.snapshot()] == ["Favorites", "Description", "Relations"]


def test_move_category_past_the_ends_is_a_no_op(view, changes):
    view.move_category("Description", -1)
    view.move_category("Favorites", 1)

    assert [n for n, _ in view.snapshot()] == ["Description", "Relations", "Favorites"]
    view.close()
    assert changes == []


def test_add_field_appends_to_the_category(view, answer_name):
    answer_name("Animal")

    view.add_field("Favorites")

    assert view.snapshot()[-1] == ("Favorites", ["Color", "Food", "Animal"])


def test_add_duplicate_field_warns(view, answer_name, dialogs):
    answer_name("color")

    view.add_field("Favorites")

    assert dialogs.kinds() == ["warning"]
    assert view.snapshot()[-1] == ("Favorites", ["Color", "Food"])


def test_rename_field_updates_the_row(view, catalog):
    view.rename_field(catalog["Color"], "Favorite color")

    assert view.snapshot()[-1] == ("Favorites", ["Favorite color", "Food"])


def test_rename_field_to_blank_or_taken_name_is_rejected(view, catalog, dialogs):
    view.rename_field(catalog["Color"], "  ")
    view.rename_field(catalog["Color"], "Food")

    assert dialogs.kinds() == ["warning", "warning"]
    assert view.snapshot()[-1] == ("Favorites", ["Color", "Food"])


def test_committing_an_edited_entry_renames_the_field(view, categories, catalog):
    field = categories.get_field(catalog["Color"])

    class FakeEntry:
        def get(self):
            return "  Hue "

    view._commit_rename(field, FakeEntry())

    assert categories.get_field(catalog["Color"]).name == "Hue"


def test_committing_an_unchanged_entry_does_nothing(view, categories, catalog, changes):
    field = categories.get_field(catalog["Color"])

    class FakeEntry:
        def get(self):
            return "Color"

    view._commit_rename(field, FakeEntry())
    view.close()

    assert changes == []


def test_change_field_type(view, categories, catalog):
    view.change_field_type(catalog["Color"], "list")

    assert categories.get_field(catalog["Color"]).field_type == "list"


def test_delete_field_asks_first_and_mentions_saved_values(
    view, conn, catalog, dialogs, categories
):
    EntityService(conn).create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    EntityService(conn).create_entity("Bram", "Character", values={catalog["Color"]: "Red"})

    view.delete_field(catalog["Color"])

    assert dialogs.kinds() == ["askyesno"]
    assert "2 saved values" in dialogs.calls[0][2]
    assert view.snapshot()[-1] == ("Favorites", ["Food"])
    assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0


def test_delete_field_declined_keeps_everything(view, conn, catalog, dialogs):
    dialogs.answer = False
    EntityService(conn).create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    view.delete_field(catalog["Color"])

    assert view.snapshot()[-1] == ("Favorites", ["Color", "Food"])
    assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 1


def test_delete_field_without_values_has_no_value_count_in_the_prompt(view, catalog, dialogs):
    view.delete_field(catalog["Color"])

    assert "saved value" not in dialogs.calls[0][2]


def test_move_field_to_another_category_at_a_position(view, catalog):
    view.move_field(catalog["Color"], "Relations", 1)

    assert view.snapshot() == [
        ("Description", ["Description"]),
        ("Relations", ["Best friend", "Color", "Enemies"]),
        ("Favorites", ["Food"]),
    ]


def test_move_field_into_a_duplicate_name_is_rejected(view, categories, catalog, dialogs):
    categories.add_field("Relations", "Color")
    view._render()

    view.move_field(catalog["Color"], "Relations")

    assert dialogs.kinds() == ["warning"]
    assert view.snapshot()[-1] == ("Favorites", ["Color", "Food"])


def test_drop_onto_another_category(view, catalog):
    view.drop_field(catalog["Color"], (0, 1))

    assert view.snapshot()[0] == ("Description", ["Description", "Color"])
    assert view.snapshot()[2] == ("Favorites", ["Food"])


def test_drop_below_itself_in_the_same_category_accounts_for_removal(view, catalog):
    view.drop_field(catalog["Color"], (2, 2))

    assert view.snapshot()[2] == ("Favorites", ["Food", "Color"])


def test_drop_above_itself_in_the_same_category(view, catalog):
    view.drop_field(catalog["Food"], (2, 0))

    assert view.snapshot()[2] == ("Favorites", ["Food", "Color"])


@pytest.mark.parametrize("target", [(2, 0), (2, 1)])
def test_drop_back_where_it_started_changes_nothing(view, catalog, changes, target):
    view.drop_field(catalog["Color"], target)
    view.close()

    assert view.snapshot()[2] == ("Favorites", ["Color", "Food"])
    assert changes == []


def test_drop_into_an_empty_category(view, answer_name, catalog):
    answer_name("Dances")
    view.add_category()

    view.drop_field(catalog["Food"], (3, 0))

    assert view.snapshot()[-1] == ("Dances", ["Food"])


def test_close_reports_changes_only_when_something_changed(view, answer_name, changes):
    answer_name("Dances")
    view.add_category()

    view.close()

    assert changes == [1]


def test_close_without_changes_does_not_notify(view, changes):
    view.close()

    assert changes == []
