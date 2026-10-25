from src.database.seeds import (
    FIELD_TYPE_CHECKBOX,
    FIELD_TYPE_LIST,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_NUMBER,
)

CHECKBOX_TRUE = "true"


def split_lines(raw) -> list[str]:
    return [item.strip() for item in (raw or "").splitlines() if item.strip()]


def format_value(field_type: str, options: dict, raw) -> str:
    text = (raw or "").strip()
    if field_type in (FIELD_TYPE_LIST, FIELD_TYPE_MULTICHOICE):
        return ", ".join(split_lines(text))
    if field_type == FIELD_TYPE_CHECKBOX:
        return "Yes" if text == CHECKBOX_TRUE else "No"
    if field_type == FIELD_TYPE_NUMBER:
        unit = (options or {}).get("unit", "")
        return f"{text} {unit}".strip() if text else ""
    return text
