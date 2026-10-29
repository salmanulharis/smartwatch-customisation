"""Blob face (light theme): stacked metaball-dot time, weather / steps / battery bubbles on an arc.

Portrait design, no stretching needed. Uses dial_duo builders on this module's background.
"""
from __future__ import annotations

import math

from PIL import Image

import dial_duo as base
import dial_duo2  # noqa: F401  (import order: duo2 sets BG first, this module overrides)
from dial_duo import CREAM, INK, SOFT, CORAL, W, H, on_bg, ttext
from dial_nothing import SS, Canvas
from dial_widgets import flat_icon, fit_ttext, rrect, WEATHER_SHORT

BUBBLE = (222, 220, 214)
ARC = (178, 176, 170)
BUBBLES = {"wx": (174, 85), "steps": (181, 152), "bat": (165, 217)}
BR = 22                                     # bubble radius

# 3x5 blob font: '#' black dot, 'o' coral accent dot; neighbours (incl. diagonal) are joined
BLOB = {
    "0": ["###", "#.o", "#.#", "#.#", "###"],
    "1": ["o#.", ".#.", ".#.", ".#.", ".#."],
    "2": ["###", "..#", "###", "#..", "##o"],
    "3": ["###", "..#", ".o#", "..#", "###"],
    "4": ["#.#", "#.#", "##o", "..#", "..#"],
    "5": ["###", "#..", "###", "..#", "##o"],
    "6": ["###", "#..", "##o", "#.#", "###"],
    "7": ["##o", "..#", "..#", "..#", "..#"],
    "8": ["###", "#.#", "#o#", "#.#", "###"],
    "9": ["###", "#.#", "#o#", "..#", "###"],
    "-": ["...", "...", "###", "...", "..."],
    ".": ["...", "...", "...", "...", ".#."],
    "/": ["..#", "..#", ".#.", "#..", "#.."],
    ":": ["...", ".#.", "...", ".#.", "..."],
}
P = 14.0                                    # blob grid pitch
DIG_W, DIG_H = 43, 71


_MASKS: dict[str, "Image.Image"] = {}


def blob_mask(rows) -> "Image.Image":
    """Metaball mask: sum of (r/d)^4 fields from each dot, thresholded at 1.

    Orthogonal neighbours melt together with a pinched neck; diagonal ones stay separate.
    Computed once per glyph at supersampled resolution.
    """
    from PIL import Image as _Image
    key = "|".join(rows)
    if key in _MASKS:
        return _MASKS[key]
    w, h = int(DIG_W * SS), int(DIG_H * SS)
    r = 0.47 * P * SS
    cells = [((i + 0.5) * P * SS + 0.5 * SS, (j + 0.5) * P * SS + 0.5 * SS)
             for j, row in enumerate(rows) for i, ch in enumerate(row) if ch in "#o"]
    m = _Image.new("L", (w, h), 0)
    px = m.load()
    r4 = r ** 4
    reach = 2.2 * r
    for y in range(h):
        near_y = [(cx, cy) for cx, cy in cells if abs(cy - y) < reach]
        if not near_y:
            continue
        for x in range(w):
            f = 0.0
            for cx, cy in near_y:
                dx, dy = cx - x, cy - y
                d2 = dx * dx + dy * dy
                if d2 < reach * reach:
                    f += r4 / (d2 * d2 + 1e-6)
            if f >= 1.0:
                px[x, y] = 255
    _MASKS[key] = m
    return m


def blob_glyph(c: Canvas, rows, ox=0.5, oy=0.5):
    """Black metaball digit with coral accent dots on top."""
    mask = blob_mask(rows)
    c.im.paste(Image.new("RGB", mask.size, INK), (0, 0), mask)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "o":
                c.dot(ox + (i + 0.5) * P, oy + (j + 0.5) * P, 1.0 * P, CORAL)


def _old_blob_glyph(c: Canvas, rows, ox, oy):
    cells = {(i, j): ch for j, r in enumerate(rows) for i, ch in enumerate(r) if ch != "."}
    pos = lambda i, j: (ox + (i + 0.5) * P, oy + (j + 0.5) * P)
    for (i, j) in cells:                                     # joints first (black)
        for di, dj in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            if (i + di, j + dj) in cells:
                (x0, y0), (x1, y1) = pos(i, j), pos(i + di, j + dj)
                c.d.line((x0 * SS, y0 * SS, x1 * SS, y1 * SS), fill=INK, width=int(0.78 * P * SS))
    for (i, j), ch in cells.items():
        x, y = pos(i, j)
        c.dot(x, y, 0.92 * P, CORAL if ch == "o" else INK)


def blob_digits(x, y):
    return [on_bg(x, y, DIG_W, DIG_H, lambda c, ch=ch: blob_glyph(c, BLOB[ch], 0.5, 0.5))
            for ch in "-./0123456789:"]


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    c.dot(222, 6, 96, CORAL)                                 # top-right coral circle
    # big arc the bubbles sit on (centre left of screen)
    ax, ay, ar = 30, 150, 158
    c.d.arc(((ax - ar) * SS, (ay - ar) * SS, (ax + ar) * SS, (ay + ar) * SS), -75, 75, fill=ARC,
            width=int(0.8 * SS))
    for key, (bx, by) in BUBBLES.items():
        c.dot(bx, by, 2 * BR, BUBBLE)
    for x, y in ((150, 90), (158, 153), (141, 215)):         # connector dots
        c.dot(x, y, 5.5, INK)
    # bottom-left decor: grey circles + black circle with a dot grid
    c.dot(30, 290, 150, (205, 203, 197))
    c.dot(68, 300, 150, (190, 188, 182))
    c.dot(28, 300, 132, (22, 22, 22))
    for k in range(9):
        c.dot(22 + (k % 3) * 8.5, 246 + (k // 3) * 8.5, 5.5, CORAL if k == 8 else (150, 150, 150))
    c.dot(72, 30, 8, CORAL)                                  # accent after weekday
    sx, sy = BUBBLES["steps"]                                # shoe glyph
    shoe = [(sx - 9, sy - 6), (sx - 4, sy - 10), (sx, sy - 4), (sx + 7, sy), (sx + 6, sy + 4),
            (sx - 7, sy), (sx - 9, sy - 6)]
    c.d.line([(x * SS, y * SS) for x, y in shoe], fill=INK, width=int(1.5 * SS), joint="curve")
    ttext(c, "STEPS", 205, 166, 7.5, SOFT, anchor="ls", spacing=1.0)
    return c


base.BG_HI = _background()


def weekday(x, y):
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    return [on_bg(x, y, 44, 20, lambda c, n=n: ttext(c, n, 0, 18, 19, INK, anchor="ls")) for n in names * 2]


def weather_frames(x, y, w=84, h=40):
    """Icon centred in the weather bubble, condition label to the right under the temperature."""
    bx, by = BUBBLES["wx"]

    def draw(code):
        def f(c):
            flat_icon(c, base.light_layers(code), bx - x - 12, by - y - 12, 24)
            fit_ttext(c, WEATHER_SHORT[code], 50, 33, 34, 7.5, SOFT, anchor="ls", spacing=1.0)
        return f
    return [on_bg(x, y, w, h, draw(code)) for code in range(13)]


def battery_frames(x, y, w=92, h=46):
    """11 frames (firmware ceil(%/10)): battery glyph filling with level + a word label."""
    bx, by = BUBBLES["bat"]

    def word(level):
        return "LOW" if level <= 2 else "MID" if level <= 5 else "GOOD" if level <= 8 else "FULL"

    def draw(level):
        def f(c):
            gx, gy = bx - x - 12, by - y - 7
            rrect(c, (gx, gy, gx + 23, gy + 14), 3, outline=INK, width=1.5)
            c.d.rectangle(((gx + 23.5) * SS, (gy + 4.5) * SS, (gx + 25.5) * SS, (gy + 9.5) * SS), fill=INK)
            if level:
                fill_w = 17 * min(level, 10) / 10
                rrect(c, (gx + 3, gy + 3, gx + 3 + fill_w, gy + 11), 1.5,
                      fill=CORAL if level > 2 else (220, 40, 40), width=0)
            ttext(c, word(level), 58, by - y + 5, 11, INK, anchor="ls")
        return f
    return [on_bg(x, y, w, h, draw(lv)) for lv in range(11)]


def layout():
    small = lambda x, y, size, color, w=7, h=12: base.text_digits(x, y, w, h, size, color)
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (15, 22, 18, weekday(22, 18)),
        (65, 24, 40, small(24, 40, 13, SOFT, 9, 15)), (66, 33, 40, small(33, 40, 13, SOFT, 9, 15)),
        (14, 42, 40, [on_bg(42, 40, 5, 15, lambda c: ttext(c, ".", 2.5, 13, 13, SOFT, anchor="ms"))]),
        (63, 47, 40, small(47, 40, 13, SOFT, 9, 15)), (64, 56, 40, small(56, 40, 13, SOFT, 9, 15)),
        (57, 22, 64, blob_digits(22, 64)), (58, 70, 64, blob_digits(70, 64)),
        (59, 22, 140, blob_digits(22, 140)), (60, 70, 140, blob_digits(70, 140)),
        (20, 150, 61, weather_frames(150, 61)),
        # "29" left-aligned at x 202: digits at x+4, x+13 → 202..220, degree 221
        (21, 198, 70, small(198, 70, 13, INK, 9, 15)),
        (22, 221, 70, base.degree(221, 70)),
        (38, 203, 142, small(203, 142, 12, INK, 7, 14)), (39, 210, 142, small(210, 142, 12, INK, 7, 14)),
        (40, 217, 142, small(217, 142, 12, INK, 7, 14)), (41, 224, 142, small(224, 142, 12, INK, 7, 14)),
        (42, 231, 142, small(231, 142, 12, INK, 7, 14)),
        (8, 143, 194, battery_frames(143, 194)),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          38: "0", 39: "8", 40: "5", 41: "1", 42: "0"}
