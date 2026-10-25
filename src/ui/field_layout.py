from src.database.seeds import (
    FIELD_TYPE_LIST,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_TEXTAREA,
)

ALWAYS_FULL_TYPES = (FIELD_TYPE_TEXTAREA, FIELD_TYPE_LIST, FIELD_TYPE_MULTICHOICE)


def is_full_width(field_type: str, full_width_override: bool) -> bool:
    return field_type in ALWAYS_FULL_TYPES or bool(full_width_override)


def plan_layout(widths: list[bool]) -> list[tuple[int, int, int, int]]:
    cells = []
    row, column = 0, 0
    for index, full in enumerate(widths):
        if full:
            if column != 0:
                row += 1
                column = 0
            cells.append((index, row, 0, 2))
            row += 1
            continue
        cells.append((index, row, column, 1))
        column += 1
        if column == 2:
            row += 1
            column = 0
    return cells
