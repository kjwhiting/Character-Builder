"""Tests for database/seeds.py: field types, templates and the template registry.

These tests double as documentation of what a valid template looks like.
"""

import pytest

from src.database import seeds
from src.database.connection import profile_noun

ALL_TEMPLATES = list(seeds.TEMPLATES.values())


def names(template):
    """[(category name, [field names]), ...] for easy comparison."""
    return [(c["name"], [f["name"] for f in c["fields"]]) for c in template["categories"]]


class TestFieldTypes:
    def test_the_three_supported_types(self):
        assert seeds.FIELD_TYPES == ("text", "textarea", "list")

    def test_constants_match_the_tuple(self):
        assert (seeds.FIELD_TYPE_TEXT, seeds.FIELD_TYPE_TEXTAREA,
                seeds.FIELD_TYPE_LIST) == seeds.FIELD_TYPES

    def test_default_type_is_a_valid_type(self):
        assert seeds.DEFAULT_FIELD_TYPE in seeds.FIELD_TYPES

    def test_entity_types(self):
        assert seeds.ENTITY_TYPES == ("Character", "Place")


class TestCharacterTemplate:
    def test_categories_and_fields_in_order(self):
        assert names(seeds.CHARACTER_TEMPLATE) == [
            ("Description", ["Description"]),
            ("Relations", ["Best friend", "Enemies", "Raised by"]),
            ("Musical Contributions", ["Instruments", "Want to learn"]),
            ("Dances", ["Ritual related", "Free form"]),
            ("Favorites", ["Color", "Food", "Drink", "Type of soup", "Animal", "Plant"]),
        ]

    def test_description_is_the_only_multiline_field(self):
        types = {
            f["name"]: f["type"]
            for c in seeds.CHARACTER_TEMPLATE["categories"] for f in c["fields"]
        }
        assert types["Description"] == seeds.FIELD_TYPE_TEXTAREA
        others = {name: t for name, t in types.items() if name != "Description"}
        assert set(others.values()) == {seeds.FIELD_TYPE_TEXT}

    def test_entity_type_and_filename(self):
        assert seeds.CHARACTER_TEMPLATE["entity_type"] == "Character"
        assert seeds.CHARACTER_TEMPLATE["profile_filename"] == "Characters.sqlite"


class TestWorldbuildingTemplate:
    def test_describes_places(self):
        assert seeds.WORLDBUILDING_TEMPLATE["entity_type"] == "Place"
        assert seeds.WORLDBUILDING_TEMPLATE["profile_filename"] == "Worldbuilding.sqlite"

    def test_starts_with_a_description_paragraph_field(self):
        first = seeds.WORLDBUILDING_TEMPLATE["categories"][0]
        assert first["name"] == "Description"
        assert first["fields"] == [{"name": "Description", "type": "textarea"}]

    def test_uses_more_than_one_field_type(self):
        types = {f["type"] for c in seeds.WORLDBUILDING_TEMPLATE["categories"]
                 for f in c["fields"]}
        assert seeds.FIELD_TYPE_LIST in types


@pytest.mark.parametrize("template", ALL_TEMPLATES, ids=lambda t: t["key"])
class TestEveryTemplateIsValid:
    def test_has_all_required_keys(self, template):
        assert set(template) == {"key", "label", "entity_type", "profile_filename",
                                 "categories"}

    def test_text_values_are_not_blank(self, template):
        for key in ("key", "label", "entity_type", "profile_filename"):
            assert template[key].strip() != ""

    def test_entity_type_is_a_known_type(self, template):
        assert template["entity_type"] in seeds.ENTITY_TYPES

    def test_has_at_least_one_category(self, template):
        assert len(template["categories"]) >= 1

    def test_every_category_has_a_name_and_fields(self, template):
        for category in template["categories"]:
            assert category["name"].strip() != ""
            assert len(category["fields"]) >= 1

    def test_category_names_are_unique_ignoring_case(self, template):
        lowered = [c["name"].lower() for c in template["categories"]]
        assert len(lowered) == len(set(lowered))

    def test_field_names_are_unique_within_a_category(self, template):
        for category in template["categories"]:
            lowered = [f["name"].lower() for f in category["fields"]]
            assert len(lowered) == len(set(lowered)), category["name"]

    def test_every_field_has_a_name_and_a_valid_type(self, template):
        for category in template["categories"]:
            for field in category["fields"]:
                assert field["name"].strip() != ""
                assert field["type"] in seeds.FIELD_TYPES

    def test_filename_is_a_sqlite_file(self, template):
        assert template["profile_filename"].endswith(".sqlite")

    def test_filename_gives_the_matching_add_button_word(self, template):
        # "Characters.sqlite" -> "Add Character", "Worldbuilding.sqlite" -> "Add Place"
        assert profile_noun(template["profile_filename"]) == template["entity_type"]


class TestRegistry:
    def test_both_templates_are_registered(self):
        assert seeds.template_keys() == ("characters", "worldbuilding")

    def test_keys_match_the_templates_they_point_to(self):
        for key, template in seeds.TEMPLATES.items():
            assert template["key"] == key

    def test_default_template_is_characters(self):
        assert seeds.DEFAULT_TEMPLATE_KEY == "characters"
        assert seeds.DEFAULT_TEMPLATE_KEY in seeds.TEMPLATES

    def test_profile_filenames_are_unique(self):
        filenames = [t["profile_filename"].lower() for t in ALL_TEMPLATES]
        assert len(filenames) == len(set(filenames))


class TestGetTemplate:
    def test_returns_the_requested_template(self):
        assert seeds.get_template("characters") == seeds.CHARACTER_TEMPLATE

    def test_returns_an_independent_copy(self):
        copy_ = seeds.get_template("characters")
        copy_["categories"][0]["name"] = "Changed"
        copy_["categories"][1]["fields"].append({"name": "Extra", "type": "text"})
        assert seeds.CHARACTER_TEMPLATE["categories"][0]["name"] == "Description"
        assert len(seeds.CHARACTER_TEMPLATE["categories"][1]["fields"]) == 3

    def test_unknown_key_lists_the_available_ones(self):
        with pytest.raises(KeyError, match="characters, worldbuilding"):
            seeds.get_template("spaceships")
