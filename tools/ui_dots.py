"""Dot-matrix numerals for the S100 UI pack (CMF/Nothing style), on top of an existing restyle.

Dots need more bytes than the stock digit slots hold, so converted sets are APPENDED to the pack
(pack growth, docs/ui-upgrade-plan.md) and the app's frame pointers are moved to the new frames:

    python tools/ui_dots.py frames --sets 1479,485 [-o research/ui/v5_append]
    python tools/s100_ui.py build research/ui/replace --append research/ui/v5_append -o ui_v5.bin
    python tools/ui_dots.py patches research/ui/build/ui_v5.append.json   # app patches (stdout)

`frames` redraws every listed 14-frame digit set (`- . / 0-9 :`) as round dots on a 5x7 grid
(DOT57 below). Frame size, ink
height, baseline and colour stay as in the base art, so the firmware draws them in the same place.
`patches` lists every word in the app image that points at a converted stock frame, with its new
address (frame tables in rodata and literal pools), in tools/s100_mods.py format.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from PIL import Image

from dial_nothing import Canvas
from s100_ui import FLASH_BASE, FW_BIN, UI_BIN, payload, rgb, walk
from ui_cmf_text import DIGITS, bands, ink, text_colour

ROOT = Path(__file__).resolve().parent.parent
FW_BASE = 0x0080DE00
# Digit sets on screens that are not drawn at boot (see docs/ui-upgrade-plan.md §9): heart rate,
# weather, stopwatch + alarm, charging, low power, sleep, activity, workout, goal popups.
# Watch-face sets (73, 154, 317, 346, 372, 412) come only after this has been proven on the watch.
DEFAULT_SETS = [1479, 485, 581, 994, 1009, 1024, 1629, 1300, 1822, 1931, 1076, 1095, 1112, 1129]


# 5x7 dot numerals, CMF/Nothing style: round zero without a slash, open shapes, large dots.
DOT57 = {
    "0": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    "-": [".....", ".....", ".....", ".###.", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".....", "..#.."],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
    ":": [".....", ".....", "..#..", ".....", "..#..", ".....", "....."],
}


def base_image(i: int, entry, base: Path) -> Image.Image:
    p = base / f"{i:04d}.png"
    if p.exists():
        return Image.open(p).convert("RGB")
    _, _, w, h, rows = entry
    im = Image.new("RGB", (w, h))
    im.putdata([rgb(c) for row in rows for c in row])
    return im


def dot_set(frames: list[Image.Image]) -> list[Image.Image]:
    """Redraw one digit set as dots, on the base art's baseline, ink height and colour."""
    zero = frames[3]
    b = bands(ink(zero))
    top, base = b[0][0], b[-1][1]
    ink_h = base - top
    colour = text_colour(zero)
    rows, cols = 7, 5
    maxw = min(f.size[0] for f in frames[3:13])
    pitch = min(ink_h / rows, maxw / (cols + 0.2))
    diam = pitch * 0.86
    out = []
    for ch, f in zip(DIGITS, frames):
        w, h = f.size
        c = Canvas(w, h)
        c.im.paste((0, 0, 0), (0, 0, *c.im.size))
        c.glyph(DOT57[ch], (w - cols * pitch) / 2, base - rows * pitch, pitch, diam, colour)
        # few colours keep the appended RLE small; dots stay round (edge blend kept)
        out.append(c.image().quantize(6, dither=Image.Dither.NONE).convert("RGB"))
    return out


def frames_cmd(a) -> None:
    a.out.mkdir(parents=True, exist_ok=True)
    for p in a.out.glob("d*.png"):
        p.unlink()
    images, _ = walk(payload(UI_BIN.read_bytes()))
    for s in a.sets:
        frames = [base_image(s + k, images[s + k], a.base) for k in range(14)]
        for k, im in enumerate(dot_set(frames)):
            im.save(a.out / f"d{s:04d}_{k:02d}.png")       # name = stock image this frame replaces
        print(f"set {s}-{s + 13}: {frames[3].size[0]}x{frames[3].size[1]} -> dots")


def table_patches(fw: bytes, append_map: dict[str, int]) -> list[tuple[int, str, str]]:
    """(address, old hex, new hex) for every aligned app word pointing at a replaced stock frame."""
    idx = json.loads((ROOT / "research" / "ui" / "index.json").read_text())["images"]
    moved = {}
    for name, new in append_map.items():
        if name.startswith("d") and "_" in name:
            s, k = name[1:].split("_")
            moved[int(idx[int(s) + int(k)]["flash"], 16)] = new
    out = []
    for pos in range(0, len(fw) - 3, 4):
        v = struct.unpack_from("<I", fw, pos)[0]
        if v in moved:
            out.append((FW_BASE + pos, struct.pack("<I", v).hex(), struct.pack("<I", moved[v]).hex()))
    return out


def patches_cmd(a) -> None:
    amap = {k: int(v, 16) for k, v in json.loads(Path(a.map).read_text()).items()}
    for addr, old, new in table_patches(FW_BIN.read_bytes(), amap):
        print(f'    (0x{addr:08X}, "{old}", "{new}"),')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("frames")
    pf.add_argument("--sets", type=lambda v: [int(x) for x in v.split(",")], default=DEFAULT_SETS)
    pf.add_argument("--base", type=Path, default=ROOT / "research" / "ui" / "replace",
                    help="existing replacement art to take size, colour and baseline from")
    pf.add_argument("-o", "--out", type=Path, default=ROOT / "research" / "ui" / "v5_append")
    pp = sub.add_parser("patches")
    pp.add_argument("map", help="<pack>.append.json written by s100_ui.py build --append")
    a = ap.parse_args()
    frames_cmd(a) if a.cmd == "frames" else patches_cmd(a)


if __name__ == "__main__":
    main()
