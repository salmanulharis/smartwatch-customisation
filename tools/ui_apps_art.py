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
ORANGE = (255, 90, 30)
TRACK = (44, 44, 48)


def spo2_ring():                                       # IMG1539 170x170 (SpO2 value sits inside)
    im = Image.new("RGB", (170 * SS, 170 * SS), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([4 * SS, 4 * SS, 166 * SS, 166 * SS], outline=TRACK, width=9 * SS)
    # drop above the value (the value digits start at y 64 in this image)
    cx, cy = 85 * SS, 44 * SS
    d.ellipse([cx - 7 * SS, cy - 2 * SS, cx + 7 * SS, cy + 12 * SS], fill=ORANGE)
    d.polygon([(cx, cy - 12 * SS), (cx + 6.4 * SS, cy + 2 * SS), (cx - 6.4 * SS, cy + 2 * SS)], fill=ORANGE)
    return im.resize((170, 170), Image.LANCZOS)


def measure_button():                                  # IMG1536 200x60 (re-measure)
    """Pill + crisp (two-level) label: the stock slot is 2488 B, anti-aliased text does not fit."""
    im = Image.new("RGB", (200 * SS, 60 * SS), (0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([2 * SS, 4 * SS, 198 * SS - 1, 56 * SS - 1], radius=26 * SS,
                                         fill=(38, 38, 42))
    im = im.resize((200, 60), Image.LANCZOS)
    im = im.quantize(palette=G._palette([(0, 0, 0), (38, 38, 42), (19, 19, 21)]),
                     dither=Image.Dither.NONE).convert("RGB")
    ink = Image.new("L", (200, 60), 0)
    d = ImageDraw.Draw(ink)
    f = ImageFont.truetype(FONT, 19)
    box = f.getbbox("Measure")
    d.text(((200 - (box[2] - box[0])) / 2 - box[0], (60 - (box[3] - box[1])) / 2 - box[1]), "Measure", font=f, fill=255)
    im.paste((245, 245, 245), (0, 0), ink.point(lambda v: 255 if v >= 110 else 0))
    return im


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
REPLACE = {1539: spo2_ring, 1536: measure_button, 1537: on_black(1537)}
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
