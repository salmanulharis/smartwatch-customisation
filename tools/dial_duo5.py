"""Duo 5 face (light theme analog): big dial with watch-rotated hands, steps / goal capsules,
weather bubble, heart-rate card. Square design stretched to 240x280 (dial kept round).
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

import dial_duo as base
import dial_duo2 as duo2
from dial_duo import CREAM, INK, SOFT, CORAL, DIGITS, W, H, on_bg, rrect, ttext
from dial_nothing import SS, Canvas, battery_dots
from dial_widgets import flat_icon, fit_ttext, WEATHER_SHORT

BLACK = (26, 26, 26)
CAPSULE = (222, 220, 214)
DISC = (226, 225, 220)
CX, CY, R = 119, 128, 68             # dial centre / radius (hand pivot)
WX_C = (204, 80, 30)                 # weather bubble (fits icon + temp + label)
GOAL = (207, 124, 230, 190)          # right capsule
STEPS_CAP = (9, 134, 50, 203)
HR_CARD = (10, 211, 115, 259)


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    # decorative coral blob + black circle (bottom right)
    rrect(c, (140, 216, 260, 300), 24, fill=CORAL, width=0)
    c.dot(184, 217, 40, BLACK)
    # dial disc with a coral gradient quadrant (6 → 9 o'clock)
    c.dot(CX, CY, 2 * R, DISC)
    quad = Image.new("RGB", (2 * R * SS, 2 * R * SS), CORAL)
    mask = Image.new("L", quad.size, 0)
    md = ImageDraw.Draw(mask)
    for k in range(R * SS, 0, -SS):                       # fade out towards the rim
        a = int(255 * (0.35 + 0.65 * (1 - k / (R * SS)) ** 0.6))
        md.pieslice((R * SS - k, R * SS - k, R * SS + k, R * SS + k), 90, 180, fill=a)
    c.im.paste(quad, ((CX - R) * SS, (CY - R) * SS), mask)
    for k in range(12):                                    # tick dots
        a = math.radians(k * 30)
        col = CORAL if k in (0, 8, 9) else (175, 173, 167)
        c.dot(CX + (R - 12) * math.sin(a), CY - (R - 12) * math.cos(a), 4.2 if k % 3 == 0 else 3, col)
    c.dot(CX, CY, 20, BLACK)                               # centre ring (hands draw over it)
    c.dot(CX, CY, 10, (190, 188, 182))
    # weather bubble, capsules, card
    c.dot(WX_C[0], WX_C[1], 2 * WX_C[2], CAPSULE)
    rrect(c, GOAL, 11.5, fill=CAPSULE, width=0)
    rrect(c, STEPS_CAP, 20, fill=CAPSULE, width=0)
    rrect(c, HR_CARD, 24, fill=BLACK, width=0)
    c.dot(77, 27, 7, CORAL)                                # accent after weekday
    shoe = [(22, 152), (27, 149), (31, 155), (38, 159), (37, 163), (24, 159), (22, 152)]
    c.d.line([(x * SS, y * SS) for x, y in shoe], fill=INK, width=int(1.4 * SS), joint="curve")
    ttext(c, "STEPS", 29.5, 193, 8, SOFT, anchor="ms", spacing=1.0)
    for k in range(9):                                     # dot-grid heart marker
        c.dot(24 + (k % 3) * 6, 225 + (k // 3) * 6, 4.4, CORAL if k == 8 else (240, 240, 236))
    ttext(c, "BPM", 82, 236, 8, (150, 150, 150), anchor="ls", spacing=0.5)
    ttext(c, "Heart rate", 52, 251, 8, (150, 150, 150), anchor="ls")
    return c


base.BG_HI = _background()


BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def dithered_background() -> Image.Image:
    """Ordered-dither the gradient quadrant to RGB565 steps so it doesn't band on the watch.

    Only the quadrant is touched; flat colours stay exactly as drawn.
    """
    im = base.BG_HI.image()
    px = im.load()
    for y in range(CY, CY + R + 1):
        for x in range(CX - R, CX + 1):
            if (x - CX) ** 2 + (y - CY) ** 2 > (R - 1) ** 2:
                continue
            t = (BAYER4[y % 4][x % 4] + 0.5) / 16
            r, g, b = px[x, y]
            q = lambda v, step: min(255, int(v / step + t) * step)
            px[x, y] = (q(r, 8), q(g, 4), q(b, 8))
    return im


def crisp_hand(w: int, h: int, tip: int, color) -> tuple[Image.Image, dict]:
    """Hand with hard edges (no anti-aliasing), so no dark fringe appears on a light face."""
    im = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=w // 2, fill=color)
    return im, {"transparent": True, "reserved": bytes([0, 0, 0, 0, tip, h, w])}


def smooth_hand(w: int, h: int, tip: int, color, face_bg=CREAM) -> tuple[Image.Image, dict]:
    """Anti-aliased hand whose edge pixels are pre-blended with the face colour, not black.

    The watch rotates hand images without smoothing and treats 0x0000 as transparent, so:
    - pixels fully outside the hand are pure black (transparent),
    - edge pixels are hand/face blends → smooth edges on a light face, no dark fringe.
    """
    ss = 8
    hi = Image.new("RGB", (w * ss, h * ss), face_bg)
    ImageDraw.Draw(hi).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=w * ss // 2, fill=color)
    cov = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(cov).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=w * ss // 2, fill=255)
    im = hi.resize((w, h), Image.LANCZOS)
    a = cov.resize((w, h), Image.BOX)
    px, ap = im.load(), a.load()
    for yy in range(h):
        for xx in range(w):
            if ap[xx, yy] < 24:                      # essentially outside → transparent key
                px[xx, yy] = (0, 0, 0)
            elif px[xx, yy] == (0, 0, 0):
                px[xx, yy] = (8, 8, 8)               # never emit the key inside the hand
    return im, {"transparent": True, "reserved": bytes([0, 0, 0, 0, tip, h, w])}


def goal_dots(x, y):
    """Step-goal progress (type 32, 11 frames): 5 dots fill top-down in coral."""
    def draw(i):
        lit = round(i * 5 / 10)

        def f(c):
            for k in range(5):
                c.dot(6, 6 + k * 12, 9, CORAL if k < lit else (190, 188, 182))
        return f
    return [on_bg(x, y, 12, 60, draw(i)) for i in range(11)]


def weather_icon(x, y, w=52, h=56):
    """Icon (24 px) on top, temperature row drawn over the middle, label near the bottom."""
    def draw(code):
        def f(c):
            flat_icon(c, base.light_layers(code), w / 2 - 12, 0, 24)
            fit_ttext(c, WEATHER_SHORT[code], w / 2, 51, 40, 7.5, SOFT, anchor="ms", spacing=0.6)
        return f
    return [on_bg(x, y, w, h, draw(code)) for code in range(13)]


def battery_dots_status(x, y):
    def draw(level):
        lit = battery_dots(level, 4)

        def f(c):
            for i in range(4):
                c.dot(5 + i * 9, 6, 7.5, CORAL if i < lit else (185, 183, 177))
        return f
    return [on_bg(x, y, 40, 12, draw(lv)) for lv in range(11)]


def layout():
    small = lambda x, y, size, color, w=7, h=12: base.text_digits(x, y, w, h, size, color)
    hr_img, hr_opt = smooth_hand(12, 42, 36, BLACK)
    mn_img, mn_opt = smooth_hand(10, 56, 50, CORAL)
    white = (240, 240, 236)
    return [
        (17, 0, 0, [dithered_background()]),
        (15, 18, 17, duo2.weekday(18, 17)),
        (65, 20, 39, small(20, 39, 12, SOFT, 8, 14)), (66, 28, 39, small(28, 39, 12, SOFT, 8, 14)),
        (14, 36, 39, [on_bg(36, 39, 5, 14, lambda c: ttext(c, ".", 2.5, 12, 12, SOFT, anchor="ms"))]),
        (63, 41, 39, small(41, 39, 12, SOFT, 8, 14)), (64, 49, 39, small(49, 39, 12, SOFT, 8, 14)),
        (9, 140, 18, base.bt(140, 18)),
        (8, 176, 20, battery_dots_status(176, 20)),
        (32, 213, 127, goal_dots(213, 127)),
        (20, 178, 52, weather_icon(178, 52)),
        # "29°" centred on the bubble: digits at x+4, x+13 → 191..209, degree 210
        (21, 187, 77, small(187, 77, 12, INK, 9, 14)),
        (22, 210, 77, base.degree(210, 77)),
        # steps count in the left capsule
        (38, 12, 167, small(12, 167, 10, INK, 7, 12)), (39, 19, 167, small(19, 167, 10, INK, 7, 12)),
        (40, 26, 167, small(26, 167, 10, INK, 7, 12)), (41, 33, 167, small(33, 167, 10, INK, 7, 12)),
        (42, 40, 167, small(40, 167, 10, INK, 7, 12)),
        # heart rate on the black card
        (35, 52, 223, small(52, 223, 14, white, 9, 16)), (36, 61, 223, small(61, 223, 14, white, 9, 16)),
        (37, 70, 223, small(70, 223, 14, white, 9, 16)),
        # analog hands, rotated by the watch about the dial centre
        (1, CX, CY, [hr_img], hr_opt),
        (2, CX, CY, [mn_img], mn_opt),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2", 38: "0", 39: "8", 40: "5", 41: "1", 42: "0"}
