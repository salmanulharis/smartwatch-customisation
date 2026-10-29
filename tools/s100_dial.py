"""Build and upload a custom watch face ("dial") for the TechLife S100 (stock firmware).

Format and protocol: docs/custom-dial-format.md. The face is a desk clock: white on black,
12-hour time with AM/PM, weekday, date, battery, Bluetooth, steps (+ goal bar) and heart rate.

Usage (venv active, phone Bluetooth off):
    python tools/s100_dial.py build                 # writes research/dials/deskclock.bin + preview PNG
    python tools/s100_dial.py upload [file.bin] [-v]
"""
from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dial_nothing import battery_dots  # noqa: E402

W, H = 240, 280
BG = (8, 8, 8)            # near-black: 0x0000 is likely the watch's transparency key
FG = (255, 255, 255)
DIM = (90, 90, 90)
OUT_DIR = Path(__file__).resolve().parent.parent / "research" / "dials"

DIGIT_CHARS = "-./0123456789:"   # 14-frame digit sprite order
FONTS = Path("C:/Windows/Fonts")


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for name in (("bahnschrift.ttf", "segoeuib.ttf", "arialbd.ttf") if bold
                 else ("segoeui.ttf", "arial.ttf")):
        p = FONTS / name
        if p.exists():
            f = ImageFont.truetype(str(p), size)
            if name == "bahnschrift.ttf":
                try:
                    f.set_variation_by_name("Bold")
                except Exception:
                    pass
            return f
    return ImageFont.load_default()


def text_frame(w: int, h: int, text: str, size: int, color=FG) -> Image.Image:
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    f = font(size)
    box = d.textbbox((0, 0), text, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text(((w - tw) / 2 - box[0], (h - th) / 2 - box[1]), text, font=f, fill=color)
    return im


def digit_frames(w: int, h: int, size: int) -> list[Image.Image]:
    return [text_frame(w, h, c, size) for c in DIGIT_CHARS]


def battery_frames(w: int, h: int) -> list[Image.Image]:
    # firmware picks frame ceil(battery%/10) → 11 frames (0 … 100 %), no bounds check
    frames = []
    for level in range(11):
        im = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(im)
        body = (1, 2, w - 6, h - 3)
        d.rectangle(body, outline=FG, width=2)
        d.rectangle((w - 5, h // 2 - 4, w - 2, h // 2 + 3), fill=FG)
        inner_w = (body[2] - body[0] - 6)
        bar_w = inner_w // 4
        for i in range(battery_dots(level, 4)):
            x0 = body[0] + 4 + i * bar_w
            d.rectangle((x0, body[1] + 4, x0 + bar_w - 2, body[3] - 4), fill=FG)
        frames.append(im)
    return frames


def bluetooth_frames(w: int, h: int) -> list[Image.Image]:
    def bt(color):
        im = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(im)
        cx, t, b = w // 2, 2, h - 3
        m = (t + b) // 2
        q = (b - t) // 4
        pts = [(cx - 5, m - q), (cx + 5, m + q), (cx, b), (cx, t), (cx + 5, m - q), (cx - 5, m + q)]
        d.line(pts, fill=color, width=2)
        return im
    return [bt(DIM), bt(FG)]   # frame meaning unverified: assume 0 = off, 1 = connected


def step_icon(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.ellipse((2, 3, 10, 15), fill=FG)
    d.ellipse((4, 16, 9, 21), fill=FG)
    d.ellipse((13, 0, 21, 12), fill=FG)
    d.ellipse((14, 13, 19, 18), fill=FG)
    return im


def progress_frames(w: int, h: int) -> list[Image.Image]:
    frames = []
    for i in range(11):
        im = Image.new("RGB", (w, h), BG)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, outline=DIM, width=1)
        if i:
            fw = max(h, int((w - 1) * i / 10))
            d.rounded_rectangle((0, 0, fw, h - 1), radius=h // 2, fill=FG)
        frames.append(im)
    return frames


def background() -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.line((16, 204, W - 16, 204), fill=(40, 40, 40), width=1)
    # static heart symbol next to heart-rate digits
    hx, hy = 152, 219
    d.ellipse((hx, hy, hx + 8, hy + 8), fill=FG)
    d.ellipse((hx + 7, hy, hx + 15, hy + 8), fill=FG)
    d.polygon([(hx, hy + 5), (hx + 15, hy + 5), (hx + 7.5, hy + 15)], fill=FG)
    return im


# (type, x, y, frames) — layout for 240x280
def layout() -> list[tuple[int, int, int, list[Image.Image]]]:
    big = digit_frames(50, 84, 92)
    small = digit_frames(18, 28, 28)
    tiny = digit_frames(16, 26, 24)
    els = [
        (17, 0, 0, [background()]),
        (15, 14, 14, [text_frame(64, 26, d, 22) for d in ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT") * 2]),
        (9, 154, 15, bluetooth_frames(16, 24)),
        (8, 182, 17, battery_frames(42, 20)),
        (57, 6, 70, big), (58, 58, 70, big),
        (7, 112, 70, [text_frame(16, 84, ":", 80)]),
        (59, 132, 70, big), (60, 184, 70, big),
        (63, 16, 166, small), (64, 34, 166, small),
        (14, 52, 166, [text_frame(14, 28, "/", 26)]),
        (65, 66, 166, small), (66, 84, 166, small),
        (16, 178, 168, [text_frame(48, 24, t, 22) for t in ("AM", "PM", "AM", "PM")]),
        (24, 16, 215, [step_icon(24, 24)]),
    ]
    els += [(38 + i, 46 + i * 16, 214, tiny) for i in range(5)]
    els += [(35 + i, 172 + i * 16, 214, tiny) for i in range(3)]
    els += [(32, 16, 252, progress_frames(208, 10))]
    return els


def rgb565_be(im: Image.Image, keep_transparent: bool = False) -> bytes:
    """keep_transparent: emit pure black as 0x0000 (the watch's transparency key, used by hands)."""
    out = bytearray()
    raw = im.convert("RGB").tobytes()
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        if v == 0 and not keep_transparent:
            v = 0x0841           # never emit the transparency key
        out += struct.pack(">H", v)
    return bytes(out)


def paste_hand(face: Image.Image, im: Image.Image, px: int, py: int, tip: int, angle: float):
    """Preview helper: rotate an upward hand image about its pivot (w/2, tip) like the watch."""
    w, h = im.size
    size = 2 * max(h, w) + 4
    layer = Image.new("RGB", (size, size), (0, 0, 0))
    layer.paste(im, (size // 2 - w // 2, size // 2 - tip))
    layer = layer.rotate(-angle, resample=Image.BICUBIC, center=(size // 2, size // 2))
    mask = layer.convert("L").point(lambda v: 255 if v > 8 else 0)
    face.paste(layer, (px - size // 2, py - size // 2), mask)


def compose_preview(els) -> Image.Image:
    """Full face rendered with sample values (for the PNG and the type-10 thumbnail)."""
    sample = {57: "1", 58: "0", 59: "4", 60: "5", 63: "1", 64: "0", 65: "2", 66: "9"}
    face = Image.new("RGB", (W, H), BG)
    for t, x, y, frames in els:
        if t in sample:
            fr = frames[DIGIT_CHARS.index(sample[t])]
        elif t == 15:
            fr = frames[11]        # THU
        elif t == 16:
            fr = frames[2]         # AM
        elif t == 8:
            fr = frames[3]
        elif t == 9:
            fr = frames[1]
        elif t in (38, 39, 40, 41, 42):
            fr = frames[DIGIT_CHARS.index("05432"[t - 38])]
        elif t in (35, 36, 37):
            fr = frames[DIGIT_CHARS.index(" 72"[t - 35])] if t != 35 else None
        elif t == 32:
            fr = frames[5]
        else:
            fr = frames[0]
        if fr is not None:
            face.paste(fr, (x, y))
    return face


def compose_sample(els, sample: dict[int, str]) -> Image.Image:
    """Render a design with representative values (types with no sample use frame 0)."""
    pick = {15: 11, 16: 0, 8: 8, 9: 1, 20: 1, 32: 7}   # THU, AM, 71-80 % battery, BT on, cloudy, half goal
    face = Image.new("RGB", (W, H), BG)
    hands = []
    for t, x, y, frames, *opt in els:
        if t in (1, 2, 3):                       # analog hands: drawn last, rotated about x/y
            hands.append((t, x, y, frames[0], opt[0]["reserved"][4]))
            continue
        if t in (21, 33):                        # temperature / battery %, placed like the firmware:
            fw = frames[0].size[0]               # char k of n at x + ((3-n)*w >> 1) + k*w
            s = sample.get(t, "29" if t == 21 else "85")
            for k, ch in enumerate(s):
                face.paste(frames[DIGIT_CHARS.index(ch)], (x + ((3 - len(s)) * fw >> 1) + k * fw, y))
            continue
        ch = opt[0].get("sample") if opt else None
        if ch is None and t in sample:
            ch = sample[t]
        if ch is not None:
            if not ch:
                continue
            fr = frames[DIGIT_CHARS.index(ch)]
        else:
            fr = frames[min(pick.get(t, 0), len(frames) - 1)]
        face.paste(fr, (x, y))
    angles = {1: (10 + 45 / 60) * 30, 2: 45 * 6, 3: 0}   # sample time 10:45:00
    for t, x, y, im, tip in sorted(hands, key=lambda h: h[0]):
        paste_hand(face, im, x, y, tip, angles[t])
    return face


def build(out: Path, design: str = "classic") -> Path:
    if design in ("nothing", "widgets", "dashboard", "duo", "duo2", "duo3", "duo4", "duo5", "duo6", "blob", "dusk", "world", "widgetsdot"):
        mod = __import__(f"dial_{design}")
        els = mod.layout()
        face = compose_sample(els, mod.SAMPLE)
    else:
        els = layout()
        face = compose_preview(els)
    thumb = Image.new("RGB", (240, 240), BG)
    small = face.resize((206, 240), Image.LANCZOS)
    thumb.paste(small, (17, 0))
    els.append((10, 0, 0, [thumb]))
    els.sort(key=lambda e: e[0])

    n = len(els)
    data_off = (n + 1) * 24 + 2
    blocks: list[bytes] = []
    seen: dict[bytes, int] = {}
    records = bytearray()
    for t, x, y, frames, *opt in els:
        o = opt[0] if opt else {}
        w, h = frames[0].size
        blob = b"".join(rgb565_be(f, o.get("transparent", False)) for f in frames)
        if blob in seen:
            off = seen[blob]
        else:
            off = data_off + sum(len(b) for b in blocks)
            seen[blob] = off
            blocks.append(blob)
        records += struct.pack("<HHIHHHHB7s", t, w, off, h, x, y, 0, len(frames),
                               o.get("reserved", b"\0" * 7))

    body = bytes(records) + b"\0\0" + b"".join(blocks)
    # The watch fails the upload ("CRC check failed") when the last 4 KB sector is within one
    # packet of being full (seen with 524190 B = 3998 mod 4096). Trailing padding avoids it.
    rem = (24 + len(body)) % 4096
    if rem == 0 or rem > 4096 - 256:
        body += bytes(4096 - rem + 128)
    header = bytearray(b"\xff" * 4 + struct.pack("<I", 24 + len(body) - 24) + b"\0" * 4
                       + struct.pack("<HH", W, H) + bytes([0, 1, 0xFF]) + b"\xff" * 5)
    struct.pack_into("<I", header, 8, zlib.crc32(body) & 0xFFFFFFFF)
    blob = bytes(header) + body
    if len(blob) > 0x100000:
        raise SystemExit(f"dial too large: {len(blob)} bytes")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    face.save(out.with_suffix(".png"))
    print(f"built {out} ({len(blob)} bytes, {n} elements), preview {out.with_suffix('.png')}")
    return out


def _print_progress(sent: int, total: int) -> None:
    print(f"\r  sent {sent}/{total}", end="", flush=True)
    if sent == total:
        print()


async def send_dial(w, blob: bytes, progress=_print_progress, log=print) -> bool:
    """Transfer a dial file over an already bound S100 connection."""
    await w.write(b"\x26\x01")
    cfg = await w.expect(b"\x26\x01", timeout=5)
    if not cfg or len(cfg) < 16:
        log("no dial config reply"); return False
    width, height = struct.unpack_from(">HH", cfg, 6)
    max_size = struct.unpack_from(">I", cfg, 11)[0]
    log(f"watch dial config: {width}x{height}, max {max_size} bytes")
    if (width, height) != (W, H) or len(blob) > max_size:
        log("dial does not fit this watch"); return False

    await w.write(b"\x26\x02")
    if not await w.expect(b"\x26\x02", timeout=10):
        log("watch not ready (no 26 02)"); return False

    step = w.max_len - 3
    packets = [blob[i:i + step] for i in range(0, len(blob), step)]
    start = 0
    for attempt in range(4):
        for seq in range(start, len(packets)):
            await w.write(bytes([0x27]) + struct.pack(">H", seq) + packets[seq], big=True)
            if (seq + 1) * step // 4096 != seq * step // 4096:
                await w.expect(b"\x26\x03\x04", timeout=3)
            elif seq % 10 == 9:
                await asyncio.sleep(0.04)
            progress(seq + 1, len(packets))
        await asyncio.sleep(3)
        await w.write(b"\x26\x03\x00")
        reply = None
        while reply is None or reply[:3] == b"\x26\x03\x04":
            reply = await w.expect(b"\x26\x03", timeout=15)
            if reply is None:
                break
        if reply is None:
            log("no final reply from watch"); return False
        code = reply[2]
        if code == 0:
            await w.sync_time()
            log("upload OK — the watch should now show the new face (time synced from this PC)")
            return True
        if code == 3 and len(reply) >= 5:
            start = struct.unpack_from(">H", reply, 3)[0]
            log(f"watch asks to resend from packet {start}")
            continue
        log({1: "CRC check failed", 2: "dial too large"}.get(code, f"error {reply.hex()}"))
        return False
    return False


async def upload(path: Path, verbose: bool) -> bool:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from s100 import S100

    blob = path.read_bytes()
    async with S100(verbose=verbose) as w:
        return await send_dial(w, blob)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("build")
    pb.add_argument("design", nargs="?", choices=["classic", "nothing", "widgets", "dashboard", "duo", "duo2", "duo3", "duo4", "duo5", "duo6", "blob", "dusk", "world", "widgetsdot"], default="nothing")
    pb.add_argument("-o", "--out")
    pu = sub.add_parser("upload")
    pu.add_argument("file", nargs="?", default=str(OUT_DIR / "nothing.bin"))
    pu.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()
    if a.cmd == "build":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        build(Path(a.out) if a.out else OUT_DIR / f"{a.design}.bin", a.design)
    else:
        ok = asyncio.run(upload(Path(a.file), a.verbose))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
