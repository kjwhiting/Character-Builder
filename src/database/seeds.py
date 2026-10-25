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


def _field(name: str, field_type: str = FIELD_TYPE_TEXT, **options) -> FieldSeed:
    seed: FieldSeed = {"name": name, "type": field_type}
    if options:
        seed["options"] = dict(options)
    return seed


def _choice(name: str, *choices: str) -> FieldSeed:
    return _field(name, FIELD_TYPE_CHOICE, choices=list(choices))


def _number(name: str, unit: str = "") -> FieldSeed:
    return _field(name, FIELD_TYPE_NUMBER, unit=unit) if unit else _field(name, FIELD_TYPE_NUMBER)


def _checkbox(name: str) -> FieldSeed:
    return _field(name, FIELD_TYPE_CHECKBOX)


CHARACTER_TEMPLATE: Template = {
    "key": "characters",
    "label": "Characters",
    "entry_noun": "Character",
    "color": "#E0A458",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Basics", "fields": [
            _number("Age", "years"),
            _number("Height", "cm"),
            _number("Weight", "kg"),
            _checkbox("Alive"),
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

MAGIC_TEMPLATE: Template = {
    "key": "magic",
    "label": "Magic",
    "entry_noun": "Spell",
    "color": "#A98BD6",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Mechanics", "fields": [
            _choice("Kind", "Arcane", "Divine", "Natural", "Spiritual", "Other"),
            _choice("Difficulty", "Novice", "Adept", "Master"),
            _field("Source of power"),
            _field("Cost"),
            _field("Limitations"),
            _number("Range", "m"),
            _checkbox("Needs components"),
            _checkbox("Forbidden"),
        ]},
        {"name": "Lore", "fields": [
            _field("Origin"),
            _field("Known practitioners", FIELD_TYPE_LIST),
            _field("Taboos"),
        ]},
    ],
}

PLACES_TEMPLATE: Template = {
    "key": "places",
    "label": "Places",
    "entry_noun": "Place",
    "color": "#7FBF8F",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Geography", "fields": [
            _choice("Terrain", "Forest", "Coast", "Mountain", "Plains", "Desert", "Swamp",
                    "Underground", "Island", "Other"),
            _field("Climate"),
            _field("Landmarks", FIELD_TYPE_LIST),
        ]},
        {"name": "People and Culture", "fields": [
            _choice("Settlement", "Wilderness", "Hamlet", "Village", "Town", "City", "Capital"),
            _number("Population"),
            _field("Inhabitants"),
            _field("Government"),
            _field("Customs"),
            _field("Languages", FIELD_TYPE_LIST),
        ]},
        {"name": "History", "fields": [
            _field("Founding"),
            _field("Notable events", FIELD_TYPE_LIST),
        ]},
    ],
}

ITEMS_TEMPLATE: Template = {
    "key": "items",
    "label": "Items",
    "entry_noun": "Item",
    "color": "#D6C06E",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Properties", "fields": [
            _choice("Kind", "Weapon", "Armor", "Tool", "Jewelry", "Container", "Relic", "Other"),
            _choice("Rarity", "Common", "Uncommon", "Rare", "Legendary", "Unique"),
            _checkbox("Magical"),
            _number("Weight", "kg"),
            _field("Materials", FIELD_TYPE_LIST),
            _field("Appearance"),
            _field("Powers"),
            _field("Limitations"),
        ]},
        {"name": "Provenance", "fields": [
            _field("Creator"),
            _field("Origin"),
            _field("Current owner"),
            _field("Location"),
        ]},
    ],
}

EVENTS_TEMPLATE: Template = {
    "key": "events",
    "label": "Events",
    "entry_noun": "Event",
    "color": "#D98080",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Details", "fields": [
            _field("When"),
            _field("Where"),
            _choice("Scale", "Personal", "Local", "Regional", "Global"),
            _number("Duration", "days"),
            _field("Participants", FIELD_TYPE_LIST),
            _checkbox("Public knowledge"),
            _field("Outcome"),
        ]},
        {"name": "Context", "fields": [
            _field("Causes"),
            _field("Consequences"),
        ]},
    ],
}

DICTIONARY_TEMPLATE: Template = {
    "key": "dictionary",
    "label": "Dictionary",
    "entry_noun": "Word",
    "color": "#8CB4C8",
    "categories": [
        {"name": "Definition", "fields": [
            _field("Meaning", FIELD_TYPE_TEXTAREA),
            _choice("Part of speech", "noun", "verb", "adjective", "adverb", "pronoun",
                    "preposition", "conjunction", "interjection", "particle", "other"),
            _field("Language"),
            _field("Example", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Pronunciation", "fields": [
            _field("Pronunciation"),
        ]},
        {"name": "Grammar", "fields": [
            _field("Forms", FIELD_TYPE_LIST),
            _field("Notes", FIELD_TYPE_TEXTAREA),
        ]},
        {"name": "Origin", "fields": [
            _field("Etymology", FIELD_TYPE_TEXTAREA),
            _field("Related words", FIELD_TYPE_LIST),
        ]},
    ],
}

BLANK_TEMPLATE: Template = {
    "key": "blank",
    "label": "Blank",
    "entry_noun": "Entry",
    "color": "#8FB3C8",
    "categories": [
        {"name": "Description", "fields": [
            _field("Description", FIELD_TYPE_TEXTAREA),
        ]},
    ],
}

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
