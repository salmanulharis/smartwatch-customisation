"""Dot-matrix ("Nothing"-style) desk clock layout for tools/s100_dial.py.

Every glyph is drawn as round dots on a grid, supersampled 4x then downscaled.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

W, H = 240, 280
BG = (8, 8, 8)
WHITE = (245, 245, 245)
GRAY = (150, 150, 150)
DARK = (55, 55, 55)
RED = (240, 50, 50)
AMBER = (245, 166, 35)
MINT = (90, 230, 180)
SS = 4  # supersampling factor

# 6x11 big digits, strokes two dots thick
BIG = {
    "0": [".####.", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    "1": ["..##..", ".###..", "#.##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##.."],
    "2": [".####.", "##..##", "....##", "....##", "...##.", "..##..", ".##...", "##....", "##....", "##....", "######"],
    "3": [".####.", "##..##", "....##", "....##", "..###.", "....##", "....##", "....##", "....##", "##..##", ".####."],
    "4": ["...##.", "..###.", "..###.", ".#.##.", ".#.##.", "#..##.", "#..##.", "######", "...##.", "...##.", "...##."],
    "5": ["######", "##....", "##....", "##....", "#####.", "....##", "....##", "....##", "....##", "##..##", ".####."],
    "6": [".####.", "##..##", "##....", "##....", "#####.", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    "7": ["######", "....##", "....##", "...##.", "...##.", "..##..", "..##..", "..##..", ".##...", ".##...", ".##..."],
    "8": [".####.", "##..##", "##..##", "##..##", ".####.", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    "9": [".####.", "##..##", "##..##", "##..##", "##..##", ".#####", "....##", "....##", "....##", "##..##", ".####."],
    "-": ["......"] * 5 + [".####."] + ["......"] * 5,
    ".": ["......"] * 9 + ["..##..", "..##.."],
    "/": ["....##", "....##", "...##.", "...##.", "..##..", "..##..", ".##...", ".##...", "##....", "##....", "......"],
    ":": ["......"] * 3 + ["..##..", "..##..", "......", "..##..", "..##.."] + ["......"] * 3,
}

# classic 5x7 font for labels and small numbers
SMALL = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    " ": ["....."] * 7,
}


def battery_dots(level: int, n: int) -> int:
    """Dots to light for firmware battery level (= ceil(%/10), 0..10) on an n-dot gauge.

    Uses the middle of the 10 % step (level 6 = 51-60 % -> 55.5 %) and rounds, so 55 % shows
    half the dots instead of rounding up. Any charge > 0 keeps at least one dot lit.
    """
    if level <= 0:
        return 0
    return max(1, min(n, round((level * 10 - 4.5) * n / 100)))


class Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w * SS, h * SS), BG)
        self.d = ImageDraw.Draw(self.im)

    def dot(self, x: float, y: float, diam: float, color):
        r = diam * SS / 2
        cx, cy = x * SS, y * SS
        self.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)

    def glyph(self, rows: list[str], x: float, y: float, pitch: float, diam: float, color):
        for j, row in enumerate(rows):
            for i, c in enumerate(row):
                if c == "#":
                    self.dot(x + (i + 0.5) * pitch, y + (j + 0.5) * pitch, diam, color)

    def text(self, s: str, x: float, y: float, pitch: float, diam: float, color, gap: int = 1):
        for k, ch in enumerate(s):
            self.glyph(SMALL[ch], x + k * (5 + gap) * pitch, y, pitch, diam, color)

    def image(self) -> Image.Image:
        return self.im.resize((self.w, self.h), Image.LANCZOS)


def text_width(s: str, pitch: float, gap: int = 1) -> float:
    return (len(s) * (5 + gap) - gap) * pitch


def frame(w, h, draw) -> Image.Image:
    c = Canvas(w, h)
    draw(c)
    return c.image()


# ---- geometry (240x280) ----
BIG_PITCH, BIG_DOT = 6.6, 5.3
BIG_W, BIG_H = 42, 75
TIME_Y = 74
SM_PITCH, SM_DOT = 2.0, 1.6       # labels / date
MID_PITCH, MID_DOT = 3.0, 2.5     # AM/PM


def big_digit_frames(color=WHITE):
    order = "-./0123456789:"
    return [frame(BIG_W, BIG_H, lambda c, ch=ch: c.glyph(BIG[ch], 1, 1, BIG_PITCH, BIG_DOT, color))
            for ch in order]


def small_digit_frames(color=GRAY):
    order = "-./0123456789:"
    w, h = 12, 15
    return [frame(w, h, lambda c, ch=ch: c.glyph(SMALL[ch], 0.5, 0.5, SM_PITCH, SM_DOT, color))
            for ch in order]


def background() -> Image.Image:
    c = Canvas(W, H)
    c.text("PHONE", 18, 30, SM_PITCH, SM_DOT, GRAY)
    for x in range(16, W - 15, 4):                       # dotted divider
        c.dot(x, 197, 1.2, DARK)
    for y in range(214, 254, 4):                         # vertical separator
        c.dot(120, y, 1.2, DARK)
    c.text("BATTERY", 132, 216, 1.7, 1.3, GRAY)
    return c.image()


def bt_frames():
    # Bluetooth rune as dotted segments: spine plus the two crossing chevrons
    segs = [((6, 2), (6, 18)), ((6, 2), (10, 6)), ((10, 6), (2, 14)),
            ((6, 18), (10, 14)), ((10, 14), (2, 6))]

    def draw(color_dot):
        def f(c):
            for (x0, y0), (x1, y1) in segs:
                n = max(abs(x1 - x0), abs(y1 - y0)) // 2
                for k in range(n + 1):
                    t = k / n
                    c.dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 1.5, WHITE)
            c.dot(22, 10, 7, color_dot)
        return f
    return [frame(28, 21, draw(DARK)), frame(28, 21, draw(MINT))]


def ampm_frames():
    w = int(text_width("AM", MID_PITCH)) + 2
    h = int(7 * MID_PITCH) + 2
    return [frame(w, h, lambda c, t=t: c.text(t, 1, 1, MID_PITCH, MID_DOT, AMBER))
            for t in ("AM", "PM", "AM", "PM")]


def week_frames():
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    w = int(text_width("WED", SM_PITCH)) + 2
    return [frame(w, 15, lambda c, n=n: c.text(n, 0.5, 0.5, SM_PITCH, SM_DOT, GRAY)) for n in names * 2]


def battery_frames():
    seg, gap, pitch = 18, 4, 4.4
    w = 4 * seg + 3 * gap + 2

    # firmware picks frame ceil(battery%/10) → 11 frames (0 … 100 %), no bounds check
    def draw(level):
        lit = battery_dots(level, 4)
        on = RED if level <= 2 else MINT

        def f(c):
            for s in range(4):
                color = on if s < lit else DARK
                ox = 1 + s * (seg + gap)
                for j in range(4):
                    for i in range(4):
                        # rounded cluster: skip corners
                        if (i in (0, 3)) and (j in (0, 3)):
                            continue
                        c.dot(ox + (i + 0.5) * pitch, 1 + (j + 0.5) * pitch, 3.8, color)
        return f
    return [frame(w, 20, draw(level)) for level in range(11)]


BLUE = (90, 170, 255)
ICON_N, ICON_PITCH = 12, 2.9          # 12x12 dot grid → ~35 px icon


def dot_icon(layers) -> Image.Image:
    """layers: list of (color, draw_fn(ImageDraw, size)) painted on a 12x12-cell mask."""
    size = int(ICON_N * ICON_PITCH) + 1
    c = Canvas(size, size)
    cell = 10
    for color, draw in layers:
        mask = Image.new("L", (ICON_N * cell, ICON_N * cell), 0)
        draw(ImageDraw.Draw(mask), ICON_N * cell)
        px = mask.load()
        for j in range(ICON_N):
            for i in range(ICON_N):
                cov = sum(px[i * cell + a, j * cell + b] for a in (3, 5, 7) for b in (3, 5, 7)) / (9 * 255)
                if cov > 0.45:
                    c.dot((i + 0.5) * ICON_PITCH, (j + 0.5) * ICON_PITCH, ICON_PITCH * 0.82, color)
    return c.image()


def _sun(d, s, cx=0.5, cy=0.5, r=0.2, rays=True):
    d.ellipse(((cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s), fill=255)
    if rays:
        import math
        for k in range(8):
            a = k * math.pi / 4
            x, y = cx + 0.4 * math.cos(a), cy + 0.4 * math.sin(a)
            d.ellipse(((x - 0.05) * s, (y - 0.05) * s, (x + 0.05) * s, (y + 0.05) * s), fill=255)


def _cloud(d, s, top=0.3):
    d.ellipse((0.12 * s, (top + 0.12) * s, 0.48 * s, (top + 0.42) * s), fill=255)
    d.ellipse((0.32 * s, top * s, 0.74 * s, (top + 0.42) * s), fill=255)
    d.ellipse((0.6 * s, (top + 0.14) * s, 0.92 * s, (top + 0.42) * s), fill=255)
    d.rectangle((0.22 * s, (top + 0.27) * s, 0.82 * s, (top + 0.42) * s), fill=255)


def _drops(d, s, n, y0=0.72):
    """Rain drops big enough to read on small icons (were ~2x3 px at 22 px)."""
    for k in range(n):
        x = 0.25 + k * (0.5 / max(n - 1, 1))
        d.ellipse(((x - 0.065) * s, y0 * s, (x + 0.065) * s, (y0 + 0.24) * s), fill=255)


def _lines(d, s, wavy=False):
    for k, y in enumerate((0.3, 0.5, 0.7)):
        x0 = 0.1 + (0.1 if k == 1 else 0)
        if wavy:
            d.arc((x0 * s, (y - 0.08) * s, 0.9 * s, (y + 0.08) * s), 0, 180, fill=255, width=int(0.08 * s))
        else:
            d.rectangle((x0 * s, (y - 0.04) * s, 0.9 * s, (y + 0.04) * s), fill=255)


def weather_icon_frames():
    """Frame n = condition code n (1 sunny … 12 wind); frame 0 = no data."""
    no_data = lambda d, s: d.rectangle((0.3 * s, 0.46 * s, 0.7 * s, 0.54 * s), fill=255)
    cloud = lambda top=0.22: (lambda d, s: _cloud(d, s, top))
    return [
        dot_icon([(DARK, no_data)]),
        dot_icon([(AMBER, lambda d, s: _sun(d, s))]),                                   # 1 sunny
        dot_icon([(AMBER, lambda d, s: _sun(d, s, 0.35, 0.35, 0.16, False)), (WHITE, cloud(0.38))]),  # 2 cloudy
        dot_icon([(GRAY, cloud(0.3))]),                                                  # 3 overcast
        dot_icon([(WHITE, cloud()), (BLUE, lambda d, s: _drops(d, s, 3))]),              # 4 shower
        dot_icon([(WHITE, cloud()), (AMBER, lambda d, s: d.polygon(
            [(0.55 * s, 0.6 * s), (0.38 * s, 0.82 * s), (0.5 * s, 0.82 * s), (0.42 * s, 1.0 * s),
             (0.66 * s, 0.74 * s), (0.54 * s, 0.74 * s)], fill=255))]),                 # 5 thunder
        dot_icon([(WHITE, cloud()), (BLUE, lambda d, s: _drops(d, s, 2)),
                  (WHITE, lambda d, s: d.ellipse((0.41 * s, 0.74 * s, 0.59 * s, 0.92 * s), fill=255))]),  # 6 sleet
        dot_icon([(WHITE, cloud()), (BLUE, lambda d, s: _drops(d, s, 2))]),              # 7 light rain
        dot_icon([(GRAY, cloud()), (BLUE, lambda d, s: _drops(d, s, 4))]),               # 8 heavy rain
        dot_icon([(WHITE, cloud()), (WHITE, lambda d, s: [d.ellipse(
            ((x - 0.05) * s, 0.8 * s, (x + 0.05) * s, 0.9 * s), fill=255) for x in (0.25, 0.5, 0.75)])]),  # 9 snow
        dot_icon([(AMBER, lambda d, s: _lines(d, s))]),                                  # 10 dust
        dot_icon([(GRAY, lambda d, s: _lines(d, s))]),                                   # 11 fog/haze
        dot_icon([(WHITE, lambda d, s: _lines(d, s, wavy=True))]),                       # 12 wind
    ]


TEMP_PITCH, TEMP_DOT = 2.6, 2.1


def temp_digit_frames():
    order = "-./0123456789:"
    w, h = int(6 * TEMP_PITCH), int(7 * TEMP_PITCH) + 1
    return [frame(w, h, lambda c, ch=ch: c.glyph(SMALL[ch], 0.5, 0.5, TEMP_PITCH, TEMP_DOT, AMBER))
            for ch in order]


def degree_frames():
    def f(c):
        for k in range(8):
            import math
            a = k * math.pi / 4
            c.dot(4 + 2.6 * math.cos(a), 4 + 2.6 * math.sin(a), 1.4, AMBER)
    return [frame(9, 9, f), frame(9, 9, f)]   # 0 = °C, 1 = °F


def colon_frame():
    return [frame(10, BIG_H, lambda c: (c.dot(5, 26, 8, RED), c.dot(5, 50, 8, RED)))]


def layout():
    big = big_digit_frames()
    small = small_digit_frames()
    week = week_frames()
    ampm = ampm_frames()
    date_y = 168
    wx = 66
    dx = wx + week[0].size[0] + 8
    els = [
        (17, 0, 0, [background()]),
        (9, 80, 26, bt_frames()),
        (16, W - 18 - ampm[0].size[0], 26, ampm),
        (57, 23, TIME_Y, big), (58, 69, TIME_Y, big),
        (7, 115, TIME_Y, colon_frame()),
        (59, 129, TIME_Y, big), (60, 175, TIME_Y, big),
        (15, wx, date_y, week),
        # day.month (European order, as in the design)
        (65, dx, date_y, small), (66, dx + 12, date_y, small),
        (14, dx + 24, date_y, [frame(8, 15, lambda c: c.glyph(SMALL["."], -0.5, 0.5, SM_PITCH, SM_DOT, GRAY))]),
        (63, dx + 32, date_y, small), (64, dx + 44, date_y, small),
        (8, 132, 230, battery_frames()),
        (20, 18, 215, weather_icon_frames()),
        # temperature: firmware centres up to 3 chars on this element
        (21, TEMP_CX - 23, 223, temp_digit_frames()),
        (22, TEMP_CX + 18, 220, degree_frames()),
    ]
    return els


TEMP_CX = 80  # horizontal centre of the temperature field


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0"}
