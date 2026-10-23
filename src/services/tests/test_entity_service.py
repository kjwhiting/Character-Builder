import pytest

from src.services.entity_service import EntityService
from src.services.errors import EntityNotFoundError, FieldNotFoundError, InvalidNameError


@pytest.fixture
def entities(conn):
    return EntityService(conn)


def test_create_entity_stores_core_data_and_values(entities, catalog):
    entity_id = entities.create_entity(
        " Aria ", "Character", "aria.png", {catalog["Color"]: "Teal"}
    )

    entity = entities.get_entity(entity_id)
    assert (entity.name, entity.type, entity.image) == ("Aria", "Character", "aria.png")
    assert entities.get_values(entity_id) == {catalog["Color"]: "Teal"}


def test_create_entity_skips_blank_values(entities, catalog):
    entity_id = entities.create_entity(
        "Aria", "Character", values={catalog["Color"]: "Teal", catalog["Food"]: "  "}
    )

    assert entities.get_values(entity_id) == {catalog["Color"]: "Teal"}


@pytest.mark.parametrize("name, entity_type", [("", "Character"), ("   ", "Character"), ("Aria", "")])
def test_create_entity_rejects_blank_name_or_type(entities, name, entity_type):
    with pytest.raises(InvalidNameError):
        entities.create_entity(name, entity_type)

    assert entities.list_entities() == []


def test_create_entity_with_unknown_field_creates_nothing(entities, catalog):
    with pytest.raises(FieldNotFoundError):
        entities.create_entity("Aria", "Character", values={999: "x"})

    assert entities.list_entities() == []


def test_get_entity_unknown_raises(entities):
    with pytest.raises(EntityNotFoundError):
        entities.get_entity(1)


def test_update_entity_changes_core_data_and_values(entities, catalog):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    entities.update_entity(
        entity_id, "Aria Vale", "Place", "new.png",
        {catalog["Color"]: "Red", catalog["Food"]: "Soup"},
    )

    entity = entities.get_entity(entity_id)
    assert (entity.name, entity.type, entity.image) == ("Aria Vale", "Place", "new.png")
    assert entities.get_values(entity_id) == {catalog["Color"]: "Red", catalog["Food"]: "Soup"}


def test_update_entity_with_blank_value_clears_it(entities, catalog):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    entities.update_entity(entity_id, "Aria", "Character", values={catalog["Color"]: ""})

    assert entities.get_values(entity_id) == {}


def test_update_entity_leaves_unmentioned_values_alone(entities, catalog):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    entities.update_entity(entity_id, "Aria", "Character", values={catalog["Food"]: "Soup"})

    assert entities.get_values(entity_id) == {catalog["Color"]: "Teal", catalog["Food"]: "Soup"}


def test_update_unknown_entity_raises(entities):
    with pytest.raises(EntityNotFoundError):
        entities.update_entity(42, "Aria", "Character")


def test_update_with_unknown_field_changes_nothing(entities, catalog):
    entity_id = entities.create_entity("Aria", "Character")

    with pytest.raises(FieldNotFoundError):
        entities.update_entity(entity_id, "Renamed", "Character", values={999: "x"})

    assert entities.get_entity(entity_id).name == "Aria"


def test_delete_entity_cascades_to_its_values(entities, conn, catalog):
    entity_id = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    entities.delete_entity(entity_id)

    assert entities.list_entities() == []
    assert conn.execute("SELECT COUNT(*) FROM field_values").fetchone()[0] == 0


def test_delete_unknown_entity_raises(entities):
    with pytest.raises(EntityNotFoundError):
        entities.delete_entity(42)


def test_list_entities_sorts_by_name_ignoring_case(entities):
    for name in ["zed", "Bram", "aria"]:
        entities.create_entity(name, "Character")

    assert [e.name for e in entities.list_entities()] == ["aria", "Bram", "zed"]


@pytest.fixture
def searchable(entities, catalog):
    entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    entities.create_entity("Bram", "Character", values={catalog["Food"]: "Mushroom soup"})
    entities.create_entity("Old Mill", "Place", values={catalog["Description"]: "100% haunted_"})
    return entities


def test_search_with_blank_query_returns_everything(searchable):
    assert [e.name for e in searchable.search_entities("  ")] == ["Aria", "Bram", "Old Mill"]


def test_search_matches_name_ignoring_case(searchable):
    assert [e.name for e in searchable.search_entities("aRIa")] == ["Aria"]


def test_search_matches_entity_type(searchable):
    assert [e.name for e in searchable.search_entities("place")] == ["Old Mill"]


def test_search_matches_field_values(searchable):
    assert [e.name for e in searchable.search_entities("mushroom")] == ["Bram"]


def test_search_returns_each_entity_once(entities, catalog):
    entities.create_entity(
        "Teal", "Character", values={catalog["Color"]: "Teal", catalog["Food"]: "Teal tea"}
    )

    assert len(entities.search_entities("teal")) == 1


def test_search_treats_like_wildcards_literally(searchable):
    assert [e.name for e in searchable.search_entities("100%")] == ["Old Mill"]
    assert [e.name for e in searchable.search_entities("d_")] == ["Old Mill"]
    assert searchable.search_entities("%") != searchable.list_entities()


def test_search_with_no_match_returns_empty_list(searchable):
    assert searchable.search_entities("dragon") == []


def test_missing_field_lists_entities_without_a_value(entities, catalog):
    entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    entities.create_entity("Bram", "Character", values={catalog["Food"]: "Soup"})
    entities.create_entity("Cleo", "Character")

    missing = entities.get_entities_missing_field(catalog["Color"])

    assert [e.name for e in missing] == ["Bram", "Cleo"]


def test_missing_field_treats_whitespace_value_as_missing(entities, conn, catalog):
    entity_id = entities.create_entity("Aria", "Character")
    with conn:
        conn.execute(
            "INSERT INTO field_values (entity_id, field_id, value) VALUES (?, ?, ' ')",
            (entity_id, catalog["Color"]),
        )

    assert [e.name for e in entities.get_entities_missing_field(catalog["Color"])] == ["Aria"]


def test_missing_field_is_empty_when_everyone_has_a_value(entities, catalog):
    entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})

    assert entities.get_entities_missing_field(catalog["Color"]) == []


def test_missing_field_unknown_field_raises(entities):
    with pytest.raises(FieldNotFoundError):
        entities.get_entities_missing_field(999)


def test_duplicate_entity_copies_core_data_and_values(entities, catalog):
    original = entities.create_entity(
        "Aria", "Character", "aria.png", {catalog["Color"]: "Teal", catalog["Food"]: "Soup"}
    )

    copy_id = entities.duplicate_entity(original)

    copy = entities.get_entity(copy_id)
    assert copy_id != original
    assert (copy.name, copy.type, copy.image) == ("Aria (Copy)", "Character", "aria.png")
    assert entities.get_values(copy_id) == entities.get_values(original)


def test_duplicate_entity_accepts_a_custom_name(entities):
    original = entities.create_entity("Aria", "Character")

    copy_id = entities.duplicate_entity(original, "  Aria Twin ")

    assert entities.get_entity(copy_id).name == "Aria Twin"


def test_duplicate_is_independent_of_the_original(entities, catalog):
    original = entities.create_entity("Aria", "Character", values={catalog["Color"]: "Teal"})
    copy_id = entities.duplicate_entity(original)

    entities.update_entity(copy_id, "Aria (Copy)", "Character", values={catalog["Color"]: "Red"})
    entities.delete_entity(original)

    assert entities.get_values(copy_id) == {catalog["Color"]: "Red"}


def test_duplicate_unknown_entity_raises(entities):
    with pytest.raises(EntityNotFoundError):
        entities.duplicate_entity(42)


def test_duplicate_with_blank_name_creates_nothing(entities):
    original = entities.create_entity("Aria", "Character")

    with pytest.raises(InvalidNameError):
        entities.duplicate_entity(original, "  ")

    assert len(entities.list_entities()) == 1
