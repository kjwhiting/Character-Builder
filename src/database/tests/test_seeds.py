import re

import pytest

from src.database import seeds


class TestFieldTypes:
    def test_seven_field_types_are_supported(self):
        assert seeds.FIELD_TYPES == (
            "text", "textarea", "list", "choice", "multichoice", "checkbox", "number")

    def test_text_is_the_default_field_type(self):
        assert seeds.DEFAULT_FIELD_TYPE == "text"
        assert seeds.DEFAULT_FIELD_TYPE in seeds.FIELD_TYPES

    @pytest.mark.parametrize("constant, expected", [
        (seeds.FIELD_TYPE_TEXT, "text"),
        (seeds.FIELD_TYPE_TEXTAREA, "textarea"),
        (seeds.FIELD_TYPE_LIST, "list"),
        (seeds.FIELD_TYPE_CHOICE, "choice"),
        (seeds.FIELD_TYPE_MULTICHOICE, "multichoice"),
        (seeds.FIELD_TYPE_CHECKBOX, "checkbox"),
        (seeds.FIELD_TYPE_NUMBER, "number"),
    ])
    def test_each_constant_names_its_stored_value(self, constant, expected):
        assert constant == expected


class TestStarterTabs:
    def test_a_new_project_starts_with_six_tabs_in_a_fixed_order(self):
        assert seeds.DEFAULT_PROJECT_TEMPLATE_KEYS == (
            "characters", "magic", "places", "items", "events", "dictionary")

    def test_every_starter_tab_has_a_template(self):
        for key in seeds.DEFAULT_PROJECT_TEMPLATE_KEYS:
            assert key in seeds.TEMPLATES

    def test_a_blank_template_exists_for_custom_tabs(self):
        assert "blank" in seeds.TEMPLATES

    def test_template_keys_match_their_registry_keys(self):
        for key, template in seeds.TEMPLATES.items():
            assert template["key"] == key

    @pytest.mark.parametrize("key", sorted(seeds.TEMPLATES))
    def test_templates_carry_a_label_noun_and_hex_colour(self, key):
        template = seeds.TEMPLATES[key]

        assert template["label"] and template["entry_noun"]
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", template["color"])

    @pytest.mark.parametrize("key", sorted(seeds.TEMPLATES))
    def test_starter_tabs_come_with_no_fields_so_the_creator_decides(self, key):
        assert seeds.TEMPLATES[key]["categories"] == []

    def test_starter_tabs_have_distinct_colours(self):
        colours = [seeds.TEMPLATES[k]["color"] for k in seeds.DEFAULT_PROJECT_TEMPLATE_KEYS]

        assert len(set(colours)) == len(colours)

    def test_each_starter_tab_names_what_one_entry_is_called(self):
        nouns = {k: seeds.TEMPLATES[k]["entry_noun"] for k in seeds.DEFAULT_PROJECT_TEMPLATE_KEYS}

        assert nouns == {
            "characters": "Character", "magic": "Spell", "places": "Place",
            "items": "Item", "events": "Event", "dictionary": "Word",
        }


class TestGettingTemplates:
    def test_a_template_is_returned_as_an_independent_copy(self):
        first = seeds.get_template("characters")
        first["categories"].append({"name": "Scratch", "fields": []})
        first["label"] = "Changed"

        assert seeds.get_template("characters")["categories"] == []
        assert seeds.get_template("characters")["label"] == "Characters"

    def test_an_unknown_template_names_the_available_ones(self):
        with pytest.raises(KeyError) as caught:
            seeds.get_template("nonsense")

        assert "characters" in str(caught.value)
        assert "nonsense" in str(caught.value)
