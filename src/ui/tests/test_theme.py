import re

import customtkinter as ctk
import pytest

from src.ui import theme

DARK = theme.PALETTES["dark"]
LIGHT = theme.PALETTES["light"]

EXPECTED_DARK = {
    "BACKGROUND": "#151918",
    "SIDEBAR_BG": "#1F302A",
    "SURFACE": "#363E40",
    "INPUT_BG": "#222828",
    "BORDER": "#4E5455",
    "INPUT_BORDER": "#979A9A",
    "TEXT": "#EDEEEE",
    "TEXT_MUTED": "#C4C5C5",
    "TEXT_ON_ACCENT": "#0A0C0C",
    "ACCENT": "#A77646",
    "ACCENT_HOVER": "#B38960",
    "GOLD": "#C8AA8C",
    "SELECTION_BG": "#3B5C4C",
    "HOVER_BG": "#2D423B",
    "DRAG_BG": "#645E46",
    "DANGER": "#F5A898",
}

EXPECTED_LIGHT_CORE = {
    "BACKGROUND": "#F4F1EA",
    "TEXT": "#2C2623",
    "ACCENT": "#B34A32",
    "GOLD": "#C28E38",
}


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground, background):
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("name, value", sorted(EXPECTED_DARK.items()))
def test_dark_palette_matches_the_spec(name, value):
    assert DARK[name] == value


@pytest.mark.parametrize("name, value", sorted(EXPECTED_LIGHT_CORE.items()))
def test_light_palette_keeps_the_original_autumn_core(name, value):
    assert LIGHT[name] == value


def test_dark_is_the_default_palette():
    assert theme.DEFAULT_PALETTE == "dark"
    assert theme.current_palette() == "dark"
    assert theme.BACKGROUND == DARK["BACKGROUND"]


def test_both_palettes_define_exactly_the_same_names():
    assert set(DARK) == set(LIGHT)
    assert set(EXPECTED_DARK) <= set(DARK)


@pytest.mark.parametrize("palette", sorted(theme.PALETTES))
def test_every_palette_color_is_a_six_digit_hex_code(palette):
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", value) for value in theme.PALETTES[palette].values())


@pytest.mark.parametrize("palette", sorted(theme.PALETTES))
def test_focus_ring_reuses_the_text_color(palette):
    assert theme.PALETTES[palette]["FOCUS_RING"] == theme.PALETTES[palette]["TEXT"]


def test_emphasis_is_gold_on_dark_and_accent_on_light():
    assert DARK["EMPHASIS"] == DARK["GOLD"]
    assert LIGHT["EMPHASIS"] == LIGHT["ACCENT"]


def test_dark_surfaces_step_up_from_the_window_background():
    assert luminance(DARK["BACKGROUND"]) < luminance(DARK["INPUT_BG"]) < luminance(DARK["SURFACE"])


def test_light_surfaces_step_down_from_the_input_background():
    assert luminance(LIGHT["INPUT_BG"]) > luminance(LIGHT["SURFACE"]) > luminance(LIGHT["BACKGROUND"])


def test_typography_uses_georgia_serif():
    assert theme.FONT_FAMILY == "Georgia"


@pytest.mark.parametrize("style", sorted(theme.FONT_STYLES))
def test_font_styles_are_well_formed(style):
    spec = theme.FONT_STYLES[style]

    assert set(spec) == {"size", "weight", "slant"}
    assert spec["size"] > 0
    assert spec["weight"] in ("normal", "bold")
    assert spec["slant"] in ("roman", "italic")


def test_title_is_larger_than_body_and_body_is_larger_than_small():
    sizes = {name: spec["size"] for name, spec in theme.FONT_STYLES.items()}

    assert sizes["title"] > sizes["heading"] > sizes["body"] > sizes["small"]


TEXT_PAIRS = (
    [("TEXT", bg) for bg in ("BACKGROUND", "SURFACE", "SIDEBAR_BG", "INPUT_BG",
                              "SELECTION_BG", "HOVER_BG", "DRAG_BG")]
    + [("TEXT_MUTED", bg) for bg in ("BACKGROUND", "SURFACE", "SIDEBAR_BG", "INPUT_BG", "HOVER_BG")]
    + [("EMPHASIS", "SURFACE")]
    + [("DANGER", bg) for bg in ("BACKGROUND", "SURFACE", "SIDEBAR_BG", "HOVER_BG")]
    + [("TEXT_ON_ACCENT", "ACCENT"), ("TEXT_ON_ACCENT", "ACCENT_HOVER")]
)

NON_TEXT_PAIRS = [
    ("INPUT_BORDER", "INPUT_BG"),
    ("INPUT_BORDER", "SURFACE"),
    ("INPUT_BORDER", "BACKGROUND"),
    ("EMPHASIS", "SURFACE"),
    ("ACCENT", "BACKGROUND"),
    ("FOCUS_RING", "SURFACE"),
    ("FOCUS_RING", "SIDEBAR_BG"),
    ("TEXT", "BORDER"),
]


@pytest.mark.parametrize("palette", sorted(theme.PALETTES))
@pytest.mark.parametrize("foreground, background", TEXT_PAIRS)
def test_text_color_pairs_meet_wcag_aa(palette, foreground, background):
    colors = theme.PALETTES[palette]

    assert contrast(colors[foreground], colors[background]) >= 4.5


@pytest.mark.parametrize("palette", sorted(theme.PALETTES))
@pytest.mark.parametrize("foreground, background", NON_TEXT_PAIRS)
def test_outlines_and_icons_meet_the_3_to_1_minimum(palette, foreground, background):
    colors = theme.PALETTES[palette]

    assert contrast(colors[foreground], colors[background]) >= 3.0


@pytest.mark.parametrize("background", ["BACKGROUND", "SURFACE", "SIDEBAR_BG"])
def test_dark_gold_outlines_meet_the_3_to_1_minimum(background):
    assert contrast(DARK["GOLD"], DARK[background]) >= 3.0


def test_dark_accent_is_reserved_for_fills_not_text_on_surfaces():
    assert contrast(DARK["ACCENT"], DARK["SURFACE"]) < 4.5
    assert contrast(DARK["EMPHASIS"], DARK["SURFACE"]) >= 4.5


def test_apply_palette_switches_constants_and_styles():
    theme.apply_palette("light")

    assert theme.current_palette() == "light"
    assert theme.BACKGROUND == LIGHT["BACKGROUND"]
    assert theme.PRIMARY_BUTTON_STYLE["fg_color"] == LIGHT["ACCENT"]
    assert theme.PRIMARY_BUTTON_STYLE["text_color"] == LIGHT["TEXT_ON_ACCENT"]
    assert theme.CARD_STYLE["fg_color"] == LIGHT["SURFACE"]
    assert theme.ENTRY_STYLE["fg_color"] == LIGHT["INPUT_BG"]
    assert theme.COMBO_STYLE["button_color"] == LIGHT["COMBO_BUTTON"]
    assert ctk.get_appearance_mode() == "Light"


def test_apply_palette_can_switch_back_to_dark():
    theme.apply_palette("light")
    theme.apply_palette("dark")

    assert theme.TEXT == DARK["TEXT"]
    assert theme.PRIMARY_BUTTON_STYLE["fg_color"] == DARK["ACCENT"]
    assert ctk.get_appearance_mode() == "Dark"


def test_apply_palette_rejects_unknown_names_and_changes_nothing():
    with pytest.raises(KeyError, match="neon"):
        theme.apply_palette("neon")

    assert theme.current_palette() == "dark"
    assert theme.TEXT == DARK["TEXT"]


def test_button_styles_follow_the_palette():
    assert theme.PRIMARY_BUTTON_STYLE["fg_color"] == theme.ACCENT
    assert theme.PRIMARY_BUTTON_STYLE["text_color"] == theme.TEXT_ON_ACCENT
    assert theme.SECONDARY_BUTTON_STYLE["fg_color"] == "transparent"
    assert theme.SECONDARY_BUTTON_STYLE["border_color"] == theme.GOLD
    assert theme.CARD_STYLE["border_color"] == theme.GOLD
    assert theme.CARD_STYLE["fg_color"] == theme.SURFACE


def test_font_factory_builds_georgia_fonts(root):
    built = theme.font("title")

    assert isinstance(built, ctk.CTkFont)
    assert built.cget("family") == "Georgia"
    assert built.cget("size") == theme.FONT_STYLES["title"]["size"]
    assert built.cget("weight") == "bold"


def test_button_factories_apply_styles_and_run_commands(root):
    calls = []
    primary = theme.primary_button(root, "Go", lambda: calls.append("primary"))
    secondary = theme.secondary_button(root, "Stop", lambda: calls.append("secondary"))
    danger = theme.secondary_button(root, "Delete", lambda: calls.append("danger"), danger=True)

    primary.invoke()
    secondary.invoke()
    danger.invoke()

    assert calls == ["primary", "secondary", "danger"]
    assert primary.cget("fg_color") == theme.ACCENT
    assert primary.cget("text_color") == theme.TEXT_ON_ACCENT
    assert secondary.cget("border_color") == theme.GOLD
    assert danger.cget("text_color") == theme.DANGER


def test_widgets_built_after_a_switch_use_the_new_palette(root):
    theme.apply_palette("light")

    button = theme.primary_button(root, "Go", lambda: None)
    entry = theme.styled_entry(root)

    assert button.cget("fg_color") == LIGHT["ACCENT"]
    assert entry.cget("fg_color") == LIGHT["INPUT_BG"]


def test_input_factories_build_expected_widgets(root):
    assert isinstance(theme.styled_entry(root), ctk.CTkEntry)
    assert isinstance(theme.styled_textbox(root), ctk.CTkTextbox)
    combo = theme.styled_combo(root, ["a", "b"])
    assert isinstance(combo, ctk.CTkComboBox)
    assert combo.cget("values") == ["a", "b"]
