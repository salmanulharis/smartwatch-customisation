"""Duo 6 face (light minimal analog): dot ring, watch-rotated hands, weather, steps, battery.

Square design stretched to 240x280 (dial kept round). Uses dial_duo builders on this background.
"""
from __future__ import annotations

import math

import dial_duo as base
import dial_duo2  # noqa: F401  (import order: duo2 sets BG first, this module overrides)
from dial_duo import CREAM, INK, SOFT, CORAL, W, H, on_bg, ttext
from dial_duo5 import smooth_hand
from dial_nothing import SS, Canvas, battery_dots
from dial_widgets import flat_icon, fit_ttext, rrect, WEATHER_SHORT

GREY_DECO = (220, 218, 212)
GREY_DOT = (168, 166, 160)
CX, CY, R = 120, 133, 60


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    c.dot(209, -16, 160, GREY_DECO)                 # top-right grey quarter
    c.dot(-22, 278, 186, GREY_DECO)                 # bottom-left grey quarter
    c.dot(256, 137, 112, CORAL)                     # coral half-circle on the right edge
    for k in range(12):
        a = math.radians(k * 30)
        x, y = CX + R * math.sin(a), CY - R * math.cos(a)
        if k % 3 == 0:
            c.dot(x, y, 10, CORAL)
        elif k in (1, 4, 8, 11):
            c.dot(x, y, 7, INK)
        else:
            c.dot(x, y, 6, GREY_DOT)
    c.dot(CX - 34, CY - 36, 3.5, GREY_DOT)          # small accent dot like the design
    c.dot(CX, CY, 13, INK)                          # centre dot (hands draw over it)
    c.dot(57, 31, 7, CORAL)                         # accent after weekday
    shoe = [(19, 211), (24, 207), (28, 213), (35, 217), (34, 221), (21, 217), (19, 211)]
    c.d.line([(x * SS, y * SS) for x, y in shoe], fill=INK, width=int(1.5 * SS), joint="curve")
    ttext(c, "STEPS", 17, 250, 8, SOFT, anchor="ls", spacing=1.2)
    return c


base.BG_HI = _background()


def weekday(x, y):
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    return [on_bg(x, y, 40, 18, lambda c, n=n: ttext(c, n, 0, 16, 17, INK, anchor="ls")) for n in names * 2]


def weather_icon(x, y, w=48, h=26):
    """Icon on the left; condition label under the temperature."""
    def draw(code):
        def f(c):
            flat_icon(c, base.light_layers(code), 0, 1, 22)
            fit_ttext(c, WEATHER_SHORT[code], 25, 25, 23, 7.5, SOFT, anchor="ls", spacing=1.0)
        return f
    return [on_bg(x, y, w, h, draw(code)) for code in range(13)]


def battery_pill(x, y):
    def draw(level):
        lit = battery_dots(level, 4)

        def f(c):
            rrect(c, (0.8, 0.8, 34, 13.2), 3.5, outline=INK, width=1.3)
            c.d.rectangle((34.5 * SS, 4.5 * SS, 36.5 * SS, 9.5 * SS), fill=INK)
            for i in range(4):
                c.dot(6 + i * 7.6, 7, 5.6, CORAL if i < lit else (178, 176, 170))
        return f
    return [on_bg(x, y, 38, 14, draw(lv)) for lv in range(11)]


def layout():
    small = lambda x, y, size, color, w=7, h=12: base.text_digits(x, y, w, h, size, color)
    hr_img, hr_opt = smooth_hand(11, 38, 32, INK)
    mn_img, mn_opt = smooth_hand(9, 50, 44, CORAL)
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (15, 19, 22, weekday(19, 22)),
        (65, 20, 40, small(20, 40, 12, SOFT, 8, 14)), (66, 28, 40, small(28, 40, 12, SOFT, 8, 14)),
        (14, 36, 40, [on_bg(36, 40, 5, 14, lambda c: ttext(c, ".", 2.5, 12, 12, SOFT, anchor="ms"))]),
        (63, 41, 40, small(41, 40, 12, SOFT, 8, 14)), (64, 49, 40, small(49, 40, 12, SOFT, 8, 14)),
        (20, 178, 22, weather_icon(178, 22)),
        # "29" left-aligned at x 203: digits at x+4, x+12; degree after
        (21, 199, 21, small(199, 21, 13, INK, 8, 15)),
        (22, 220, 22, base.degree(220, 22)),
        (38, 15, 226, small(15, 226, 13, INK, 8, 15)), (39, 23, 226, small(23, 226, 13, INK, 8, 15)),
        (40, 31, 226, small(31, 226, 13, INK, 8, 15)), (41, 39, 226, small(39, 226, 13, INK, 8, 15)),
        (42, 47, 226, small(47, 226, 13, INK, 8, 15)),
        (8, 184, 229, battery_pill(184, 229)),
        (1, CX, CY, [hr_img], hr_opt),
        (2, CX, CY, [mn_img], mn_opt),
    ]


SAMPLE = {65: "2", 66: "9", 63: "1", 64: "0", 38: "0", 39: "8", 40: "5", 41: "1", 42: "0"}
