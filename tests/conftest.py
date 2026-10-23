import tkinter as tk

import customtkinter as ctk
import pytest

from src.services.tests.conftest import catalog, conn  # noqa: F401
from src.ui import theme


class FakeMessageBox:
    def __init__(self):
        self.calls = []
        self.answer = True

    def _record(self, kind, title, message):
        self.calls.append((kind, title, message))

    def showinfo(self, title, message, **kwargs):
        self._record("info", title, message)

    def showwarning(self, title, message, **kwargs):
        self._record("warning", title, message)

    def showerror(self, title, message, **kwargs):
        self._record("error", title, message)

    def askyesno(self, title, message, **kwargs):
        self._record("askyesno", title, message)
        return self.answer

    def kinds(self):
        return [kind for kind, _title, _message in self.calls]


@pytest.fixture
def root():
    try:
        window = ctk.CTk()
    except tk.TclError:
        pytest.skip("no display available")
    window.withdraw()
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def dialogs():
    return FakeMessageBox()


@pytest.fixture(autouse=True)
def restore_dark_palette():
    yield
    theme.apply_palette(theme.DEFAULT_PALETTE)
