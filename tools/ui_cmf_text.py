"""CMF-style text for the S100 UI pack: re-render text labels and digit sprites in Bahnschrift.

Labels (tools/ui_labels.json, read from the stock images with Windows OCR and checked by eye) and
14-frame digit sets (`- . / 0-9 :`) keep the stock image size, ink height, line positions and
alignment, so they sit exactly where the stock text was. Colour = the themed stock text colour.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/bahnschrift.ttf"
LABELS = Path(__file__).with_name("ui_labels.json")
DIGITS = "-./0123456789:"
SS = 4


def font(px: float, style: str = "Regular") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, max(4, round(px * SS)))
    try:
        f.set_variation_by_name(style)
    except (OSError, ValueError):
        pass
    return f


def lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def ink(im: Image.Image, thr: int = 40):
    """Ink mask rows/cols of a text image on black."""
    w, h = im.size
    px = im.load()
    return [[lum(px[x, y]) > thr for x in range(w)] for y in range(h)]


def is_plain_text(im: Image.Image) -> bool:
    """Black background, one text colour family (white/grey OR one hue), no filled panels."""
    w, h = im.size
    px = im.load()
    bright_neutral = bright_colour = panel = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            l = lum((r, g, b))
            if l < 12:
                continue
            chroma = max(r, g, b) - min(r, g, b)
            if l > 110:
                if chroma > 60:
                    bright_colour += 1
                else:
                    bright_neutral += 1
            elif 25 < l < 80 and chroma < 25:
                panel += 1
    if bright_neutral and bright_colour and min(bright_neutral, bright_colour) > 4:
        return False
    return panel < 0.25 * w * h


def text_colour(im: Image.Image):
    px = im.load()
    w, h = im.size
    return max((px[x, y] for y in range(h) for x in range(w)), key=lum)


def bands(mask) -> list[tuple[int, int]]:
    out, start = [], None
    for y, row in enumerate(mask):
        on = any(row)
        if on and start is None:
            start = y
        elif not on and start is not None:
            out.append((start, y))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def cols(mask, y0, y1):
    xs = [x for y in range(y0, y1) for x, v in enumerate(mask[y]) if v]
    return (min(xs), max(xs) + 1) if xs else (0, 0)


def ink_box(text: str, f: ImageFont.FreeTypeFont):
    return ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)


def sized_font(text: str, target_h: float, max_w: float):
    """Font whose ink height for `text` equals target_h; condensed or smaller if too wide."""
    for style in ("Regular", "SemiCondensed", "Condensed"):
        px = target_h * 1.4
        for _ in range(6):
            x0, y0, x1, y1 = ink_box(text, font(px, style))
            hh = (y1 - y0) / SS
            if hh <= 0:
                break
            px *= target_h / hh
        f = font(px, style)
        x0, y0, x1, y1 = ink_box(text, f)
        if (x1 - x0) / SS <= max_w:
            return f
    while (ink_box(text, f)[2] - ink_box(text, f)[0]) / SS > max_w and f.size > 2 * SS:
        f = ImageFont.truetype(FONT, f.size - SS)
        f.set_variation_by_name("Condensed")
    return f


def render_label(stock: Image.Image, text: str, colour) -> Image.Image | None:
    w, h = stock.size
    mask = ink(stock)
    lines = [t.strip() for t in text.split("/")] if " / " in text else [text]
    bs = bands(mask)
    if len(bs) != len(lines):
        if len(bs) < len(lines):
            return None
        # merge bands (e.g. dots of i/j or accents) down to the line count by closing smallest gaps
        while len(bs) > len(lines):
            gaps = [bs[i + 1][0] - bs[i][1] for i in range(len(bs) - 1)]
            k = gaps.index(min(gaps))
            bs[k:k + 2] = [(bs[k][0], bs[k + 1][1])]
    big = Image.new("RGB", (w * SS, h * SS), (0, 0, 0))
    d = ImageDraw.Draw(big)
    for line, (y0, y1) in zip(lines, bs):
        x0, x1 = cols(mask, y0, y1)
        left, right = x0, w - x1
        align = "c" if abs(left - right) <= 4 and left > 2 else ("r" if right <= 2 and left > 6 else "l")
        avail = w - (2 * min(left, right) if align == "c" else (left if align == "l" else right)) - 1
        f = sized_font(line, y1 - y0, avail)
        bx0, by0, bx1, by1 = ink_box(line, f)
        tw = bx1 - bx0
        if align == "l":
            tx = x0 * SS - bx0
        elif align == "r":
            tx = x1 * SS - tw - bx0
        else:
            tx = (w * SS - tw) / 2 - bx0
        d.text((tx, y0 * SS - by0), line, font=f, fill=colour)
    return big.resize((w, h), Image.LANCZOS)


def render_digits(stocks: list[Image.Image], colour, scale: float = 1.0) -> list[Image.Image]:
    """14 frames '- . / 0-9 :' with a shared size and baseline taken from the stock '0'
    (scale < 1 shrinks the whole set, still on the stock baseline)."""
    w0, h0 = stocks[3].size
    m0 = ink(stocks[3])
    b0 = bands(m0)
    top, base = b0[0][0], b0[-1][1]
    maxw = min(im.size[0] for im in stocks[3:13])
    f = sized_font("0", (base - top) * scale, maxw)
    out = []
    for ch, st in zip(DIGITS, stocks):
        w, h = st.size
        big = Image.new("RGB", (w * SS, h * SS), (0, 0, 0))
        d = ImageDraw.Draw(big)
        bx0, by0, bx1, by1 = ink_box(ch, f)
        zx0, zy0, zx1, zy1 = ink_box("0", f)
        tx = (w * SS - (bx1 - bx0)) / 2 - bx0
        ty = base * SS - zy1                                  # shared baseline with '0'
        d.text((tx, ty), ch, font=f, fill=colour)
        out.append(big.resize((w, h), Image.LANCZOS))
    return out


def digit_sets(images) -> list[int]:
    """Start indices of 14-image runs (one height) that look like '- . / 0-9 :' by glyph shape:
    a thin '-', a low '.', a tall '0', a '1' narrower than '0', and a two-part ':'."""
    def mask(entry):
        return [[lum(rgb565(c)) > 60 for c in row] for row in entry[4]]

    def ink_w(m):
        xs = [x for row in m for x, v in enumerate(row) if v]
        return max(xs) - min(xs) + 1 if xs else 0

    starts, i = [], 0
    while i + 14 <= len(images):
        run = images[i:i + 14]
        ok = False
        if len({r[3] for r in run}) == 1 and run[3][3] >= 9:
            h = run[0][3]
            m = [mask(r) for r in run]
            b = [bands(x) for x in m]
            ok = (len(b[0]) == 1 and b[0][0][1] - b[0][0][0] <= h * 0.3
                  and len(b[1]) == 1 and b[1][0][0] > h * 0.45
                  and len(b[13]) == 2
                  and len(b[3]) == 1 and b[3][0][1] - b[3][0][0] >= h * 0.45
                  and ink_w(m[4]) < ink_w(m[3]))
        if ok:
            starts.append(i)
            i += 14
        else:
            i += 1
    return starts


def rgb565(c: int) -> tuple[int, int, int]:
    return (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)


def load_labels() -> dict[int, str]:
    return {int(k): v for k, v in json.loads(LABELS.read_text(encoding="utf-8")).items()}
