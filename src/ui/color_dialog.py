import tkinter as tk
from tkinter import colorchooser

import customtkinter as ctk

from src.ui import colors, theme

SWATCH_COLUMNS = 6


class ColorDialog(ctk.CTkToplevel):
    def __init__(self, master, label: str, current: str | None):
        super().__init__(master)
        self.result = None
        self._color = current if colors.is_hex(current or "") else colors.PRESET_COLORS[0]
        self._swatches: dict[str, ctk.CTkButton] = {}

        self.title("Highlight Colour")
        self.resizable(False, False)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=32, pady=22)
        theme.primary_button(bar, "Save", self.save, width=100).pack(side="left")
        theme.secondary_button(bar, "Cancel", self.destroy, width=100).pack(side="left", padx=10)

        ctk.CTkLabel(self, text=f"Highlight colour for {label}", font=theme.font("heading"),
                     text_color=theme.TEXT, anchor="w").pack(padx=32, pady=(26, 2), anchor="w")
        ctk.CTkLabel(
            self, text="Names and words from this tab are highlighted in this colour.",
            font=theme.font("note"), text_color=theme.TEXT_MUTED, anchor="w",
        ).pack(padx=32, anchor="w")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=32, pady=(18, 8), anchor="w")
        for index, hex_color in enumerate(colors.PRESET_COLORS):
            swatch = ctk.CTkButton(
                grid, text="", width=44, height=34, corner_radius=4, fg_color=hex_color,
                hover_color=hex_color, border_width=2, border_color=theme.SURFACE,
                command=lambda c=hex_color: self.set_color(c))
            swatch.grid(row=index // SWATCH_COLUMNS, column=index % SWATCH_COLUMNS,
                        padx=4, pady=4)
            self._swatches[hex_color] = swatch

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=32, pady=(4, 0), anchor="w")
        ctk.CTkLabel(row, text="Hex", font=theme.font("label"),
                     text_color=theme.TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.hex_entry = theme.styled_entry(row, width=120)
        self.hex_entry.pack(side="left")
        self.hex_entry.bind("<KeyRelease>", lambda _event: self._on_hex_typed())
        theme.secondary_button(row, "Pick...", self.pick_custom, width=90).pack(
            side="left", padx=(10, 0))

        self.preview = ctk.CTkLabel(
            self, text="Aria Vale, Old Mill, aelwyn", font=theme.font("subheading"),
            fg_color=theme.SURFACE, corner_radius=4, height=54)
        self.preview.pack(fill="x", padx=32, pady=(18, 0))
        self.error_label = ctk.CTkLabel(self, text="", font=theme.font("note"),
                                        text_color=theme.DANGER, anchor="w")
        self.error_label.pack(padx=32, pady=(6, 0), anchor="w")

        self.set_color(self._color)
        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.grab_set()
        except tk.TclError:
            pass

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color.upper()
        self.hex_entry.delete(0, "end")
        self.hex_entry.insert(0, self._color)
        self.error_label.configure(text="")
        self._refresh()

    def pick_custom(self) -> None:
        chosen = colorchooser.askcolor(color=self._color, parent=self, title="Choose a colour")
        if chosen and chosen[1]:
            self.set_color(chosen[1])
            try:
                self.grab_set()
            except tk.TclError:
                pass

    def _on_hex_typed(self) -> None:
        text = self.hex_entry.get().strip()
        if text and not text.startswith("#"):
            text = "#" + text
        if colors.is_hex(text):
            self._color = text.upper()
            self.error_label.configure(text="")
            self._refresh()
        else:
            self.error_label.configure(text="Use a colour like #E0A458.")

    def _refresh(self) -> None:
        shown = colors.readable_on(self._color, theme.SURFACE)
        self.preview.configure(text_color=shown)
        for hex_color, swatch in self._swatches.items():
            swatch.configure(border_color=theme.TEXT if hex_color == self._color else theme.SURFACE)

    def save(self) -> None:
        if self.error_label.cget("text"):
            return
        self.result = self._color
        self.destroy()


def ask_color(parent, label: str, current: str | None):
    dialog = ColorDialog(parent, label, current)
    parent.wait_window(dialog)
    return dialog.result
