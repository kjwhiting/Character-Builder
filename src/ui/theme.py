import tkinter as tk

import customtkinter as ctk

BACKGROUND = "#151918"
SIDEBAR_BG = "#1F302A"
SURFACE = "#363E40"
INPUT_BG = "#222828"

BORDER = "#4E5455"
INPUT_BORDER = "#979A9A"

TEXT = "#EDEEEE"
TEXT_MUTED = "#C4C5C5"
TEXT_ON_ACCENT = "#0A0C0C"

ACCENT = "#A77646"
ACCENT_HOVER = "#B38960"
GOLD = "#C8AA8C"

SELECTION_BG = "#3B5C4C"
HOVER_BG = "#2D423B"
DRAG_BG = "#645E46"
DANGER = "#F5A898"
FOCUS_RING = TEXT

FONT_FAMILY = "Georgia"

FONT_STYLES = {
    "title": {"size": 28, "weight": "bold", "slant": "roman"},
    "heading": {"size": 21, "weight": "bold", "slant": "roman"},
    "subheading": {"size": 16, "weight": "bold", "slant": "roman"},
    "body": {"size": 15, "weight": "normal", "slant": "roman"},
    "label": {"size": 15, "weight": "bold", "slant": "roman"},
    "button": {"size": 14, "weight": "bold", "slant": "roman"},
    "small": {"size": 12, "weight": "normal", "slant": "roman"},
    "note": {"size": 13, "weight": "normal", "slant": "italic"},
    "placeholder": {"size": 18, "weight": "normal", "slant": "italic"},
}

PRIMARY_BUTTON_STYLE = {
    "fg_color": ACCENT,
    "hover_color": ACCENT_HOVER,
    "text_color": TEXT_ON_ACCENT,
    "corner_radius": 4,
}

SECONDARY_BUTTON_STYLE = {
    "fg_color": "transparent",
    "hover_color": HOVER_BG,
    "text_color": TEXT,
    "border_width": 1,
    "border_color": GOLD,
    "corner_radius": 4,
}

DANGER_BUTTON_STYLE = {
    "fg_color": "transparent",
    "hover_color": HOVER_BG,
    "text_color": DANGER,
    "border_width": 1,
    "border_color": DANGER,
    "corner_radius": 4,
}

ENTRY_STYLE = {
    "fg_color": INPUT_BG,
    "text_color": TEXT,
    "placeholder_text_color": TEXT_MUTED,
    "border_color": INPUT_BORDER,
    "border_width": 1,
    "corner_radius": 4,
}

COMBO_STYLE = {
    "fg_color": INPUT_BG,
    "text_color": TEXT,
    "border_color": INPUT_BORDER,
    "border_width": 1,
    "corner_radius": 4,
    "button_color": BORDER,
    "button_hover_color": ACCENT,
    "dropdown_fg_color": INPUT_BG,
    "dropdown_text_color": TEXT,
    "dropdown_hover_color": SELECTION_BG,
}

TEXTBOX_STYLE = {
    "fg_color": INPUT_BG,
    "text_color": TEXT,
    "border_color": INPUT_BORDER,
    "border_width": 1,
    "corner_radius": 4,
    "wrap": "word",
    "scrollbar_button_color": INPUT_BORDER,
    "scrollbar_button_hover_color": GOLD,
}

CARD_STYLE = {
    "fg_color": SURFACE,
    "border_width": 1,
    "border_color": GOLD,
    "corner_radius": 6,
}


def font(style: str = "body") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, **FONT_STYLES[style])


def make_focusable(button, key_command=None):
    try:
        canvas = button._canvas
        base_width = button.cget("border_width")
        base_color = button.cget("border_color")
        canvas.configure(takefocus=1)

        def on_focus_in(_event):
            try:
                button.configure(border_width=max(base_width, 3), border_color=FOCUS_RING)
            except tk.TclError:
                pass

        def on_focus_out(_event):
            try:
                button.configure(border_width=base_width, border_color=base_color)
            except tk.TclError:
                pass

        def on_key(_event):
            command = key_command or button.cget("command")
            if command:
                command()
            return "break"

        canvas.bind("<FocusIn>", on_focus_in)
        canvas.bind("<FocusOut>", on_focus_out)
        for sequence in ("<Return>", "<KP_Enter>", "<space>"):
            canvas.bind(sequence, on_key)
    except (AttributeError, tk.TclError):
        pass


def primary_button(parent, text, command, width=96, height=38):
    button = ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height,
        font=font("button"), **PRIMARY_BUTTON_STYLE,
    )
    make_focusable(button)
    return button


def secondary_button(parent, text, command, width=96, height=38, danger=False):
    style = DANGER_BUTTON_STYLE if danger else SECONDARY_BUTTON_STYLE
    button = ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height,
        font=font("body"), **style,
    )
    make_focusable(button)
    return button


def styled_entry(parent, height=38, **kwargs):
    return ctk.CTkEntry(parent, height=height, font=font("body"), **ENTRY_STYLE, **kwargs)


def styled_combo(parent, values, height=38, **kwargs):
    return ctk.CTkComboBox(
        parent, values=values, state="readonly", height=height,
        font=font("body"), dropdown_font=font("body"), **COMBO_STYLE, **kwargs,
    )


def styled_textbox(parent, height=110, **kwargs):
    return ctk.CTkTextbox(parent, height=height, font=font("body"), **TEXTBOX_STYLE, **kwargs)


def scrollable(parent, fg_color=SURFACE, **kwargs):
    return ctk.CTkScrollableFrame(
        parent, fg_color=fg_color, corner_radius=0, scrollbar_fg_color=fg_color,
        scrollbar_button_color=INPUT_BORDER, scrollbar_button_hover_color=GOLD, **kwargs,
    )


def ornament(parent, color=GOLD):
    frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, height=16)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_columnconfigure(2, weight=1)
    tk.Frame(frame, height=1, bd=0, highlightthickness=0, bg=color).grid(
        row=0, column=0, sticky="ew")
    ctk.CTkLabel(frame, text="\u25C6", font=font("small"), text_color=color).grid(
        row=0, column=1, padx=12)
    tk.Frame(frame, height=1, bd=0, highlightthickness=0, bg=color).grid(
        row=0, column=2, sticky="ew")
    return frame


def section_header(parent, text):
    frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
    frame.grid_columnconfigure(2, weight=1)
    ctk.CTkLabel(frame, text="\u25C6", font=font("small"), text_color=GOLD).grid(
        row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(frame, text=text.upper(), font=font("subheading"),
                 text_color=GOLD).grid(row=0, column=1)
    tk.Frame(frame, height=1, bd=0, highlightthickness=0, bg=GOLD).grid(
        row=0, column=2, sticky="ew", padx=(14, 0))
    return frame
