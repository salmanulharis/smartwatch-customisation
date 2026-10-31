"""Art for the S100 feature screens (appended to the UI pack; docs/ui-upgrade-plan.md §12.7).

    python tools/ui_feature_art.py [-o research/ui/feature_append]
    python tools/s100_ui.py build research/ui/replace --append research/ui/feature_append --version N

Writes PNGs named so that sorted order = append order (the firmware build reads their addresses
from the pack's .append.json): quick-panel tiles (64x64, same look as the stock tiles IMG888-894)
and navigation arrows (96x96, white on black, black = transparent).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ui_cmf import CHIP, ORANGE, WHITE, Icon

BLUE = (40, 130, 255)
GREEN = (40, 220, 110)
GREEN_DIM = (22, 70, 40)
PURPLE = (125, 95, 255)
FONT = "C:/Windows/Fonts/bahnschrift.ttf"
SS = 4

ROOT = Path(__file__).resolve().parent.parent


class Bare(Icon):
    """Icon canvas without the grey disc (for arrows)."""

    def __init__(self, size):
        super().__init__(size)
        self.d.rectangle((0, 0, *self.im.size), fill=(0, 0, 0))


def tile(fn, on=False):
    """Rounded-square quick-panel tile (same shape as tools/ui_v9_art.tile)."""
    def make():
        c = Icon(64)
        c.d.rectangle((0, 0, *c.im.size), fill=(0, 0, 0))
        c.rect(0.75, 0.75, 47.25, 47.25, 12.75, ORANGE if on else CHIP)
        fn(c, on)
        return c.image()
    return make


def aod(c, on):
    ink = WHITE
    c.rect(15, 11, 33, 37, 5, ink)                  # watch body
    c.rect(18, 15, 30, 33, 2.5, ORANGE if not on else (60, 20, 5))
    c.rect(19, 6, 29, 11, 1.5, ink)                 # straps
    c.rect(19, 37, 29, 42, 1.5, ink)
    c.stroke([(21, 24), (24, 24), (24, 19)], 2, ink if not on else WHITE)


def find_phone(c, on):
    c.rect(17, 9, 31, 39, 3.5, WHITE)
    c.rect(19.5, 13, 28.5, 33, 1.5, CHIP)
    c.circle(24, 36, 1.4, CHIP)
    for r in (8, 12):
        c.arc(24, 23, r + 10, -40, 40, 2, ORANGE)


def watch_settings(c, on):
    import math as m
    pts = []
    for k in range(24):
        a = m.radians(k * 15 - 7.5)
        rr = 13 if k % 3 else 10.5
        pts.append((24 + rr * m.sin(a), 24 - rr * m.cos(a)))
    c.poly(pts, WHITE)
    c.circle(24, 24, 5.5, CHIP)
    c.rect(20.5, 21, 27.5, 27, 1.2, ORANGE)


def desk_clock(c, on):
    c.circle(24, 24, 14, WHITE)
    c.circle(24, 24, 11.5, CHIP)
    c.stroke([(24, 24), (24, 16)], 2.4, WHITE)
    c.stroke([(24, 24), (30, 27)], 2.4, ORANGE)
    c.rect(16, 38, 32, 41, 1.5, WHITE)              # stand


# ---- navigation arrows (96 px, 48-unit grid) ----
def arrow_head(c, x, y, ang, size=9.5, col=WHITE):
    a = math.radians(ang)
    tip = (x + size * math.cos(a), y + size * math.sin(a))
    l = (x + size * 0.9 * math.cos(a + 2.4), y + size * 0.9 * math.sin(a + 2.4))
    r = (x + size * 0.9 * math.cos(a - 2.4), y + size * 0.9 * math.sin(a - 2.4))
    c.poly([tip, l, r], col)


NAV = BLUE          # arrow colour (mockup: blue)


def straight(c):
    c.stroke([(24, 42), (24, 12)], 6, NAV)
    arrow_head(c, 24, 10, -90, col=NAV)


def turn(sign):                           # one stroke with a rounded corner (no seam at the bend)
    def f(c):
        c.stroke([(24 - sign * 6, 42), (24 - sign * 6, 20), (24 + sign * 10, 20)], 6, NAV)
        arrow_head(c, 24 + sign * 12, 20, 0 if sign > 0 else 180, col=NAV)
    return f


def slight(sign):
    def f(c):
        c.stroke([(22 - sign * 2, 42), (22 - sign * 2, 28), (30 * (sign > 0) + 14 * (sign < 0), 14)], 6, NAV)
        ang = -55 if sign > 0 else -125
        x, y = (30 * (sign > 0) + 14 * (sign < 0), 14)
        arrow_head(c, x + 2 * math.cos(math.radians(ang)), y + 2 * math.sin(math.radians(ang)), ang, col=NAV)
    return f


def uturn(c):
    c.stroke([(30, 42), (30, 22)], 6, NAV)
    c.arc(23, 22, 7, 180, 360, 6, NAV)
    c.stroke([(16, 22), (16, 30)], 6, NAV)
    arrow_head(c, 16, 33, 90, col=NAV)


def arrive(c):
    c.circle(24, 20, 11, ORANGE)
    c.circle(24, 20, 4.5, (0, 0, 0))
    c.poly([(15, 26), (33, 26), (24, 42)], ORANGE)
    c.circle(24, 20, 4.5, (0, 0, 0))


def roundabout(c):
    c.arc(24, 22, 9, 0, 360, 4.5, NAV)
    c.stroke([(24, 42), (24, 31)], 6, NAV)
    c.stroke([(31, 16), (38, 9)], 6, NAV)
    arrow_head(c, 39, 8, -45, col=NAV)


# ---- dock / AOD digits: 11 glyphs "0-9" and "." per set (C draws them with add_image)
GLYPHS = "0123456789."
DIG_W, DIG_H = 56, 84


def digit(ch: str, colour, style: str):
    def make():
        big = Image.new("RGB", (DIG_W * SS, DIG_H * SS))
        d = ImageDraw.Draw(big)
        f = ImageFont.truetype(FONT, int(DIG_H * SS * 1.18))
        f.set_variation_by_name("Bold" if style == "bold" else "Light")
        x0, y0, x1, y1 = d.textbbox((0, 0), "0", font=f)
        bx0, _, bx1, _ = d.textbbox((0, 0), ch, font=f)
        d.text(((DIG_W * SS - (bx1 - bx0)) / 2 - bx0, (DIG_H * SS - (y1 - y0)) / 2 - y0), ch, font=f, fill=colour)
        return big.resize((DIG_W, DIG_H), Image.LANCZOS)
    return make


# ---- charging face: 11 ring frames (battery 0..100 % in 10 % steps)
RING = 196


def ring(level: int):
    """Charging ring (rev 16): 196 px, 14 px stroke, green arc from the top over a dark track, round
    caps; 5 colours, which encodes smaller than the 176 px / 8-colour set it replaces."""
    def make():
        big = Image.new("RGB", (RING * SS, RING * SS))
        d = ImageDraw.Draw(big)
        w = 14 * SS
        box = (w // 2, w // 2, RING * SS - w // 2, RING * SS - w // 2)
        d.arc(box, 0, 360, fill=(20, 62, 36), width=w)
        if level:
            d.arc(box, -90, -90 + 36 * level, fill=GREEN, width=w)
            for a in (-90, -90 + 36 * level):           # round caps
                r = (RING * SS - w) / 2
                cx = RING * SS / 2 + r * math.cos(math.radians(a)); cy = RING * SS / 2 + r * math.sin(math.radians(a))
                d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=GREEN)
        return big.resize((RING, RING), Image.LANCZOS).quantize(palette=RING_PAL, dither=Image.Dither.NONE).convert("RGB")
    return make


def _ring_palette():                      # one fixed palette for every frame (consistent colours)
    track = (20, 62, 36)
    cols = [(0, 0, 0), track, GREEN, tuple((a + b) // 2 for a, b in zip((0, 0, 0), track)),
            tuple((a + b) // 2 for a, b in zip(track, GREEN))]
    pal = Image.new("P", (1, 1))
    pal.putpalette([v for c in cols for v in c] + [0] * (768 - 3 * len(cols)))
    return pal


RING_PAL = _ring_palette()


def small(fn, size):
    def make():
        c = Bare(size)
        fn(c)
        return c.image()
    return make


def bolt(c, col=GREEN):
    c.poly([(27, 4), (13, 27), (23, 27), (20, 44), (35, 19), (25, 19), (29, 4)], col)


def sun(c):
    c.circle(24, 24, 10, ORANGE)
    for k in range(8):
        a = math.radians(k * 45)
        c.stroke([(24 + 15 * math.cos(a), 24 + 15 * math.sin(a)), (24 + 20 * math.cos(a), 24 + 20 * math.sin(a))], 3, ORANGE)


def moon(c):
    c.circle(24, 24, 17, (210, 210, 210))
    c.circle(33, 16, 15, (0, 0, 0))


def cloud(c, col=(230, 230, 230)):
    c.circle(18, 28, 9, col); c.circle(28, 22, 12, col); c.circle(36, 30, 7, col)
    c.rect(9, 28, 43, 37, 4, col)


def rain(c):
    cloud(c)
    for x in (16, 25, 34):
        c.stroke([(x, 40), (x - 3, 46)], 2.5, BLUE)


def battery(c):
    c.rect(6, 15, 38, 33, 3, (0, 0, 0))
    c.d.rounded_rectangle([v * c.k for v in (6, 15, 38, 33)], radius=3 * c.k, outline=WHITE, width=int(2.5 * c.k))
    c.rect(39, 20, 43, 28, 1, WHITE)
    c.rect(10, 19, 34, 29, 1.5, WHITE)


def bare(fn, size=96, colours=None):
    def make():
        c = Bare(size)
        fn(c)
        im = c.image()
        if colours:                       # few colours: much shorter RLE (the pack is near its limit)
            im = im.quantize(colours, dither=Image.Dither.NONE).convert("RGB")
        return im
    return make


def nav_arrow(fn):                        # navigation arrows: 6 colours look the same at 96 px
    return bare(fn, colours=6)


# name -> generator; sorted names = append order
ART = {
    "a_tile_aod_off": tile(aod), "a_tile_aod_on": tile(aod, on=True),
    "b_tile_find": tile(find_phone), "c_tile_watchset": tile(watch_settings), "d_tile_clock": tile(desk_clock),
    # file names must differ case-insensitively (Windows); order fixes the firmware's arrow index
    "e_nav0_straight": nav_arrow(straight), "e_nav1_left": nav_arrow(turn(-1)), "e_nav2_right": nav_arrow(turn(1)),
    "e_nav3_slight_left": nav_arrow(slight(-1)), "e_nav4_slight_right": nav_arrow(slight(1)), "e_nav5_uturn": nav_arrow(uturn),
    "e_nav6_arrive": nav_arrow(arrive), "e_nav7_roundabout": nav_arrow(roundabout),
}
# dock (bold white hours / bold orange minutes) and AOD (light) digit sets; names keep the order
for k, ch in enumerate(GLYPHS):
    ART[f"f_bw{k:02d}"] = digit(ch, WHITE, "bold")
    ART[f"g_bo{k:02d}"] = digit(ch, ORANGE, "bold")
    # (light h_lw / i_lo sets of the first always-on screen dropped in rev 15: pack space)
for k in range(11):
    ART[f"j_ring{k:02d}"] = ring(k)
ART.update({"k_bolt": small(bolt, 40), "k_wx0_sun": small(sun, 40), "k_wx1_moon": small(moon, 40),
            "k_wx2_cloud": small(cloud, 40), "k_wx3_rain": small(rain, 40), "k_battery": small(battery, 40)})


from ui_qp_art import ART as QP_ART      # quick-panel tile set (rev 10), appended after the rest
ART.update(QP_ART)
from ui_aod_art import ART as AOD_ART    # always-on display (rev 12)
ART.update(AOD_ART)
from ui_apps_art import ART as APPS_ART  # app list / grid after the owner's reference (rev 15)
ART.update(APPS_ART)


# ---- more navigation arrows (rev 16, appended after everything else: "r_nav*"). Same 48-unit
# grid, stroke and heads as the first eight; the road not taken is drawn dim.
NAV_DIM = (52, 62, 80)


def sharp(sign):                          # sign -1 = left
    def f(c):
        sx = 24 - sign * 6
        end = (24 + sign * 10, 32)
        c.stroke([(sx, 42), (sx, 14)], 6, NAV)
        c.stroke([(sx, 14), end], 6, NAV)
        ang = math.degrees(math.atan2(end[1] - 14, end[0] - sx))
        a = math.radians(ang)
        arrow_head(c, end[0] + 2 * math.cos(a), end[1] + 2 * math.sin(a), ang, col=NAV)
    return f


def keep(sign):                           # fork: take the `sign` branch
    def f(c):
        c.stroke([(24, 28), (24 - sign * 10, 13)], 6, NAV_DIM)
        c.stroke([(24, 42), (24, 28), (24 + sign * 10, 13)], 6, NAV)
        ang = -90 + sign * 34
        a = math.radians(ang)
        arrow_head(c, 24 + sign * 10 + 2 * math.cos(a), 13 + 2 * math.sin(a), ang, col=NAV)
    return f


def merge(c):
    c.stroke([(34, 42), (34, 10)], 6, NAV_DIM)
    c.stroke([(14, 42), (14, 31), (25, 20), (25, 12)], 6, NAV)
    arrow_head(c, 25, 10, -90, col=NAV)


def uturn_right(c):                       # left-hand traffic (India, UK, ...): U-turn to the right
    c.stroke([(18, 42), (18, 22)], 6, NAV)
    c.arc(25, 22, 7, 180, 360, 6, NAV)
    c.stroke([(32, 22), (32, 30)], 6, NAV)
    arrow_head(c, 32, 33, 90, col=NAV)


def ramp(sign):                           # exit / slip road on the `sign` side
    def f(c):
        c.stroke([(24 - sign * 4, 42), (24 - sign * 4, 9)], 6, NAV_DIM)
        c.stroke([(24 - sign * 4, 42), (24 - sign * 4, 30), (24 + sign * 10, 15)], 6, NAV)
        ang = -90 + sign * 43
        a = math.radians(ang)
        arrow_head(c, 24 + sign * 10 + 2 * math.cos(a), 15 + 2 * math.sin(a), ang, col=NAV)
    return f


# firmware arrow index 8.. (ext.c NAV_DIRS): < > k K M e E u
ART.update({"r_nav08_sharp_left": nav_arrow(sharp(-1)), "r_nav09_sharp_right": nav_arrow(sharp(1)),
            "r_nav10_keep_left": nav_arrow(keep(-1)), "r_nav11_keep_right": nav_arrow(keep(1)),
            "r_nav12_merge": nav_arrow(merge), "r_nav13_exit_left": nav_arrow(ramp(-1)), "r_nav14_exit_right": nav_arrow(ramp(1)),
            "r_nav15_uturn_right": nav_arrow(uturn_right)})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", type=Path, default=ROOT / "research" / "ui" / "feature_append")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for p in a.out.glob("*.png"):
        p.unlink()
    for name, fn in ART.items():
        fn().save(a.out / f"{name}.png")
    print(f"{len(ART)} images -> {a.out}")



# ---- navigation distance digits (rev 16, "s_navd*"): bold, 32 x 44 (the 84 px dock digits left no
# room for the time on the navigation screen); 6 colours for a short encoding
NAVD_W, NAVD_H = 32, 44


def nav_digit(ch):
    def make():
        big = Image.new("RGB", (NAVD_W * SS, NAVD_H * SS))
        d = ImageDraw.Draw(big)
        f = ImageFont.truetype(FONT, int(NAVD_H * SS * 1.18))
        f.set_variation_by_name("Bold")
        x0, y0, x1, y1 = d.textbbox((0, 0), "0", font=f)
        bx0, _, bx1, _ = d.textbbox((0, 0), ch, font=f)
        d.text(((NAVD_W * SS - (bx1 - bx0)) / 2 - bx0, (NAVD_H * SS - (y1 - y0)) / 2 - y0), ch, font=f, fill=WHITE)
        im = big.resize((NAVD_W, NAVD_H), Image.LANCZOS)
        return im.quantize(6, dither=Image.Dither.NONE).convert("RGB")
    return make


ART.update({f"s_navd{k:02d}": nav_digit(ch) for k, ch in enumerate(GLYPHS)})

from ui_dials_art import ART as DIALS_ART  # built-in faces after the favourites (rev 16, "u_dial*")
ART.update(DIALS_ART)


if __name__ == "__main__":
    main()
