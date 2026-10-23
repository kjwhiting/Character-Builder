import pytest
from PIL import Image

from src.services.category_service import CategoryService
from src.services.entity_service import EntityService
from src.services.export_service import ExportService
from src.ui import card_view, theme
from src.ui.card_view import CardView, import_image, load_image
from src.ui.tests.helpers import find_buttons, label_texts, button_texts


@pytest.fixture
def entities(conn):
    return EntityService(conn)


@pytest.fixture
def clipboard():
    return []


@pytest.fixture
def events():
    return {"saved": [], "deleted": [], "duplicated": []}


@pytest.fixture
def card(root, conn, entities, catalog, clipboard, events, tmp_path, dialogs, monkeypatch):
    monkeypatch.setattr(card_view, "messagebox", dialogs)
    view = CardView(
        root, entities, CategoryService(conn), ExportService(conn, clipboard.append),
        images_dir=tmp_path / "images", noun="Character",
        on_saved=events["saved"].append, on_deleted=events["deleted"].append,
        on_duplicated=events["duplicated"].append,
    )
    view.grid(row=0, column=0)
    return view


@pytest.fixture
def aria(entities, catalog):
    return entities.create_entity(
        "Aria", "Character",
        values={
            catalog["Description"]: "A brave hero",
            catalog["Enemies"]: "Orc\nTroll",
            catalog["Color"]: "Teal",
        },
    )


def set_text(widget, value):
    if widget.__class__.__name__ == "CTkTextbox":
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
    else:
        widget.delete(0, "end")
        widget.insert(0, value)


def test_starts_on_the_empty_prompt(card):
    assert any("Select a character on the left" in t for t in label_texts(card))
    assert card.action_buttons == {}


def test_shows_name_type_and_only_filled_fields(card, aria):
    card.show_entity(aria)

    texts = label_texts(card)
    assert "Aria" in texts
    assert "  Character  " in texts
    assert "A brave hero" in texts
    assert "Teal" in texts
    assert "Best friend" not in texts
    assert "FAVORITES" in texts
    assert "DESCRIPTION" in texts


def test_list_fields_render_as_bullets(card, aria):
    card.show_entity(aria)

    assert "\u2022 Orc\n\u2022 Troll" in label_texts(card)


def test_entity_without_details_shows_hint(card, entities):
    card.show_entity(entities.create_entity("Bare", "Character"))

    assert "No details yet. Press Edit to add some." in label_texts(card)


def test_action_buttons_are_copy_edit_duplicate_in_that_order(card, aria):
    card.show_entity(aria)

    assert list(card.action_buttons) == ["Copy", "Edit", "Duplicate"]
    card.update_idletasks()
    xs = [b.winfo_x() for b in card.action_buttons.values()]
    assert xs == sorted(xs)


def test_unknown_entity_falls_back_to_empty_state(card):
    card.show_entity(999)

    assert card.entity_id is None
    assert card.action_buttons == {}


def test_copy_pushes_plain_text_and_confirms_on_the_button(card, aria, clipboard):
    card.show_entity(aria)

    card.action_buttons["Copy"].invoke()

    assert clipboard == [
        "Description\nDescription: A brave hero\n\nRelations\nEnemies: Orc, Troll"
        "\n\nFavorites\nColor: Teal"
    ]
    assert card.action_buttons["Copy"].cget("text") == "Copied \u2713"


def test_copy_with_nothing_filled_in_informs_and_leaves_clipboard_alone(
    card, entities, clipboard, dialogs
):
    card.show_entity(entities.create_entity("Bare", "Character"))

    card.action_buttons["Copy"].invoke()

    assert clipboard == []
    assert dialogs.kinds() == ["info"]


def test_duplicate_creates_a_copy_shows_it_and_notifies(card, aria, entities, events):
    card.show_entity(aria)

    card.action_buttons["Duplicate"].invoke()

    new_id = events["duplicated"][0]
    assert new_id != aria
    assert entities.get_entity(new_id).name == "Aria (Copy)"
    assert card.entity_id == new_id
    assert "Aria (Copy)" in label_texts(card)
    assert entities.get_values(new_id) == entities.get_values(aria)


def test_edit_button_opens_a_prefilled_form(card, aria, catalog):
    card.show_entity(aria)

    card.action_buttons["Edit"].invoke()

    assert card.editing
    data = card.collect_form()
    assert data["name"] == "Aria"
    assert data["type"] == "Character"
    assert data["values"][catalog["Description"]] == "A brave hero"
    assert data["values"][catalog["Enemies"]] == "Orc\nTroll"
    assert data["values"][catalog["Best friend"]] == ""


def test_form_has_one_widget_per_field_matching_its_type(card, aria, catalog):
    card.show_entity(aria)
    card.start_edit()

    kinds = {fid: w.__class__.__name__ for fid, (w, _t) in card._field_widgets.items()}

    assert kinds[catalog["Color"]] == "CTkEntry"
    assert kinds[catalog["Description"]] == "CTkTextbox"
    assert kinds[catalog["Enemies"]] == "CTkTextbox"
    assert len(kinds) == 5


def test_form_reflects_fields_added_after_the_card_was_built(card, conn, aria):
    CategoryService(conn).add_field("Favorites", "Animal")
    card.show_entity(aria)
    card.start_edit()

    assert len(card._field_widgets) == 6


def test_collect_form_trims_values_and_normalises_lists(card, aria, catalog):
    card.show_entity(aria)
    card.start_edit()
    set_text(card.name_entry, "  Aria Vale  ")
    set_text(card._field_widgets[catalog["Enemies"]][0], "  Orc \n\n Troll  \n")
    set_text(card._field_widgets[catalog["Color"]][0], "  Red ")

    data = card.collect_form()

    assert data["name"] == "Aria Vale"
    assert data["values"][catalog["Enemies"]] == "Orc\nTroll"
    assert data["values"][catalog["Color"]] == "Red"


def test_save_updates_the_entity_returns_to_card_and_notifies(
    card, aria, entities, events, catalog
):
    card.show_entity(aria)
    card.start_edit()
    set_text(card.name_entry, "Aria Vale")
    set_text(card._field_widgets[catalog["Color"]][0], "")
    set_text(card._field_widgets[catalog["Food"]][0], "Soup")

    card.save()

    assert not card.editing
    assert events["saved"] == [aria]
    assert entities.get_entity(aria).name == "Aria Vale"
    assert catalog["Color"] not in entities.get_values(aria)
    assert entities.get_values(aria)[catalog["Food"]] == "Soup"
    assert "Aria Vale" in label_texts(card)


def test_save_new_entity_creates_it_with_the_default_type(card, entities, events, catalog):
    card.start_new()
    set_text(card.name_entry, "Bram")
    set_text(card._field_widgets[catalog["Food"]][0], "Soup")

    card.save()

    new_id = events["saved"][0]
    entity = entities.get_entity(new_id)
    assert (entity.name, entity.type) == ("Bram", "Character")
    assert card.entity_id == new_id


def test_new_form_heading_uses_the_profile_noun(card):
    card.set_profile("Place", card._images_dir)
    card.start_new()

    assert "New Place" in label_texts(card)
    assert card.type_box.get() == "Place"
    assert "Place" in card.type_box.cget("values")


def test_save_with_blank_name_warns_and_stays_in_edit_mode(card, entities, events, dialogs):
    card.start_new()

    card.save()

    assert card.editing
    assert dialogs.kinds() == ["warning"]
    assert entities.list_entities() == []
    assert events["saved"] == []


def test_cancel_discards_edits_and_shows_the_card_again(card, aria, entities):
    card.show_entity(aria)
    card.start_edit()
    set_text(card.name_entry, "Changed")

    card.cancel()

    assert not card.editing
    assert entities.get_entity(aria).name == "Aria"
    assert "Aria" in label_texts(card)


def test_cancel_a_new_entry_returns_to_the_previously_shown_card(card, aria):
    card.show_entity(aria)
    card.start_new()

    card.cancel()

    assert card.entity_id == aria
    assert "Aria" in label_texts(card)


def test_cancel_a_new_entry_with_nothing_selected_shows_the_empty_prompt(card):
    card.start_new()

    card.cancel()

    assert card.entity_id is None
    assert any("Select a character" in t for t in label_texts(card))


def test_delete_button_only_exists_when_editing_an_existing_entry(card, aria):
    card.start_new()
    assert find_buttons(card, "Delete") == []

    card.show_entity(aria)
    card.start_edit()
    assert len(find_buttons(card, "Delete")) == 1


def test_delete_removes_the_entity_after_confirmation(card, aria, entities, events, dialogs):
    card.show_entity(aria)
    card.start_edit()

    card.delete()

    assert entities.list_entities() == []
    assert events["deleted"] == [aria]
    assert card.entity_id is None
    assert dialogs.kinds() == ["askyesno"]


def test_delete_declined_keeps_the_entity(card, aria, entities, events, dialogs):
    dialogs.answer = False
    card.show_entity(aria)
    card.start_edit()

    card.delete()

    assert len(entities.list_entities()) == 1
    assert events["deleted"] == []
    assert card.editing


def test_missing_image_file_is_reported(card, entities):
    card.show_entity(entities.create_entity("Aria", "Character", image="ghost.png"))

    assert "(image not found: images/ghost.png)" in label_texts(card)


def test_existing_image_is_rendered(card, entities, tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (40, 60), "red").save(images / "hero.png")

    card.show_entity(entities.create_entity("Aria", "Character", image="hero.png"))

    assert card._image_ref is not None
    assert not any("image not found" in t for t in label_texts(card))


def test_load_image_scales_within_the_max_side(root, tmp_path):
    Image.new("RGB", (1000, 500), "blue").save(tmp_path / "wide.png")

    image = load_image(tmp_path, "wide.png", max_side=200)

    assert image.cget("size") == (200, 100)


def test_load_image_never_leaves_the_images_folder(root, tmp_path):
    Image.new("RGB", (10, 10), "blue").save(tmp_path / "secret.png")
    (tmp_path / "images").mkdir()

    assert load_image(tmp_path / "images", "../secret.png") is None


def test_load_image_handles_blank_missing_and_corrupt_files(root, tmp_path):
    (tmp_path / "broken.png").write_text("not an image")

    assert load_image(tmp_path, "") is None
    assert load_image(tmp_path, "absent.png") is None
    assert load_image(tmp_path, "broken.png") is None


def test_import_image_copies_into_the_images_folder(tmp_path):
    source = tmp_path / "elsewhere" / "hero.png"
    source.parent.mkdir()
    Image.new("RGB", (4, 4), "red").save(source)

    name = import_image(source, tmp_path / "images")

    assert name == "hero.png"
    assert (tmp_path / "images" / "hero.png").is_file()


def test_import_image_never_overwrites_a_different_file(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "hero.png").write_bytes(b"original")
    source = tmp_path / "hero.png"
    source.write_bytes(b"new")

    first = import_image(source, images)
    second = import_image(source, images)

    assert (first, second) == ("hero_1.png", "hero_2.png")
    assert (images / "hero.png").read_bytes() == b"original"


def test_import_image_keeps_the_name_for_a_file_already_in_the_folder(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "hero.png").write_bytes(b"x")

    assert import_image(images / "hero.png", images) == "hero.png"
    assert sorted(p.name for p in images.iterdir()) == ["hero.png"]


def test_browse_image_fills_the_entry_with_the_imported_name(card, monkeypatch, tmp_path):
    source = tmp_path / "pick.png"
    Image.new("RGB", (4, 4), "red").save(source)
    monkeypatch.setattr(card_view.filedialog, "askopenfilename", lambda **kwargs: str(source))
    card.start_new()

    card.browse_image()

    assert card.image_entry.get() == "pick.png"
    assert (tmp_path / "images" / "pick.png").is_file()


def test_browse_image_cancelled_leaves_entry_untouched(card, monkeypatch):
    monkeypatch.setattr(card_view.filedialog, "askopenfilename", lambda **kwargs: "")
    card.start_new()

    card.browse_image()

    assert card.image_entry.get() == ""


def test_edit_form_buttons_are_save_and_cancel(card, aria):
    card.show_entity(aria)
    card.start_edit()

    texts = button_texts(card)

    assert "Save" in texts and "Cancel" in texts
    assert "Copy" not in texts and "Duplicate" not in texts
