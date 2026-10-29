"""Dusk face (dark analog landscape): watch-rotated hands, weather bubble, battery bar,
step-goal dots, moon and layered landscape. Portrait design, no stretching.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

import dial_duo as base
import dial_duo2  # noqa: F401  (import order: duo2 sets BG first, this module overrides)
from dial_duo import W, H, on_bg
from dial_duo5 import smooth_hand
from dial_nothing import SS, Canvas
from dial_widgets import flat_icon, rrect

BG = (22, 22, 22)
BUBBLE = (40, 40, 40)
CREAM = (232, 228, 220)
GREY = (150, 148, 144)
DARK_GREY = (70, 70, 70)
MID_GREY = (110, 108, 104)
CORAL = (240, 88, 52)
TRACK = (60, 60, 60)
CX, CY, R = 136, 129, 66


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=BG)
    c.dot(43, 40, 54, BUBBLE)                                   # weather bubble
    c.dot(212, 38, 22, CREAM)                                   # moon
    c.dot(215, 36, 18, GREY)
    # ---- landscape (bottom-left) ----
    c.dot(5, 190, 76, CORAL)                                    # setting sun at the left edge
    def layer(box, color):
        m = Image.new("L", c.im.size, 0)
        ImageDraw.Draw(m).ellipse([v * SS for v in box], fill=255)
        c.im.paste(Image.new("RGB", c.im.size, color), (0, 0), m)

    def bezier(p0, p1, p2, p3, n=40):
        out = []
        for k in range(n + 1):
            t = k / n
            mt = 1 - t
            x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
            out.append((x * SS, y * SS))
        return out
    # dark hill: smooth top edge sloping from (70,194) down to the bottom-right corner
    ridge = bezier((30, 215), (95, 186), (160, 212), (190, 245)) + bezier((190, 245), (210, 265), (225, 272), (245, 276))
    m = Image.new("L", c.im.size, 0)
    ImageDraw.Draw(m).polygon(ridge + [(245 * SS, 300 * SS), (30 * SS, 300 * SS)], fill=255)
    c.im.paste(Image.new("RGB", c.im.size, DARK_GREY), (0, 0), m)
    layer((-150, 182, 125, 425), CREAM)            # cream band
    layer((-140, 224, 92, 405), MID_GREY)          # grey inner hill
    wave = bezier((0, 125), (40, 126), (62, 175), (88, 196)) + \
        bezier((88, 196), (125, 222), (150, 245), (175, 253)) + \
        bezier((175, 253), (200, 260), (220, 256), (234, 262))
    c.d.line(wave, fill=CREAM, width=int(0.7 * SS), joint="curve")
    # ---- dial ticks ----
    for k in range(12):
        a = math.radians(k * 30)
        x, y = CX + R * math.sin(a), CY - R * math.cos(a)
        if k == 0:
            c.dot(x, y, 7, CORAL)
        elif k in (3, 9):
            c.dot(x, y, 7 if k == 9 else 4.5, CREAM if k == 9 else GREY)
        else:
            c.dot(x, y, 4.5, CREAM if k % 2 else GREY)
    c.dot(CX, CY, 15, CREAM)                                    # centre cap (hands draw over it)
    return c


base.BG_HI = _background()


def weather_icon(x, y, w=40, h=34):
    def dark_layers(code):
        remap = {(245, 245, 245): CREAM, (150, 150, 150): GREY, (55, 55, 55): TRACK}
        from dial_widgets import weather_layers
        return [(remap.get(col, col), fn) for col, fn in weather_layers(code)]
    return [on_bg(x, y, w, h, lambda c, code=code: flat_icon(c, dark_layers(code), 2, 0, 36))
            for code in range(13)]


def battery_bar(x, y, w=9, h=54):
    """11 frames (firmware ceil(%/10)): vertical bar filling from the bottom, red when low."""
    def draw(level):
        def f(c):
            rrect(c, (0.5, 0.5, w - 0.5, h - 0.5), w / 2, fill=TRACK, width=0)
            if level:
                fh = max(w, (h - 1) * level / 10)
                rrect(c, (0.5, h - 0.5 - fh, w - 0.5, h - 0.5), w / 2,
                      fill=CORAL if level > 2 else (220, 40, 40), width=0)
        return f
    return [on_bg(x, y, w, h, draw(lv)) for lv in range(11)]


def goal_dots(x, y):
    """Step-goal progress (type 32, 11 frames): 3 dots fill top-down in coral."""
    def draw(i):
        lit = round(i * 3 / 10)

        def f(c):
            for k in range(3):
                c.dot(5, 5 + k * 11, 8.5, CORAL if k < lit else TRACK)
        return f
    return [on_bg(x, y, 10, 32, draw(i)) for i in range(11)]


def layout():
    hr_img, hr_opt = smooth_hand(11, 46, 40, CREAM, face_bg=BG)
    mn_img, mn_opt = smooth_hand(10, 58, 52, CORAL, face_bg=BG)
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (20, 23, 22, weather_icon(23, 22)),
        (8, 220, 94, battery_bar(220, 94)),
        (32, 219, 192, goal_dots(219, 192)),
        (1, CX, CY, [hr_img], hr_opt),
        (2, CX, CY, [mn_img], mn_opt),
    ]


SAMPLE = {}
