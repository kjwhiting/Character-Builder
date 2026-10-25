import colorsys
import re

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")

PRESET_COLORS = (
    "#E0A458", "#D98080", "#E07A5F", "#D6C06E", "#7FBF8F", "#5FB3A1",
    "#8CB4C8", "#6C9BD1", "#A98BD6", "#C98BC4", "#B58863", "#9AA0A6",
)


def is_hex(value: str) -> bool:
    return bool(HEX_COLOR.fullmatch(value or ""))


def _channels(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def luminance(color: str) -> float:
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in _channels(color)]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def readable_on(color: str | None, background: str, minimum: float = 4.5) -> str:
    if not is_hex(color or ""):
        return "#EDEEEE" if luminance(background) < 0.4 else "#2C2623"
    if contrast_ratio(color, background) >= minimum:
        return color.upper()
    hue, lightness, saturation = colorsys.rgb_to_hls(*_channels(color))
    step = 0.02 if luminance(background) < 0.4 else -0.02
    for _ in range(50):
        lightness = min(1.0, max(0.0, lightness + step))
        red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
        candidate = "#{:02X}{:02X}{:02X}".format(
            round(red * 255), round(green * 255), round(blue * 255))
        if contrast_ratio(candidate, background) >= minimum:
            return candidate
    return "#FFFFFF" if step > 0 else "#000000"
