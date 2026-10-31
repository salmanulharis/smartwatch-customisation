"""Breathe screen after the owner's reference (UI pack rev 16): in-place art only (the pack is full).

Every image here replaces a stock slot of the same size (black = transparent), so no address moves:
  - Breathe's own slots (title, value digits / words, labels, lead-in dots, the 11 animation frames),
  - the stock SpO2 slots the reworked SpO2 screen no longer draws (its ring frames IMG1556-1566 are
    still *compared* by address to detect "measuring", never drawn; their content is free).
Wide panels sit in 170 x 170 slots anchored to a corner, the rest of the slot left black.
The firmware side is ext.c t_breath_build; positions there match the anchors here.

    python tools/ui_breathe_art.py      # after ui_cmf.py / ui_cmf_text.py / ui_apps_art.py
    python tools/s100_ui.py build research/ui/replace --append research/ui/feature_append --version N
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import ui_cmf as G

SS = 4
GEO = r"C:\Windows\Fonts\GOTHICB.TTF"
GEO_R = r"C:\Windows\Fonts\GOTHIC.TTF"
ORANGE_TOP, ORANGE_BOT = (255, 112, 46), (246, 76, 18)
DOT = (255, 246, 240)
DOT_MIX = (255, 190, 160)            # dots where the two circles overlap
WHITE = (242, 242, 242)
GREY = (140, 140, 146)
CARD = (24, 24, 26)
CARD_EDGE = (52, 52, 56)
PANEL = (16, 16, 18)
PANEL_DOT = (62, 62, 66)
TRACK = (58, 58, 62)


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _font(px, path=GEO):
    return ImageFont.truetype(path, int(px * SS))


def _canvas(w, h):
    im = Image.new("RGB", (w * SS, h * SS), (0, 0, 0))
    return im, ImageDraw.Draw(im)


def _down(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


def _key(im):
    """Near-black anti-aliasing pixels would vanish (black is the key) or look dirty: snap them to black."""
    im.putdata([(0, 0, 0) if max(p) < 14 else p for p in im.getdata()])
    return im


def _pal(im, cols):
    """Reduce to an explicit palette: the slot fitter's fallback palettes would tint white / grey art."""
    return im.quantize(palette=G._palette(cols), dither=Image.Dither.NONE).convert("RGB")


def _ink(col, levels=4):
    return [_mix((0, 0, 0), col, t / (levels - 1)) for t in range(levels)]


def _spaced(d, x, y, text, f, fill, track):
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + track * SS
    return x


def _spaced_w(text, f, track):
    return sum(f.getlength(c) for c in text) + track * SS * (len(text) - 1)


def _gradient(w, h, top, bot):
    g = Image.new("RGB", (1, h))
    for y in range(h):
        g.putpixel((0, y), _mix(top, bot, y / max(1, h - 1)))
    return g.resize((w, h), Image.NEAREST)


# ---- header: "Breathe" (IMG598 88 x 20, the face of the SpO2 header) and the back chevron (IMG605, the
# unused '/' digit)
def title():
    w, h = 88, 20
    im, d = _canvas(w, h)
    f = _font(19)
    d.text((1 * SS, 16 * SS - f.getmetrics()[0]), "Breathe", font=f, fill=WHITE)   # baseline 16 px down
    return _key(_down(im, w, h))


def chevron():
    im, d = _canvas(11, 16)
    d.line([(8 * SS, 2.5 * SS), (2.5 * SS, 8 * SS), (8 * SS, 13.5 * SS)], fill=WHITE, width=int(2.4 * SS), joint="curve")
    # white + one grey only: the 304-byte slot does not take full anti-aliasing (and the slot fitter's
    # fallback palettes would tint it orange)
    return _key(_down(im, 11, 16).quantize(palette=G._palette([(0, 0, 0), WHITE, (120, 120, 124)]),
                                            dither=Image.Dither.NONE).convert("RGB"))


# ---- value glyphs: digits 0-9 (IMG606-615, 11 x 16), "min" (IMG600 32 x 16), pace words (46 x 14)
def _word(text, w, h, px, colour=WHITE, align="left"):
    im, d = _canvas(w, h)
    f = _font(px)
    asc = f.getmetrics()[0]
    tw = f.getlength(text)
    x = (w * SS - tw) / 2 if align == "center" else 0
    d.text((x, h * SS - asc - 0.5 * SS), text, font=f, fill=colour)   # baseline 0.5 px above the bottom
    return _key(_pal(_down(im, w, h), _ink(colour)))


def value_digit(ch):
    return lambda: _word(ch, 11, 16, 17, align="center")


# ---- labels for the running states (black-keyed, centred in their slot)
def label(text, w, h, px=18):
    def make():
        im, d = _canvas(w, h)
        f = _font(px)
        tw = _spaced_w(text, f, 0.6)
        a, dsc = f.getmetrics()
        _spaced(d, (w * SS - tw) / 2, (h * SS - (a + dsc)) / 2, text, f, WHITE, 0.6)
        return _key(_down(im, w, h))
    return make


def lead_dot(col):
    def make():
        im, d = _canvas(8, 8)
        d.ellipse([0.8 * SS, 0.8 * SS, 7.2 * SS, 7.2 * SS], fill=col)
        return _key(_pal(_down(im, 8, 8), _ink(col, 3)))
    return make


# ---- halftone "breath": two overlapping dot circles (the reference's mark)
# Dots are crisp pixel shapes drawn on the final (1x) image: a halftone reads as dots anyway, and
# single-colour dots keep the row RLE small (anti-aliased dots of many sizes did not fit the slots).
DOT_SHAPES = [[(0, 0)],                                                   # small: 1 px
              [(0, 0), (1, 0), (0, 1), (1, 1)],                           # 2 x 2
              [(0, -1), (-1, 0), (0, 0), (1, 0), (0, 1)]]                 # 3 px round (plus)


def _venn(im, cx, cy, rc, dx, dy, pitch, big=2):
    """Dots on a fixed hex grid inside two circles, shrinking towards the rims; dots inside both
    circles take the mixed colour. `big`: largest shape index (0-2)."""
    px = im.load()
    W, H = im.size
    c1, c2 = (cx - dx, cy - dy), (cx + dx, cy + dy)
    row = pitch * 0.87
    nj = int((rc + abs(dy)) / row) + 2
    ni = int((rc + abs(dx)) / pitch) + 2
    for j in range(-nj, nj + 1):
        y = cy + j * row
        for i in range(-ni, ni + 1):
            x = cx + i * pitch + (pitch / 2 if j & 1 else 0.0)
            e1 = rc - math.hypot(x - c1[0], y - c1[1])
            e2 = rc - math.hypot(x - c2[0], y - c2[1])
            if e1 < 0 and e2 < 0:
                continue
            col = DOT_MIX if (e1 >= 0 and e2 >= 0) else DOT
            edge = max(e1, e2)
            shape = DOT_SHAPES[min(big, 0 if edge < 0.45 * pitch else 1 if edge < 1.1 * pitch else 2)]
            ix, iy = int(round(x - 0.5)), int(round(y - 0.5))
            for ox, oy in shape:
                if 0 <= ix + ox < W and 0 <= iy + oy < H:
                    px[ix + ox, iy + oy] = col


FRAME_PAL = ([(0, 0, 0), TRACK, _mix((0, 0, 0), TRACK, 0.5), DOT, DOT_MIX] +
             [_mix(ORANGE_TOP, ORANGE_BOT, t / 9) for t in range(10)] +
             [_mix((0, 0, 0), c, f) for c in (ORANGE_TOP, ORANGE_BOT) for f in (0.3, 0.6)])
FRAMES = 20                          # breath levels 0 (exhaled) .. 19 (inhaled)
STAGE = 120                          # stage centre is the centre of a 120 x 120 frame


def breath_level(k):
    t = k / (FRAMES - 1)
    return 54 + 64 * t               # disc diameter


def frame(k, size):
    """Level k drawn centred in a size x size slot (120 or 170)."""
    def make():
        im, d = _canvas(size, size)
        D = breath_level(k)
        c = size / 2
        disc = Image.new("L", im.size, 0)
        ImageDraw.Draw(disc).ellipse([(c - D / 2) * SS, (c - D / 2) * SS, (c + D / 2) * SS, (c + D / 2) * SS], fill=255)
        top = int((c - D / 2) * SS)
        g = _gradient(size * SS, int(D * SS) + 2, ORANGE_TOP, ORANGE_BOT)
        layer = Image.new("RGB", im.size, (0, 0, 0))
        layer.paste(g, (0, top))
        im.paste(layer, (0, 0), disc)
        # fixed palette (the slot fitter's own reduction can tint the grey track orange)
        im = _down(im, size, size).quantize(palette=G._palette(FRAME_PAL), dither=Image.Dither.NONE).convert("RGB")
        # track: where a full breath reaches; a crisp 1 px ring in one grey (anti-aliased, it cost ~2 KB
        # a frame), drawn on black only so it never cuts the disc
        R = breath_level(FRAMES - 1) / 2 - 0.5
        if D / 2 < R - 1.5:
            px = im.load()
            for n in range(int(2 * math.pi * R * 2)):
                a = n / (2 * R)                         # half-pixel steps round the circle
                x, y = int(c + R * math.cos(a)), int(c + R * math.sin(a))
                if px[x, y] == (0, 0, 0):
                    px[x, y] = TRACK
        t = k / (FRAMES - 1)
        rc = D * 0.27
        dx = D * (0.07 + 0.10 * t)           # the circles drift apart as the breath fills
        _venn(im, c, c, rc, dx, D * 0.03, 4.0)
        return im
    return make


# ---- setup screen panels (170 x 170 slots, the panel anchored to a corner)
HERO_W, HERO_H = 138, 98             # orange stadium (top-left of IMG1565, drawn at 18, 52)
PANEL_W, PANEL_H = 100, 98           # dark dot panel (top-right of IMG1566, drawn at 70, 52 -> 128..228)
CARD_W, CARD_H = 100, 44             # cards: bottom-left of IMG1539 at (16, 34), bottom-right of IMG1540 at (54, 34)


def hero():
    im, d = _canvas(170, 170)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, HERO_W * SS - 1, HERO_H * SS - 1], radius=HERO_H * SS // 2, fill=255)
    im.paste(_gradient(HERO_W * SS, HERO_H * SS, ORANGE_TOP, ORANGE_BOT), (0, 0), mask.crop((0, 0, HERO_W * SS, HERO_H * SS)))
    im = _down(im, 170, 170)
    _venn(im, 62, 51, 26, 12, 4, 3.4, big=1)
    return im


# reference dot panel: 6 columns x 8 rows, grey dots with an orange "level" figure
PANEL_PATTERN = [
    "ggggg.",
    "gggGo.",
    "gggoog",
    "gggoog",
    "gggoog",
    "gggoo.",
    "ggggg.",
    "gggg..",
]


def panel():
    im, d = _canvas(170, 170)
    x0 = 170 - PANEL_W
    d.rounded_rectangle([x0 * SS, 0, 170 * SS - 1, PANEL_H * SS - 1], radius=PANEL_H * SS // 2, fill=PANEL)
    for j, row in enumerate(PANEL_PATTERN):
        for i, c in enumerate(row):
            if c == ".":
                continue
            col = {"g": PANEL_DOT, "G": (110, 110, 114), "o": G.ORANGE if hasattr(G, "ORANGE") else (255, 90, 30)}[c]
            cx, cy = (x0 + 32 + i * 8.6) * SS, (21 + j * 8.4) * SS
            r = 1.7 * SS
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    return _down(im, 170, 170)


def _clock_icon(d, cx, cy):
    r = 8.5
    d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], outline=WHITE, width=int(2.0 * SS))
    d.line([(cx * SS, (cy - 5) * SS), (cx * SS, cy * SS), ((cx + 3.6) * SS, cy * SS)], fill=WHITE, width=int(2.0 * SS),
           joint="curve")


def _sliders_icon(d, cx, cy):
    for k, kx in ((-5, 3), (0, -3), (5, 2)):
        y = cy + k
        d.line([((cx - 8) * SS, y * SS), ((cx + 8) * SS, y * SS)], fill=WHITE, width=int(1.7 * SS))
        r = 2.3
        d.ellipse([(cx + kx - r) * SS, (y - r) * SS, (cx + kx + r) * SS, (y + r) * SS], fill=CARD, outline=WHITE,
                  width=int(1.5 * SS))


def card(icon, text, right):
    def make():
        im, d = _canvas(170, 170)
        x0 = 170 - CARD_W if right else 0
        y0 = 170 - CARD_H
        d.rounded_rectangle([x0 * SS, y0 * SS, (x0 + CARD_W) * SS - 1, 170 * SS - 1], radius=14 * SS, fill=CARD,
                            outline=CARD_EDGE, width=int(1.2 * SS))
        icon(d, x0 + 21, y0 + CARD_H / 2)
        _spaced(d, (x0 + 40) * SS, (y0 + 27) * SS, text, _font(7.5, GEO_R), GREY, 1.3)
        return _key(_down(im, 170, 170))
    return make


def start_button():
    im, d = _canvas(200, 60)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 200 * SS - 1, 38 * SS - 1], radius=19 * SS, fill=255)
    im.paste(_gradient(200 * SS, 38 * SS, ORANGE_TOP, ORANGE_BOT), (0, 0), mask.crop((0, 0, 200 * SS, 38 * SS)))
    d = ImageDraw.Draw(im)
    f = _font(13)
    tw = _spaced_w("START", f, 3.2)
    x = (200 * SS - tw - 18 * SS) / 2
    d.polygon([(x, 12 * SS), (x + 11 * SS, 19 * SS), (x, 26 * SS)], fill=WHITE)
    a, dsc = f.getmetrics()
    _spaced(d, x + 19 * SS, (38 * SS - (a + dsc)) / 2 + 0.5 * SS, "START", f, WHITE, 3.2)
    shades = [_mix(ORANGE_TOP, ORANGE_BOT, t / 4) for t in range(5)]
    mid = _mix(ORANGE_TOP, ORANGE_BOT, 0.5)
    return _pal(_down(im, 200, 60), [(0, 0, 0), WHITE, _mix(mid, WHITE, 0.5)] + shades + [_mix((0, 0, 0), mid, 0.5)])


# ---- slots
SLOTS_120 = list(range(627, 638))                    # stock frames, 120 x 120
SLOTS_170 = list(range(1556, 1565))                  # stock SpO2 measuring frames, 170 x 170 (9 of 11)


def frame_slots(budget: dict[int, int]) -> list[int]:
    """Breath level -> slot: the cheapest level goes to the smallest slot."""
    return sorted(SLOTS_120 + SLOTS_170, key=lambda i: budget[i])


REPLACE_FIXED = {
    598: title, 605: chevron, 600: lambda: _word("min", 32, 16, 15),
    599: lambda: _word("Fast", 46, 14, 14), 601: lambda: _word("Slow", 46, 14, 14), 602: lambda: _word("Calm", 46, 14, 14),
    624: label("Get ready", 139, 24), 1555: label("Hold", 140, 26), 621: label("Well done", 90, 90),
    639: label("Inhale", 78, 29), 638: label("Exhale", 85, 29),
    625: lead_dot((70, 70, 74)), 626: lead_dot((255, 90, 30)),
    1565: hero, 1566: panel,
    1539: card(_clock_icon, "DURATION", False), 1540: card(_sliders_icon, "PACE", True),
    1536: start_button,
}
REPLACE_FIXED.update({606 + k: value_digit(str(k)) for k in range(10)})


def replace(budget: dict[int, int]) -> dict:
    out = dict(REPLACE_FIXED)
    for level, slot in enumerate(frame_slots(budget)):
        out[slot] = frame(level, 120 if slot in SLOTS_120 else 170)
    return out


def main() -> None:
    from s100_ui import UI_BIN, payload, walk
    out = Path(__file__).resolve().parent.parent / "research" / "ui" / "replace"
    images, _ = walk(payload(UI_BIN.read_bytes()))
    budget = {i: images[i][1] for i in SLOTS_120 + SLOTS_170}
    rep = replace(budget)
    for i, fn in rep.items():
        G.fit(fn(), images[i][1]).save(out / f"{i:04d}.png")
    print(f"{len(rep)} images -> {out}")


if __name__ == "__main__":
    main()
