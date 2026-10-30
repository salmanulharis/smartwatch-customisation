"""CMF-style picker/roller strips for the S100 UI pack (the 19 uncompressed strips in the raw tail).

    python tools/ui_pickers.py [-o research/ui/replace]
    python tools/s100_ui.py build research/ui/replace [--append ...] --version N

The strips are drawn by 0x843A54 one frame per character (layout in tools/s100_ui.RAW_TAIL). Each
picker has a normal strip and a highlight strip for the selected row. Here: highlight = CMF orange,
normal = the stock grey/white; numbers and words in Bahnschrift (5x7 dots if DOTS is set).
Strips are uncompressed, so any art fits; frame sizes stay stock. The screen-timeout picker's third
value ("15") is shown as an infinity sign, because firmware mod b2_timeout makes it "always on".
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from dial_nothing import Canvas
from s100_ui import FLASH_BASE, RAW_TAIL, UI_BIN, payload, raw_name, rgb
from ui_cmf import ORANGE
from ui_cmf_text import bands, font, ink, text_colour
from ui_dots import DOT57

ROOT = Path(__file__).resolve().parent.parent
SS = 4
DOTS = False        # dot-matrix numbers were tried (UI rev 6) and dropped: numbers use Bahnschrift
DIGITS = list("-./0123456789:") + [""]          # 15th frame of the long strips is blank
# word strips by flash address (frame 0 is always blank)
WORDS = {
    0xE6167C: ["", "Slow", "Calm", "Fast"], 0xE66C7C: ["", "Slow", "Calm", "Fast"],
    0xE77F7C: ["", "Grid", "List", "Grid", "List"], 0xE7CA7C: ["", "Grid", "List", "Grid", "List"],
    0xE8157C: ["", "25", "50", "75", "100"], 0xE8445C: ["", "25", "50", "75", "100"],
    0xE8733C: ["", "5", "10", "inf"], 0xE888FC: ["", "5", "10", "inf"],
    0xE89EBC: ["", "High", "Medium", "Low"], 0xE90BBC: ["", "High", "Medium", "Low"],
    0xEADC84: [":"],
}


def stock_strip(p: bytes, off: int, w: int, fh: int, n: int) -> list[Image.Image]:
    import struct
    px = struct.unpack_from(f">{w * fh * n}H", p, off)
    im = Image.new("RGB", (w, fh * n))
    im.putdata([rgb(c) for c in px])
    return [im.crop((0, k * fh, w, (k + 1) * fh)) for k in range(n)]


def is_highlight(colour) -> bool:
    r, g, b = colour
    return max(r, g, b) - min(r, g, b) > 60          # cyan / orange vs white / grey


def ink_metrics(frames: list[Image.Image]) -> tuple[int, int]:
    """(top, baseline) of the tallest ink in the strip."""
    tops, bases = [], []
    for f in frames:
        b = bands(ink(f))
        if b:
            tops.append(b[0][0]); bases.append(b[-1][1])
    return (min(tops), max(bases)) if tops else (0, frames[0].size[1])


def dots(text: str, w: int, h: int, top: int, base: int, colour) -> Image.Image:
    c = Canvas(w, h)
    c.im.paste((0, 0, 0), (0, 0, *c.im.size))
    rows = 7
    n = len(text)
    pitch = min((base - top) * 0.8 / rows, w / (n * 6 - 1 + 0.6))   # stock glyphs fill the frame
    total = (n * 6 - 1) * pitch
    y0 = (top + base) / 2 - rows * pitch / 2
    for k, ch in enumerate(text):
        c.glyph(DOT57[ch], (w - total) / 2 + k * 6 * pitch, y0, pitch, pitch * 0.86, colour)
    return c.image()


def infinity(w: int, h: int, top: int, base: int, colour) -> Image.Image:
    big = Image.new("RGB", (w * SS, h * SS))
    d = ImageDraw.Draw(big)
    ih = (base - top) * 0.62 * SS
    cy = (top + base) / 2 * SS
    r = ih / 2
    for cx in (w * SS / 2 - r * 0.95, w * SS / 2 + r * 0.95):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=colour, width=int(SS * 2.2))
    return big.resize((w, h), Image.LANCZOS)


def word(text: str, w: int, h: int, top: int, base: int, colour) -> Image.Image:
    big = Image.new("RGB", (w * SS, h * SS))
    d = ImageDraw.Draw(big)
    target = (base - top) * SS * 0.92
    px = target
    while True:
        f = font(px / SS * 1.38, "SemiBold")
        x0, y0, x1, y1 = d.textbbox((0, 0), text, font=f)
        if (x1 - x0) <= w * SS * 0.96 or px < 6:
            break
        px *= 0.95
    # baseline: cap height of the text sits on the stock baseline
    d.text(((w * SS - (x1 - x0)) / 2 - x0, base * SS - y1), text, font=f, fill=colour)
    return big.resize((w, h), Image.LANCZOS)


def strip(frames: list[Image.Image], labels: list[str], colour) -> Image.Image:
    w, fh = frames[0].size
    top, base = ink_metrics(frames)
    out = Image.new("RGB", (w, fh * len(frames)))
    for k, lab in enumerate(labels[:len(frames)]):
        if not lab:
            im = Image.new("RGB", (w, fh))
        elif lab == "inf":
            im = infinity(w, fh, top, base, colour)
        elif DOTS and all(ch in DOT57 for ch in lab):
            im = dots(lab, w, fh, top, base, colour)
        else:
            im = word(lab, w, fh, top, base, colour)
        out.paste(im, (0, k * fh))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", type=Path, default=ROOT / "research" / "ui" / "replace")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    p = payload(UI_BIN.read_bytes())
    for off, w, fh, n in RAW_TAIL:
        frames = stock_strip(p, off, w, fh, n)
        addr = FLASH_BASE + off
        labels = WORDS.get(addr, DIGITS)
        stock_col = text_colour(max(frames, key=lambda f: sum(1 for v in ink(f) for x in v if x)))
        colour = ORANGE if is_highlight(stock_col) else stock_col
        strip(frames, labels, colour).save(a.out / f"{raw_name(off)}.png")
        print(f"{raw_name(off)}: {w}x{fh} x{n} {'highlight' if colour == ORANGE else 'normal'}")


if __name__ == "__main__":
    main()
