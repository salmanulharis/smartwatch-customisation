"""Grid face (dark): sun/weather, dot clock, small mono time, step-goal dot grid, battery dots.

Geometry is measured from the design mockup (screen 290 px wide = 240 watch px).
Every part is live: weather icon + temperature (20/21), minute dot on the ring (2) and hour hand (1)
rotated by the watch, hours/minutes/AM-PM (57-60, 16), step-goal progress (32), battery (8).
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

import dial_duo as base
import dial_duo2  # noqa: F401  (import order: duo2 sets BG first, this module overrides)
from dial_duo import W, H, on_bg
from dial_nothing import SS, Canvas, battery_dots
from dial_widgets import flat_icon, weather_layers

BG = (8, 8, 8)
WHITE = (255, 255, 255)
GREY = (140, 138, 134)
DISC = (59, 59, 59)
RING = (48, 48, 48)
CORAL = (230, 84, 51)
MONO = "C:/Windows/Fonts/consola.ttf"
DIGITS = "-./0123456789:"

# dot clock
CX, CY = 162, 73                   # disc centre = rotation pivot
DISC_R, RING_R, RING_N, RING_D = 42.5, 50, 30, 4.4
MIN_D, CAP_D, HAND_W, HAND_L = 6.5, 10.0, 2.6, 25
# sun + temperature
SUN_X, SUN_Y, SUN_CORE, RAY_R, RAY_D = 48, 74, 16.6, 15.5, 4.2
TEMP_X0, TEMP_Y, TEMP_W, TEMP_H = 34, 96, 6, 12          # 3-char field; "°C" follows at x0 + 2.5w
# time "4:35 PM": monospace cells of CW px
TX, TY, CW, CH, TSIZE = 18, 152, 7, 15, 12.5
# step grid 12 x 3 and battery 5 dots
GX, GY, GPX, GPY, GD, COLS, ROWS = 28.6, 182, 16.36, 17.2, 9.9, 12, 3
BX, BY, BP, BD, BN = 99.7, 248, 11.6, 8.0, 5


def mono(size):
    return ImageFont.truetype(MONO, int(size * SS))


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=BG)
    for k in range(RING_N):
        a = math.radians(k * 360 / RING_N)
        c.dot(CX + RING_R * math.sin(a), CY - RING_R * math.cos(a), RING_D, RING)
    c.dot(CX, CY, 2 * DISC_R, DISC)
    c.dot(CX, CY, CAP_D, WHITE)                                  # static cap; the hand starts at its rim
    c.d.text(((TX + 2.5 * CW) * SS, (TY + CH - 4) * SS), ":", font=mono(TSIZE), fill=WHITE, anchor="ms")
    c.d.text(((TEMP_X0 + 2.5 * TEMP_W) * SS, (TEMP_Y + TEMP_H - 4) * SS), "°C", font=mono(10), fill=WHITE,
             anchor="ls")
    bx, by = 90.2, BY                                            # charge bolt, 5 x 8.3 px
    c.d.polygon([((bx + 1.3) * SS, (by - 4.2) * SS), ((bx - 2.5) * SS, (by + 0.6) * SS), ((bx - 0.2) * SS, (by + 0.6) * SS),
                 ((bx - 1.3) * SS, (by + 4.2) * SS), ((bx + 2.5) * SS, (by - 0.6) * SS), ((bx + 0.2) * SS, (by - 0.6) * SS)],
                fill=WHITE)
    return c


base.BG_HI = _background()


# ---------------- hands (rotated by the watch about (w // 2, byte21)) ----------------
def _hand_image(w, h, draw_cov, draw_col, edge_bg):
    """Supersampled hand art; outside pixels = transparent key (pure black), edges blended with edge_bg."""
    ss = 8
    col = Image.new("RGB", (w * ss, h * ss), edge_bg)
    cov = Image.new("L", (w * ss, h * ss), 0)
    draw_col(ImageDraw.Draw(col), ss)
    draw_cov(ImageDraw.Draw(cov), ss)
    im, a = col.resize((w, h), Image.LANCZOS), cov.resize((w, h), Image.BOX)
    px, ap = im.load(), a.load()
    for yy in range(h):
        for xx in range(w):
            if ap[xx, yy] < 24:
                px[xx, yy] = (0, 0, 0)
            elif px[xx, yy] == (0, 0, 0):
                px[xx, yy] = (8, 8, 8)
    return im


def hour_hand():
    """Coral stick from the cap rim up to HAND_L px; the white cap itself is static in the background
    (the watch clipped a cap drawn inside the rotating image to a half disc)."""
    w, tip = 4, HAND_L + 1
    h = tip + 1
    cx, r0 = w / 2, CAP_D / 2 - 0.5

    def shape(d, ss, fill):
        d.rounded_rectangle(((cx - HAND_W / 2) * ss, (tip - HAND_L) * ss, (cx + HAND_W / 2) * ss, (tip - r0) * ss),
                            radius=HAND_W * ss / 2, fill=fill)
    im = _hand_image(w, h, lambda d, ss: shape(d, ss, 255), lambda d, ss: shape(d, ss, CORAL), DISC)
    return im, {"transparent": True, "reserved": bytes([0, 0, 0, 0, tip, h, w])}


def minute_dot():
    """Minute 'hand' = one coral dot on the ring; the rest of the image is transparent."""
    w, tip = 10, RING_R + 4
    h = tip + 1
    cx, cy = w / 2, tip - RING_R

    def shape(d, ss, fill):
        d.ellipse(((cx - MIN_D / 2) * ss, (cy - MIN_D / 2) * ss, (cx + MIN_D / 2) * ss, (cy + MIN_D / 2) * ss),
                  fill=fill)
    im = _hand_image(w, h, lambda d, ss: shape(d, ss, 255), lambda d, ss: shape(d, ss, CORAL), BG)
    return im, {"transparent": True, "reserved": bytes([0, 0, 0, 0, tip, h, w])}


# ---------------- elements ----------------
def sun(c: Canvas, cx, cy):
    c.dot(cx, cy, SUN_CORE, CORAL)
    for k in range(8):
        a = math.radians(k * 45)
        c.dot(cx + RAY_R * math.sin(a), cy - RAY_R * math.cos(a), RAY_D, WHITE)


def weather_icon(x, y, w=36, h=36):
    """Code 1 (sunny) is the mockup's sun; other conditions use the shared flat icons."""
    def layers(code):
        remap = {(245, 245, 245): WHITE, (150, 150, 150): GREY, (55, 55, 55): RING}
        return [(remap.get(col, col), fn) for col, fn in weather_layers(code)]

    def draw(code):
        if code == 1:
            return lambda c: sun(c, SUN_X - x, SUN_Y - y)
        return lambda c: flat_icon(c, layers(code), (w - 30) / 2, (h - 30) / 2, 30)
    return [on_bg(x, y, w, h, draw(code)) for code in range(13)]


def cells(x, y, w, h, size, blank_zero=False):
    def draw(ch):
        if blank_zero and ch == "0":
            return lambda c: None
        return lambda c: c.d.text((w / 2 * SS, (h - 4) * SS), ch, font=mono(size), fill=WHITE, anchor="ms")
    return [on_bg(x, y, w, h, draw(ch)) for ch in DIGITS]


def ampm(x, y):
    return [on_bg(x, y, 2 * CW + 1, CH, lambda c, t=t: c.d.text((0, (CH - 4) * SS), t, font=mono(TSIZE),
                                                               fill=WHITE, anchor="ls"))
            for t in ("AM", "PM", "AM", "PM")]


def step_grid(x, y, w, h):
    """Step-goal progress (type 32, 11 frames): coral dots fill column by column."""
    total = COLS * ROWS

    def draw(i):
        lit = round(i * total / 10)
        return lambda c: [c.dot(GX - x + col * GPX, GY - y + row * GPY, GD,
                                CORAL if col * ROWS + row < lit else WHITE)
                          for col in range(COLS) for row in range(ROWS)]
    return [on_bg(x, y, w, h, draw(i)) for i in range(11)]


def battery(x, y, w, h):
    """11 frames (firmware ceil(%/10)): coral fills from the right, as in the mockup."""
    def draw(level):
        lit = battery_dots(level, BN)
        return lambda c: [c.dot(BX - x + k * BP, BY - y, BD, CORAL if k >= BN - lit else WHITE) for k in range(BN)]
    return [on_bg(x, y, w, h, draw(lv)) for lv in range(11)]


def layout():
    hr_img, hr_opt = hour_hand()
    mn_img, mn_opt = minute_dot()
    gx0, gy0 = int(GX - GD / 2 - 1), int(GY - GD / 2 - 1)
    gw, gh = int((COLS - 1) * GPX + GD + 3), int((ROWS - 1) * GPY + GD + 3)
    bx0, by0 = int(BX - BD / 2 - 1), int(BY - BD / 2 - 1)
    sx0, sy0 = SUN_X - 18, SUN_Y - 18
    return [
        (17, 0, 0, [base.BG_HI.image()]),
        (20, sx0, sy0, weather_icon(sx0, sy0)),
        (21, TEMP_X0, TEMP_Y, cells(TEMP_X0, TEMP_Y, TEMP_W, TEMP_H, 10)),
        (57, TX, TY, cells(TX, TY, CW, CH, TSIZE, blank_zero=True)),
        (58, TX + CW, TY, cells(TX + CW, TY, CW, CH, TSIZE)),
        (59, TX + 3 * CW, TY, cells(TX + 3 * CW, TY, CW, CH, TSIZE)),
        (60, TX + 4 * CW, TY, cells(TX + 4 * CW, TY, CW, CH, TSIZE)),
        (16, TX + 6 * CW, TY, ampm(TX + 6 * CW, TY)),
        (32, gx0, gy0, step_grid(gx0, gy0, gw, gh)),
        (8, bx0, by0, battery(bx0, by0, int((BN - 1) * BP + BD + 3), int(BD + 3))),
        (1, CX, CY, [hr_img], hr_opt),
        (2, CX, CY, [mn_img], mn_opt),
    ]


SAMPLE = {57: "0", 58: "4", 59: "3", 60: "5", 21: "35"}
