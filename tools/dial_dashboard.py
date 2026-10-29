"""Dashboard face: status pills, dot-matrix time, weather tile, clock + heart card, steps card.

Every element is live data the watch provides (see docs/custom-dial-format.md).
"""
from __future__ import annotations

import math

from PIL import Image

from dial_nothing import BIG, WHITE, GRAY, DARK, MINT, SS, Canvas, frame, battery_dots
from dial_widgets import (CORAL, CARD, ttext, fit_ttext, rrect, arc, hand, flat_icon, weather_layers, WEATHER,
                          WEATHER_SHORT,
                          phone_glyph)

W, H = 240, 280
DIGITS = "-./0123456789:"
TILE = (18, 18, 18)

# ---------------- top row ----------------
def weekday():
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    return [frame(42, 17, lambda c, n=n: c.text(n, 0.5, 0.5, 2.3, 1.9, WHITE)) for n in names * 2]


def small_digits(size=12, color=WHITE, w=8, h=14):
    return [frame(w, h, lambda c, ch=ch: ttext(c, ch, w / 2, h - 2, size, color, anchor="ms"))
            for ch in DIGITS]


def bt_status():
    def draw(on):
        def f(c):
            pts = [(4, 6), (11, 12), (7, 16), (7, 2), (11, 6), (4, 12)]
            c.d.line([(x * SS, (y + 2) * SS) for x, y in pts], fill=WHITE, width=int(1.5 * SS), joint="curve")
            c.dot(17, 11, 5, MINT if on else DARK)
            ttext(c, "CONNECTED" if on else "OFFLINE", 23, 15, 7, WHITE if on else GRAY, spacing=0.2)
        return f
    return [frame(70, 22, draw(False)), frame(70, 22, draw(True))]


def battery_status():
    """11 frames: firmware gives ceil(%/10); label shows that 10 % step honestly."""
    def draw(level):
        lit = battery_dots(level, 5)
        on = CORAL

        def f(c):
            rrect(c, (1, 5, 29, 17), 3.5, outline=WHITE, width=1.3)
            c.d.rectangle((30 * 4, 9 * 4, 31.5 * 4, 13 * 4), fill=WHITE)
            for i in range(5):
                c.dot(6 + i * 4.6, 11, 3.6, on if i < lit else DARK)
            label = "0%" if level == 0 else f"{level * 10 - 9}-{level * 10}%"
            ttext(c, label, 35, 15, 8, WHITE)
        return f
    return [frame(62, 22, draw(lv)) for lv in range(11)]


# ---------------- time ----------------
PITCH, DOT = 5.2, 4.6
DW, DH = 32, 59
TY = 66


def big_digits():
    return [frame(DW, DH, lambda c, ch=ch: c.glyph(BIG[ch], 0.4, 0.7, PITCH, DOT, WHITE)) for ch in DIGITS]


def colon():
    return [frame(8, DH, lambda c: (c.dot(4, 21, 7, CORAL), c.dot(4, 40, 7, CORAL)))]


def ampm():
    return [frame(30, 18, lambda c, t=t: ttext(c, t, 30, 16, 17, CORAL, anchor="rs"))
            for t in ("AM", "PM", "AM", "PM")]


# ---------------- weather tile ----------------
WX = (168, 58, 226, 150)


def weather_frames():
    x0, y0, x1, y1 = WX
    w, h = x1 - x0 - 4, y1 - y0 - 4

    def draw(code):
        def f(c):
            flat_icon(c, weather_layers(code), w / 2 - 17, 4, 34)
            fit_ttext(c, WEATHER_SHORT[code], w / 2, h - 5, w - 4, 7.5, WHITE, anchor="ms", spacing=1.0)
        return f
    return [frame(w, h, draw(code)) for code in range(13)]


def temp_digits():
    return [frame(12, 20, lambda c, ch=ch: ttext(c, ch, 6, 18, 22, WHITE, anchor="ms")) for ch in DIGITS]


def degree():
    f = lambda c: arc(c, 4, 4, 2.6, 0, 360, WHITE, 1.3)
    return [frame(8, 8, f), frame(8, 8, f)]


# ---------------- cards ----------------
CLOCK = (42, 182)


def footprints(c, cx, cy, color):
    for dx, dy, s in ((-4, -2, 1), (3, 2, 1)):
        x, y = cx + dx, cy + dy
        c.d.ellipse(((x - 2.6) * 4, (y - 5) * 4, (x + 2.6) * 4, (y + 2) * 4), fill=color)
        c.d.ellipse(((x - 1.8) * 4, (y + 3) * 4, (x + 1.8) * 4, (y + 6) * 4), fill=color)


def heart(c, cx, cy, s, color):
    c.d.ellipse(((cx - s) * 4, (cy - s * 0.6) * 4, cx * 4 + 1, (cy + s * 0.3) * 4), fill=color)
    c.d.ellipse((cx * 4 - 1, (cy - s * 0.6) * 4, (cx + s) * 4, (cy + s * 0.3) * 4), fill=color)
    c.d.polygon([((cx - s) * 4, (cy - 0.05 * s) * 4), ((cx + s) * 4, (cy - 0.05 * s) * 4),
                 (cx * 4, (cy + s) * 4)], fill=color)


def step_progress():
    def draw(i):
        def f(c):
            rrect(c, (0.5, 0.5, 77.5, 6.5), 3, fill=CARD)
            if i:
                rrect(c, (0.5, 0.5, max(7, 77.5 * i / 10), 6.5), 3, fill=MINT)
        return f
    return [frame(78, 7, draw(i)) for i in range(11)]


def background() -> Image.Image:
    c = Canvas(W, H)
    rrect(c, (78, 18, 154, 50), 12, outline=CARD, width=1.4)          # BT pill
    rrect(c, (160, 18, 228, 50), 12, outline=CARD, width=1.4)         # battery pill
    rrect(c, (166, 56, 228, 152), 12, outline=CARD, fill=TILE, width=1.4)  # weather tile
    # clock + heart card
    rrect(c, (12, 158, 228, 207), 12, outline=CARD, width=1.4)
    arc(c, *CLOCK, 19, 0, 360, CARD, 2.2)
    arc(c, *CLOCK, 19, -90, -30, CORAL, 2.2)
    for k in range(12):
        a = math.radians(k * 30)
        c.dot(CLOCK[0] + 14.5 * math.sin(a), CLOCK[1] - 14.5 * math.cos(a), 2.3 if k % 3 == 0 else 1.3,
              WHITE if k % 3 == 0 else GRAY)
    c.dot(*CLOCK, 4, CORAL)
    ttext(c, "HEART RATE", 72, 170, 7.5, GRAY, spacing=0.8)
    ttext(c, "BPM", 108, 196, 8, GRAY, spacing=0.6)
    c.dot(204, 182, 26, CORAL)
    heart(c, 204, 181, 7, WHITE)
    # steps card
    rrect(c, (12, 213, 228, 262), 12, outline=CARD, width=1.4)
    c.dot(42, 237, 30, (34, 34, 34))
    footprints(c, 42, 236, MINT)
    ttext(c, "STEPS", 72, 222, 7.5, GRAY, spacing=0.8)      # y = top of text (anchor "la")
    ttext(c, "GOAL", 140, 228, 7.5, GRAY, spacing=0.8)
    return c.image()


def layout():
    big = big_digits()
    sd = small_digits(12, WHITE, 8, 14)
    hd = small_digits(17, WHITE, 11, 19)
    st = small_digits(15, WHITE, 10, 18)
    hr_img, hr_opt = hand(4, 12, 10, WHITE)
    mn_img, mn_opt = hand(3, 16, 14, CORAL)
    return [
        (17, 0, 0, [background()]),
        (15, 18, 20, weekday()),
        (65, 19, 38, sd), (66, 27, 38, sd),
        (14, 35, 38, [frame(4, 14, lambda c: ttext(c, ".", 2, 12, 12, WHITE, anchor="ms"))]),
        (63, 39, 38, sd), (64, 47, 38, sd),
        (9, 82, 23, bt_status()),
        (8, 164, 23, battery_status()),
        (57, 10, TY, big), (58, 44, TY, big),
        (7, 79, TY, colon()),
        (59, 90, TY, big), (60, 124, TY, big),
        (16, 126, 128, ampm()),
        (20, WX[0] + 2, WX[1] + 2, weather_frames()),
        (21, 179, 103, temp_digits()),          # firmware: char k at x + ((3-n)w>>1) + k*w
        (22, 211, 103, degree()),
        (1, *CLOCK, [hr_img], hr_opt),
        (2, *CLOCK, [mn_img], mn_opt),
        (35, 72, 181, hd), (36, 83, 181, hd), (37, 94, 181, hd),
        (38, 72, 233, st), (39, 82, 233, st), (40, 92, 233, st), (41, 102, 233, st), (42, 112, 233, st),
        (32, 140, 242, step_progress()),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2", 38: "0", 39: "5", 40: "4", 41: "3", 42: "2"}
