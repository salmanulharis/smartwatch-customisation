"""Duo 2 face (light theme): hour on a black circle, minutes on a coral pill, step-goal column.

Builds on dial_duo: its element builders draw on a crop of `dial_duo.BG_HI`, so this module
swaps in its own background before using them.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFont

import dial_duo as base
from dial_duo import (CREAM, INK, SOFT, CORAL, OVERLAP, UNLIT, DIGITS, W, H, on_bg, rrect, ttext)
from dial_nothing import SS, Canvas

CIRCLE = (80, 116, 47)                 # black circle: cx, cy, r
PILL = (72, 135, 184, 203)             # coral stadium
STEP_X, STEP_Y0 = 215, 113             # step-goal dot column (top dot)
FONT = "C:/Windows/Fonts/bahnschrift.ttf"


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    cx, cy, r = CIRCLE
    circ = ((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS)
    pill = [v * SS for v in PILL]
    rad = (PILL[3] - PILL[1]) / 2 * SS
    c.d.ellipse(circ, fill=(30, 30, 30))
    c.d.rounded_rectangle(pill, radius=rad, fill=CORAL)
    m1, m2 = Image.new("L", c.im.size, 0), Image.new("L", c.im.size, 0)
    ImageDraw.Draw(m1).ellipse(circ, fill=255)
    ImageDraw.Draw(m2).rounded_rectangle(pill, radius=rad, fill=255)
    c.im.paste(Image.new("RGB", c.im.size, OVERLAP), (0, 0), ImageChops.multiply(m1, m2))
    c.dot(74, 42, 7, CORAL)                                     # accent after weekday
    c.dot(156, 125, 6, CORAL)                                   # dot after AM/PM
    rrect(c, (124, 30, 229, 54), 12, outline=(170, 168, 162), width=1.2)
    c.d.line((166 * SS, 36 * SS, 166 * SS, 48 * SS), fill=(170, 168, 162), width=int(1 * SS))
    # shoe glyph above the step column
    c.d.line([(209 * SS, 97 * SS), (213 * SS, 94 * SS), (216 * SS, 99 * SS), (221 * SS, 103 * SS),
              (219 * SS, 106 * SS), (211 * SS, 102 * SS), (209 * SS, 97 * SS)], fill=INK,
             width=int(1.4 * SS), joint="curve")
    ttext(c, "STEPS", STEP_X, 187, 6.5, SOFT, anchor="ms", spacing=1.4)
    c.d.line((120 * SS, 214 * SS, 120 * SS, 252 * SS), fill=(190, 188, 182), width=int(1 * SS))
    heart = [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."]
    for j, row in enumerate(heart):
        for i, ch in enumerate(row):
            c.dot(137 + i * 3.4, 222 + j * 3.4, 2.6, CORAL if ch == "#" else UNLIT)
    ttext(c, "BPM", 196, 236, 9, SOFT, anchor="ls", spacing=0.6)
    ttext(c, "Heart rate", 167, 248, 8.5, SOFT, anchor="ls")
    return c


base.BG_HI = _background()           # dial_duo builders now draw on this background


def thin_font(size: float) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, int(size * SS))
    try:
        f.set_variation_by_name("Light")
    except Exception:
        pass
    return f


def thin_digits(x, y, w=26, h=34, size=42, color=(244, 242, 236)):
    def draw(ch):
        def f(c):
            c.d.text((w / 2 * SS, (h - 1) * SS), ch, font=thin_font(size), fill=color, anchor="ms")
        return f
    return [on_bg(x, y, w, h, draw(ch)) for ch in DIGITS]


def weekday(x, y):
    from dial_nothing import SMALL
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")

    def draw(n):
        def f(c):
            for k, ch in enumerate(n):
                c.glyph(SMALL[ch], 0.5 + k * 17.4, 0.5, 2.9, 2.4, INK)
        return f
    return [on_bg(x, y, 52, 22, draw(n)) for n in names * 2]


def ampm(x, y):
    return [on_bg(x, y, 20, 12, lambda c, t=t: ttext(c, t, 0, 11, 11, SOFT, anchor="ls"))
            for t in ("AM", "PM", "AM", "PM")]


def step_column(x, y):
    """Step-goal progress (type 32, 11 frames): 6 dots fill bottom-up in coral."""
    def draw(i):
        lit = round(i * 6 / 10)

        def f(c):
            for k in range(6):                     # k = 0 is the bottom dot
                c.dot(5, 5 + (5 - k) * 9.2, 5, CORAL if k < lit else INK)
        return f
    return [on_bg(x, y, 10, 57, draw(i)) for i in range(11)]


def layout():
    date = lambda x: base.text_digits(x, 54, 8, 14, 12, SOFT)
    hrd = lambda x: base.text_digits(x, 219, 11, 19, 18, INK)
    tmp = lambda x: base.text_digits(x, 213, 12, 21, 22, INK)
    stp = lambda x: base.text_digits(x, 168, 6, 11, 9.5, INK)
    sx = STEP_X - 15
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (15, 15, 29, weekday(15, 29)),
        (65, 19, 54, date(19)), (66, 27, 54, date(27)),
        (14, 35, 54, [on_bg(35, 54, 5, 14, lambda c: ttext(c, ".", 2.5, 12, 12, SOFT, anchor="ms"))]),
        (63, 40, 54, date(40)), (64, 48, 54, date(48)),
        (9, 136, 35, base.bt(136, 35)),
        (8, 172, 34, base.battery(172, 34)),
        (57, 50, 98, thin_digits(50, 98)), (58, 76, 98, thin_digits(76, 98)),
        (59, 106, 157, thin_digits(106, 157)), (60, 134, 157, thin_digits(134, 157)),
        (16, 132, 119, ampm(132, 119)),
        (32, STEP_X - 5, STEP_Y0 - 5, step_column(STEP_X - 5, STEP_Y0 - 5)),
        (38, sx, 168, stp(sx)), (39, sx + 6, 168, stp(sx + 6)), (40, sx + 12, 168, stp(sx + 12)),
        (41, sx + 18, 168, stp(sx + 18)), (42, sx + 24, 168, stp(sx + 24)),
        (20, base.WX[0], base.WX[1], base.weather(*base.WX)),
        (21, 58, 213, tmp(58)),
        (22, 89, 214, base.degree(89, 214)),
        (35, 166, 219, hrd(166)), (36, 175, 219, hrd(175)), (37, 184, 219, hrd(184)),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2", 38: "0", 39: "8", 40: "5", 41: "1", 42: "0"}
