import re

import customtkinter as ctk
import pytest

from src.ui import theme


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground, background):
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_core_palette_matches_the_autumn_spec():
    assert theme.BACKGROUND == "#F4F1EA"
    assert theme.TEXT == "#2C2623"
    assert theme.ACCENT == "#B34A32"
    assert theme.GOLD == "#C28E38"


def test_every_palette_color_is_a_six_digit_hex_code():
    colors = [value for name, value in vars(theme).items()
              if name.isupper() and isinstance(value, str) and value.startswith("#")]

    assert len(colors) >= 15
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", color) for color in colors)


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


def test_primary_button_style_uses_accent_on_cream():
    assert theme.PRIMARY_BUTTON_STYLE["fg_color"] == theme.ACCENT
    assert theme.PRIMARY_BUTTON_STYLE["text_color"] == theme.BACKGROUND


def test_secondary_button_style_is_outlined_in_gold():
    assert theme.SECONDARY_BUTTON_STYLE["fg_color"] == "transparent"
    assert theme.SECONDARY_BUTTON_STYLE["border_color"] == theme.GOLD


def test_card_style_is_framed_in_gold():
    assert theme.CARD_STYLE["border_color"] == theme.GOLD
    assert theme.CARD_STYLE["fg_color"] == theme.SURFACE


@pytest.mark.parametrize(
    "foreground, background",
    [
        (theme.TEXT, theme.BACKGROUND),
        (theme.TEXT, theme.SURFACE),
        (theme.TEXT, theme.SIDEBAR_BG),
        (theme.TEXT, theme.SELECTION_BG),
        (theme.TEXT, theme.INPUT_BG),
        (theme.TEXT_MUTED, theme.BACKGROUND),
        (theme.TEXT_MUTED, theme.SURFACE),
        (theme.TEXT_MUTED, theme.SIDEBAR_BG),
        (theme.ACCENT, theme.BACKGROUND),
        (theme.ACCENT, theme.SURFACE),
        (theme.DANGER, theme.BACKGROUND),
        (theme.TEXT_ON_ACCENT, theme.ACCENT),
        (theme.TEXT_ON_ACCENT, theme.ACCENT_HOVER),
    ],
)
def test_text_color_pairs_meet_wcag_aa(foreground, background):
    assert contrast(foreground, background) >= 4.5


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
    assert secondary.cget("border_color") == theme.GOLD
    assert danger.cget("text_color") == theme.DANGER


def test_input_factories_build_expected_widgets(root):
    assert isinstance(theme.styled_entry(root), ctk.CTkEntry)
    assert isinstance(theme.styled_textbox(root), ctk.CTkTextbox)
    combo = theme.styled_combo(root, ["a", "b"])
    assert isinstance(combo, ctk.CTkComboBox)
    assert combo.cget("values") == ["a", "b"]
