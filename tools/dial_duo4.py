"""Duo 4 face (light theme): twin time capsules, weather / steps / heart cards, battery pill.

Square design stretched to 240x280. Uses dial_duo builders on this module's background.
"""
from __future__ import annotations

import dial_duo as base
import dial_duo2 as duo2  # noqa: F401  (keeps import order: duo2 swaps BG first, we swap after)
from dial_duo import CREAM, INK, SOFT, CORAL, UNLIT, DIGITS, W, H, on_bg, rrect, ttext, TIME_FONT
from dial_nothing import SS, Canvas, battery_dots

BLACK = (26, 26, 26)
CARD = (218, 216, 210)
LIGHT_DOT = (250, 214, 204)
WHITE_DOT = (242, 240, 235)

BLACK_CAP = (12, 49, 81, 205)
CORAL_CAP = (81, 49, 150, 201)
WX_CARD = (143, 25, 232, 86)
STEP_CARD = (153, 96, 234, 142)
HR_CARD = (153, 152, 234, 198)
BAT_PILL = (13, 222, 99, 244)


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    # decorative circles at the bottom
    c.d.ellipse(((133 - 39) * SS, (239 - 39) * SS, (133 + 39) * SS, (239 + 39) * SS), fill=CARD)
    c.d.ellipse(((215 - 41) * SS, (250 - 41) * SS, (215 + 41) * SS, (250 + 41) * SS), fill=CORAL)
    # cards
    rrect(c, WX_CARD, 20, fill=CARD, width=0)
    rrect(c, STEP_CARD, 23, fill=BLACK, width=0)
    rrect(c, HR_CARD, 23, fill=CARD, width=0)
    # time capsules (coral drawn after black so it overlaps the weather card like the design)
    rrect(c, BLACK_CAP, (BLACK_CAP[2] - BLACK_CAP[0]) / 2, fill=BLACK, width=0)
    rrect(c, CORAL_CAP, (CORAL_CAP[2] - CORAL_CAP[0]) / 2, fill=CORAL, width=0)
    c.dot(70, 21, 7, CORAL)                                          # accent after weekday
    # shoe glyph on the steps card
    shoe = [(163, 113), (168, 110), (172, 116), (180, 121), (179, 125), (165, 121), (163, 113)]
    c.d.line([(x * SS, y * SS) for x, y in shoe], fill=(235, 235, 235), width=int(1.4 * SS), joint="curve")
    ttext(c, "STEPS", 191, 132, 7, (140, 140, 140), anchor="ls", spacing=1.3)
    # dot-grid heart on the heart card
    for k in range(9):
        c.dot(166 + (k % 3) * 5, 168 + (k // 3) * 5, 3.6, CORAL if k == 8 else INK)
    ttext(c, "BPM", 214, 175, 8, SOFT, anchor="ls", spacing=0.5)
    ttext(c, "Heart rate", 189, 188, 8, SOFT, anchor="ls")
    # battery pill
    rrect(c, BAT_PILL, 11, outline=(160, 158, 152), width=1.1)
    rrect(c, (20, 229, 30, 237), 1.5, outline=INK, width=1.1)
    c.d.rectangle((30.5 * SS, 231.5 * SS, 32 * SS, 234.5 * SS), fill=INK)
    return c


base.BG_HI = _background()


def dot_digits(x, y, color, w=26, h=36, pitch=5.0, dot=4.1):
    return [on_bg(x, y, w, h, lambda c, ch=ch: c.glyph(TIME_FONT[ch], 0.5, 0.5, pitch, dot, color))
            for ch in DIGITS]


def battery_pill(x, y):
    """11 frames (firmware ceil(%/10)); 5 dots, coral, last ones grey when not lit."""
    def draw(level):
        lit = battery_dots(level, 5)

        def f(c):
            for i in range(5):
                c.dot(5 + i * 8.5, 5, 7, CORAL if i < lit else (175, 173, 167))
        return f
    return [on_bg(x, y, 44, 10, draw(lv)) for lv in range(11)]


def weather_icon(x, y, w=76, h=40):
    """Icon on the left; condition label under the temperature (temp/degree draw on top)."""
    from dial_widgets import flat_icon, fit_ttext, WEATHER_SHORT

    def draw(code):
        def f(c):
            flat_icon(c, base.light_layers(code), 2, 0, 30)
            fit_ttext(c, WEATHER_SHORT[code], 39, 37, 36, 7.5, SOFT, anchor="ls", spacing=1.0)
        return f
    return [on_bg(x, y, w, h, draw(code)) for code in range(13)]


def layout():
    small = lambda x, y, size, color, w=7, h=12: base.text_digits(x, y, w, h, size, color)
    hx, mx, ty = 20, 89, 108
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (15, 25, 13, base.weekday(25, 13)),
        (65, 26, 32, small(26, 32, 12, SOFT, 8, 14)), (66, 34, 32, small(34, 32, 12, SOFT, 8, 14)),
        (14, 42, 32, [on_bg(42, 32, 5, 14, lambda c: ttext(c, ".", 2.5, 12, 12, SOFT, anchor="ms"))]),
        (63, 47, 32, small(47, 32, 12, SOFT, 8, 14)), (64, 55, 32, small(55, 32, 12, SOFT, 8, 14)),
        (57, hx, ty, dot_digits(hx, ty, WHITE_DOT)), (58, hx + 27, ty, dot_digits(hx + 27, ty, WHITE_DOT)),
        (59, mx, ty, dot_digits(mx, ty, LIGHT_DOT)), (60, mx + 27, ty, dot_digits(mx + 27, ty, LIGHT_DOT)),
        (16, 36, 176, [on_bg(36, 176, 22, 13, lambda c, t=t: ttext(c, t, 11, 11, 11, (170, 170, 170),
                                                                      anchor="ms", spacing=1))
                       for t in ("AM", "PM", "AM", "PM")]),
        # weather: icon (+ condition label under the temperature), temp "29" at x+5..x+27, degree after
        (20, 151, 38, weather_icon(151, 38)),
        (21, 185, 40, small(185, 40, 17, INK, 11, 18)),
        (22, 213, 40, base.degree(213, 40)),
        # steps on the black card
        (38, 189, 104, small(189, 104, 12, (240, 240, 240), 8, 14)),
        (39, 197, 104, small(197, 104, 12, (240, 240, 240), 8, 14)),
        (40, 205, 104, small(205, 104, 12, (240, 240, 240), 8, 14)),
        (41, 213, 104, small(213, 104, 12, (240, 240, 240), 8, 14)),
        (42, 221, 104, small(221, 104, 12, (240, 240, 240), 8, 14)),
        # heart rate
        (35, 189, 162, small(189, 162, 13, INK, 8, 15)),
        (36, 197, 162, small(197, 162, 13, INK, 8, 15)),
        (37, 205, 162, small(205, 162, 13, INK, 8, 15)),
        (8, 33, 228, battery_pill(33, 228)),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2", 38: "0", 39: "8", 40: "5", 41: "1", 42: "0"}
