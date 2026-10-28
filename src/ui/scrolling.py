import sys
import tkinter as tk

import customtkinter as ctk

PIXELS_PER_UNIT = 40
UNITS_PER_NOTCH = 3
TEXT_LINES_PER_NOTCH = 3
_PLATFORM_MAC = sys.platform == "darwin"


class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_canvas.configure(
            xscrollincrement=PIXELS_PER_UNIT, yscrollincrement=PIXELS_PER_UNIT)

    def _mouse_wheel_all(self, event):
        return None

    @property
    def is_horizontal(self) -> bool:
        return getattr(self, "_orientation", "vertical") == "horizontal"

    def can_scroll(self, direction: int) -> bool:
        view = (self._parent_canvas.xview() if self.is_horizontal
                else self._parent_canvas.yview())
        if view[0] <= 0.0 and view[1] >= 1.0:
            return False
        return view[0] > 0.0 if direction < 0 else view[1] < 1.0

    def scroll_by(self, direction: int, notches: int) -> None:
        amount = direction * notches * UNITS_PER_NOTCH
        if self.is_horizontal:
            self._parent_canvas.xview_scroll(amount, "units")
        else:
            self._parent_canvas.yview_scroll(amount, "units")


def wheel_steps(event) -> tuple[int, int]:
    number = getattr(event, "num", None)
    if number == 4:
        return -1, 1
    if number == 5:
        return 1, 1
    delta = getattr(event, "delta", 0) or 0
    if delta == 0:
        return 0, 0
    direction = -1 if delta > 0 else 1
    if _PLATFORM_MAC:
        return direction, min(4, max(1, abs(delta)))
    return direction, max(1, abs(delta) // 120)


def text_can_scroll(text: tk.Text, direction: int) -> bool:
    first, last = text.yview()
    if first <= 0.0 and last >= 1.0:
        return False
    return first > 0.0 if direction < 0 else last < 1.0


def handle_wheel(event, widget=None):
    direction, notches = wheel_steps(event)
    if direction == 0:
        return None
    node = widget if widget is not None else _widget_under_pointer(event)
    while node is not None:
        if isinstance(node, tk.Text) and text_can_scroll(node, direction):
            node.yview_scroll(direction * notches * TEXT_LINES_PER_NOTCH, "units")
            return "break"
        if isinstance(node, SmoothScrollableFrame) and node.can_scroll(direction):
            node.scroll_by(direction, notches)
            return "break"
        node = getattr(node, "master", None)
    return None


def _widget_under_pointer(event):
    try:
        found = event.widget.winfo_containing(event.x_root, event.y_root)
    except (KeyError, tk.TclError, AttributeError):
        found = None
    return found if found is not None else event.widget


def install(window) -> None:
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        window.bind_all(sequence, handle_wheel, add=True)


def capture_wheel_on(textbox) -> None:
    inner = getattr(textbox, "_textbox", textbox)

    def forward(event):
        handle_wheel(event, inner)
        return "break"

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        inner.bind(sequence, forward)
