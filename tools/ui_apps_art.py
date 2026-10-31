"""App launcher art after the owner's reference (UI pack rev 15): list rows and grid tiles.

Imported by tools/ui_feature_art.py (names "p_*", appended after every earlier image, so no existing
address moves). The firmware tables are repointed by tools/s100_ext.py:
  - list (MainMenuListScreenUI, 4 rows of 70 px): each row is one 220 x 55 pill split in two images,
    the icon part (55 x 55 at x 8: colour disc + white glyph) and the label part (165 x 55 at x 63:
    name + chevron), so the stock builder keeps placing, scrolling and hit-testing them;
  - grid (GridLayoutScreenUI, 64 x 64 at the stock 3-column positions): dark rounded tile with the
    glyph in the app's colour (Workout: orange tile).
Glyphs are the drawers of tools/ui_cmf.py, recoloured per app through its colour globals.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

import ui_cmf as G

SS = 4
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
PILL = (30, 30, 33)
TILE = (30, 30, 33)
LABEL = (240, 240, 240)
CHEVRON = (120, 120, 126)
ROW_H, ICON_W, LABEL_W, RADIUS = 55, 55, 165, 17


def temperature(c):
    c.rect(20.5, 8, 27.5, 31, 3.5, G.WHITE)
    c.circle(24, 32.5, 7.2, G.WHITE)
    c.circle(24, 32.5, 4.2, G.ORANGE)
    c.rect(22.6, 15, 25.4, 32, 1.4, G.ORANGE)
    for y in (12, 17, 22):
        c.stroke([(30.5, y), (34, y)], 1.8, G.WHITE)


# list order of the stock tables 0x88B718 / 0x88B7A8 (= grid order of 0x88CE3C)
APPS = [  # (name, drawer, colour)
    ("Temperature", temperature, (255, 106, 61)),
    ("Workout", G.workout, (255, 90, 30)),
    ("Activity Records", G.records, (94, 92, 230)),
    ("Heart Rate", G.heart, (255, 59, 48)),
    ("SpO\u2082", G.spo2, (40, 150, 235)),
    ("Activity", G.activity, (52, 199, 89)),
    ("Sleep", G.sleep, (125, 110, 255)),
    ("Notifications", G.messages, (10, 132, 255)),
    ("Weather", G.weather, (70, 160, 240)),
    ("Breathe", G.breathe, (40, 190, 150)),
    ("Music", G.music, (255, 55, 95)),
    ("Alarm", G.alarm, (255, 159, 10)),
    ("Timer", G.timer, (255, 120, 40)),
    ("Stopwatch", G.stopwatch, (255, 90, 30)),
    ("Camera", G.camera, (99, 99, 104)),
    ("Flashlight", G.flashlight, (99, 99, 104)),
    ("Find Phone", G.find_phone, (10, 132, 255)),
    ("Settings", G.settings, (99, 99, 104)),
]


def glyph(fn, size, white, accent, hole, disc):
    """ui_cmf drawer at `size` px on a disc (or nothing) with the given colours."""
    saved = (G.WHITE, G.ORANGE, G.CHIP)
    G.WHITE, G.ORANGE, G.CHIP = white, accent, hole
    try:
        c = G.Icon(size)
        if disc is None:                              # no disc: glyph on the hole colour
            c.d.rectangle([0, 0, size * G.SS, size * G.SS], fill=hole)
        fn(c)
        return c.image()
    finally:
        G.WHITE, G.ORANGE, G.CHIP = saved


def list_icon(fn, colour):
    def make():
        im = Image.new("RGB", (ICON_W * SS, ROW_H * SS), (0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, (ICON_W + 40) * SS, ROW_H * SS - 1], radius=RADIUS * SS, fill=PILL)
        im = im.resize((ICON_W, ROW_H), Image.LANCZOS)
        g = glyph(fn, 38, (255, 255, 255), (255, 255, 255), colour, True)
        mask = Image.new("L", (38 * SS, 38 * SS), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 38 * SS - 1, 38 * SS - 1], fill=255)
        im.paste(g, (9, (ROW_H - 38) // 2), mask.resize((38, 38), Image.LANCZOS))
        return im
    return make


def list_label(name):
    def make():
        im = Image.new("RGB", (LABEL_W * SS, ROW_H * SS), (0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([-40 * SS, 0, LABEL_W * SS - 1, ROW_H * SS - 1], radius=RADIUS * SS, fill=PILL)
        size = 17.0
        f = ImageFont.truetype(FONT, int(size * SS))
        while f.getlength(name) > 122 * SS:            # long names: a little smaller, never clipped
            size -= 0.5
            f = ImageFont.truetype(FONT, int(size * SS))
        box = f.getbbox("Hg")
        y = (ROW_H * SS - (box[3] - box[1])) / 2 - box[1]
        sub = name.endswith("₂")                    # the font has no subscript digits: draw it
        base = name[:-1] if sub else name
        d.text((6 * SS, y), base, font=f, fill=LABEL)
        if sub:
            fs = ImageFont.truetype(FONT, int(size * 0.62 * SS))
            d.text((6 * SS + f.getlength(base) + 0.5 * SS, y + size * 0.45 * SS), "2", font=fs, fill=LABEL)
        cx, cy = (LABEL_W - 18) * SS, ROW_H * SS / 2
        d.line([(cx - 3.5 * SS, cy - 7 * SS), (cx + 3.5 * SS, cy), (cx - 3.5 * SS, cy + 7 * SS)], fill=CHEVRON,
               width=int(2.2 * SS), joint="curve")
        return im.resize((LABEL_W, ROW_H), Image.LANCZOS)
    return make


def grid_tile(fn, colour, first):
    def make():
        im = Image.new("RGB", (64 * SS, 64 * SS), (0, 0, 0))
        tile = colour if first else TILE
        ImageDraw.Draw(im).rounded_rectangle([1 * SS, 1 * SS, 63 * SS - 1, 63 * SS - 1], radius=18 * SS, fill=tile)
        im = im.resize((64, 64), Image.LANCZOS)
        if first:
            g = glyph(fn, 46, (255, 255, 255), (255, 255, 255), tile, None)
        elif fn is G.heart:
            g = glyph(fn, 46, colour, (255, 255, 255), tile, None)
        else:
            accent = (255, 196, 40) if fn is G.weather else colour      # the sun stays yellow
            g = glyph(fn, 46, (240, 240, 240), accent, tile, None)
        im.paste(g, (9, 9))
        return im
    return make


ART = {}
for k, (name, fn, colour) in enumerate(APPS):
    ART[f"p_apps_a_icon{k:02d}"] = list_icon(fn, colour)
    ART[f"p_apps_b_label{k:02d}"] = list_label(name)
    ART[f"p_apps_c_grid{k:02d}"] = grid_tile(fn, colour, k == 1)


# ---- health screens: in-place replacements (same size as stock, must fit the stock slot)
def on_black(index):
    """Stock white-on-red SpO2 digit / % frame -> white on black (the value no longer sits on a disc):
    ink = min(G, B), which is ~0 on the red background and 255 on the white digits."""
    def make():
        from pathlib import Path
        im = Image.open(Path(__file__).resolve().parent.parent / "research" / "ui" / "img" / f"{index:04d}.png")
        im = im.convert("RGB")
        im.putdata([(v, v, v) for v in (min(g, b) for _r, g, b in im.convert('RGB').get_flattened_data())])
        return im
    return make


# (a smooth heart IMG1476 does not fit its 478-byte slot; the current one stays)
# (IMG1536 / 1539, the old SpO2 button and ring, now hold Breathe art: tools/ui_breathe_art.py)
REPLACE = {1537: on_black(1537)}
REPLACE.update({i: on_black(i) for i in range(1522, 1536)})        # 37x44 digits "- . / 0-9 :"


def main() -> None:
    """Write the in-place replacements into research/ui/replace (fitted to their stock slots)."""
    from pathlib import Path
    from s100_ui import UI_BIN, payload, walk
    out = Path(__file__).resolve().parent.parent / "research" / "ui" / "replace"
    images, _ = walk(payload(UI_BIN.read_bytes()))
    for i, fn in REPLACE.items():
        G.fit(fn(), images[i][1]).save(out / f"{i:04d}.png")
    print(f"{len(REPLACE)} images -> {out}")


if __name__ == "__main__":
    main()


# ---- quick-panel status bar text (rev 15): one size for the date and the battery, slightly smaller
# than the 24 px system font. Names start with "q_" (appended after the launcher art).
from ui_aod_art import text_img, word_width                       # noqa: E402

QS_SIZE, QS_H, QS_DIGIT_W, QS_WD_W = 20, 20, 11, 44
QS_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
QS_WHITE = (240, 240, 240)
for k, ch in enumerate("-./0123456789:"):
    ART[f"q_qs_a_d{k:02d}"] = text_img(ch, QS_WHITE, QS_DIGIT_W, QS_H, size=QS_SIZE, align="center")
ART["q_qs_b_pct"] = text_img("%", QS_WHITE, 16, QS_H, size=QS_SIZE)
for k, n in enumerate(QS_WEEKDAYS):
    ART[f"q_qs_c_wd{k}"] = text_img(n, QS_WHITE, QS_WD_W, QS_H, size=QS_SIZE)


def qs_weekday_widths() -> list[int]:
    """Ink width of each weekday image (the day number follows it)."""
    return [round(word_width(n, QS_SIZE)) for n in QS_WEEKDAYS]


# ---- SpO2 screen after the owner's reference (rev 16, "v_spo2_*", appended after everything else).
# Geometric type (Century Gothic Bold, the closest system face to the reference), an orange card with a
# soft vertical gradient (row-constant, so it costs nothing in the row RLE), O2 icon, letter-spaced
# BLOOD OXYGEN and a crescent of halftone dots growing towards the right edge; below it a ring spinner,
# a status line and a 12-pill progress bar. The value glyphs are black-keyed (transparent background,
# near-black ink), so they sit on the gradient and the dots without boxes. Proportional digits: their
# widths go to the firmware (spo2_widths()).
GEO = r"C:\Windows\Fonts\GOTHICB.TTF"
SPO2_TOP, SPO2_BOT = (255, 122, 58), (246, 82, 26)     # card gradient
SPO2_ORANGE = (255, 98, 34)                            # spinner / pills
SPO2_INK = (20, 20, 20)
SPO2_DOT = (255, 214, 192)
SPO2_WHITE = (242, 242, 242)
SPO2_TRACK = (58, 58, 62)
CARD_W, CARD_H = 212, 128
VAL_H, PCT_H, DROP = 50, 26, 2                          # value glyph frames; baseline DROP px above the bottom
VAL_PX = 62


def _pal(cols):
    p = Image.new("P", (1, 1))
    p.putpalette([v for c in cols for v in c] + [0] * (768 - 3 * len(cols)))
    return p


def _q(im, cols):
    return im.quantize(palette=_pal(cols), dither=Image.Dither.NONE).convert("RGB")


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _geo(px):
    return ImageFont.truetype(GEO, int(px * SS))


def _spaced(d, x, y, text, f, fill, track):
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + track * SS
    return x


def spo2_card():
    import math
    im = Image.new("RGB", (CARD_W * SS, CARD_H * SS), (0, 0, 0))
    grad = Image.new("RGB", (1, CARD_H))
    for y in range(CARD_H):
        grad.putpixel((0, y), _mix(SPO2_TOP, SPO2_BOT, y / (CARD_H - 1)))
    grad = grad.resize((CARD_W * SS, CARD_H * SS), Image.NEAREST)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, CARD_W * SS - 1, CARD_H * SS - 1], radius=24 * SS, fill=255)
    im.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(im)
    # halftone crescent: dots on concentric arcs bulging to the right, larger on the outer arcs and
    # shrinking towards the arc ends
    cx, cy = 62, 64
    for ring in range(6):
        r = 76 + ring * 12.5
        steps = int(2 * math.pi * r / 12.5)
        for k in range(steps):
            a = 2 * math.pi * (k + 0.5 * (ring & 1)) / steps
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            if not (x > cx and x <= CARD_W - 9 and 9 <= y <= CARD_H - 9):
                continue
            end = min(1.0, (y - 9) / 30, (CARD_H - 9 - y) / 30)
            rad = (0.9 + 2.6 * (ring / 5) ** 1.2) * (0.35 + 0.65 * max(0.0, end))
            if rad < 0.7:
                continue
            d.ellipse([(x - rad) * SS, (y - rad) * SS, (x + rad) * SS, (y + rad) * SS], fill=SPO2_DOT)
    # O2 icon: ring + subscript 2
    d.ellipse([16 * SS, 14 * SS, 36 * SS, 34 * SS], outline=SPO2_INK, width=int(3 * SS))
    d.text((38 * SS, 25 * SS), "2", font=_geo(12), fill=SPO2_INK)
    _spaced(d, 18 * SS, 100 * SS, "BLOOD OXYGEN", _geo(11), SPO2_INK, 1.8)
    im = im.resize((CARD_W, CARD_H), Image.LANCZOS)
    cols = [(0, 0, 0), SPO2_INK, SPO2_DOT] + [_mix(SPO2_TOP, SPO2_BOT, t / 9) for t in range(10)]
    cols += [_mix(SPO2_INK, SPO2_TOP, 0.5), _mix(SPO2_DOT, SPO2_TOP, 0.5), _mix(SPO2_DOT, SPO2_BOT, 0.5)]
    return _q(im, cols)


def _glyph(ch, px, h, ink, bg, levels, pad=1, drop=0):
    """Black-keyed glyph frame `h` high, baseline `drop` px above the bottom (room for round overshoot),
    ink width + pad on both sides."""
    f = _geo(px)
    asc = f.getmetrics()[0] + drop * SS
    probe = Image.new("L", (3 * px * SS, h * SS), 0)
    ImageDraw.Draw(probe).text((px * SS, h * SS - asc), ch, font=f, fill=255)
    x0, y0, x1, _ = probe.getbbox()
    assert y0 > 0, f"{ch!r} clipped at the top of its {h} px frame"
    w = max(1, -(-(x1 - x0) // SS) + 2 * pad)
    im = Image.new("RGB", (w * SS, h * SS), bg)
    ImageDraw.Draw(im).text((px * SS - x0 + pad * SS, h * SS - asc), ch, font=f, fill=ink)
    im = _q(im.resize((w, h), Image.LANCZOS), [_mix(bg, ink, t / (levels - 1)) for t in range(levels)])
    # key: the background becomes pure black (transparent); the ink stays off pure black
    im.putdata([(0, 0, 0) if p == bg else p for p in im.getdata()])
    return im


def spo2_value(ch, px, h):
    return lambda: _glyph(ch, px, h, SPO2_INK, SPO2_BOT, 3, drop=DROP)


def spo2_percent():
    """'%' drawn geometrically (the font's own has a joining stroke and does not fit a small frame):
    two rings and a slash, ring bottoms on the baseline (DROP px above the frame bottom)."""
    w, h, r, t = 25, PCT_H, 5.8, 3.3
    bg = SPO2_BOT
    im = Image.new("RGB", (w * SS, h * SS), bg)
    d = ImageDraw.Draw(im)
    base = h - DROP
    for cx, cy in ((0.6 + r, base - 23.4 + r), (w - 0.6 - r, base - r)):
        d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=SPO2_INK)
        d.ellipse([(cx - r + t) * SS, (cy - r + t) * SS, (cx + r - t) * SS, (cy + r - t) * SS], fill=bg)
    d.line([((w - 4.5) * SS, (base - 23.4) * SS), (4.5 * SS, base * SS)], fill=SPO2_INK, width=int(3.3 * SS))
    im = _q(im.resize((w, h), Image.LANCZOS), [_mix(bg, SPO2_INK, k / 3) for k in range(4)])
    im.putdata([(0, 0, 0) if p == bg else p for p in im.getdata()])
    return im


SPIN = 32
SPIN_COLS = [(0, 0, 0), SPO2_TRACK, SPO2_ORANGE, SPO2_WHITE, _mix((0, 0, 0), SPO2_TRACK, 0.5),
             _mix((0, 0, 0), SPO2_ORANGE, 0.5), _mix(SPO2_TRACK, SPO2_ORANGE, 0.5), _mix(SPO2_ORANGE, SPO2_WHITE, 0.5)]


def _ring(col):
    im = Image.new("RGB", (SPIN * SS, SPIN * SS), (0, 0, 0))
    ImageDraw.Draw(im).arc([2.5 * SS, 2.5 * SS, 29.5 * SS, 29.5 * SS], 0, 360, fill=col, width=int(3.6 * SS))
    return _q(im.resize((SPIN, SPIN), Image.LANCZOS), SPIN_COLS)


def _octant(k):
    """Orange ring piece for octant k (clockwise from 12 o'clock), cropped; drawn over the grey track."""
    import math
    im = _ring(SPO2_ORANGE)
    keep = Image.new("L", (SPIN, SPIN), 0)
    for y in range(SPIN):
        for x in range(SPIN):
            a = math.degrees(math.atan2(x + 0.5 - SPIN / 2, -(y + 0.5 - SPIN / 2))) % 360
            if 45 * k <= a < 45 * (k + 1):
                keep.putpixel((x, y), 255)
    out = Image.new("RGB", (SPIN, SPIN), (0, 0, 0))
    out.paste(im, (0, 0), keep)
    return out, out.getbbox()


def spo2_octant(k):
    return lambda: _octant(k)[0].crop(_octant(k)[1])


def spo2_octant_boxes() -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) of each octant piece inside the 32 x 32 spinner."""
    return [(b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in (_octant(k)[1] for k in range(8))]


def spo2_dot():                         # idle: a small orange dot riding on top of the track
    im = Image.new("RGB", (6 * SS, 6 * SS), (0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, 6 * SS - 1, 6 * SS - 1], fill=SPO2_ORANGE)
    return _q(im.resize((6, 6), Image.LANCZOS), SPIN_COLS)


def spo2_pill(col):
    def make():
        im = Image.new("RGB", (6 * SS, 12 * SS), (0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, 6 * SS - 1, 12 * SS - 1], radius=3 * SS, fill=col)
        return _q(im.resize((6, 12), Image.LANCZOS), [(0, 0, 0), col, _mix((0, 0, 0), col, 0.5)])
    return make


def spo2_status(text):                  # letter-spaced status line, 160 x 18, black-keyed
    def make():
        im = Image.new("RGB", (160 * SS, 18 * SS), (0, 0, 0))
        _spaced(ImageDraw.Draw(im), 0, 1 * SS, text, _geo(13), SPO2_WHITE, 0.9)
        return _q(im.resize((160, 18), Image.LANCZOS), [_mix((0, 0, 0), SPO2_WHITE, t / 2) for t in range(3)])
    return make


def spo2_head():                        # back chevron + "SpO2" with a real subscript, 96 x 28
    im = Image.new("RGB", (96 * SS, 28 * SS), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line([(9 * SS, 6 * SS), (2.5 * SS, 13.5 * SS), (9 * SS, 21 * SS)], fill=SPO2_WHITE, width=int(2.6 * SS),
           joint="curve")
    f, fs = _geo(20), _geo(11)
    d.text((22 * SS, 22 * SS - f.getmetrics()[0]), "SpO", font=f, fill=SPO2_WHITE)
    d.text((22 * SS + f.getlength("SpO") + 1 * SS, 27 * SS - fs.getmetrics()[0]), "2", font=fs, fill=SPO2_WHITE)
    return _q(im.resize((96, 28), Image.LANCZOS), [_mix((0, 0, 0), SPO2_WHITE, t / 3) for t in range(4)])


SPO2_STATUS = ["Measuring...", "Tap to measure", "Tap to measure again"]
ART.update({"v_spo2_a_card": spo2_card, "v_spo2_a_head": spo2_head})
ART.update({f"v_spo2_b_d{k}": spo2_value(str(k), VAL_PX, VAL_H) for k in range(10)})
ART.update({"v_spo2_c_dash": spo2_value("-", VAL_PX, VAL_H), "v_spo2_c_pct": spo2_percent})
ART.update({"v_spo2_d_track": lambda: _ring(SPO2_TRACK), "v_spo2_d_dot": spo2_dot})
ART.update({f"v_spo2_d_oct{k}": spo2_octant(k) for k in range(8)})
ART.update({"v_spo2_e_seg_on": spo2_pill(SPO2_ORANGE), "v_spo2_e_seg_off": spo2_pill(SPO2_TRACK)})
ART.update({f"v_spo2_f_st{k}": spo2_status(t) for k, t in enumerate(SPO2_STATUS)})


def spo2_widths() -> dict:
    """Frame widths the firmware lays out with: value digits 0-9, '-' and '%'."""
    return {"val": [ART[f"v_spo2_b_d{k}"]().size[0] for k in range(10)],
            "dash": ART["v_spo2_c_dash"]().size[0], "pct": ART["v_spo2_c_pct"]().size[0]}


