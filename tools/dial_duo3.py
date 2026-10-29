"""Duo 3 face (light theme): stacked time, weather capsule, coral/black steps capsule, info circles.

The design is square; it is stretched to 240x280 by spacing the rows. Uses dial_duo builders
(they draw on a crop of dial_duo.BG_HI, which this module replaces).
"""
from __future__ import annotations

import math

from PIL import Image

import dial_duo as base
import dial_duo2 as duo2
from dial_duo import CREAM, INK, SOFT, CORAL, UNLIT, DIGITS, W, H, on_bg, rrect, ttext
from dial_nothing import SS, Canvas
from dial_widgets import flat_icon

GREY_PILL = (205, 203, 197)
BUBBLE = (240, 239, 234)
BLACK = (24, 24, 24)
CIRCLE_BG = (220, 218, 212)
CORAL_C = (195, 101, 35)              # coral circle cx, cy, r
ROW_Y = 240                           # bottom circles centre
ROW_X = (62, 120, 178)


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    c.dot(73, 33, 7, CORAL)                                         # accent after weekday
    rrect(c, (124, 26, 229, 50), 12, outline=(170, 168, 162), width=1.2)
    c.d.line((166 * SS, 32 * SS, 166 * SS, 44 * SS), fill=(170, 168, 162), width=int(1 * SS))
    # left rail with coral marker
    c.d.line((21 * SS, 89 * SS, 21 * SS, 180 * SS), fill=(160, 158, 152), width=int(0.9 * SS))
    c.dot(21, 135, 6, CORAL)
    # weather capsule + bubble
    rrect(c, (108, 69, 164, 193), 28, fill=GREY_PILL, width=0)
    c.dot(136, 97, 38, BUBBLE)
    # steps capsule (black) under the coral circle
    rrect(c, (163, 120, 225, 196), 31, fill=BLACK, width=0)
    cx, cy, r = CORAL_C
    c.d.ellipse(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=CORAL)
    for j in range(8):                                               # halftone dots
        for i in range(8):
            x, y = 167 + i * 4.6, 96 + j * 4.6
            if (x - cx) ** 2 + (y - cy) ** 2 < (r - 2) ** 2 and x < cx + 8 and y > cy - 12:
                c.dot(x, y, 2.2, (250, 190, 170))
    # shoe glyph + label in the black capsule
    shoe = [(176, 149), (180, 146), (183, 151), (190, 155), (189, 158), (177, 155), (176, 149)]
    c.d.line([(x * SS, y * SS) for x, y in shoe], fill=(235, 235, 235), width=int(1.3 * SS), joint="curve")
    ttext(c, "STEPS", 194, 186, 7, (140, 140, 140), anchor="ms", spacing=1.3)
    # bottom row
    for k, x in enumerate(ROW_X):
        c.dot(x, ROW_Y, 32, CIRCLE_BG)
    for x in (91, 149):
        c.dot(x, ROW_Y, 4, (165, 163, 157))
    hx, hy = ROW_X[0], ROW_Y - 7                                    # tiny heart
    c.d.ellipse(((hx - 4) * SS, (hy - 2.5) * SS, hx * SS + 1, (hy + 1.2) * SS), fill=CORAL)
    c.d.ellipse((hx * SS - 1, (hy - 2.5) * SS, (hx + 4) * SS, (hy + 1.2) * SS), fill=CORAL)
    c.d.polygon([((hx - 4) * SS, (hy - 0.3) * SS), ((hx + 4) * SS, (hy - 0.3) * SS), (hx * SS, (hy + 4) * SS)],
                fill=CORAL)
    cx3 = ROW_X[2]                                                   # calendar outline
    rrect(c, (cx3 - 9, ROW_Y - 9, cx3 + 9, ROW_Y + 9), 2, outline=INK, width=1.2)
    c.d.line(((cx3 - 9) * SS, (ROW_Y - 4) * SS, (cx3 + 9) * SS, (ROW_Y - 4) * SS), fill=INK, width=int(1.1 * SS))
    for dx in (-4, 4):
        c.d.line(((cx3 + dx) * SS, (ROW_Y - 11) * SS, (cx3 + dx) * SS, (ROW_Y - 7) * SS), fill=INK,
                 width=int(1.2 * SS))
    return c


base.BG_HI = _background()


def dark_layers(code):
    """Design shows a black sun: any coral/orange layer becomes ink."""
    def recolor(col):
        r, g, b = col
        return INK if r > 200 and g < 140 else col
    return [(recolor(col), fn) for col, fn in base.light_layers(code)]


def weather_icon(x, y, w=20, h=16):
    return [on_bg(x, y, w, h, lambda c, code=code: flat_icon(c, dark_layers(code), w / 2 - 8, 0, 16))
            for code in range(13)]


def goal_grid(x, y):
    """Step-goal progress (type 32, 11 frames) as a 3x3 dot grid filling in coral."""
    def draw(i):
        lit = round(i * 9 / 10)

        def f(c):
            for k in range(9):
                c.dot(4 + (k % 3) * 6, 4 + (k // 3) * 6, 4.2, CORAL if k < lit else INK)
        return f
    return [on_bg(x, y, 17, 17, draw(i)) for i in range(11)]


def layout():
    small = lambda x, y, size, color, w=7, h=12: base.text_digits(x, y, w, h, size, color)
    thin = lambda x, y: duo2.thin_digits(x, y, 27, 33, 40, INK)
    stp = lambda x: base.text_digits(x, 161, 9, 15, 13, (240, 240, 240))
    hx, gx, cx = ROW_X
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (15, 15, 24, duo2.weekday(15, 24)),
        (65, 19, 47, small(19, 47, 12, SOFT, 8, 14)), (66, 27, 47, small(27, 47, 12, SOFT, 8, 14)),
        (14, 35, 47, [on_bg(35, 47, 5, 14, lambda c: ttext(c, ".", 2.5, 12, 12, SOFT, anchor="ms"))]),
        (63, 40, 47, small(40, 47, 12, SOFT, 8, 14)), (64, 48, 47, small(48, 47, 12, SOFT, 8, 14)),
        (9, 136, 31, base.bt(136, 31)),
        (8, 172, 30, base.battery(172, 30)),
        (57, 36, 96, thin(36, 96)), (58, 64, 96, thin(64, 96)),
        (59, 36, 134, thin(36, 134)), (60, 64, 134, thin(64, 134)),
        (16, 37, 170, [on_bg(37, 170, 22, 13, lambda c, t=t: ttext(c, t, 0, 11, 11, SOFT, anchor="ls", spacing=1))
                       for t in ("AM", "PM", "AM", "PM")]),
        (20, 126, 82, weather_icon(126, 82)),
        # "29°" centred on the bubble (cx 136): digits drawn at x+3, x+10 → 126..140, degree 141..148
        (21, 123, 99, small(123, 99, 11, INK, 7, 13)),
        (22, 141, 99, base.degree(141, 99)),
        (38, 172, 161, stp(172)), (39, 181, 161, stp(181)), (40, 190, 161, stp(190)),
        (41, 199, 161, stp(199)), (42, 208, 161, stp(208)),
        # bottom circles: heart rate | goal grid | today's date
        (35, hx - 12, ROW_Y - 3, small(hx - 12, ROW_Y - 3, 11, INK, 8, 13)),
        (36, hx - 4, ROW_Y - 3, small(hx - 4, ROW_Y - 3, 11, INK, 8, 13)),
        (37, hx + 4, ROW_Y - 3, small(hx + 4, ROW_Y - 3, 11, INK, 8, 13)),
        (32, gx - 8, ROW_Y - 8, goal_grid(gx - 8, ROW_Y - 8)),
        (65, cx - 7, ROW_Y - 3, small(cx - 7, ROW_Y - 3, 10, CORAL, 7, 12)),
        (66, cx, ROW_Y - 3, small(cx, ROW_Y - 3, 10, CORAL, 7, 12)),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2", 38: "0", 39: "8", 40: "5", 41: "1", 42: "0"}
