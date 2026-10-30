"""UI pack revision 9 art: stock screens restyled after the owner's mockup (2026-10-30).

    python tools/ui_v9_art.py [-o research/ui/replace]
    python tools/s100_ui.py build research/ui/replace --append research/ui/feature_append --version 9

Redraws stock images in place (same w x h, reduced to fit each stock byte slot like ui_cmf.fit):
quick-panel tiles as rounded squares, music player (dark disc, orange arc, big orange play
button), find-phone ringing frames (phone + blue waves), charging / low-battery rings (green /
red), red heart, purple sleep moon, green message bubble, red call decline, flat weather icons.
Black (0x0000) is transparent on the watch, so shapes are drawn on black.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

from s100_ui import UI_BIN, payload, walk
from ui_cmf import fit

ROOT = Path(__file__).resolve().parent.parent
SS = 4
BLACK = (0, 0, 0)
WHITE = (245, 245, 245)
TILE = (40, 40, 40)            # = ui_cmf.CHIP, also used by tools/ui_feature_art tiles
DISC = (20, 20, 20)
ORANGE = (255, 90, 30)
RED = (240, 68, 58)
GREEN = (40, 220, 110)
GREEN_DIM = (22, 70, 40)
RED_DIM = (70, 24, 22)
BLUE = (40, 130, 255)
PURPLE = (125, 95, 255)
GREY = (140, 140, 140)
CLOUD = (232, 232, 232)
CLOUD_D = (150, 150, 155)


class Art:
    """Supersampled drawing in pixel coordinates of the final w x h image."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w * SS, h * SS), BLACK)
        self.d = ImageDraw.Draw(self.im)

    def circle(self, x, y, r, fill=None, outline=None, width=0):
        self.d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=fill, outline=outline,
                       width=int(width * SS))

    def rect(self, x0, y0, x1, y1, r, fill):
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=fill)

    def poly(self, pts, fill):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)

    def line(self, pts, w, fill):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=int(w * SS), joint="curve")
        for x, y in (pts[0], pts[-1]):
            self.circle(x, y, w / 2, fill)

    def arc(self, x, y, r, a0, a1, w, fill, caps=True):
        self.d.arc([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], a0, a1, fill=fill, width=int(w * SS))
        if caps:
            rr = r - w / 2
            for a in (a0, a1):
                t = math.radians(a)
                self.circle(x + rr * math.cos(t), y + rr * math.sin(t), w / 2, fill)

    def image(self):
        return self.im.resize((self.w, self.h), Image.LANCZOS)


# ---------------------------------------------------------------- quick-panel tiles (64x64)
def tile(glyph, on=False):
    def make():
        a = Art(64, 64)
        a.rect(1, 1, 63, 63, 17, ORANGE if on else TILE)
        glyph(a, on)
        return a.image()
    return make


def g_moon(a, on):
    a.circle(30, 32, 15, WHITE)
    a.circle(39, 25, 13, ORANGE if on else TILE)


def g_sun(a, on):
    a.circle(32, 32, 8, WHITE)
    for k in range(8):
        t = math.radians(k * 45)
        a.line([(32 + 13 * math.cos(t), 32 + 13 * math.sin(t)), (32 + 17 * math.cos(t), 32 + 17 * math.sin(t))], 3, WHITE)


def g_raise(a, on):
    a.rect(24, 22, 40, 42, 4, WHITE)                    # watch
    a.rect(27, 25, 37, 39, 2, ORANGE if on else TILE)
    a.rect(27, 15, 37, 22, 1.5, WHITE)
    a.rect(27, 42, 37, 49, 1.5, WHITE)
    if on:                                              # motion arcs (off tile: no room in its slot)
        a.arc(32, 32, 22, 200, 250, 2.5, WHITE)
        a.arc(32, 32, 22, 20, 70, 2.5, WHITE)


def g_torch(a, on):
    a.poly([(24, 16), (40, 16), (37, 27), (27, 27)], WHITE)
    a.rect(27, 27, 37, 49, 2.5, WHITE)
    a.circle(32, 34, 2.3, TILE)


def g_gear(a, on):
    pts = []
    for k in range(32):
        t = math.radians(k * 360 / 32 - 360 / 64)
        rr = 15.5 if k % 4 in (1, 2) else 12
        pts.append((32 + rr * math.sin(t), 32 - rr * math.cos(t)))
    a.poly(pts, WHITE)
    a.circle(32, 32, 5.5, TILE)


# ---------------------------------------------------------------- music (screen origin of 725: 16,18)
def music_panel():
    a = Art(208, 250)
    cx, cy = 104, 117                                   # disc centre; play button centre (123,144) -> (107,126)
    a.circle(cx, cy, 96, DISC)
    a.arc(cx, cy, 96, -62, -18, 7, ORANGE)              # accent arc (decorative: no song position in stock)
    a.circle(107, 126, 36, ORANGE)
    return a.image()


def play():
    a = Art(32, 39)
    a.poly([(8, 6), (8, 33), (29, 19.5)], WHITE)
    return a.image()


def pause():
    a = Art(26, 36)
    a.rect(5, 6, 11, 30, 2, WHITE)
    a.rect(15, 6, 21, 30, 2, WHITE)
    return a.image()


# ---------------------------------------------------------------- find phone (8 frames, 112x112)
def find_frame(k):
    def make():
        a = Art(112, 112)
        a.rect(42, 26, 70, 86, 7, WHITE)
        a.rect(45.5, 31, 66.5, 78, 3, BLACK)
        a.rect(51, 81, 61, 83, 1, BLACK)
        lit = [(k + 0) % 4, (k + 2) % 4]
        for i, r in enumerate((24, 33, 42)):
            col = BLUE if i <= (k % 4) else (20, 50, 100)
            a.arc(56, 56, r + 6, -38, 38, 4, col)
            a.arc(56, 56, r + 6, 142, 218, 4, col)
        return a.image()
    return make


# ---------------------------------------------------------------- charging / low battery rings (118x118)
def charge_frame(k, n=5):
    def make():
        a = Art(118, 118)
        a.arc(59, 59, 57, 0, 360, 9, GREEN_DIM, caps=False)
        a.arc(59, 59, 57, -90, -90 + 360 * (k + 1) / n, 9, GREEN)
        return a.image()
    return make


def low_power():
    a = Art(118, 118)
    a.arc(59, 59, 57, 0, 360, 9, RED_DIM, caps=False)
    a.arc(59, 59, 57, -90, -54, 9, RED)
    a.poly([(62, 34), (45, 62), (57, 62), (54, 84), (73, 52), (61, 52), (65, 34)], RED)
    return a.image()


# ---------------------------------------------------------------- health / popups
def heart():
    a = Art(28, 25)
    a.circle(8.5, 8.5, 7, RED); a.circle(19.5, 8.5, 7, RED)
    a.poly([(2, 11), (26, 11), (14, 24)], RED)
    # crisp edges: the stock slot is only 478 bytes (about 3 colour runs per row)
    return a.image().point(lambda v: 255 if v > 100 else 0).quantize(2, dither=Image.Dither.NONE).convert("RGB")


def sleep_bg():
    a = Art(240, 280)
    a.circle(120, 86, 46, PURPLE)
    a.circle(144, 66, 40, BLACK)
    return a.image()


def bubble():
    a = Art(71, 71)
    a.circle(33, 37, 25, GREEN)
    a.poly([(14, 50), (10, 64), (28, 56)], GREEN)
    for x in (23, 33, 43):
        a.circle(x, 37, 3.2, (10, 60, 30))
    a.circle(57, 14, 9, ORANGE)
    return crisp(a.image(), [BLACK, GREEN, (10, 60, 30), ORANGE, (20, 110, 55)])


def decline():
    a = Art(65, 65)
    a.circle(32.5, 32.5, 31, RED)
    a.d.chord([16 * SS, 26 * SS, 49 * SS, 48 * SS], 180, 360, fill=WHITE)
    a.rect(15, 33, 24, 41, 3, WHITE); a.rect(41, 33, 50, 41, 3, WHITE)
    a.d.chord([20 * SS, 31 * SS, 45 * SS, 46 * SS], 180, 360, fill=RED)
    return crisp(a.image(), [BLACK, RED, WHITE, (120, 34, 29)])


# ---------------------------------------------------------------- weather (102x92, flat)
def wx(fn):
    def make():
        a = Art(102, 92)
        fn(a)
        return a.image()
    return make


def sun_at(a, x, y, r):
    a.circle(x, y, r, ORANGE)


def cloud_at(a, x, y, s=1.0, col=CLOUD):
    a.circle(x - 16 * s, y + 4 * s, 13 * s, col)
    a.circle(x + 2 * s, y - 6 * s, 19 * s, col)
    a.circle(x + 20 * s, y + 6 * s, 11 * s, col)
    a.rect(x - 29 * s, y + 4 * s, x + 31 * s, y + 17 * s, 8 * s, col)


def drops(a, n, y=70, col=BLUE):
    for i in range(n):
        x = 36 + i * 12
        a.line([(x, y), (x - 4, y + 9)], 3.5, col)


def flakes(a, y=72):
    for x in (36, 52, 68):
        for t in (0, 60, 120):
            r = math.radians(t)
            a.line([(x - 5 * math.cos(r), y - 5 * math.sin(r)), (x + 5 * math.cos(r), y + 5 * math.sin(r))], 2, WHITE)


def question(a):
    from PIL import ImageFont
    f = ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 64 * SS)
    a.d.text((51 * SS, 46 * SS), "?", font=f, fill=GREY, anchor="mm")


def crisp(im, colours):
    """Map to an exact small palette (keeps green / red and pure black = transparent; the slot
    fitter would otherwise fall back to the CMF palette)."""
    pal = Image.new("P", (1, 1))
    flat = [v for c in colours for v in c]
    pal.putpalette(flat + [0] * (768 - len(flat)))
    return im.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")


def moon_at(a, x, y, r, col=(255, 200, 80)):
    a.circle(x, y, r, col)
    a.circle(x + r * 0.55, y - r * 0.45, r * 0.85, BLACK)


WEATHER = [
    lambda a: question(a),                                                          # 0 unknown
    lambda a: sun_at(a, 51, 46, 30),                                                # 1 sunny
    lambda a: (sun_at(a, 64, 30, 20), cloud_at(a, 46, 48)),                         # 2 partly cloudy
    lambda a: (cloud_at(a, 58, 36, 0.8, CLOUD_D), cloud_at(a, 46, 50)),             # 3 overcast
    lambda a: (sun_at(a, 66, 24, 16), cloud_at(a, 46, 40), drops(a, 3, 66)),        # 4 shower
    lambda a: (cloud_at(a, 50, 38, 1, CLOUD_D), a.poly([(52, 54), (40, 74), (50, 74), (46, 90), (62, 66), (52, 66), (58, 54)], ORANGE)),  # 5 thunder
    lambda a: (cloud_at(a, 50, 38), drops(a, 2, 66), flakes(a, 80)),                # 6 sleet
    lambda a: (cloud_at(a, 50, 38), drops(a, 3, 66)),                               # 7 light rain
    lambda a: (cloud_at(a, 50, 34, 1, CLOUD_D), drops(a, 4, 62), drops(a, 4, 76)),  # 8 heavy rain
    lambda a: (cloud_at(a, 50, 36), flakes(a, 72)),                                 # 9 snow
    lambda a: [a.line([(22, y), (70, y)], 4, CLOUD) for y in (32, 46, 60)] and a.arc(70, 39, 7, -90, 90, 4, CLOUD),  # 10 wind
    lambda a: cloud_at(a, 50, 44),                                                  # 11 cloudy
    lambda a: [a.line([(20 + 6 * (i % 2), 26 + 12 * i), (82 - 6 * (i % 2), 26 + 12 * i)], 4, CLOUD_D) for i in range(5)],  # 12 haze
    lambda a: moon_at(a, 50, 46, 28),                                               # 13 clear night
    lambda a: (moon_at(a, 64, 28, 18), cloud_at(a, 46, 50)),                        # 14 cloudy night
    lambda a: (moon_at(a, 66, 24, 15), cloud_at(a, 46, 40), drops(a, 3, 66)),       # 15 night shower
]

ART = {888: tile(g_moon), 889: tile(g_moon, True), 890: tile(g_sun), 891: tile(g_raise), 892: tile(g_raise, True),
       893: tile(g_torch), 894: tile(g_gear),
       725: music_panel, 723: play, 724: pause,
       1023: low_power, 1476: heart, 1625: sleep_bg, 916: bubble, 982: decline}
ART.update({657 + k: find_frame(k) for k in range(8)})
ART.update({989 + k: charge_frame(k) for k in range(5)})
ART.update({523 + k: wx(f) for k, f in enumerate(WEATHER)})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", type=Path, default=ROOT / "research" / "ui" / "replace")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    images, _ = walk(payload(UI_BIN.read_bytes()))
    bad = []
    for i, fn in ART.items():
        _, size, w, h, _ = images[i]
        im = fn()
        assert im.size == (w, h), (i, im.size, (w, h))
        try:
            fit(im, size).save(a.out / f"{i:04d}.png")
        except SystemExit:
            bad.append(i)
    print(f"{len(ART) - len(bad)} images written to {a.out}; too big for their slot: {bad}")


if __name__ == "__main__":
    main()
