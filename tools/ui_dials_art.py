"""Built-in watch faces re-done after the owner's favourites (UI pack rev 16).

The three stock faces keep their stock builders (no new code on the face, which is the first screen
after boot); only their art and constants change:
  - backgrounds are replaced in place (they must fit their stock slot after encoding);
  - new digit frames are appended ("u_dial*", after every earlier image) and the builders' frame
    tables / sizes / positions are patched in tools/s100_ext.py.
Slot 3 (WatchScreenD2640001, time + date) -> "Grid": dark dot-ring disc, time centred in it.

    python tools/ui_dials_art.py          # writes the in-place backgrounds into research/ui/replace
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import ui_cmf as G

SS = 4
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
W, H = 240, 280
CORAL = (255, 90, 30)

# ---- slot 3: Grid
G3_CX, G3_CY, G3_R = 120, 124, 88            # disc
G3_DW, G3_DH = 32, 44                        # time frame size = the bold navigation digits (s_navd)
FRAMES = "-./0123456789:"


def grid_background():
    im = Image.new("RGB", (W * SS, H * SS), (0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = G3_CX * SS, G3_CY * SS, G3_R * SS
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(34, 34, 37))
    for k in range(60):                      # dot ring (minute marks); 12 o'clock bright
        a = math.radians(k * 6 - 90)
        rr = (G3_R + 14) * SS
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        dot = (3.2 if k % 5 == 0 else 2.0) * SS
        col = (235, 235, 235) if k == 0 else ((96, 96, 100) if k % 5 == 0 else (54, 54, 58))
        d.ellipse([x - dot, y - dot, x + dot, y + dot], fill=col)
    # a thin coral accent under the date line (static decoration, not data)
    d.rounded_rectangle([(G3_CX - 14) * SS, 176 * SS, (G3_CX + 14) * SS, 179 * SS], radius=2 * SS, fill=CORAL)
    return im.resize((W, H), Image.LANCZOS)


def grid_digit(ch):
    def make():
        im = Image.new("RGB", (G3_DW * SS, G3_DH * SS), (0, 0, 0))
        d = ImageDraw.Draw(im)
        f = ImageFont.truetype(FONT, int(G3_DH * SS * 1.12))
        f.set_variation_by_name("Bold")
        x0, y0, x1, y1 = d.textbbox((0, 0), "0", font=f)
        bx0, _, bx1, _ = d.textbbox((0, 0), ch, font=f)
        d.text(((G3_DW * SS - (bx1 - bx0)) / 2 - bx0, (G3_DH * SS - (y1 - y0)) / 2 - y0), ch, font=f,
               fill=(244, 244, 244))
        return im.resize((G3_DW, G3_DH), Image.LANCZOS).quantize(6, dither=Image.Dither.NONE).convert("RGB")
    return make


# ---- slot 1: Dashboard (WatchScreenD2687001: time, heart rate, steps, kcal, 3 activity rings, weekday)
CARD = (26, 26, 29)
GREYT = (150, 150, 156)


def _font(size, var="Regular"):
    f = ImageFont.truetype(FONT, int(size * SS))
    f.set_variation_by_name(var)
    return f


def dashboard_background():
    im = Image.new("RGB", (W * SS, H * SS), (0, 0, 0))
    d = ImageDraw.Draw(im)
    r = 16 * SS
    d.rounded_rectangle([10 * SS, 122 * SS, 118 * SS, 204 * SS], radius=r, fill=CARD)     # heart rate
    d.rounded_rectangle([124 * SS, 122 * SS, 230 * SS, 204 * SS], radius=r, fill=CARD)    # activity rings
    d.rounded_rectangle([10 * SS, 210 * SS, 230 * SS, 266 * SS], radius=r, fill=CARD)     # steps / kcal
    for y in (76, 98):                                                                      # time colon
        d.ellipse([(120 - 4.5) * SS, (y - 4.5) * SS, (120 + 4.5) * SS, (y + 4.5) * SS], fill=CORAL)
    # heart icon + label
    hx, hy = 26, 142
    d.ellipse([(hx - 6) * SS, (hy - 4) * SS, (hx + 1) * SS, (hy + 3) * SS], fill=CORAL)
    d.ellipse([(hx - 1) * SS, (hy - 4) * SS, (hx + 6) * SS, (hy + 3) * SS], fill=CORAL)
    d.polygon([((hx - 6) * SS, (hy + 1) * SS), ((hx + 6) * SS, (hy + 1) * SS), (hx * SS, (hy + 8) * SS)], fill=CORAL)
    d.text((38 * SS, 136 * SS), "HEART RATE", font=_font(10, "SemiBold"), fill=GREYT)
    d.text((86 * SS, 172 * SS), "BPM", font=_font(10, "SemiBold"), fill=GREYT)
    # footprints for the steps / kcal card
    for (x, y) in ((22, 230), (28, 236)):
        d.ellipse([(x - 3) * SS, (y - 5) * SS, (x + 3) * SS, (y + 4) * SS], fill=(90, 200, 150))
    d.line([(122 * SS, 220 * SS), (122 * SS, 256 * SS)], fill=(50, 50, 54), width=SS)
    return im.resize((W, H), Image.LANCZOS)


def weekday_word(name):
    def make():
        im = Image.new("RGB", (159 * SS, 38 * SS), (0, 0, 0))
        d = ImageDraw.Draw(im)
        f = _font(30, "SemiBold")
        x = 2 * SS
        for ch in name:                      # letter-spaced, as the dashboard's dot weekday
            d.text((x, 2 * SS), ch, font=f, fill=(244, 244, 244))
            x += f.getlength(ch) + 5 * SS
        return im.resize((159, 38), Image.LANCZOS)
    return make


# the time digits are the bold 32 x 44 navigation digits already in the pack (s_navd; pack space):
# only the ':' frame is drawn here, in the same size, bold and white
ART = {"u_dial3_d13": grid_digit(":")}
REPLACE = {343: grid_background,             # slot 3 background (stock "planet", 42,778 B slot)
           371: dashboard_background}        # slot 1 background (21,400 B slot)
# slot 1 weekday frames IMG440-446 (159 x 38), Sunday first (the stock frames: IMG440 highlights SUN)
REPLACE.update({440 + k: weekday_word(n) for k, n in enumerate(["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"])})


def main() -> None:
    from s100_ui import UI_BIN, payload, walk
    out = Path(__file__).resolve().parent.parent / "research" / "ui" / "replace"
    images, _ = walk(payload(UI_BIN.read_bytes()))
    for i, fn in REPLACE.items():
        G.fit(fn(), images[i][1]).save(out / f"{i:04d}.png")
    print(f"{len(REPLACE)} backgrounds -> {out}")


if __name__ == "__main__":
    main()
