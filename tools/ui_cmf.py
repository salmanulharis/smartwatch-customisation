"""CMF-style restyle of the S100 UI pack (our own drawings, stock sizes).

    python tools/ui_cmf.py [-o research/ui/replace] [--no-theme]
    python tools/s100_ui.py build research/ui/replace --version N

1. ART: redrawn images (app icons), each exactly the stock w x h.
2. Text: labels and digit sets re-rendered in Bahnschrift (tools/ui_cmf_text.py), same size,
   ink height, line positions and alignment as stock.
3. Theme (every other image): per-colour remap, warm hues -> CMF orange, cool hues -> neutral
   grey/white, neutrals untouched. Shapes, sizes and anti-aliasing stay; an image whose remapped
   encoding would not fit its stock slot is left stock.
"""
from __future__ import annotations

import argparse
import colorsys
import math
from pathlib import Path

from PIL import Image, ImageDraw

import ui_cmf_text as txt
from s100_ui import UI_BIN, encode, payload, rgb, to565, walk

SS = 8
BLACK = (0, 0, 0)
CHIP = (40, 40, 40)          # dark grey icon disc
WHITE = (245, 245, 245)
ORANGE = (255, 90, 30)


def canvas(w, h):
    im = Image.new("RGB", (w * SS, h * SS), BLACK)
    return im, ImageDraw.Draw(im)


def done(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


class Icon:
    """Draw in a 48-unit design grid, scaled to the stock icon size (supersampled)."""

    def __init__(self, size):
        self.size, self.k = size, size * SS / 48
        self.im, self.d = canvas(size, size)
        self.circle(24, 24, 23.6, CHIP)

    def p(self, x, y):
        return x * self.k, y * self.k

    def circle(self, x, y, r, fill=None, outline=None, width=0):
        k = self.k
        self.d.ellipse((x * k - r * k, y * k - r * k, x * k + r * k, y * k + r * k), fill=fill, outline=outline,
                       width=int(width * k))

    def rect(self, x0, y0, x1, y1, r, fill):
        k = self.k
        self.d.rounded_rectangle((x0 * k, y0 * k, x1 * k, y1 * k), radius=r * k, fill=fill)

    def poly(self, pts, fill):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=fill)

    def stroke(self, pts, w, fill):
        self.d.line([self.p(x, y) for x, y in pts], fill=fill, width=int(w * self.k), joint="curve")
        for x, y in (pts[0], pts[-1]):
            self.circle(x, y, w / 2, fill)

    def arc(self, x, y, r, a0, a1, w, fill):
        k = self.k
        self.d.arc((x * k - r * k, y * k - r * k, x * k + r * k, y * k + r * k), a0, a1, fill=fill, width=int(w * k))

    def image(self):
        return done(self.im, self.size, self.size)


def workout(c):
    c.circle(29, 11.5, 3.3, ORANGE)
    c.stroke([(27, 17), (22.5, 27)], 3.4, WHITE)
    c.stroke([(19, 21), (25.5, 18), (30, 23), (34, 21)], 3, WHITE)
    c.stroke([(22.5, 27), (28, 31), (27, 37.5)], 3.2, WHITE)
    c.stroke([(22.5, 27), (18.5, 32.5), (13, 32.5)], 3.2, WHITE)


def records(c):
    c.rect(14, 11, 34, 37, 4, WHITE)
    c.rect(17, 15, 31, 33, 2, CHIP)
    for i, y in enumerate((19, 24, 29)):
        c.stroke([(20, y), (28 if i < 2 else 24, y)], 2.2, ORANGE if i == 0 else WHITE)


def heart(c):
    c.circle(18.8, 20.5, 6.4, WHITE)
    c.circle(29.2, 20.5, 6.4, WHITE)
    c.poly([(12.7, 22.5), (35.3, 22.5), (24, 35)], WHITE)
    c.stroke([(10, 24.5), (17.5, 24.5), (20.5, 19.5), (25, 30), (28, 24.5), (38, 24.5)], 2.2, ORANGE)


def spo2(c):
    c.circle(24, 28.5, 8.5, WHITE)
    c.poly([(24, 10.5), (31.8, 25), (16.2, 25)], WHITE)
    c.circle(24, 28.5, 3.6, ORANGE)


def activity(c):
    """Solid bars (compresses like the stock flat icons)."""
    c.rect(13, 22, 19, 35, 2, WHITE)
    c.rect(21, 15, 27, 35, 2, ORANGE)
    c.rect(29, 26, 35, 35, 2, WHITE)


def sleep(c):
    c.circle(22.5, 25.5, 11, WHITE)
    c.circle(28.5, 19.5, 9.2, CHIP)
    c.circle(32.5, 13.5, 2.1, ORANGE)
    c.circle(36.5, 20.5, 1.4, ORANGE)


def messages(c):
    c.rect(11, 13, 37, 31.5, 7, WHITE)
    c.poly([(15.5, 29), (14, 37), (23, 30)], WHITE)
    for x in (18, 24, 30):
        c.circle(x, 22.3, 2, ORANGE)


def weather(c):
    c.circle(19.5, 18.5, 6.3, ORANGE)
    c.circle(22, 28, 6, CHIP)
    c.circle(29, 25, 7.6, CHIP)
    c.circle(22, 28, 5, WHITE)
    c.circle(29, 25, 6.6, WHITE)
    c.circle(34, 30.5, 4.5, WHITE)
    c.rect(15, 28, 38.5, 35, 3.5, WHITE)


def breathe(c):
    c.circle(19.5, 24, 8.5, outline=WHITE, width=2.6)
    c.circle(28.5, 24, 8.5, outline=ORANGE, width=2.6)


def music(c):
    c.rect(27, 11, 30.2, 31, 1.2, WHITE)
    c.poly([(29, 11), (37, 14.5), (37, 19.5), (29, 16.5)], ORANGE)
    c.circle(23.5, 31, 5.6, WHITE)


def alarm(c):
    c.circle(16.5, 15.5, 4, WHITE)
    c.circle(31.5, 15.5, 4, WHITE)
    c.circle(24, 25.5, 11.5, WHITE)
    c.stroke([(24, 25.5), (24, 18.5)], 2.6, ORANGE)
    c.stroke([(24, 25.5), (29, 28)], 2.6, ORANGE)


def timer(c):
    c.stroke([(16, 11.5), (32, 11.5)], 2.6, WHITE)
    c.stroke([(16, 36.5), (32, 36.5)], 2.6, WHITE)
    c.poly([(18, 13), (30, 13), (25.3, 24), (30, 35), (18, 35), (22.7, 24)], WHITE)
    c.poly([(20.7, 15.2), (27.3, 15.2), (24, 22.5)], CHIP)
    c.poly([(20.7, 32.8), (27.3, 32.8), (24, 25.5)], CHIP)
    c.poly([(21.5, 32.8), (26.5, 32.8), (24, 28)], ORANGE)


def stopwatch(c):
    c.rect(21, 9.5, 27, 13, 1.2, WHITE)
    c.rect(22.8, 12, 25.2, 15.5, 0.5, WHITE)
    c.circle(24, 26, 11.2, WHITE)
    c.circle(24, 26, 8.6, CHIP)
    c.stroke([(24, 26), (24, 19.5)], 2.2, ORANGE)
    c.circle(24, 26, 1.8, ORANGE)


def camera(c):
    c.rect(18, 13, 27, 19, 2, WHITE)
    c.rect(10.5, 16.5, 37.5, 34.5, 4.5, WHITE)
    c.circle(24, 25.5, 6.6, CHIP)
    c.circle(24, 25.5, 4, ORANGE)


def flashlight(c):
    c.poly([(15.5, 10.5), (32.5, 10.5), (28.5, 19.5), (19.5, 19.5)], WHITE)
    c.rect(19.5, 18, 28.5, 38, 2.2, WHITE)
    c.circle(24, 25.5, 2, ORANGE)
    c.stroke([(17.5, 14), (30.5, 14)], 1.2, ORANGE)


def find_phone(c):
    c.rect(12.5, 11, 27.5, 37, 3.5, WHITE)
    c.circle(20, 32.5, 1.8, ORANGE)
    c.arc(27.5, 21, 8, -60, 30, 2.6, ORANGE)


def settings(c):
    import math as m
    pts = []
    for k in range(32):
        a = m.radians(k * 360 / 32 - 360 / 64)
        rr = 14.5 if k % 4 in (1, 2) else 11
        pts.append((24 + rr * m.sin(a), 24 - rr * m.cos(a)))
    c.poly(pts, WHITE)
    c.circle(24, 24, 6.2, CHIP)
    c.circle(24, 24, 3.4, ORANGE)


def icon(fn, size):
    def make():
        c = Icon(size)
        fn(c)
        return c.image()
    return make


# app order of the 64 px grid set (1144-1160) and of the 48 px list set (1258-1274)
GRID_ORDER = [workout, records, heart, spo2, activity, sleep, messages, weather, breathe, music, alarm,
              timer, stopwatch, camera, flashlight, find_phone, settings]
LIST_ORDER = [workout, records, heart, spo2, activity, sleep, messages, breathe, music, alarm, timer,
              stopwatch, camera, flashlight, find_phone, settings, weather]


ART = {}
ART.update({1144 + k: icon(fn, 64) for k, fn in enumerate(GRID_ORDER)})
ART.update({1258 + k: icon(fn, 48) for k, fn in enumerate(LIST_ORDER)})


def _palette(cols) -> Image.Image:
    p = Image.new("P", (1, 1))
    flat = [v for c in cols for v in c]
    p.putpalette(flat + [0] * (768 - len(flat)))
    return p


def _mix(a, b):
    return tuple((x + y) // 2 for x, y in zip(a, b))


# Theme colours plus one edge blend per pair: keeps anti-aliasing but few distinct colours.
THEME7 = _palette([BLACK, CHIP, WHITE, ORANGE, _mix(BLACK, CHIP), _mix(CHIP, WHITE), _mix(CHIP, ORANGE)])
THEME4 = _palette([BLACK, CHIP, WHITE, ORANGE])


def fit(im: Image.Image, slot: int) -> Image.Image:
    """Best-looking reduction whose RLE encoding fits the stock slot."""
    w, h = im.size
    for colours in (None, 48, 32, 24, 16, 12, THEME7, 8, 6, THEME4):
        if colours is None:
            q = im
        elif isinstance(colours, int):
            q = im.quantize(colours, dither=Image.Dither.NONE).convert("RGB")
        else:
            q = im.quantize(palette=colours, dither=Image.Dither.NONE).convert("RGB")
        rows = [[to565(q.getpixel((x, y))) for x in range(w)] for y in range(h)]
        try:
            encode(rows, slot)              # fits and pads to exactly the stock length
        except ValueError:
            continue
        return q
    raise SystemExit(f"art for {w}x{h} does not fit {slot} bytes even with the 4-colour theme palette")


def theme_colour(c: int, neutral: bool = False) -> int:
    """RGB565 -> RGB565. Bright accents (any hue) -> CMF orange with the same brightness and
    saturation, so white glyphs keep their contrast; dark tints (tracks) -> neutral grey;
    neutrals unchanged. neutral=True greys every colour (for "off"/"disconnected" states)."""
    r, g, b = rgb(c)
    _h, sat, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if sat < 0.25 or v < 0.08:
        return c
    if neutral or v < 0.3:
        out = (v * (0.55 if neutral else 1.0),) * 3
    else:
        out = tuple(sat * x * v + (1 - sat) * v for x in (1.0, 90 / 255, 30 / 255))
    return to565(tuple(min(255, round(x * 255)) for x in out))


# images whose colour carries a state: shown grey instead of orange
NEUTRAL = {668}                     # link icon, "not connected" (669 = connected stays orange)


def theme(rows: list[list[int]], memo: dict[int, int], neutral: bool = False) -> list[list[int]]:
    if neutral:
        return [[theme_colour(c, True) for c in row] for row in rows]
    return [[memo[c] if c in memo else memo.setdefault(c, theme_colour(c)) for c in row] for row in rows]


def _stock_image(entry) -> Image.Image:
    _off, _size, w, h, rows = entry
    im = Image.new("RGB", (w, h))
    im.putdata([rgb(c) for row in rows for c in row])
    return im


def _themed(c) -> tuple:
    return rgb(theme_colour(to565(c)))


def _fits(im: Image.Image, slot: int) -> Image.Image | None:
    try:
        return fit(im, slot)
    except SystemExit:
        return None


def text_pass(images, out: Path) -> set[int]:
    """Re-render labels and digit sets; returns the indices written."""
    written: set[int] = set()
    skipped = 0
    for i, text in txt.load_labels().items():
        if i in ART:
            continue
        stock = _stock_image(images[i])
        if not txt.is_plain_text(stock):
            skipped += 1
            continue
        im = txt.render_label(stock, text, _themed(txt.text_colour(stock)))
        q = _fits(im, images[i][1]) if im is not None else None
        if q is None:
            skipped += 1
            continue
        q.save(out / f"{i:04d}.png")
        written.add(i)
    sets = 0
    for start in txt.digit_sets(images):
        frames = [_stock_image(images[start + k]) for k in range(14)]
        if not txt.is_plain_text(frames[3]):
            continue
        colour = _themed(txt.text_colour(frames[3]))
        for scale in (1.0, 0.95, 0.9, 0.85):
            new = txt.render_digits(frames, colour, scale)
            fitted = [_fits(im, images[start + k][1]) for k, im in enumerate(new)]
            if all(f is not None for f in fitted):
                break
        else:
            skipped += 1
            continue
        for k, q in enumerate(fitted):
            q.save(out / f"{start + k:04d}.png")
            written.add(start + k)
        sets += 1
    print(f"text: {len(written) - 14 * sets} labels + {sets} digit sets re-rendered, {skipped} left to the theme pass")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(Path(__file__).resolve().parent.parent / "research" / "ui" / "replace"))
    ap.add_argument("--no-theme", action="store_true", help="only the redrawn ART images")
    ap.add_argument("--no-text", action="store_true", help="skip the text re-render pass")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    images, _ = walk(payload(UI_BIN.read_bytes()))
    for i, fn in ART.items():
        off, size, w, h, _rows = images[i]
        im = fn()
        assert im.size == (w, h), (i, im.size, (w, h))
        fit(im, size).save(out / f"{i:04d}.png")
    print(f"{len(ART)} redrawn image(s) written to {out}")
    done_ids = set(ART)
    if not a.no_text:
        done_ids |= text_pass(images, out)
    if a.no_theme:
        return
    memo: dict[int, int] = {}
    themed = same = kept = 0
    for i, (off, size, w, h, rows) in enumerate(images):
        if i in done_ids:
            continue
        new = theme(rows, memo, i in NEUTRAL)
        if new == rows:
            same += 1
            continue
        try:
            encode(new, size)
        except ValueError:
            kept += 1
            continue
        im = Image.new("RGB", (w, h))
        im.putdata([rgb(c) for row in new for c in row])
        im.save(out / f"{i:04d}.png")
        themed += 1
    print(f"theme: {themed} recoloured, {same} already neutral, {kept} left stock (would not fit)")


if __name__ == "__main__":
    main()
