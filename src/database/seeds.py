from __future__ import annotations

import copy
from typing import Dict, List, Tuple, TypedDict

FIELD_TYPE_TEXT = "text"
FIELD_TYPE_TEXTAREA = "textarea"
FIELD_TYPE_LIST = "list"
FIELD_TYPE_CHOICE = "choice"
FIELD_TYPE_MULTICHOICE = "multichoice"
FIELD_TYPE_CHECKBOX = "checkbox"
FIELD_TYPE_NUMBER = "number"

FIELD_TYPES: Tuple[str, ...] = (
    FIELD_TYPE_TEXT,
    FIELD_TYPE_TEXTAREA,
    FIELD_TYPE_LIST,
    FIELD_TYPE_CHOICE,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_CHECKBOX,
    FIELD_TYPE_NUMBER,
)
DEFAULT_FIELD_TYPE = FIELD_TYPE_TEXT


class FieldSeed(TypedDict, total=False):
    name: str
    type: str
    options: dict


class CategorySeed(TypedDict):
    name: str
    fields: List[FieldSeed]


class Template(TypedDict):
    key: str
    label: str
    entry_noun: str
    color: str
    categories: List[CategorySeed]


def _tab(key: str, label: str, entry_noun: str, color: str) -> Template:
    return {"key": key, "label": label, "entry_noun": entry_noun, "color": color,
            "categories": []}


CHARACTER_TEMPLATE: Template = _tab("characters", "Characters", "Character", "#E0A458")
MAGIC_TEMPLATE: Template = _tab("magic", "Magic", "Spell", "#A98BD6")
PLACES_TEMPLATE: Template = _tab("places", "Places", "Place", "#7FBF8F")
ITEMS_TEMPLATE: Template = _tab("items", "Items", "Item", "#D6C06E")
EVENTS_TEMPLATE: Template = _tab("events", "Events", "Event", "#D98080")
DICTIONARY_TEMPLATE: Template = _tab("dictionary", "Dictionary", "Word", "#8CB4C8")
BLANK_TEMPLATE: Template = _tab("blank", "Blank", "Entry", "#8FB3C8")

TEMPLATES: Dict[str, Template] = {
    template["key"]: template
    for template in (
        CHARACTER_TEMPLATE,
        MAGIC_TEMPLATE,
        PLACES_TEMPLATE,
        ITEMS_TEMPLATE,
        EVENTS_TEMPLATE,
        DICTIONARY_TEMPLATE,
        BLANK_TEMPLATE,
    )
}
DEFAULT_PROJECT_TEMPLATE_KEYS: Tuple[str, ...] = (
    "characters", "magic", "places", "items", "events", "dictionary",
)


def get_template(key: str) -> Template:
    try:
        return copy.deepcopy(TEMPLATES[key])
    except KeyError:
        known = ", ".join(TEMPLATES)
        raise KeyError(f"Unknown template {key!r}. Available templates: {known}") from None
