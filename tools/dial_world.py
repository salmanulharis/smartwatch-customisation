"""World face (dark): dotted world map, big coral dot-matrix time, 2x2 world-clock grid, three rings.

The city clocks need firmware mod b5_worldclock (v1323+): every world digit is element type 71
with the minute offset and digit position in the record's reserved bytes. City offsets are
computed for the build date (DST included), so rebuild + re-upload after a DST change.
"""
from __future__ import annotations

import math

from PIL import ImageFont

import dial_duo as base
import dial_duo2  # noqa: F401  (import order: duo2 sets BG first, this module overrides)
from dial_duo import W, H, on_bg
from dial_nothing import SS, Canvas, SMALL, battery_dots
from dial_widgets import flat_icon, arc, WEATHER_SHORT, fit_ttext

BG = (8, 8, 8)
MAPDOT = (80, 80, 80)
CORAL = (240, 88, 52)
WHITE = (236, 234, 228)
GREY = (140, 138, 134)
TRACK = (55, 55, 55)
FONT = "C:/Windows/Fonts/bahnschrift.ttf"
DIGITS = "-./0123456789:"

# rough continent outlines (lon, lat)
LAND = [
    [(-168, 65), (-140, 70), (-95, 72), (-75, 62), (-60, 55), (-55, 48), (-70, 43), (-80, 25), (-97, 25),
     (-105, 20), (-90, 15), (-83, 9), (-78, 8), (-100, 18), (-110, 23), (-117, 32), (-125, 40), (-125, 50),
     (-135, 58), (-150, 60)],
    [(-55, 60), (-45, 60), (-20, 70), (-25, 82), (-60, 82), (-70, 76)],
    [(-80, 10), (-62, 11), (-50, 0), (-35, -7), (-40, -22), (-55, -35), (-68, -55), (-75, -50), (-72, -20),
     (-80, -5)],
    [(-10, 36), (0, 43), (-5, 48), (-2, 51), (5, 53), (10, 58), (5, 62), (15, 70), (30, 71), (40, 65),
     (30, 55), (40, 45), (28, 41), (20, 40), (12, 38), (5, 44)],
    [(-6, 50), (2, 51), (-2, 58), (-6, 57)],
    [(-17, 21), (-10, 35), (10, 37), (32, 31), (35, 28), (43, 12), (51, 12), (40, -15), (35, -25), (20, -35),
     (15, -28), (12, -5), (8, 4), (-8, 5), (-17, 14)],
    [(30, 40), (40, 45), (30, 55), (40, 65), (60, 70), (80, 73), (110, 76), (140, 72), (170, 68), (178, 65),
     (160, 60), (140, 55), (130, 42), (122, 40), (120, 30), (110, 20), (105, 10), (100, 15), (95, 20),
     (90, 22), (80, 15), (77, 8), (72, 20), (65, 25), (57, 25), (50, 30), (48, 30), (45, 40), (35, 36)],
    [(35, 28), (40, 13), (45, 12), (55, 17), (58, 22), (52, 25), (48, 30), (35, 30)],
    [(95, 5), (105, -6), (120, -8), (130, -3), (140, -5), (150, -8), (140, -2), (125, 3), (118, 5), (110, 0),
     (100, 3)],
    [(113, -22), (122, -17), (131, -12), (142, -11), (146, -19), (153, -28), (150, -37), (140, -38),
     (130, -32), (115, -34)],
    [(130, 31), (141, 40), (142, 45), (140, 36)],
]
MARKERS = [(73, 19), (-74, 41), (0, 51), (55, 25)]          # Mumbai, New York, London, Dubai


def inside(lon, lat, poly):
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


MAP = (10, 22, 230, 112)                                     # x0, y0, x1, y1


def to_xy(lon, lat):
    x0, y0, x1, y1 = MAP
    return x0 + (lon + 170) / 350 * (x1 - x0), y0 + (80 - lat) / 136 * (y1 - y0)


def font(size, weight="Regular"):
    f = ImageFont.truetype(FONT, int(size * SS))
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def _background() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=BG)
    pitch = 4.6
    x0, y0, x1, y1 = MAP
    for j in range(int((y1 - y0) / pitch) + 1):
        for i in range(int((x1 - x0) / pitch) + 1):
            x, y = x0 + i * pitch, y0 + j * pitch
            lon = (x - x0) / (x1 - x0) * 350 - 170
            lat = 80 - (y - y0) / (y1 - y0) * 136
            if any(inside(lon, lat, p) for p in LAND):
                c.dot(x, y, 3.0, MAPDOT)
    for k, (lon, lat) in enumerate(MARKERS):
        x, y = to_xy(lon, lat)
        c.dot(x, y, 5 if k == 0 else 4, CORAL)
    bx, by = 96, 9                                           # charge bolt before the battery dots
    c.d.polygon([((bx + 1.5) * SS, (by - 6) * SS), ((bx - 3) * SS, (by + 0.5) * SS), (bx * SS, (by + 0.5) * SS),
                 ((bx - 1.5) * SS, (by + 6) * SS), ((bx + 3) * SS, (by - 0.5) * SS), (bx * SS, (by - 0.5) * SS)],
                fill=WHITE)
    for (gx, gy), (name, _) in zip(GRID, CITIES):
        c.dot(gx + 20, gy + 6, 2.2, CORAL)                   # baked H:MM colon
        c.dot(gx + 20, gy + 12, 2.2, CORAL)
        c.d.text((gx * SS, (gy + 28) * SS), name, font=font(7.5), fill=WHITE, anchor="ls")
    # rings: steps (track drawn by element), weather, heart
    arc(c, 54, 222, 17, 0, 360, TRACK, 4)
    arc(c, 186, 222, 17, 0, 360, CORAL, 4)
    hx, hy = 186, 221
    c.d.ellipse(((hx - 6) * SS, (hy - 4) * SS, hx * SS + 1, (hy + 1.5) * SS), fill=WHITE)
    c.d.ellipse((hx * SS - 1, (hy - 4) * SS, (hx + 6) * SS, (hy + 1.5) * SS), fill=WHITE)
    c.d.polygon([((hx - 6) * SS, (hy - 0.6) * SS), ((hx + 6) * SS, (hy - 0.6) * SS), (hx * SS, (hy + 6) * SS)],
                fill=WHITE)
    c.d.text((191 * SS, 259 * SS), "BPM", font=font(8), fill=GREY, anchor="ls")
    # Static parts baked in: the renderer (0x85D3DC) draws at most 34 sprites per frame.
    c.dot(61, 134, 4.2, CORAL)                                # main time colon
    c.dot(61, 144, 4.2, CORAL)
    c.d.text((54 * SS, 171 * SS), ".", font=font(12), fill=WHITE, anchor="ms")   # date dot
    c.d.text((118 * SS, 260 * SS), "°C", font=font(9.5), fill=GREY, anchor="ls")  # temp unit
    for k in range(5):                                       # dim zeros behind hidden leading step digits
        c.d.text(((37 + 7 * k + 3.5) * SS, 260 * SS), "0", font=font(11), fill=(75, 75, 75), anchor="ms")
    return c



def dot_time_digits(x, y, w=24, h=34):
    return [on_bg(x, y, w, h, lambda c, ch=ch: c.glyph(SMALL[ch], 0.5, 0.5, 4.7, 4.0, CORAL)) for ch in DIGITS]


def colon(x, y):
    return [on_bg(x, y, 8, 34, lambda c: (c.dot(4, 12, 4.2, CORAL), c.dot(4, 22, 4.2, CORAL)))]


def text_digits(x, y, w, h, size, color, weight="Regular"):
    return [on_bg(x, y, w, h, lambda c, ch=ch: c.d.text((w / 2 * SS, (h - 2) * SS), ch, font=font(size, weight),
                                                         fill=color, anchor="ms")) for ch in DIGITS]


def value(x, y, w, h, texts):
    return [on_bg(x, y, w, h, lambda c, t=t: c.d.text((0, (h - 2) * SS), t, font=font(12), fill=CORAL,
                                                       anchor="ls")) for t in texts]


def weekday(x, y):
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    return [on_bg(x, y, 30, 13, lambda c, n=n: c.d.text((0, 12 * SS), n, font=font(12, "Bold"), fill=WHITE,
                                                        anchor="ls")) for n in names * 2]


def top_battery(x, y):
    def draw(level):
        lit = battery_dots(level, 5)
        return lambda c: [c.dot(4 + i * 9, 4, 6.5, (CORAL if level > 2 else (220, 40, 40)) if i < lit else WHITE)
                          for i in range(5)]
    return [on_bg(x, y, 44, 9, draw(lv)) for lv in range(11)]


def power_word(x, y):
    word = lambda lv: "LOW" if lv <= 2 else "MID" if lv <= 5 else "GOOD" if lv <= 8 else "FULL"
    return value(x, y, 46, 15, [word(lv) for lv in range(11)])


def sky_word(x, y):
    return [on_bg(x, y, 50, 15, lambda c, code=code: fit_ttext(c, WEATHER_SHORT[code], 0, 13, 48, 12, CORAL,
                                                               anchor="ls")) for code in range(13)]


def step_ring(x, y):
    """Step-goal progress (type 32, 11 frames): coral arc + footprint glyph."""
    cx, cy = 54 - x, 222 - y

    def draw(i):
        def f(c):
            arc(c, cx, cy, 17, 0, 360, TRACK, 4)
            if i:
                arc(c, cx, cy, 17, -90, -90 + 36 * i, CORAL, 4)
            for dx, dy in ((-3, -1), (3, 2)):
                c.d.ellipse(((cx + dx - 2.2) * SS, (cy + dy - 4.5) * SS, (cx + dx + 2.2) * SS, (cy + dy + 1.5) * SS),
                            fill=WHITE)
        return f
    return [on_bg(x, y, 42, 42, draw(i)) for i in range(11)]


def weather_icon(x, y, w=36, h=30):
    def dark_layers(code):
        remap = {(245, 245, 245): WHITE, (150, 150, 150): GREY, (55, 55, 55): TRACK}
        from dial_widgets import weather_layers
        return [(remap.get(col, col), fn) for col, fn in weather_layers(code)]
    return [on_bg(x, y, w, h, lambda c, code=code: flat_icon(c, dark_layers(code), 3, 0, 30)) for code in range(13)]


def unit(x, y):
    return [on_bg(x, y, 14, 12, lambda c, t=t: c.d.text((0, 11 * SS), t, font=font(9.5), fill=GREY, anchor="ls"))
            for t in ("°C", "°F")]


# ---- world clocks (firmware mod b5_worldclock): type 71 digits, offset/position in reserved ----
import datetime as _dt
import struct as _struct

WORLD_TYPE = 71
CITY_DIG_W, CITY_DIG_H = 9, 17
GRID = [(124, 122), (174, 122), (124, 158), (174, 158)]       # top-left of each H:MM block


def _nth_sunday(year, month, n):
    """n-th Sunday of a month (n = -1: last)."""
    if n > 0:
        d = _dt.date(year, month, 1)
        return d + _dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
    d = _dt.date(year + month // 12, month % 12 + 1, 1) - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() + 1) % 7)


def _utc_offset(zone, day):
    """Minutes east of UTC on a date: 'us' (Eastern), 'eu' (UK), or a fixed number."""
    if zone == "us":
        dst = _nth_sunday(day.year, 3, 2) <= day < _nth_sunday(day.year, 11, 1)
        return -300 + 60 * dst
    if zone == "eu":
        dst = _nth_sunday(day.year, 3, -1) <= day < _nth_sunday(day.year, 10, -1)
        return 60 * dst
    return zone


CITY_ZONES = [("MUMBAI", 330), ("NEW YORK", "us"), ("DUBAI", 240), ("LONDON", "eu")]
_today = _dt.date.today()
_local = int(_dt.datetime.now().astimezone().utcoffset().total_seconds() // 60)   # watch = PC time
CITIES = [(name, _utc_offset(z, _today) - _local) for name, z in CITY_ZONES]


def _reserved(offset_minutes: int, pos: int) -> bytes:
    """[0]=0 (digit flag), [1:3]=signed LE16 minute offset, [3]=digit position, rest 0."""
    return bytes([0]) + _struct.pack("<h", offset_minutes) + bytes([pos, 0, 0, 0])


def city_digits(x, y, blank_zero=False):
    w, h = CITY_DIG_W, CITY_DIG_H

    def draw(ch):
        if blank_zero and ch == "0":
            return lambda c: None
        return lambda c: c.d.text((w / 2 * SS, (h - 1) * SS), ch, font=font(15.5), fill=CORAL, anchor="ms")
    return [on_bg(x, y, w, h, draw(ch)) for ch in DIGITS]


SAMPLE_LOCAL = (13, 10)


def city_elements():
    els = []
    for (gx, gy), (_, off) in zip(GRID, CITIES):
        hh, mm = divmod((SAMPLE_LOCAL[0] * 60 + SAMPLE_LOCAL[1] + off) % 1440, 60)
        sample = f"{hh:02d}{mm:02d}"
        for pos, dx in enumerate((0, 9, 22, 31)):
            x = gx + dx
            els.append((WORLD_TYPE, x, gy, city_digits(x, gy, blank_zero=pos == 0),
                        {"reserved": _reserved(off, pos), "sample": sample[pos]}))
    return els


base.BG_HI = _background()          # rebuild now that GRID/CITIES exist


def layout():
    small = lambda x, y: text_digits(x, y, 7, 13, 11, WHITE)
    els = [
        (17, 0, 0, [base.BG_HI.image()]),
        (8, 104, 5, top_battery(104, 5)),
        (57, 8, 122, dot_time_digits(8, 122)), (58, 33, 122, dot_time_digits(33, 122)),
        (59, 65, 122, dot_time_digits(65, 122)), (60, 90, 122, dot_time_digits(90, 122)),
        (15, 10, 160, weekday(10, 160)),
        (65, 38, 160, text_digits(38, 160, 7, 13, 12, WHITE)), (66, 45, 160, text_digits(45, 160, 7, 13, 12, WHITE)),
        (63, 56, 160, text_digits(56, 160, 7, 13, 12, WHITE)), (64, 63, 160, text_digits(63, 160, 7, 13, 12, WHITE)),

        # bottom: steps ring + count, weather, heart rate
        (32, 33, 201, step_ring(33, 201)),
        (38, 37, 249, small(37, 249)), (39, 44, 249, small(44, 249)), (40, 51, 249, small(51, 249)),
        (41, 58, 249, small(58, 249)), (42, 65, 249, small(65, 249)),
        (20, 102, 203, weather_icon(102, 203)),
        (21, 101, 249, small(101, 249)),
        (35, 165, 249, small(165, 249)), (36, 172, 249, small(172, 249)), (37, 179, 249, small(179, 249)),
    ]
    return els + city_elements()


SAMPLE = {57: "1", 58: "3", 59: "1", 60: "0", 65: "2", 66: "1", 63: "1", 64: "2",
          38: "", 39: "3", 40: "0", 41: "0", 42: "0", 35: "", 36: "7", 37: "5", 21: "35"}
