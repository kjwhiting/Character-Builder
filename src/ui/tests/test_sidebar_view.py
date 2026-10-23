import pytest

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.ui import theme
from src.ui.sidebar_view import ALL_ENTRIES_LABEL, SidebarView
from src.ui.tests.helpers import label_texts


@pytest.fixture
def entities(conn):
    return EntityService(conn)


@pytest.fixture
def events():
    return {"selected": [], "added": 0}


@pytest.fixture
def sidebar(root, conn, entities, catalog, events):
    def on_add():
        events["added"] += 1

    view = SidebarView(
        root, entities, CategoryService(conn), noun="Character", profile_name="characters",
        on_select=events["selected"].append, on_add=on_add,
    )
    view.grid(row=0, column=0)
    return view


def names(sidebar):
    return [sidebar.entity_buttons[e.id].cget("text").split("  ", 1)[1]
            for e in sidebar.visible_entities()]


def populate(entities, catalog):
    entities.create_entity("Bram", "Character", values={catalog["Food"]: "Mushroom soup"})
    entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    entities.create_entity("Old Mill", "Place", values={catalog["Description"]: "Haunted"})


def test_shows_placeholder_when_there_are_no_entities(sidebar):
    assert "Nothing here yet." in label_texts(sidebar)
    assert sidebar.entity_buttons == {}


def test_lists_entities_alphabetically_with_type_glyphs(sidebar, entities, catalog):
    populate(entities, catalog)

    sidebar.refresh()

    assert names(sidebar) == ["Aria", "Bram", "Old Mill"]
    texts = [b.cget("text") for b in sidebar.entity_buttons.values()]
    assert texts[0].startswith("\u2694") and texts[2].startswith("\u2302")


def test_add_button_label_follows_the_active_profile(sidebar):
    assert sidebar.add_button.cget("text") == "Add Character"

    sidebar.set_profile("Place", "places")

    assert sidebar.add_button.cget("text") == "Add Place"
    assert "places" in label_texts(sidebar)


def test_add_button_triggers_callback(sidebar, events):
    sidebar.add_button.invoke()

    assert events["added"] == 1


def test_clicking_an_entry_reports_its_id_without_changing_selection(
    sidebar, entities, catalog, events
):
    populate(entities, catalog)
    sidebar.refresh()
    aria = next(e for e in sidebar.visible_entities() if e.name == "Aria")

    sidebar.entity_buttons[aria.id].invoke()

    assert events["selected"] == [aria.id]
    assert sidebar.selected_id is None


def test_search_filters_by_name_and_by_field_value(sidebar, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()

    sidebar.set_search_text("aria")
    assert names(sidebar) == ["Aria"]

    sidebar.set_search_text("mushroom")
    assert names(sidebar) == ["Bram"]


def test_search_with_no_results_shows_no_matches(sidebar, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()

    sidebar.set_search_text("dragon")

    assert "No matches." in label_texts(sidebar)
    assert sidebar.entity_buttons == {}


def test_enter_in_search_opens_the_first_match(sidebar, entities, catalog, events):
    populate(entities, catalog)
    sidebar.refresh()
    sidebar.set_search_text("o")

    result = sidebar.open_first_match()

    assert result == "break"
    assert events["selected"] == [sidebar.visible_entities()[0].id]


def test_enter_with_no_matches_does_nothing(sidebar, events):
    sidebar.open_first_match()

    assert events["selected"] == []


def test_filter_dropdown_lists_every_field(sidebar):
    assert sidebar.filter_labels == [
        ALL_ENTRIES_LABEL,
        "Missing: Description / Description",
        "Missing: Relations / Best friend",
        "Missing: Relations / Enemies",
        "Missing: Favorites / Color",
        "Missing: Favorites / Food",
    ]


def test_missing_field_filter_shows_only_entries_lacking_that_field(
    sidebar, entities, catalog
):
    populate(entities, catalog)
    sidebar.refresh()

    sidebar.select_filter("Missing: Favorites / Color")

    assert names(sidebar) == ["Bram", "Old Mill"]


def test_filter_and_search_combine(sidebar, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()
    sidebar.select_filter("Missing: Favorites / Color")

    sidebar.set_search_text("mill")

    assert names(sidebar) == ["Old Mill"]


def test_returning_to_all_entries_clears_the_filter(sidebar, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()
    sidebar.select_filter("Missing: Favorites / Color")

    sidebar.select_filter(ALL_ENTRIES_LABEL)

    assert len(sidebar.visible_entities()) == 3


def test_filter_with_everyone_having_the_field_shows_no_matches(sidebar, entities, catalog):
    entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    sidebar.refresh()

    sidebar.select_filter("Missing: Favorites / Color")

    assert "No matches." in label_texts(sidebar)


def test_refresh_resets_filter_when_its_field_disappears(sidebar, conn, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()
    sidebar.select_filter("Missing: Favorites / Color")

    CategoryService(conn).delete_field(catalog["Color"])
    sidebar.refresh()

    assert sidebar.filter_combo.get() == ALL_ENTRIES_LABEL
    assert len(sidebar.visible_entities()) == 3


def test_set_selected_highlights_only_that_entry(sidebar, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()
    first, second, _third = sidebar.visible_entities()

    sidebar.set_selected(second.id)

    assert sidebar.entity_buttons[second.id].cget("fg_color") == theme.SELECTION_BG
    assert sidebar.entity_buttons[first.id].cget("fg_color") == "transparent"


def test_selection_highlight_survives_a_refresh(sidebar, entities, catalog):
    populate(entities, catalog)
    sidebar.refresh()
    target = sidebar.visible_entities()[0]
    sidebar.set_selected(target.id)

    sidebar.refresh()

    assert sidebar.entity_buttons[target.id].cget("fg_color") == theme.SELECTION_BG
