import sys
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def require_display():
    try:
        probe = ctk.CTk()
    except tk.TclError:
        pytest.skip("no display available")
    probe.destroy()
