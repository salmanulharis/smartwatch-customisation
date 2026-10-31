"""'One Dot': the dot-matrix ("Nothing"-style) face refined, for tools/s100_dial.py.

Same identity as dial_nothing (round dots, black, white / grey) with one red dot as the signature: the
time's colon. Single-stroke 5x9 dot digits, centred; a quiet header (weekday + date left, Bluetooth dot
and AM/PM right); a full-width dot line for the step goal; weather and steps under tiny dot labels;
battery as ten dots along the bottom. 24 sprites (the watch draws at most 34 per frame).
"""
from __future__ import annotations

from dial_nothing import SMALL, Canvas, frame, text_width, battery_dots, weather_icon_frames

W, H = 240, 280
BG = (8, 8, 8)
WHITE = (242, 242, 242)
GREY = (128, 128, 132)
DARK = (44, 44, 46)
RED = (235, 34, 40)

# single-stroke 5 x 9 digits (frame order "-./0123456789:")
DIGITS = {
    "0": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "1": ["..#..", ".##..", "#.#..", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "2": [".###.", "#...#", "....#", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "3": [".###.", "#...#", "....#", "....#", "..##.", "....#", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#..#.", "#####", "...#.", "...#.", "...#."],
    "5": ["#####", "#....", "#....", "####.", "....#", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", "#...#", ".###.", "#...#", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", "#...#", ".####", "....#", "....#", "...#.", ".##.."],
    "-": ["....."] * 4 + [".###."] + ["....."] * 4,
    ".": ["....."] * 8 + ["..#.."],
    "/": ["....#", "....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#....", "#...."],
    ":": ["....."] * 9,
}
ORDER = "-./0123456789:"

BIG_P, BIG_DOT = 8.4, 6.3                 # time
BIG_W, BIG_H = 42, 76
SM_P, SM_DOT = 2.2, 1.75                  # header text
LB_P, LB_DOT = 1.6, 1.25                  # tiny labels
VAL_P, VAL_DOT = 2.7, 2.15                # weather / steps values

# time row: four digits 42 wide, 6 apart, a 20 px slot for the red dot in the middle (centre x 120)
TIME_Y = 68
TIME_X = (20, 68, 130, 178)
COLON_X = 110
HEAD_Y = 24
GOAL_Y = 170
LABEL_Y = 190
VALUE_Y = 214
BATT_Y = 248


def _glyph(c, rows, x, y, p, d, col):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "#":
                c.dot(x + (i + 0.5) * p, y + (j + 0.5) * p, d, col)


def _text(c, s, x, y, p, d, col):
    for k, ch in enumerate(s):
        _glyph(c, SMALL[ch], x + k * 6 * p, y, p, d, col)


def time_digits():
    return [frame(BIG_W, BIG_H, lambda c, ch=ch: _glyph(c, DIGITS[ch], 0, 0, BIG_P, BIG_DOT, WHITE)) for ch in ORDER]


def one_dot():                            # the colon: a single red dot, centred on the digits
    return [frame(20, BIG_H, lambda c: c.dot(10, BIG_H / 2, 9.0, RED))]


def small_digits(col, p=SM_P, d=SM_DOT):
    w, h = int(6 * p), int(7 * p) + 1
    return [frame(w, h, lambda c, ch=ch: _glyph(c, SMALL[ch], 0.5, 0.5, p, d, col)) for ch in ORDER]


def weekday():
    names = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
    w = int(text_width("WED", SM_P)) + 2
    return [frame(w, 17, lambda c, n=n: _text(c, n, 0.5, 0.5, SM_P, SM_DOT, WHITE)) for n in names * 2]


def ampm():
    w = int(text_width("AM", SM_P)) + 2
    return [frame(w, 17, lambda c, t=t: _text(c, t, 0.5, 0.5, SM_P, SM_DOT, GREY)) for t in ("AM", "PM", "AM", "PM")]


def bt():                                 # 0 = off (dark), 1 = connected (white)
    return [frame(10, 10, lambda c: c.dot(5, 5, 6, DARK)), frame(10, 10, lambda c: c.dot(5, 5, 6, WHITE))]


GOAL_N, GOAL_PITCH = 21, 9.8


def step_goal():                          # frame k = k tenths of the goal: a line of dots fills left to right
    def draw(k):
        lit = round(k * GOAL_N / 10)
        return lambda c: [c.dot(3 + i * GOAL_PITCH, 3, 3.6, WHITE if i < lit else DARK) for i in range(GOAL_N)]
    return [frame(int(6 + (GOAL_N - 1) * GOAL_PITCH), 7, draw(k)) for k in range(11)]


def battery():                            # frame = ceil(%/10): that many of 10 dots lit, red at 20 % or less
    def draw(level):
        lit = battery_dots(level, 10)
        on = RED if level <= 2 else WHITE
        return lambda c: [c.dot(4 + i * 10, 4, 5.2, on if i < lit else DARK) for i in range(10)]
    return [frame(98, 9, draw(level)) for level in range(11)]


def degree():
    return [frame(9, 9, lambda c: [c.dot(4.5 + 2.6 * __import__("math").cos(k * 0.785), 4.5 + 2.6 *
                                         __import__("math").sin(k * 0.785), 1.3, WHITE) for k in range(8)])] * 2


def background():
    c = Canvas(W, H)
    _text(c, "WEATHER", 20, LABEL_Y, LB_P, LB_DOT, GREY)
    _text(c, "STEPS", 132, LABEL_Y, LB_P, LB_DOT, GREY)
    return c.image()


def layout():
    sd_head = small_digits(GREY)
    val = small_digits(WHITE, VAL_P, VAL_DOT)
    wk = weekday()
    am = ampm()
    dx = 20 + wk[0].size[0] + 8                          # date after the weekday
    sw = sd_head[0].size[0]
    vw = val[0].size[0]
    gw = step_goal()[0].size[0]
    els = [
        (17, 0, 0, [background()]),
        (15, 20, HEAD_Y, wk),
        (65, dx, HEAD_Y, sd_head), (66, dx + sw, HEAD_Y, sd_head),
        (14, dx + 2 * sw, HEAD_Y, [frame(sw - 4, 17, lambda c: _glyph(c, SMALL["."], -1, 0.5, SM_P, SM_DOT, GREY))]),
        (63, dx + 3 * sw - 4, HEAD_Y, sd_head), (64, dx + 4 * sw - 4, HEAD_Y, sd_head),
        (9, W - 20 - 10, HEAD_Y + 3, bt()),
        (16, W - 20 - 10 - 6 - am[0].size[0], HEAD_Y, am),
        (57, TIME_X[0], TIME_Y, time_digits()), (58, TIME_X[1], TIME_Y, time_digits()),
        (7, COLON_X, TIME_Y, one_dot()),
        (59, TIME_X[2], TIME_Y, time_digits()), (60, TIME_X[3], TIME_Y, time_digits()),
        (32, (W - gw) // 2, GOAL_Y, step_goal()),
        (20, 18, VALUE_Y - 8, weather_icon_frames()),
        # temperature: the firmware centres up to 3 chars on this element (char k at x + ((3-n)w>>1) + k w)
        (21, 58, VALUE_Y, val), (22, 58 + int(2.5 * vw) + 2, VALUE_Y - 1, degree()),
        (38, 132, VALUE_Y, val), (39, 132 + vw, VALUE_Y, val), (40, 132 + 2 * vw, VALUE_Y, val),
        (41, 132 + 3 * vw, VALUE_Y, val), (42, 132 + 4 * vw, VALUE_Y, val),
        (8, (W - 98) // 2, BATT_Y, battery()),
    ]
    return els


SAMPLE = {57: "1", 58: "0", 59: "4", 60: "5", 65: "2", 66: "9", 63: "1", 64: "0",
          38: "0", 39: "6", 40: "8", 41: "4", 42: "2", 21: "29"}
