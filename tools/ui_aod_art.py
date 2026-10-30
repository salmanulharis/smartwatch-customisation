"""Always-on display art (UI pack rev 12): dot-matrix digits and small outline icons.

Imported by tools/ui_feature_art.py (names "m_aod_*", appended after the quick-panel set).
Layout and logic live in firmware/s100_ext/ext.c (dock style 1 = always-on).
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

SS = 4
BLACK = (0, 0, 0)
WHITE = (238, 238, 238)
ORANGE = (255, 90, 30)
GREY = (120, 120, 124)
DIM = (150, 150, 154)

# 4 x 6 dot font (round dots), as in the owner's reference
DOT46 = {
    "0": [".##.", "#..#", "#..#", "#..#", "#..#", ".##."],
    "1": ["..#.", ".##.", "..#.", "..#.", "..#.", "..#."],
    "2": [".##.", "#..#", "..##", ".#..", "#...", "####"],
    "3": ["###.", "...#", ".##.", "...#", "...#", "###."],
    "4": ["#..#", "#..#", "####", "...#", "...#", "...#"],
    "5": ["####", "#...", "###.", "...#", "#..#", ".##."],
    "6": [".##.", "#...", "###.", "#..#", "#..#", ".##."],
    "7": ["####", "...#", "..#.", ".#..", ".#..", ".#.."],
    "8": [".##.", "#..#", ".##.", "#..#", "#..#", ".##."],
    "9": [".##.", "#..#", "#..#", ".###", "...#", ".##."],
}
DW, DH, PITCH, DOT = 40, 60, 10, 8.4


def dots(rows, colour):
    def make():
        im = Image.new("RGB", (DW * SS, DH * SS), BLACK)
        d = ImageDraw.Draw(im)
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch == "#":
                    cx, cy = (i + 0.5) * PITCH, (j + 0.5) * PITCH
                    d.ellipse([(cx - DOT / 2) * SS, (cy - DOT / 2) * SS, (cx + DOT / 2) * SS, (cy + DOT / 2) * SS],
                              fill=colour)
        return im.resize((DW, DH), Image.LANCZOS)
    return make


class C:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w * SS, h * SS), BLACK)
        self.d = ImageDraw.Draw(self.im)

    def arc(self, x, y, r, a0, a1, w, col=WHITE):
        self.d.arc([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], a0, a1, fill=col, width=int(w * SS))

    def line(self, pts, w, col=WHITE):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=col, width=int(w * SS))

    def rr(self, x0, y0, x1, y1, r, outline=None, fill=None, w=1.6):
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, outline=outline, fill=fill,
                                 width=int(w * SS))

    def image(self):
        return self.im.resize((self.w, self.h), Image.LANCZOS)


ART = {}
for k in range(10):
    ART[f"m_aod_a_w{k}"] = dots(DOT46[str(k)], WHITE)
    ART[f"m_aod_b_o{k}"] = dots(DOT46[str(k)], ORANGE)
# (rev-12 colon / icons / battery m_aod_c..g dropped in rev 15, replaced by the o_aod_* set)


def ws_row():                                         # watch-settings row: 224 x 40 slate pill
    im = Image.new("RGB", (224 * SS, 40 * SS), BLACK)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, 224 * SS - 1, 40 * SS - 1], radius=14 * SS, fill=(30, 32, 37))
    return im.resize((224, 40), Image.LANCZOS)


ART["n_ws_row"] = ws_row


# ---- rev 14: always-on display redone after the owner's reference (small letter-spaced labels,
# outline icons at reference size). Names start with "o_" so they append after every earlier image
# and no existing address moves.
from PIL import ImageFont

FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
LABEL = (232, 232, 232)
LGREY = (138, 138, 142)
SMALL = "-./0123456789:"                              # type-5 digit frame order
SW, SH = 8, 14                                        # small digit frame (cap height 10)


def text_img(s, colour, w, h, size=13.5, spacing=0.0, align="left"):
    """Render text at 4x and downsample (crisp, centred vertically in h)."""
    def make():
        f = ImageFont.truetype(FONT, int(size * SS))
        widths = [f.getlength(ch) for ch in s]
        total = sum(widths) + spacing * SS * (len(s) - 1)
        im = Image.new("RGB", (w * SS, h * SS), BLACK)
        d = ImageDraw.Draw(im)
        asc = f.getbbox("0")                           # digit/cap box: centre the caps
        y = (h * SS - (asc[3] - asc[1])) / 2 - asc[1]
        x = {"left": 0, "center": (w * SS - total) / 2, "right": w * SS - total}[align]
        for ch, cw in zip(s, widths):
            d.text((x, y), ch, font=f, fill=colour)
            x += cw + spacing * SS
        return im.resize((w, h), Image.LANCZOS)
    return make


def word_width(s, size=13.5, spacing=0.0):
    f = ImageFont.truetype(FONT, int(size * SS))
    return (sum(f.getlength(ch) for ch in s) + spacing * SS * (len(s) - 1)) / SS


def icon_s(draw_fn, w, h):
    def make():
        c = C(w, h); draw_fn(c); return c.image()
    return make


def s_cloud(c, col=LABEL):
    c.arc(6, 9.5, 3.6, 90, 270, 1.4, col)
    c.arc(10, 6.5, 4.4, 190, 340, 1.4, col)
    c.arc(14, 9, 3.4, 270, 90, 1.4, col)
    c.line([(6, 13.1), (14, 13.1)], 1.4, col)


def s_sun(c):
    c.arc(10, 8, 3.6, 0, 360, 1.4, LABEL)
    for k in range(8):
        a = math.radians(k * 45)
        c.line([(10 + 5.6 * math.cos(a), 8 + 5.6 * math.sin(a)), (10 + 7.4 * math.cos(a), 8 + 7.4 * math.sin(a))], 1.3, LABEL)


def s_moon(c):
    c.arc(9, 8, 5.6, 60, 300, 1.4, LABEL)
    c.arc(12.6, 5.6, 4.6, 95, 205, 1.4, LABEL)


def s_rain(c):
    c.d.rectangle([0, 0, c.w * SS, c.h * SS], fill=BLACK)
    c.arc(6, 7.5, 3.4, 90, 270, 1.3, LABEL)
    c.arc(10, 4.8, 4.0, 190, 340, 1.3, LABEL)
    c.arc(14, 7, 3.2, 270, 90, 1.3, LABEL)
    c.line([(6, 10.9), (14, 10.9)], 1.3, LABEL)
    for x in (7.5, 10.5, 13.5):
        c.line([(x, 12.6), (x - 1, 15)], 1.1, LGREY)


def s_battery(level):
    def f(c):
        c.rr(0.8, 0.8, 18.2, 10.2, 2.2, outline=LABEL, w=1.3)
        c.rr(19, 3.4, 20.6, 7.6, 0.8, fill=LABEL)
        if level:
            c.rr(2.8, 2.8, 2.8 + 13.4 * level / 4, 8.2, 0.8, fill=LABEL)
    return f


def s_steps(c):
    for (x, y) in ((4.6, 5.6), (9.6, 8.4)):
        c.d.ellipse([(x - 2.1) * SS, (y - 3.6) * SS, (x + 2.1) * SS, (y + 2.6) * SS], fill=LGREY)
        c.d.ellipse([(x - 1.5) * SS, (y + 3.4) * SS, (x + 1.5) * SS, (y + 5.4) * SS], fill=LGREY)


def s_divider(c):
    c.line([(0.5, 0), (0.5, 18)], 1.0, (64, 64, 68))


def s_colon(c):
    for cy in (4.5, 20.5):
        c.d.ellipse([(5 - 4.2) * SS, (cy - 4.2) * SS, (5 + 4.2) * SS, (cy + 4.2) * SS], fill=(110, 110, 114))


WEEKDAY_NAMES = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
MONTH_NAMES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
WD_W, MO_W, WORD_H = 40, 30, 14                      # letter-spaced weekday / month word images

for k, n in enumerate(WEEKDAY_NAMES):
    ART[f"o_aod_a_day{k}"] = text_img(n, LABEL, WD_W, WORD_H, size=13.5, spacing=4.2)
for k, n in enumerate(MONTH_NAMES):
    ART[f"o_aod_b_mon{k:02d}"] = text_img(n, LGREY, MO_W, WORD_H, size=13.5, spacing=1.2)
for k, ch in enumerate(SMALL):
    ART[f"o_aod_c_sw{k:02d}"] = text_img(ch, LABEL, SW, SH, align="center")
    ART[f"o_aod_d_sg{k:02d}"] = text_img(ch, LGREY, SW, SH, align="center")
ART.update({
    "o_aod_e_pct": text_img("%", LABEL, 11, SH, align="left"),
    "o_aod_e_deg": text_img("\u00b0", LABEL, 6, SH, align="left"),
    "o_aod_f_wx0": icon_s(s_sun, 20, 16), "o_aod_f_wx1": icon_s(s_moon, 20, 16),
    "o_aod_f_wx2": icon_s(lambda c: s_cloud(c), 20, 16), "o_aod_f_wx3": icon_s(s_rain, 20, 16),
    "o_aod_g_steps": icon_s(s_steps, 14, 16), "o_aod_g_div": icon_s(s_divider, 1, 18),
    "o_aod_h_colon": icon_s(s_colon, 10, 26),
})
ART.update({f"o_aod_i_bat{k}": icon_s(s_battery(k), 21, 11) for k in range(5)})
