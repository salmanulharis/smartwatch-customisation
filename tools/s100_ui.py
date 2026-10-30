"""Decode / rebuild the TechLife S100 UI resource pack (menus, icons, labels, digits).

    python tools/s100_ui.py export [ui.bin] [-o research/ui] [--fw fw.bin]
    python tools/s100_ui.py build <replace_dir> [-o out.bin] [--version N]

export: one PNG per image, contact sheets of 100, and index.json (offset, size, w, h, and the
firmware locations that point at each image).
build: replaces images in place from <replace_dir>/NNNN.png (same w x h; the encoding is padded
to the stock byte length, so no firmware pointer moves), then fixes the payload CRC-32 and the
image SHA-256. Writes a file only; flashing is a separate, deliberate step.
Format: docs/ui-resource-format.md.
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

from rehash_rtl_image import image_digest

ROOT = Path(__file__).resolve().parent.parent
UI_BIN = ROOT / "research" / "firmware" / "RH288A_V000957_U0006_ui_1641738154_5635.bin"
FW_BIN = ROOT / "research" / "firmware" / "RH288A_V001319_fw_1660354713_5619.bin"
PAYLOAD = 0x600            # MP header (0x200) + Realtek image header (0x400)
FLASH_BASE = 0xACB400      # flash address of payload offset 0 (from 2176 firmware pointers)


def payload(ui: bytes) -> bytes:
    p = ui[PAYLOAD:]
    size, crc = struct.unpack_from("<II", p, 0x1C)
    if size != len(p) - 0x40 or zlib.crc32(p[0x40:]) != crc:
        raise ValueError("pack header size/CRC mismatch")
    return p


def rgb(c: int) -> tuple[int, int, int]:
    return (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)


def decode(p: bytes, off: int, max_h: int = 400):
    """Row-RLE image at payload offset: u32 row offsets (h of them, relative to the image start),
    each row = groups of [n][rep] + n big-endian RGB565 colours, each repeated rep times.
    Returns (w, h, rows, end) or None."""
    first = struct.unpack_from("<I", p, off)[0]
    if first % 4 or not 4 <= first <= max_h * 4:
        return None
    h = first // 4
    starts = list(struct.unpack_from(f"<{h}I", p, off))
    if starts != sorted(starts):
        return None
    w, rows, pos = None, [], 0
    for i in range(h):
        pos = off + starts[i]
        stop = off + starts[i + 1] if i + 1 < h else None
        px: list[int] = []
        while (pos < stop) if stop is not None else (len(px) < w):
            n, rep = p[pos], p[pos + 1]
            pos += 2
            if n == 0:
                return None
            for _ in range(n):
                px.extend([struct.unpack_from(">H", p, pos)[0]] * rep)
                pos += 2
        if w is None:
            w = len(px)
        if not 0 < len(px) == w <= 480:
            return None
        rows.append(px)
    return w, h, rows, pos


def to565(px: tuple) -> int:
    r, g, b = px[:3]
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def groups(row: list[int]) -> list[list]:
    """Runs of equal colour, then consecutive runs of equal length merged: [rep, [colours]].
    Matches the vendor encoder byte for byte on all 2,163 stock images."""
    runs: list[list[int]] = []
    for c in row:
        if runs and runs[-1][0] == c and runs[-1][1] < 255:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    out: list[list] = []
    for c, n in runs:
        if out and out[-1][0] == n and len(out[-1][1]) < 255:
            out[-1][1].append(c)
        else:
            out.append([n, [c]])
    return out


def pad(rows_groups: list[list[list]], extra: int) -> None:
    """Grow the encoding by exactly `extra` bytes (even) without changing the pixels:
    split a multi-colour group (+2), turn a 2-run into 2 literals (+2), split a run (+4)."""
    while extra > 0:
        done = False
        for gs in rows_groups:
            for k, (rep, cols) in enumerate(gs):
                if len(cols) >= 2:
                    gs[k:k + 1] = [[rep, cols[:1]], [rep, cols[1:]]]
                    extra -= 2; done = True
                elif extra >= 4 and rep >= 2:
                    gs[k:k + 1] = [[rep - 1, cols], [1, cols[:]]]
                    extra -= 4; done = True
                elif rep == 2:
                    gs[k] = [1, cols * 2]
                    extra -= 2; done = True
                if done:
                    break
            if done:
                break
        if not done:
            raise ValueError(f"cannot pad by {extra} more bytes")


def encode(rows: list[list[int]], size: int | None = None) -> bytes:
    rg = [groups(r) for r in rows]

    def blob() -> bytes:
        body = [b"".join(bytes((len(cols), rep)) + b"".join(struct.pack(">H", c) for c in cols)
                         for rep, cols in gs) for gs in rg]
        offs, o = [], 4 * len(rows)
        for b in body:
            offs.append(o)
            o += len(b)
        return struct.pack(f"<{len(rows)}I", *offs) + b"".join(body)
    out = blob()
    if size is not None and len(out) != size:
        if len(out) > size:
            raise ValueError(f"encodes to {len(out)} bytes, stock slot is {size}: simplify the art")
        pad(rg, size - len(out))
        out = blob()
    return out


# Uncompressed tail (big-endian RGB565, no header), decoded 2026-10-30 from the draw calls:
# (payload offset, width, frame height, frames). Frames are stacked vertically; picker strips
# ("- . / 0-9 :" or word lists) are drawn through 0x843A54 with the frame size from the widget.
RAW_TAIL = [
    (0x38C4FC, 24, 28, 15), (0x3913BC, 24, 28, 15),      # BreathTraining duration (cyan / white)
    (0x39627C, 86, 32, 4), (0x39B87C, 86, 32, 4),        # BreathTraining speed: -, Slow, Sooth, Fast
    (0x3A0E7C, 27, 32, 14), (0x3A6CFC, 27, 32, 14),      # CountDown / NoDisturb rollers
    (0x3ACB7C, 60, 32, 5), (0x3B167C, 60, 32, 5),        # Menu style: -, Grid, List, Grid, List
    (0x3B617C, 50, 24, 5), (0x3B905C, 50, 24, 5),        # Brightness: -, 25, 50, 75, 100
    (0x3BBF3C, 29, 24, 4), (0x3BD4FC, 29, 24, 4),        # Screen timeout: -, 5, 10, 15
    (0x3BEABC, 109, 32, 4), (0x3C57BC, 109, 32, 4),      # Vibration: -, High, Medium, Low
    (0x3CC4BC, 25, 30, 15), (0x3D1CA0, 25, 30, 15),      # NoDisturb ':' (rest unused)
    (0x3D7484, 24, 32, 15), (0x3DCE84, 24, 32, 15),      # AlarmTimeSetting rollers (orange / grey)
    (0x3E2884, 8, 24, 1),                                # orange ':' (no pointer found)
]


def raw_name(off: int) -> str:
    return f"raw_{FLASH_BASE + off:06X}"


def walk(p: bytes):
    """The compressed images are stored back to back from payload 0x40; raw RGB565 data follows."""
    off, out = 0x40, []
    while (r := decode(p, off)) is not None:
        w, h, rows, end = r
        out.append((off, end - off, w, h, rows))
        off = end
    return out, off


def export(ui_path: Path, fw_path: Path, out: Path) -> None:
    p = payload(ui_path.read_bytes())
    images, raw_start = walk(p)
    fw = fw_path.read_bytes() if fw_path.exists() else b""
    refs: dict[int, list[str]] = {}
    for pos in range(0, len(fw) - 3, 4):
        refs.setdefault(struct.unpack_from("<I", fw, pos)[0] - FLASH_BASE, []).append(hex(pos))
    (out / "img").mkdir(parents=True, exist_ok=True)
    index = []
    for i, (off, size, w, h, rows) in enumerate(images):
        im = Image.new("RGB", (w, h))
        im.putdata([rgb(c) for row in rows for c in row])
        im.save(out / "img" / f"{i:04d}.png")
        index.append({"i": i, "off": off, "flash": hex(FLASH_BASE + off), "size": size, "w": w, "h": h,
                      "fw_refs": refs.get(off, [])})
    (out / "index.json").write_text(json.dumps({"raw_start": raw_start, "payload_len": len(p),
                                                "images": index}, indent=0))
    for s in range(0, len(index), 100):
        sheet(out, index[s:s + 100]).save(out / f"sheet_{s:04d}.png")
    for off, w, fh, n in RAW_TAIL:
        h = fh * n
        im = Image.new("RGB", (w, h))
        im.putdata([rgb(c) for c in struct.unpack_from(f">{w * h}H", p, off)])
        im.save(out / "img" / f"{raw_name(off)}.png")
    linked = sum(1 for it in index if it["fw_refs"])
    print(f"{len(index)} images ({linked} pointed at directly by the firmware), raw data from {raw_start:#x}")


def sheet(out: Path, items) -> Image.Image:
    W, x, y, row_h, cells = 1300, 0, 0, 0, []
    for it in items:
        tw, th = min(it["w"], 240), min(it["h"], 280)
        if x + max(tw, 40) + 6 > W:
            x, y, row_h = 0, y + row_h + 16, 0
        cells.append((it, x, y))
        x += max(tw, 40) + 6
        row_h = max(row_h, th)
    im = Image.new("RGB", (W, y + row_h + 16), (60, 0, 60))
    d = ImageDraw.Draw(im)
    for it, x, y in cells:
        src = Image.open(out / "img" / f"{it['i']:04d}.png")
        im.paste(src.crop((0, 0, min(src.width, 240), min(src.height, 280))), (x, y + 12))
        d.text((x, y), str(it["i"]), fill=(255, 255, 0))
    return im


# The DFU code (0x82C272) limits image 0xFFFE to flash bank 5: 0x465000 bytes from 0xACB000, header
# included, so the pack can grow up to the font at 0xF30000 (532,988 bytes over stock).
MAX_IMAGE = 0x465000 - 0x400


def append_images(data: bytearray, append_dir: Path) -> dict[str, int]:
    """Append every PNG in append_dir (sorted by name) as a row-RLE image after the raw tail and fix
    the three size fields (MP header TLVs 0x04/0x14, control-header payload_len, payload header).
    Returns {name: flash address}. Images start 4-byte aligned."""
    placed: dict[str, int] = {}
    blob = bytearray()
    end = len(data) - PAYLOAD                    # payload length = offset of the first new byte
    for png in sorted(append_dir.glob("*.png")):
        pad = (-(end + len(blob))) % 4
        blob += bytes(pad)
        im = Image.open(png).convert("RGB")
        b = im.tobytes()
        px = [to565(b[k:k + 3]) for k in range(0, len(b), 3)]
        rows = [px[y * im.width:(y + 1) * im.width] for y in range(im.height)]
        enc = encode(rows)
        assert decode(enc, 0)[2] == rows
        placed[png.stem] = FLASH_BASE + end + len(blob)
        blob += enc
    data += blob
    # The DFU body (file minus MP header and 12-byte control header) must end on a word boundary:
    # pack v9 (body length 2 mod 4) was rejected at its last buffer every time (2026-10-30).
    data += bytes((-(len(data) - 0x20C)) % 16)
    image_size = len(data) - 0x200               # control header + payload, as in TLV 0x04/0x14
    if image_size > MAX_IMAGE:
        raise SystemExit(f"pack would be {image_size:#x} bytes, limit {MAX_IMAGE:#x} (DFU bank 5)")
    for tlv in (0x04, 0x14):                     # MP header TLVs (u16 type, u8 len, value)
        i = 0
        while i < 0x200:
            t, n = struct.unpack_from("<HB", data, i)
            if t == tlv:
                struct.pack_into("<I", data, i + 3, image_size)
                break
            i += 3 + n
        else:
            raise SystemExit(f"MP header TLV {tlv:#x} not found")
    struct.pack_into("<I", data, 0x208, len(data) - PAYLOAD)        # control header payload_len
    struct.pack_into("<I", data, PAYLOAD + 0x1C, len(data) - PAYLOAD - 0x40)
    return placed


def build(ui_path: Path, replace_dir: Path, out_path: Path, version: int | None,
          append_dir: Path | None = None) -> None:
    data = bytearray(ui_path.read_bytes())
    p = payload(bytes(data))
    images, _ = walk(p)
    changed = 0
    for png in sorted(replace_dir.glob("[0-9][0-9][0-9][0-9].png")):
        i = int(png.stem)
        off, size, w, h, _rows = images[i]
        im = Image.open(png).convert("RGB")
        if im.size != (w, h):
            raise SystemExit(f"{png.name}: {im.size[0]}x{im.size[1]}, stock is {w}x{h} (layout is fixed in code)")
        px = [to565(im.getpixel((x, y))) for y in range(h) for x in range(w)]
        rows = [px[y * w:(y + 1) * w] for y in range(h)]
        try:
            blob = encode(rows, size)
        except ValueError as e:
            raise SystemExit(f"{png.name}: {e}")
        assert decode(blob, 0)[2] == rows
        data[PAYLOAD + off:PAYLOAD + off + size] = blob
        changed += 1
    for off, w, fh, n in RAW_TAIL:                      # uncompressed strips: same size by definition
        png = replace_dir / f"{raw_name(off)}.png"
        if not png.exists():
            continue
        im = Image.open(png).convert("RGB")
        if im.size != (w, fh * n):
            raise SystemExit(f"{png.name}: {im.size[0]}x{im.size[1]}, stock is {w}x{fh * n}")
        b = im.tobytes()
        px = [to565(b[k:k + 3]) for k in range(0, len(b), 3)]
        data[PAYLOAD + off:PAYLOAD + off + 2 * len(px)] = struct.pack(f">{len(px)}H", *px)
        changed += 1
    placed = append_images(data, append_dir) if append_dir else {}
    pl = memoryview(data)[PAYLOAD:]
    struct.pack_into("<I", pl, 0x20, zlib.crc32(pl[0x40:]))
    img = memoryview(data)[0x200:]
    if version is not None:
        ver = struct.unpack_from("<I", img, 96)[0]
        struct.pack_into("<I", img, 96, (ver & ~(0x7FFF << 12)) | ((version & 0x7FFF) << 12))
    img[372:404] = image_digest(img)
    # self-check: every image still decodes, untouched ones are byte-identical, header checks pass
    new_p = payload(bytes(data))
    new_images, raw = walk(new_p)
    if len(new_images) != len(images) or raw != walk(p)[1]:
        raise SystemExit("rebuilt pack no longer walks like stock — not written")
    if bytes(img[372:404]) != image_digest(img):
        raise SystemExit("hash self-check failed — not written")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    if placed:
        (out_path.with_suffix(".append.json")).write_text(json.dumps({k: hex(v) for k, v in placed.items()},
                                                                      indent=1))
        print(f"{len(placed)} image(s) appended at {min(placed.values()):#x}.., map in "
              f"{out_path.with_suffix('.append.json').name}; pack grew by {len(data) - len(ui_path.read_bytes())} B")
    print(f"{changed} image(s) replaced; wrote {out_path} ({len(data)} bytes, stock images in place)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("export")
    pe.add_argument("ui", nargs="?", default=str(UI_BIN))
    pe.add_argument("--fw", default=str(FW_BIN))
    pe.add_argument("-o", "--out", default=str(ROOT / "research" / "ui"))
    pb = sub.add_parser("build")
    pb.add_argument("replace_dir")
    pb.add_argument("--ui", default=str(UI_BIN))
    pb.add_argument("-o", "--out", default=str(ROOT / "research" / "ui" / "build" / "ui_mod.bin"))
    pb.add_argument("--version", type=int, help="image revision field (header +96 bits 12..26)")
    pb.add_argument("--append", help="dir of PNGs to append after the stock data (pack growth)")
    a = ap.parse_args()
    if a.cmd == "export":
        export(Path(a.ui), Path(a.fw), Path(a.out))
    else:
        build(Path(a.ui), Path(a.replace_dir), Path(a.out), a.version, Path(a.append) if a.append else None)


if __name__ == "__main__":
    main()
