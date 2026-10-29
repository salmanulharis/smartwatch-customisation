"""Duo face (light theme): hour on a dark pill, minutes on a coral circle.

Every element frame is drawn on a crop of the background, so live parts sit seamlessly on
whatever shape is underneath (dark pill, coral circle, cream).
"""
from __future__ import annotations

from PIL import Image

from dial_nothing import SMALL, MINT, SS, Canvas, battery_dots
from dial_widgets import ttext, rrect, arc, flat_icon, weather_layers, WEATHER

W, H = 240, 280
DIGITS = "-./0123456789:"
CREAM = (233, 231, 225)
INK = (30, 30, 30)
SOFT = (125, 123, 118)
PILL = (36, 36, 36)
CORAL = (240, 88, 52)
OVERLAP = (122, 46, 30)
BUBBLE = (216, 214, 208)
DOT_WHITE = (242, 240, 235)
UNLIT = (190, 188, 182)

PILL_BOX = (34, 77, 120, 203)
CIRCLE = (159, 143, 52)            # cx, cy, r


def _background_hi() -> Canvas:
    c = Canvas(W, H)
    c.d.rectangle((0, 0, W * SS, H * SS), fill=CREAM)
    x0, y0, x1, y1 = PILL_BOX
    rrect(c, PILL_BOX, (x1 - x0) / 2, fill=PILL, width=0)
    cx, cy, r = CIRCLE
    c.d.ellipse(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=CORAL)
    # overlap of pill and circle, darker
    m1 = Image.new("L", c.im.size, 0)
    m2 = Image.new("L", c.im.size, 0)
    from PIL import ImageDraw
    ImageDraw.Draw(m1).rounded_rectangle([v * SS for v in PILL_BOX], radius=(x1 - x0) / 2 * SS, fill=255)
    ImageDraw.Draw(m2).ellipse(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=255)
    from PIL import ImageChops
    c.im.paste(Image.new("RGB", c.im.size, OVERLAP), (0, 0), ImageChops.multiply(m1, m2))
    c.dot(21, 141, 9, CORAL)                                  # side dots
    c.dot(220, 143, 9, INK)
    c.dot(60, 42, 7, CORAL)                                   # accent after weekday
    rrect(c, (124, 30, 229, 54), 12, outline=(170, 168, 162), width=1.2)   # status pill
    c.d.line((166 * SS, 36 * SS, 166 * SS, 48 * SS), fill=(170, 168, 162), width=int(1 * SS))
    c.d.line((120 * SS, 214 * SS, 120 * SS, 252 * SS), fill=(190, 188, 182), width=int(1 * SS))
    # dot-matrix heart
    heart = [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."]
    for j, row in enumerate(heart):
        for i, ch in enumerate(row):
            c.dot(137 + i * 3.4, 222 + j * 3.4, 2.6, CORAL if ch == "#" else UNLIT)
    ttext(c, "BPM", 196, 236, 9, SOFT, anchor="ls", spacing=0.6)
    ttext(c, "Heart rate", 167, 248, 8.5, SOFT, anchor="ls")
    return c


BG_HI = _background_hi()


def on_bg(x: int, y: int, w: int, h: int, draw) -> Image.Image:
    """Frame whose base is the background crop at (x, y)."""
    c = Canvas(w, h)
    c.im.paste(BG_HI.im.crop((x * SS, y * SS, (x + w) * SS, (y + h) * SS)), (0, 0))
    draw(c)
    return c.image()


def background() -> Image.Image:
    return BG_HI.image()


# ---- elements ----
TIME_FONT = dict(SMALL)
TIME_FONT["0"] = [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."]   # plain, no slash
TIME_FONT["1"] = ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "..#.."]   # no base bar


def time_digits(x, y, w=32, h=45, color=DOT_WHITE):
    """Chunky 5x7 dot digits like the design (pitch 6.2, dot 5.0)."""
    return [on_bg(x, y, w, h, lambda c, ch=ch: c.glyph(TIME_FONT[ch], 0.5, 0.5, 6.2, 5.0, color))
            for ch in DIGITS]


def text_digits(x, y, w, h, size, color):
    return [on_bg(x, y, w, h, lambda c, ch=ch: ttext(c, ch, w / 2, h - 2, size, color, anchor="ms"))
            for ch in DIGITS]


def weekday(x, y):
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    return [on_bg(x, y, 40, 18, lambda c, n=n: ttext(c, n, 0, 16, 17, INK, anchor="ls")) for n in names * 2]


def ampm(x, y):
    def draw(t):
        def f(c):
            c.dot(15, 15, 30, BUBBLE)
            ttext(c, t, 15, 20, 12, SOFT, anchor="ms")
        return f
    return [on_bg(x, y, 30, 30, draw(t)) for t in ("AM", "PM", "AM", "PM")]


def bt(x, y):
    def draw(on):
        def f(c):
            pts = [(3, 4), (10, 10), (6, 14), (6, 0), (10, 4), (3, 10)]
            c.d.line([(px * SS, (py + 1) * SS) for px, py in pts], fill=INK, width=int(1.4 * SS), joint="curve")
            c.dot(19, 8, 6, MINT if on else UNLIT)
        return f
    return [on_bg(x, y, 26, 16, draw(on)) for on in (False, True)]


def battery(x, y):
    """11 frames (firmware: ceil(%/10)); 4 dots inside a pill."""
    def draw(level):
        lit = battery_dots(level, 4)

        def f(c):
            rrect(c, (1, 2, 41, 14), 4, outline=INK, width=1.4)
            c.d.rectangle((42 * SS, 6 * SS, 44 * SS, 10 * SS), fill=INK)
            for i in range(4):
                c.dot(8 + i * 8.6, 8, 6, CORAL if i < lit else UNLIT)
        return f
    return [on_bg(x, y, 46, 16, draw(lv)) for lv in range(11)]


def light_layers(code):
    remap = {(245, 245, 245): (150, 148, 142), (150, 150, 150): (135, 133, 128), (55, 55, 55): UNLIT}
    return [(remap.get(col, col), fn) for col, fn in weather_layers(code)]


WX = (16, 212, 112, 250)


def weather(x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0

    def draw(code):
        def f(c):
            flat_icon(c, light_layers(code), 2, 3, 32)
            ttext(c, WEATHER[code], 47, h - 2, 6.5, SOFT, anchor="ls", spacing=1.4)
        return f
    return [on_bg(x0, y0, w, h, draw(code)) for code in range(13)]


def degree(x, y):
    f = lambda c: arc(c, 4, 4, 2.6, 0, 360, INK, 1.3)
    return [on_bg(x, y, 8, 8, f), on_bg(x, y, 8, 8, f)]


def layout():
    date = lambda x: text_digits(x, 52, 8, 14, 12, SOFT)
    hrd = lambda x: text_digits(x, 219, 11, 19, 18, INK)
    tmp = lambda x: text_digits(x, 213, 12, 21, 22, INK)
    return [
        (17, 0, 0, [background()]),
        (15, 18, 31, weekday(18, 31)),
        (65, 19, 52, date(19)), (66, 27, 52, date(27)),
        (14, 35, 52, [on_bg(35, 52, 5, 14, lambda c: ttext(c, ".", 2.5, 12, 12, SOFT, anchor="ms"))]),
        (63, 40, 52, date(40)), (64, 48, 52, date(48)),
        (9, 136, 35, bt(136, 35)),
        (8, 172, 34, battery(172, 34)),
        (57, 42, 118, time_digits(42, 118)), (58, 78, 118, time_digits(78, 118)),
        (59, 125, 120, time_digits(125, 120)), (60, 161, 120, time_digits(161, 120)),
        (16, 198, 95, ampm(198, 95)),
        (20, WX[0], WX[1], weather(*WX)),
        (21, 58, 213, tmp(58)),                    # firmware: char k at x + ((3-n)w>>1) + k*w
        (22, 89, 214, degree(89, 214)),
        (35, 166, 219, hrd(166)), (36, 175, 219, hrd(175)), (37, 184, 219, hrd(184)),
    ]


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          35: "", 36: "7", 37: "2"}
