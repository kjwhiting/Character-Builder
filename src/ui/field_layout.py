from src.database.seeds import (
    FIELD_TYPE_LIST,
    FIELD_TYPE_MULTICHOICE,
    FIELD_TYPE_TEXTAREA,
)

ALWAYS_FULL_TYPES = (FIELD_TYPE_TEXTAREA, FIELD_TYPE_LIST, FIELD_TYPE_MULTICHOICE)


def is_full_width(field_type: str, full_width_override: bool) -> bool:
    return field_type in ALWAYS_FULL_TYPES or bool(full_width_override)


def plan_layout(widths: list[bool], columns: int = 2) -> list[tuple[int, int, int, int]]:
    columns = max(1, columns)
    cells = []
    row, column = 0, 0
    for index, full in enumerate(widths):
        if full or columns == 1:
            if column != 0:
                row += 1
                column = 0
            cells.append((index, row, 0, columns))
            row += 1
            continue
        cells.append((index, row, column, 1))
        column += 1
        if column == columns:
            row += 1
            column = 0
    return cells


COLUMN_GAP = 18


class SectionGrid:
    def __init__(self, frame):
        self.frame = frame
        self._cells: list[tuple[object, bool]] = []
        self._columns = 0

    def add(self, widget, full: bool) -> None:
        self._cells.append((widget, full))

    def reflow(self, columns: int) -> None:
        columns = max(1, columns)
        for column in range(max(columns, self._columns)):
            self.frame.grid_columnconfigure(
                column, weight=1 if column < columns else 0,
                uniform="cells" if column < columns else "")
        plan = plan_layout([full for _widget, full in self._cells], columns)
        for index, row, column, span in plan:
            widget = self._cells[index][0]
            last = column + span >= columns
            widget.grid(row=row, column=column, columnspan=span, sticky="ew", pady=3,
                        padx=(0, 0) if last else (0, COLUMN_GAP))
        self._columns = columns
