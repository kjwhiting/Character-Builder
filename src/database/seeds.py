"""Default templates (schema seeds) and field-type constants.

This module is pure data. It imports nothing from the rest of the project and
never touches a database, so it is safe to import from anywhere (database layer,
services, UI, tests).

A *template* describes the categories and fields a brand-new profile starts with:

    Template
      key               short identifier, e.g. "characters"
      label             human-readable name, e.g. "Characters"
      entity_type       what one entry is called, e.g. "Character"
      profile_filename  default file name for this profile, e.g. "Characters.sqlite"
      categories        ordered list of CategorySeed
        CategorySeed
          name          e.g. "Relations"
          fields        ordered list of FieldSeed
            FieldSeed
              name      e.g. "Best friend"
              type      one of FIELD_TYPES

Templates are only used to seed an empty profile. Once a profile exists, its fields
and categories live in the database and are changed through File > Adjust Fields.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Tuple, TypedDict

# --------------------------------------------------------------------------- #
# Field types
# --------------------------------------------------------------------------- #
FIELD_TYPE_TEXT = "text"          # one line
FIELD_TYPE_TEXTAREA = "textarea"  # free-form paragraph(s)
FIELD_TYPE_LIST = "list"          # one item per line

FIELD_TYPES: Tuple[str, ...] = (FIELD_TYPE_TEXT, FIELD_TYPE_TEXTAREA, FIELD_TYPE_LIST)
DEFAULT_FIELD_TYPE = FIELD_TYPE_TEXT

# --------------------------------------------------------------------------- #
# Entity kinds
# --------------------------------------------------------------------------- #
ENTITY_TYPE_CHARACTER = "Character"
ENTITY_TYPE_PLACE = "Place"
ENTITY_TYPES: Tuple[str, ...] = (ENTITY_TYPE_CHARACTER, ENTITY_TYPE_PLACE)


# --------------------------------------------------------------------------- #
# Shapes
# --------------------------------------------------------------------------- #
class FieldSeed(TypedDict):
    name: str
    type: str


class CategorySeed(TypedDict):
    name: str
    fields: List[FieldSeed]


class Template(TypedDict):
    key: str
    label: str
    entity_type: str
    profile_filename: str
    categories: List[CategorySeed]


def _field(name: str, field_type: str = FIELD_TYPE_TEXT) -> FieldSeed:
    return {"name": name, "type": field_type}


# --------------------------------------------------------------------------- #
# Characters
# --------------------------------------------------------------------------- #
CHARACTER_TEMPLATE: Template = {
    "key": "characters",
    "label": "Characters",
    "entity_type": ENTITY_TYPE_CHARACTER,
    "profile_filename": "Characters.sqlite",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Relations", "fields": [
            _field("Best friend"),
            _field("Enemies"),
            _field("Raised by"),
        ]},
        {"name": "Musical Contributions", "fields": [
            _field("Instruments"),
            _field("Want to learn"),
        ]},
        {"name": "Dances", "fields": [
            _field("Ritual related"),
            _field("Free form"),
        ]},
        {"name": "Favorites", "fields": [
            _field("Color"),
            _field("Food"),
            _field("Drink"),
            _field("Type of soup"),
            _field("Animal"),
            _field("Plant"),
        ]},
    ],
}

# --------------------------------------------------------------------------- #
# Worldbuilding
#
# PROVISIONAL: a small, generic starting set for places. Replace the categories
# and fields below with your own list; nothing else in the project depends on
# their names (tests only check that the structure is valid).
# --------------------------------------------------------------------------- #
WORLDBUILDING_TEMPLATE: Template = {
    "key": "worldbuilding",
    "label": "Worldbuilding",
    "entity_type": ENTITY_TYPE_PLACE,
    "profile_filename": "Worldbuilding.sqlite",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Geography", "fields": [
            _field("Terrain"),
            _field("Climate"),
            _field("Landmarks", FIELD_TYPE_LIST),
        ]},
        {"name": "People and Culture", "fields": [
            _field("Inhabitants"),
            _field("Government"),
            _field("Customs"),
            _field("Languages"),
        ]},
        {"name": "History", "fields": [
            _field("Founding"),
            _field("Notable events", FIELD_TYPE_LIST),
        ]},
    ],
}

# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
TEMPLATES: Dict[str, Template] = {
    CHARACTER_TEMPLATE["key"]: CHARACTER_TEMPLATE,
    WORLDBUILDING_TEMPLATE["key"]: WORLDBUILDING_TEMPLATE,
}
DEFAULT_TEMPLATE_KEY = CHARACTER_TEMPLATE["key"]


def template_keys() -> Tuple[str, ...]:
    """Keys of every available template, in registration order."""
    return tuple(TEMPLATES)


def get_template(key: str) -> Template:
    """Return an independent copy of a template.

    A copy is returned so callers can never change the shared defaults by accident.
    Raises KeyError for an unknown key.
    """
    try:
        return copy.deepcopy(TEMPLATES[key])
    except KeyError:
        known = ", ".join(TEMPLATES)
        raise KeyError(f"Unknown template {key!r}. Available templates: {known}") from None
