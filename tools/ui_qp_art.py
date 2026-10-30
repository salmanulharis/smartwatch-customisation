"""Quick-panel tile set (UI pack rev 10): 64x64 tiles drawn fresh and appended to the pack.

Imported by tools/ui_feature_art.py (names "l_qp_*", appended after the feature art). The quick
panel's image pointers (stock IMG888-894 and the c2 tiles) are moved to these by tools/s100_ext.py.

Look: dark slate rounded square with a subtle vertical gradient and a 1-px top highlight, a large
white glyph with one orange detail; "on" state = orange tile with a white glyph.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

SS = 4
W = 68                                   # tile size (px)
K = W / 64                               # glyphs are designed on a 64 grid
BLACK = (0, 0, 0)
WHITE = (244, 244, 246)
ORANGE = (255, 90, 30)
ORANGE_HI = (255, 120, 64)
SLATE_TOP = (44, 47, 54)
SLATE_BOT = (27, 29, 34)
HILITE = (70, 74, 82)
LEVEL_OFF = (70, 74, 82)


class T:
    """Tile background + a separate RGBA glyph layer (holes are real transparency)."""

    HOLE = (0, 0, 0, 0)

    def __init__(self, on: bool):
        self.on = on
        self.im = Image.new("RGB", (W * SS, W * SS), BLACK)
        mask = Image.new("L", self.im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([SS, SS, (W - 1) * SS, (W - 1) * SS], radius=17 * SS, fill=255)
        top, bot = (ORANGE_HI, ORANGE) if on else (SLATE_TOP, SLATE_BOT)
        grad = Image.new("RGB", self.im.size)
        gd = ImageDraw.Draw(grad)
        for y in range(W * SS):
            f = y / (W * SS)
            gd.line([(0, y), (W * SS, y)], fill=tuple(int(a + (b - a) * f) for a, b in zip(top, bot)))
        self.im.paste(grad, (0, 0), mask)
        self.glyph = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.glyph)
        self.bg = self.HOLE                          # "draw background" = punch a hole in the glyph
        self.acc = WHITE if on else ORANGE

    def c(self, x, y, r, fill=None, outline=None, w=0):
        x, y, r, w = x * K, y * K, r * K, w * K
        self.d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=fill, outline=outline, width=int(w * SS))

    def rr(self, x0, y0, x1, y1, r, fill=None, outline=None, w=0):
        x0, y0, x1, y1, r, w = (v * K for v in (x0, y0, x1, y1, r, w))
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=fill, outline=outline,
                                 width=int(w * SS))

    def ln(self, pts, w, fill):
        pts = [(x * K, y * K) for x, y in pts]
        w = w * K
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=int(w * SS), joint="curve")
        for x, y in (pts[0], pts[-1]):
            self.c(x / K, y / K, w / K / 2, fill)

    def arc(self, x, y, r, a0, a1, w, fill):
        x, y, r, w = x * K, y * K, r * K, w * K
        self.d.arc([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], a0, a1, fill=fill, width=int(w * SS))

    def poly(self, pts, fill):
        self.d.polygon([(x * K * SS, y * K * SS) for x, y in pts], fill=fill)

    def image(self):
        out = self.im.convert("RGBA")
        out.alpha_composite(self.glyph)
        return out.convert("RGB").resize((W, W), Image.LANCZOS)


def dnd(t):
    t.c(30, 32, 15, WHITE)
    t.c(38.5, 25.5, 13, t.bg)


def brightness(t):                                   # sun; level bar is drawn by the firmware below it
    t.c(32, 28, 8, WHITE)
    for k in range(8):
        a = math.radians(k * 45 - 90)
        col = t.acc if k % 2 else WHITE
        t.ln([(32 + 12.5 * math.cos(a), 28 + 12.5 * math.sin(a)), (32 + 16 * math.cos(a), 28 + 16 * math.sin(a))], 2.6, col)


def watch(t, cx, cy, screen=True):
    """Compact watch: 22 x 24 body, short straps (about 1:1.5 overall, like the reference)."""
    t.rr(cx - 8, cy - 18, cx + 8, cy - 10, 2, WHITE)          # top strap
    t.rr(cx - 8, cy + 10, cx + 8, cy + 18, 2, WHITE)          # bottom strap
    t.rr(cx - 12, cy - 12, cx + 12, cy + 12, 6, WHITE)        # body
    if screen:
        t.rr(cx - 8.5, cy - 8.5, cx + 8.5, cy + 8.5, 3.5, t.bg)


def always_on(t):                                    # watch with a lit screen
    watch(t, 32, 32)
    t.ln([(32, 32), (32, 27)], 2.4, t.acc)
    t.ln([(32, 32), (35.5, 34)], 2.4, t.acc)


def raise_wake(t):                                   # watch with motion arcs
    watch(t, 32, 32)
    t.arc(32, 32, 24, 200, 240, 2.6, t.acc)
    t.arc(32, 32, 24, 20, 60, 2.6, t.acc)


def flashlight(t):
    t.poly([(24, 24), (40, 24), (37, 33), (27, 33)], WHITE)
    t.rr(27, 33, 37, 51, 3, WHITE)
    t.c(32, 39, 2.2, t.bg)
    for x0, y0, x1, y1 in ((32, 12, 32, 17), (22, 15, 25, 19), (42, 15, 39, 19)):
        t.ln([(x0, y0), (x1, y1)], 2.6, t.acc)


def find_phone(t):                                   # 20 x 32 phone with sound waves
    t.rr(19, 16, 39, 48, 5, WHITE)
    t.rr(22, 20, 36, 41, 2, t.bg)
    t.c(29, 44.5, 1.6, t.bg)
    t.arc(29, 32, 15, -38, 38, 2.6, t.acc)
    t.arc(29, 32, 20.5, -38, 38, 2.6, t.acc)


def watch_settings(t):                               # two sliders: distinct from the settings gear
    for y, kx in ((25, 38), (39, 26)):
        t.ln([(18, y), (46, y)], 3, WHITE)
        t.c(kx, y, 5.5, t.acc)
        t.c(kx, y, 2.4, t.bg)


def desk_clock(t):                                   # alarm-clock silhouette = desk / dock clock
    t.c(32, 34, 14, WHITE)
    t.c(32, 34, 11, t.bg)
    t.arc(21, 20, 6, 180, 300, 3, WHITE)
    t.arc(43, 20, 6, 240, 360, 3, WHITE)
    t.ln([(23, 47), (26, 44)], 2.6, WHITE)
    t.ln([(41, 47), (38, 44)], 2.6, WHITE)
    t.ln([(32, 34), (32, 27)], 2.6, WHITE)
    t.ln([(32, 34), (37, 37)], 2.6, t.acc)


def settings(t):
    pts = []
    for k in range(32):
        a = math.radians(k * 360 / 32 - 360 / 64)
        rr = 16 if k % 4 in (1, 2) else 12.5
        pts.append((32 + rr * math.sin(a), 32 - rr * math.cos(a)))
    t.poly(pts, WHITE)
    t.c(32, 32, 6.5, t.bg)
    t.c(32, 32, 4, t.acc)


def tile(fn, on=False):
    def make():
        t = T(on)
        fn(t)
        return t.image()
    return make


def level(n):                                         # brightness level bar: n of 4 segments lit
    def make():
        im = Image.new("RGB", (44 * SS, 5 * SS), BLACK)
        d = ImageDraw.Draw(im)
        for k in range(4):
            x0 = k * 11 * SS
            d.rounded_rectangle([x0 + SS, 0, x0 + 10 * SS, 5 * SS - 1], radius=2 * SS,
                                fill=ORANGE if k < n else LEVEL_OFF)
        return im.resize((44, 5), Image.LANCZOS)
    return make


# appended in this (sorted) order; tools/s100_ext.py maps them by name
ART = {
    "l_qp_a_dnd": tile(dnd), "l_qp_b_dnd_on": tile(dnd, True),
    "l_qp_c_bright": tile(brightness),
    "l_qp_d_aod": tile(always_on), "l_qp_e_aod_on": tile(always_on, True),
    "l_qp_f_raise": tile(raise_wake), "l_qp_g_raise_on": tile(raise_wake, True),
    "l_qp_h_torch": tile(flashlight), "l_qp_i_find": tile(find_phone),
    "l_qp_j_watchset": tile(watch_settings), "l_qp_k_dock": tile(desk_clock), "l_qp_l_settings": tile(settings),
}
ART.update({f"l_qp_m_level{n}": level(n) for n in range(1, 5)})
