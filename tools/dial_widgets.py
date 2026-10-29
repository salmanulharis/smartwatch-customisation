"""Widget-style face (dot-matrix time + cards + rings) for tools/s100_dial.py.

Everything shown is live: weekday, BT, battery (pill + ring with %), time, AM/PM,
weather icon with condition label + temperature, date card, heart-rate card, connection ring.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from dial_nothing import (BIG, BG, WHITE, GRAY, DARK, RED, MINT, SS, Canvas, frame, text_width, battery_dots,
                          _sun, _cloud, _drops, _lines)

W, H = 240, 280
CORAL = (250, 85, 60)
CARD = (48, 48, 48)
FONT = "C:/Windows/Fonts/bahnschrift.ttf"


def ttf(size: float) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, int(size * SS))
    try:
        f.set_variation_by_name("SemiBold")
    except Exception:
        pass
    return f


def ttext(c: Canvas, s: str, x: float, y: float, size: float, color, anchor="la", spacing=0.0):
    f = ttf(size)
    if not spacing:
        c.d.text((x * SS, y * SS), s, font=f, fill=color, anchor=anchor)
        return
    total = sum(c.d.textlength(ch, font=f) for ch in s) + spacing * SS * (len(s) - 1)
    cx = x * SS - (total / 2 if anchor[0] == "m" else 0)
    for ch in s:
        c.d.text((cx, y * SS), ch, font=f, fill=color, anchor="l" + anchor[1])
        cx += c.d.textlength(ch, font=f) + spacing * SS


def fit_ttext(c: Canvas, s: str, x: float, y: float, max_w: float, size: float, color, anchor="ms",
              spacing=0.0, min_size=6.5):
    """ttext that shrinks spacing, then size, until the label fits max_w (never clips)."""
    while True:
        f = ttf(size)
        w = (sum(c.d.textlength(ch, font=f) for ch in s) + spacing * SS * (len(s) - 1)) / SS
        if w <= max_w or (size <= min_size and spacing <= 0):
            break
        if spacing > 0:
            spacing = max(0.0, spacing - 0.3)
        else:
            size -= 0.25
    ttext(c, s, x, y, size, color, anchor=anchor, spacing=spacing)


def rrect(c: Canvas, box, r, outline=None, fill=None, width=1.5):
    x0, y0, x1, y1 = box
    c.d.rounded_rectangle((x0 * SS, y0 * SS, x1 * SS, y1 * SS), radius=r * SS,
                          outline=outline, fill=fill, width=int(width * SS))


def arc(c: Canvas, cx, cy, r, start, end, color, width):
    c.d.arc(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), start, end,
            fill=color, width=int(width * SS))


# ---------------- time ----------------
BIG_PITCH, BIG_DOT = 5.8, 5.1
DIG_W, DIG_H = 36, 66
TIME_Y = 54


def big_digits():
    return [frame(DIG_W, DIG_H, lambda c, ch=ch: c.glyph(BIG[ch], 0.5, 1, BIG_PITCH, BIG_DOT, WHITE))
            for ch in "-./0123456789:"]


def colon():
    return [frame(10, DIG_H, lambda c: (c.dot(5, 24, 8, CORAL), c.dot(5, 45, 8, CORAL)))]


def ampm():
    return [frame(34, 20, lambda c, t=t: ttext(c, t, 34, 18, 20, CORAL, anchor="rs"))
            for t in ("AM", "PM", "AM", "PM")]


# ---------------- top bar ----------------
def weekday():
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    from dial_nothing import SMALL
    w = int(text_width("WED", 2.4)) + 2
    return [frame(w, 18, lambda c, n=n: c.text(n, 0.5, 0.5, 2.4, 2.0, WHITE)) for n in names * 2]


def bt_icon():
    def draw(dot):
        def f(c):
            pts = [(4, 4), (12, 11), (8, 15), (8, 1), (12, 5), (4, 12)]
            c.d.line([(x * SS, (y + 2) * SS) for x, y in pts], fill=WHITE, width=int(1.6 * SS), joint="curve")
            c.dot(19, 10, 5, dot)
        return f
    return [frame(24, 20, draw(DARK)), frame(24, 20, draw(MINT))]


def battery_pill():
    """11 frames (firmware uses ceil(%/10)); 5 dots inside a pill."""
    def draw(level):
        lit = battery_dots(level, 5)
        on = RED if level <= 2 else CORAL

        def f(c):
            rrect(c, (1, 2, 41, 18), 6, outline=WHITE, width=1.6)
            c.d.rectangle((42 * SS, 7 * SS, 44 * SS, 13 * SS), fill=WHITE)
            for i in range(5):
                c.dot(8 + i * 6.5, 10, 5, on if i < lit else DARK)
        return f
    return [frame(45, 20, draw(lv)) for lv in range(11)]


# ---------------- weather card ----------------
WEATHER = ["--", "SUNNY", "CLOUDY", "OVERCAST", "SHOWERS", "THUNDER", "SLEET", "LIGHT RAIN",
           "HEAVY RAIN", "SNOW", "DUST", "FOG", "WINDY"]
# compact labels (<= 8 chars) for small tiles/bubbles
WEATHER_SHORT = ["--", "SUNNY", "CLOUDY", "OVERCAST", "SHOWERS", "STORM", "SLEET", "DRIZZLE",
                 "RAIN", "SNOW", "DUST", "FOG", "WINDY"]
BLUE = (100, 170, 255)


def flat_icon(c: Canvas, layers, x, y, size):
    for color, draw in layers:
        mask = Image.new("L", (int(size * SS), int(size * SS)), 0)
        draw(ImageDraw.Draw(mask), size * SS)
        c.im.paste(Image.new("RGB", mask.size, color), (int(x * SS), int(y * SS)), mask)


def weather_layers(code):
    cloud = lambda top=0.3: (lambda d, s: _cloud(d, s, top))
    return {
        0: [(DARK, lambda d, s: d.rectangle((0.3 * s, 0.46 * s, 0.7 * s, 0.54 * s), fill=255))],
        1: [(CORAL, lambda d, s: _sun(d, s))],
        2: [(CORAL, lambda d, s: _sun(d, s, 0.4, 0.38, 0.2, False)), (WHITE, cloud(0.42))],
        3: [(GRAY, cloud(0.3))],
        4: [(WHITE, cloud(0.2)), (BLUE, lambda d, s: _drops(d, s, 3))],
        5: [(WHITE, cloud(0.2)), (CORAL, lambda d, s: d.polygon(
            [(0.55 * s, 0.6 * s), (0.38 * s, 0.82 * s), (0.5 * s, 0.82 * s), (0.42 * s, 1.0 * s),
             (0.66 * s, 0.74 * s), (0.54 * s, 0.74 * s)], fill=255))],
        6: [(WHITE, cloud(0.2)), (BLUE, lambda d, s: _drops(d, s, 2)),
            (WHITE, lambda d, s: d.ellipse((0.41 * s, 0.74 * s, 0.59 * s, 0.92 * s), fill=255))],  # sleet: rain + snow
        7: [(WHITE, cloud(0.2)), (BLUE, lambda d, s: _drops(d, s, 2))],
        8: [(GRAY, cloud(0.2)), (BLUE, lambda d, s: _drops(d, s, 4))],
        9: [(WHITE, cloud(0.2)), (WHITE, lambda d, s: [d.ellipse(
            ((x - 0.05) * s, 0.8 * s, (x + 0.05) * s, 0.9 * s), fill=255) for x in (0.25, 0.5, 0.75)])],
        10: [(CORAL, lambda d, s: _lines(d, s))],
        11: [(GRAY, lambda d, s: _lines(d, s))],
        12: [(WHITE, lambda d, s: _lines(d, s, wavy=True))],
    }[code]


WX_BOX = (20, 156, 128, 200)        # icon element covers the card interior; label sits under temp


def weather_frames():
    x0, y0, x1, y1 = WX_BOX
    w, h = x1 - x0, y1 - y0

    def draw(code):
        def f(c):
            flat_icon(c, weather_layers(code), 2, 5, 36)
            ttext(c, WEATHER[code], 78, 43, 7.5, GRAY, anchor="ms", spacing=1.4)
        return f
    return [frame(w, h, draw(code)) for code in range(13)]


def temp_digits():
    return [frame(14, 24, lambda c, ch=ch: ttext(c, ch, 7, 22, 26, WHITE, anchor="ms"))
            for ch in "-./0123456789:"]


def degree():
    f = lambda c: arc(c, 4.5, 4.5, 3, 0, 360, WHITE, 1.4)
    return [frame(9, 9, f), frame(9, 9, f)]


# ---------------- small cards ----------------
def date_digits():
    return [frame(9, 16, lambda c, ch=ch: ttext(c, ch, 4.5, 14, 16, WHITE, anchor="ms"))
            for ch in "-./0123456789:"]


def hr_digits():
    return [frame(9, 16, lambda c, ch=ch: ttext(c, ch, 4.5, 14, 16, WHITE, anchor="ms"))
            for ch in "-./0123456789:"]


# ---------------- rings ----------------
RING_R, RING_W = 20, 4.5
RING_PCT_X0, RING_PCT_W = 53, 7       # type 33 exact battery %: 3-char field under the ring
MINI_CLOCK = True                     # False = dot-matrix variant: battery ring instead of the mini clock


def battery_ring():
    def draw(level):
        def f(c):
            cx, cy = 27, 23
            arc(c, cx, cy, RING_R, 0, 360, CARD, RING_W)
            if level:
                arc(c, cx, cy, RING_R, -90, -90 + 36 * level, RED if level <= 2 else WHITE, RING_W)
            rrect(c, (cx - 7, cy - 4, cx + 6, cy + 4), 1.5, outline=WHITE, width=1.4)
            c.d.rectangle(((cx + 6.5) * SS, (cy - 1.5) * SS, (cx + 8) * SS, (cy + 1.5) * SS), fill=WHITE)
            fill_w = 12 * level / 10
            if level:
                c.d.rectangle(((cx - 5.5) * SS, (cy - 2.5) * SS, (cx - 5.5 + fill_w) * SS, (cy + 2.5) * SS),
                              fill=RED if level <= 2 else WHITE)
            ttext(c, "%", RING_PCT_X0 - 40 + 3 * RING_PCT_W, 63, 10, WHITE, anchor="ls")   # number = type 33
        return f
    return [frame(54, 66, draw(lv)) for lv in range(11)]


def phone_glyph(c, cx, cy, color):
    c.d.line([((cx - 5) * SS, (cy - 6) * SS), ((cx - 6) * SS, (cy - 1) * SS),
              ((cx - 1) * SS, (cy + 5) * SS), ((cx + 5) * SS, (cy + 6) * SS)],
             fill=color, width=int(3 * SS), joint="curve")
    c.dot(cx - 5, cy - 6, 3.5, color)
    c.dot(cx + 5, cy + 6, 3.5, color)


def connection_ring():
    def draw(connected):
        def f(c):
            cx, cy = 38, 23
            arc(c, cx, cy, RING_R, 0, 360, MINT if connected else CARD, RING_W)
            phone_glyph(c, cx, cy, WHITE if connected else GRAY)
            ttext(c, "CONNECTED" if connected else "OFFLINE", cx, 63, 10, WHITE if connected else GRAY,
                  anchor="ms")
        return f
    return [frame(76, 66, draw(False)), frame(76, 66, draw(True))]


# ---------------- mini analog clock ----------------
CLOCK_X, CLOCK_Y = 67, 235          # pivot = ring centre


def hand(w: int, h: int, tip: int, color) -> tuple[Image.Image, dict]:
    """Upward-pointing hand on pure black (0x0000 = transparent on the watch).

    Record reserved bytes 21/22/23 = tip-to-pivot distance, image height, image width
    (firmware rotates the image about (w/2, tip) at runtime, see docs/hour12-patch-notes.md).
    """
    c = Canvas(w, h)
    c.im.paste((0, 0, 0), (0, 0, w * SS, h * SS))
    rrect(c, (0.4, 0.4, w - 0.4, h - 0.4), w / 2, fill=color)
    return c.image(), {"transparent": True, "reserved": bytes([0, 0, 0, 0, tip, h, w])}


def clock_face(c: Canvas):
    arc(c, CLOCK_X, CLOCK_Y, 21, 0, 360, CARD, 2.5)
    for k in range(12):
        a = math.radians(k * 30)
        r = 16.5
        c.dot(CLOCK_X + r * math.sin(a), CLOCK_Y - r * math.cos(a), 2.6 if k % 3 == 0 else 1.6,
              WHITE if k % 3 == 0 else GRAY)
    c.dot(CLOCK_X, CLOCK_Y, 4.5, CORAL)
    ttext(c, "LOCAL", CLOCK_X, 275, 9, GRAY, anchor="ms", spacing=1.2)


# ---------------- static background ----------------
def background() -> Image.Image:
    c = Canvas(W, H)
    c.dot(64, 26, 5, CORAL)                                         # accent dot after weekday
    c.d.line((172 * SS, 22 * SS, 172 * SS, 40 * SS), fill=CARD, width=int(1.2 * SS))
    rrect(c, (14, 150, 134, 206), 9, outline=CARD, width=1.6)       # weather card
    c.d.line((66 * SS, 160 * SS, 66 * SS, 196 * SS), fill=CARD, width=int(1.2 * SS))
    rrect(c, (142, 150, 226, 175), 7, outline=CARD, width=1.6)      # date card
    rrect(c, (142, 181, 226, 206), 7, outline=CARD, width=1.6)      # heart card
    # calendar glyph
    rrect(c, (149, 155, 163, 169), 2, outline=WHITE, width=1.3)
    for i in range(3):
        c.dot(152.5 + i * 3.5, 163, 1.8, CORAL)
    # heart glyph
    hx, hy = 149, 188
    c.d.ellipse((hx * SS, hy * SS, (hx + 8) * SS, (hy + 8) * SS), fill=CORAL)
    c.d.ellipse(((hx + 6) * SS, hy * SS, (hx + 14) * SS, (hy + 8) * SS), fill=CORAL)
    c.d.polygon([(hx * SS, (hy + 5) * SS), ((hx + 14) * SS, (hy + 5) * SS), ((hx + 7) * SS, (hy + 14) * SS)],
                fill=CORAL)
    ttext(c, "BPM", 200, 199, 8, GRAY, anchor="ls", spacing=0.8)
    c.d.line((120 * SS, 222 * SS, 120 * SS, 262 * SS), fill=CARD, width=int(1.2 * SS))
    if MINI_CLOCK:
        clock_face(c)
    return c.image()


def layout():
    big = big_digits()
    dd = date_digits()
    hr = hr_digits()
    hr_img, hr_opt = hand(4, 13, 11, WHITE)
    mn_img, mn_opt = hand(4, 18, 16, CORAL)
    return [
        (17, 0, 0, [background()]),
        (15, 16, 18, weekday()),
        (9, 146, 21, bt_icon()),
        (8, 180, 20, battery_pill()),
        (57, 26, TIME_Y, big), (58, 68, TIME_Y, big),
        (7, 111, TIME_Y, colon()),
        (59, 128, TIME_Y, big), (60, 170, TIME_Y, big),
        (16, 196, 124, ampm()),
        (20, WX_BOX[0], WX_BOX[1], weather_frames()),
        (21, 76, 158, temp_digits()),                 # firmware: char k at x + ((3-n)w>>1) + k*w
        (22, 113, 158, degree()),
        # date card: day.month
        (65, 172, 154, dd), (66, 181, 154, dd),
        (14, 190, 154, [frame(5, 16, lambda c: ttext(c, ".", 2.5, 14, 16, WHITE, anchor="ms"))]),
        (63, 195, 154, dd), (64, 204, 154, dd),
        # heart rate (hundreds/tens/units)
        (35, 168, 185, hr), (36, 177, 185, hr), (37, 186, 185, hr),
        (9, 144, 212, connection_ring()),
    ] + ([  # bottom-left: mini analog clock (hands rotated by the watch) …
        (1, CLOCK_X, CLOCK_Y, [hr_img], hr_opt),
        (2, CLOCK_X, CLOCK_Y, [mn_img], mn_opt),
    ] if MINI_CLOCK else [  # … or battery ring with the exact percentage
        (8, 40, 212, battery_ring()),
        (33, RING_PCT_X0, 265, [frame(RING_PCT_W, 12, lambda c, ch=ch: ttext(c, ch, RING_PCT_W / 2, 10, 10, WHITE,
                                                                             anchor="ms")) for ch in "-./0123456789:"]),
    ])


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2", 33: "85"}
