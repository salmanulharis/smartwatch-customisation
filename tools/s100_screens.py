"""Offline screen previewer for the TechLife S100: runs the stock firmware's own screen code.

Each screen's constructor and build function are executed in Unicorn (Thumb-2) against the app
image, with ROM helpers stubbed in Python and the LCD renderer skipped. The widget list the
firmware builds is then drawn with the UI pack's images, so a preview shows exactly what the
firmware would draw — including the effect of patched coordinates or tables in a modded image.

    python tools/s100_screens.py list
    python tools/s100_screens.py render StatusBarScreenUI [-o out.png] [--fw app.bin] [--ui pack.bin]
    python tools/s100_screens.py all [-o research/screens] [--fw ...] [--ui ...]

Nothing is sent to the watch. Text is drawn with a stand-in font (the watch font at flash
0xF30000 is not available offline), and live data (time, steps, ...) is whatever the RAM init
image holds (mostly zero) unless set with --set ADDR=VAL.
Firmware map: docs/ui-framework-notes.md.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, \
    UC_HOOK_MEM_UNMAPPED
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s100_ui  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FW_BIN = s100_ui.FW_BIN
UI_BIN = s100_ui.UI_BIN
FW_BASE = 0x0080DE00            # flash address of firmware file offset 0
FONT0_W = FW_BIN.read_bytes()[0x0088E38C - FW_BASE:][:96]      # font 0 advance, chars 0x20-0x7F
UI_BASE = s100_ui.FLASH_BASE - s100_ui.PAYLOAD
RAMCODE = (0x00890898, 0x00208400, 0x3914)     # startup copies (flash, ram, size), see 0x829A64
RAMDATA = (0x008941AC, 0x0020BD14, 0x3324)
BSS = (0x0020F038, 0xA4E4)
DESC_FIRST, DESC_LAST, DESC_STEP = 0x0020D74C, 0x0020E744, None   # descriptor table (RAM)
INSTANCES = {"cur": (0x0020D698, 0x00211F44), "sub": (0x0020D6D0, 0x00212918),
             "par": (0x0020D708, 0x002132EC)}
CUR_SCREEN = 0x00210760
LANG_PTR = 0x0020FBE8           # -> language block (byte +1 = language code), set at runtime
LANG_BLOCK = 0x0021A000         # unused RAM (after .bss) used for that block in the emulator
RENDER_STUBS = (0x00208E74, 0x00209290, 0x002096F8,   # band renderers: skipped
                0x00841476, 0x008415AC,                 # gui_update tail calls (render + LCD/DMA)
                0x0084648C)                             # screen-enter wake (touch/LCD over I2C)
# gui_switch's resource check (0x830678) reads flash through the SPI driver, which cannot work
# offline; on the watch it passes (otherwise every switch would show the OTA-fail screen)
OK_STUBS = (0x00830678,)
RET = 0x00FFFFF0                # magic return address
W, H = 240, 280

# ROM routines the GUI code calls (addresses from the SDK rom_symbol table)
ROM = {0x3A1FC: "memcmp", 0x3A254: "strlen", 0x3A292: "memcpy", 0x3A31C: "memcpy", 0x3A380: "aeabi_memset",
       0x3A390: "memclr", 0x3A394: "memset", 0x3A3D4: "memclr", 0x3A3D8: "memset", 0x3B5EC: "strcmp",
       0x3A07E: "uldivmod", 0x3C528: "d2f", 0x3C58C: "dadd", 0x3C6F4: "ddiv", 0x3CA7C: "d2uiz",
       0x3CAD6: "i2d", 0x3CB04: "ui2d", 0x3CBA4: "dmul", 0x3CE0C: "drsub", 0x3CE24: "dsub",
       0x3CFF8: "f2d", 0x3C9A4: "cdcmpeq", 0x3CB2C: "cdcmple", 0x3CDA0: "cdrcmple",
       0x134D2: "ret1", 0x13518: "ret1", 0x1353A: "ret1", 0x13560: "ret1", 0x13582: "ret1",
       0x135C0: "timer_state"}


def descriptors(fw: bytes) -> dict[str, int]:
    """name -> RAM address of each UI_MenuTypeDef (0x38 bytes, name pointer at +0)."""
    out = {}
    lo, hi = RAMDATA[1], RAMDATA[1] + RAMDATA[2]
    for ram in range(DESC_FIRST, DESC_LAST + 4, 4):
        if not lo <= ram < hi - 0x38:
            continue
        name_ptr, = struct.unpack_from("<I", fw, RAMDATA[0] - FW_BASE + ram - lo)
        if not FW_BASE <= name_ptr < FW_BASE + len(fw):
            continue
        s = fw[name_ptr - FW_BASE:name_ptr - FW_BASE + 48].split(b"\0")[0]
        if s.endswith(b"UI") or b"ScreenUI" in s or s.startswith(b"WatchPreview") or s == b"WatchOnlinePreview":
            try:
                out.setdefault(s.decode(), ram)
            except UnicodeDecodeError:
                pass
    return out


class Sim:
    def __init__(self, fw: bytes, ui: bytes, pokes: dict[int, int] | None = None, verbose=False, lang=2):
        self.fw, self.ui, self.verbose = fw, ui, verbose
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        mu.mem_map(0, 0x100000)                       # ROM (stubbed)
        mu.mem_map(0x00200000, 0x40000)               # RAM
        mu.mem_map(0x00800000, 0x00800000)            # external flash (XIP)
        mu.mem_map(0x40000000, 0x00100000)            # peripherals (read as zero)
        mu.mem_map(0xE0000000, 0x00100000)            # system control space
        mu.mem_write(FW_BASE, fw)
        mu.mem_write(UI_BASE, ui)
        mu.mem_write(RAMCODE[1], fw[RAMCODE[0] - FW_BASE:RAMCODE[0] - FW_BASE + RAMCODE[2]])
        mu.mem_write(RAMDATA[1], fw[RAMDATA[0] - FW_BASE:RAMDATA[0] - FW_BASE + RAMDATA[2]])
        self.w32(LANG_PTR, LANG_BLOCK)
        mu.mem_write(LANG_BLOCK, bytes([0, lang]) + bytes(0x1FE))
        for a, v in (pokes or {}).items():
            mu.mem_write(a, bytes([v & 0xFF]))
        for name, (inst, widgets) in INSTANCES.items():
            self.w32(inst + 0x24, widgets)
        mu.hook_add(UC_HOOK_CODE, self._rom, begin=0, end=0xFFFFF)
        for a in RENDER_STUBS:
            mu.hook_add(UC_HOOK_CODE, self._ret, begin=a, end=a)
        for a in OK_STUBS:
            mu.hook_add(UC_HOOK_CODE, self._ret1, begin=a, end=a)
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)
        self.missing: dict[int, int] = {}

    # --- memory helpers
    def r32(self, a): return struct.unpack("<I", self.mu.mem_read(a, 4))[0]
    def w32(self, a, v): self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    def reg(self, r): return self.mu.reg_read(r)

    def _unmapped(self, mu, access, addr, size, value, data):
        if self.verbose:
            print(f"  unmapped access {addr:#x} at pc {mu.reg_read(UC_ARM_REG_PC):#x}")
        return False

    def _ret1(self, mu, addr, size, data):
        mu.reg_write(UC_ARM_REG_R0, 1)
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR) | 1)

    def _ret(self, mu, addr, size, data):
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR) | 1)

    def _d(self, lo, hi): return struct.unpack("<d", struct.pack("<II", lo, hi))[0]

    def _setd(self, x):
        lo, hi = struct.unpack("<II", struct.pack("<d", x))
        self.mu.reg_write(UC_ARM_REG_R0, lo)
        self.mu.reg_write(UC_ARM_REG_R1, hi)

    def _rom(self, mu, addr, size, data):
        op = ROM.get(addr)
        r0, r1, r2, r3 = (mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        if op in ("memcpy",):
            if r2:
                mu.mem_write(r0, bytes(mu.mem_read(r1, r2)))
        elif op == "memset":                    # (dst, c, n)
            if r2:
                mu.mem_write(r0, bytes([r1 & 0xFF]) * r2)
        elif op == "aeabi_memset":              # (dst, n, c)
            if r1:
                mu.mem_write(r0, bytes([r2 & 0xFF]) * r1)
        elif op == "memclr":
            if r1:
                mu.mem_write(r0, bytes(r1))
        elif op == "memcmp":
            a, b = bytes(mu.mem_read(r0, r2)), bytes(mu.mem_read(r1, r2))
            mu.reg_write(UC_ARM_REG_R0, 0 if a == b else (1 if a > b else 0xFFFFFFFF))
        elif op in ("strlen", "strcmp"):
            s = bytes(mu.mem_read(r0, 512)).split(b"\0")[0]
            if op == "strlen":
                mu.reg_write(UC_ARM_REG_R0, len(s))
            else:
                t = bytes(mu.mem_read(r1, 512)).split(b"\0")[0]
                mu.reg_write(UC_ARM_REG_R0, 0 if s == t else (1 if s > t else 0xFFFFFFFF))
        elif op == "uldivmod":
            n, d = r0 | r1 << 32, r2 | r3 << 32
            q, r = (n // d, n % d) if d else (0, 0)
            for reg, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                              (q & 0xFFFFFFFF, q >> 32, r & 0xFFFFFFFF, r >> 32)):
                mu.reg_write(reg, v)
        elif op in ("dadd", "dsub", "drsub", "dmul", "ddiv"):
            a, b = self._d(r0, r1), self._d(r2, r3)
            self._setd({"dadd": a + b, "dsub": a - b, "drsub": b - a, "dmul": a * b,
                        "ddiv": a / b if b else 0.0}[op])
        elif op in ("i2d", "ui2d"):
            self._setd(float(struct.unpack("<i", struct.pack("<I", r0))[0] if op == "i2d" else r0))
        elif op == "f2d":
            self._setd(struct.unpack("<f", struct.pack("<I", r0))[0])
        elif op == "d2f":
            mu.reg_write(UC_ARM_REG_R0, struct.unpack("<I", struct.pack("<f", self._d(r0, r1)))[0])
        elif op == "d2uiz":
            mu.reg_write(UC_ARM_REG_R0, max(0, min(int(self._d(r0, r1)), 0xFFFFFFFF)))
        elif op in ("cdcmpeq", "cdcmple", "cdrcmple"):
            a, b = self._d(r0, r1), self._d(r2, r3)
            if op == "cdrcmple":
                a, b = b, a
            n, z, c = a < b, a == b, a >= b
            cpsr = mu.reg_read(UC_ARM_REG_CPSR) & 0x0FFFFFFF
            mu.reg_write(UC_ARM_REG_CPSR, cpsr | (n << 31) | (z << 30) | (c << 29))
        elif op == "ret1":
            mu.reg_write(UC_ARM_REG_R0, 1)
        elif op == "ret0":
            mu.reg_write(UC_ARM_REG_R0, 0)
        elif op == "timer_state":               # os_timer_state_get(handle, &state): not active
            if r1:
                mu.mem_write(r1, bytes(4))
            mu.reg_write(UC_ARM_REG_R0, 1)
        else:
            self.missing[addr] = self.missing.get(addr, 0) + 1
            mu.reg_write(UC_ARM_REG_R0, 0)
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR) | 1)

    def call(self, fn: int, *args: int, limit: int = 3_000_000) -> int:
        mu = self.mu
        for reg, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args[:4]):
            mu.reg_write(reg, v)
        sp = 0x00203400 - 0x40
        for i, v in enumerate(args[4:]):
            self.w32(sp + 4 * i, v)
        mu.reg_write(UC_ARM_REG_SP, sp)
        mu.reg_write(UC_ARM_REG_LR, RET | 1)
        start = fn | 1
        for _ in range(200):
            try:
                mu.emu_start(start, RET, count=limit)
                break
            except UcError:
                pc = mu.reg_read(UC_ARM_REG_PC)
                if pc >= 0x100000:
                    raise
                # call through a function pointer that is only set at runtime (NULL here): return
                key = ("null", mu.reg_read(UC_ARM_REG_LR)) if pc < 0x100 else pc
                self.missing[key] = self.missing.get(key, 0) + 1
                mu.reg_write(UC_ARM_REG_R0, 0)
                start = mu.reg_read(UC_ARM_REG_LR) | 1
        return mu.reg_read(UC_ARM_REG_R0)

    def enter(self, desc: int) -> None:
        """Make `desc` the current screen and run its constructor (which builds via gui_update)."""
        self.w32(CUR_SCREEN, desc)
        ctor = self.r32(desc + 0x14)
        try:
            self.call(ctor & ~1, 4, 0)
        except UcError as e:
            print(f"  constructor stopped: {e} at {self.reg(UC_ARM_REG_PC):#x}")

    def widgets(self, which="cur") -> list[dict]:
        inst, arr = INSTANCES[which]
        arr = self.r32(inst + 0x24) or arr
        cap = self.mu.mem_read(inst + 0x33, 1)[0] or 37   # the renderer draws +0x33 widgets; slots past it
        out = []                                           # can still hold the previous screen's widgets
        for i in range(min(cap, 37)):
            b = bytes(self.mu.mem_read(arr + i * 0x44, 0x44))
            typ = b[0x1D]
            if not typ:
                continue
            x, y = struct.unpack_from("<hh", b, 0)
            w, h = struct.unpack_from("<HH", b, 8)
            out.append(dict(i=i, type=typ, x=x, y=y, w=w, h=h, data=struct.unpack_from("<I", b, 0xC)[0],
                            color=struct.unpack_from("<I", b, 0x18)[0], mode=b[0x1C], key=b[0x1F],
                            packed=b[0x21], raw=b))
        return out

    def touch_areas(self) -> list[tuple]:
        out = []
        for i in range(15):
            x, y, w, h, cb = struct.unpack_from("<hhhhI", bytes(self.mu.mem_read(0x00213CC0 + 16 * i, 16)))
            en = self.mu.mem_read(0x00213CC0 + 16 * i + 12, 1)[0]
            if w and h:
                out.append((x, y, w, h, cb, en))
        return out


# ---------------------------------------------------------------- navigation
SWITCHES = {0x00844B1C: "switch", 0x00844D2E: "slide<", 0x00844CF6: "slide>", 0x00844DB6: "slide v",
            0x00844D6C: "slide ^", 0x0084236C: "screen off"}
GESTURES = {"swipe R->L": 6, "swipe L->R": 7, "swipe up": 8, "swipe down": 9}
EVENT = 0x0021A400              # scratch RAM for a synthetic touch event
# runtime state the key-action dispatcher (0x84329C) checks before acting: state byte >= 3,
# a "ready" flag and an app-state flag; set as on a running, awake watch
NAV_POKES = {0x0020D244: 3, 0x0021401F: 1, 0x0020CBC0: 1}


def navigate(sim: Sim, desc: int, gesture: str) -> str:
    """Feed one gesture ("swipe ...", "key short", "key long") to the current screen's real handler
    and report where the firmware would go."""
    names = {v: k for k, v in descriptors(sim.fw).items()}
    hit: list[str] = []

    def hook(mu, addr, size, data):
        r0, r1 = mu.reg_read(UC_ARM_REG_R0), mu.reg_read(UC_ARM_REG_R1)
        tgt = r0 if SWITCHES[addr] == "switch" else r1
        hit.append(f"{SWITCHES[addr]} {names.get(tgt, hex(tgt))}" if SWITCHES[addr] != "screen off"
                   else "screen off")
        mu.emu_stop()
    hs = [sim.mu.hook_add(UC_HOOK_CODE, hook, begin=a, end=a) for a in SWITCHES]
    try:
        if gesture.startswith("key"):
            fn = sim.r32(desc + 0x28) & ~1
            sim.call(fn, 2 if gesture == "key short" else 1, 1)     # (press class, button id 1)
        else:
            dx, dy = {6: (60, 0), 7: (-60, 0), 8: (0, -60), 9: (0, 60)}[GESTURES[gesture]]
            ev = struct.pack("<BBhhhhH", GESTURES[gesture], 0, dx, dy, 120, 140, 20)
            sim.mu.mem_write(EVENT, ev + bytes(16))
            sim.call(sim.r32(desc + 0x10) & ~1, EVENT)
    except UcError as e:
        hit.append(f"(emulation stopped: {e})")
    finally:
        for h in hs:
            sim.mu.hook_del(h)
    return hit[0] if hit else "-"


# ---------------------------------------------------------------- drawing
class Art:
    """Pack images by flash address; optional replacement PNGs (same w x h) override stock."""

    def __init__(self, ui: bytes, replace: Path | None):
        self.p = s100_ui.payload(ui)
        self.index = {}
        idx = json.loads((ROOT / "research" / "ui" / "index.json").read_text())
        for e in idx["images"]:
            self.index[int(e["flash"], 16)] = e
        self.by_i = {e["i"]: e for e in idx["images"]}
        self.replace = replace
        self.stock_len = idx["payload_len"]
        self.raw_start = idx["raw_start"]
        self.cache: dict[int, Image.Image] = {}

    def image(self, addr: int, w: int, h: int, packed: bool) -> Image.Image | None:
        if addr in self.cache:
            return self.cache[addr]
        im = None
        e = self.index.get(addr)
        if e is not None:
            p = self.replace / f"{e['i']:04d}.png" if self.replace else None
            if p and p.exists():
                im = Image.open(p).convert("RGB")
            else:
                d = s100_ui.decode(self.p, addr - s100_ui.FLASH_BASE)
                if d:
                    dw, dh, rows, _ = d
                    im = Image.new("RGB", (dw, dh))
                    im.putdata([s100_ui.rgb(c) for r in rows for c in r])
        elif addr >= s100_ui.FLASH_BASE + self.stock_len and addr < s100_ui.FLASH_BASE + len(self.p):
            d = s100_ui.decode(self.p, addr - s100_ui.FLASH_BASE)     # appended (pack growth) image
            if d:
                dw, dh, rows, _ = d
                im = Image.new("RGB", (dw, dh))
                im.putdata([s100_ui.rgb(c) for r in rows for c in r])
        elif w and h and s100_ui.FLASH_BASE + self.raw_start <= addr < s100_ui.FLASH_BASE + self.stock_len:
            o = addr - s100_ui.FLASH_BASE
            raw = self.p[o:o + w * h * 2]
            if len(raw) == w * h * 2:          # uncompressed tail image (big-endian RGB565)
                im = Image.new("RGB", (w, h))
                im.putdata([s100_ui.rgb(c) for c in struct.unpack(f">{w * h}H", raw)])
        self.cache[addr] = im
        return im

    def by_index(self, i: int) -> Image.Image:
        e = self.by_i[i]
        return self.image(int(e["flash"], 16), e["w"], e["h"], True)


def font(px: int) -> ImageFont.FreeTypeFont:
    for f in ("C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            pass
    return ImageFont.load_default()


def rgb24(c: int) -> tuple:
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


DIGITS = "-./0123456789:"


def draw_raw_strip(img: Image.Image, art: "Art", wd: dict, s: bytes, x: int, y: int) -> None:
    """Uncompressed picker strip (0x843A54): +0xC points at the '0' frame, frames are w x fh
    (fh = +0x2C if set, else h) stacked vertically; '-' '.' '/' sit 3..1 frames before '0'."""
    w = wd["w"]
    fh = struct.unpack_from("<h", wd["raw"], 0x2C)[0] or wd["h"]
    for k, ch in enumerate(s.decode("ascii", "replace")):
        i = DIGITS.find(ch)
        if i < 0:
            continue
        im = art.image(wd["data"] + (i - 3) * w * fh * 2, w, fh, False)
        if im is not None:
            img.paste(im, (x + k * w, y), key_mask(im))


def key_mask(im: Image.Image) -> Image.Image:
    """Black (0x0000) is the blitter's transparent colour."""
    return im.convert("L").point(lambda v: 255 if v else 0) if im.mode == "RGB" else None


def draw(sim: Sim, art: Art, widgets: list[dict], dx=0, dy=0, canvas=None, outline=False) -> Image.Image:
    img = canvas or Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for wd in widgets:
        x, y, t = wd["x"] + dx, wd["y"] + dy, wd["type"]
        if t in (1, 2):
            im = art.image(wd["data"], wd["w"], wd["h"], wd["packed"])
            if im is None:
                d.rectangle([x, y, x + max(wd["w"], 1) - 1, y + max(wd["h"], 1) - 1], outline=(255, 0, 255))
                continue
            img.paste(im, (x, y), None if wd["key"] == 1 else key_mask(im))
        elif t == 5:   # sprite digits: string at +0x14, frames "-./0-9:" are consecutive pack images
            s = bytes(sim.mu.mem_read(struct.unpack_from("<I", wd["raw"], 0x14)[0], 20)).split(b"\0")[0]
            base = art.index.get(wd["data"])
            table = struct.unpack_from("<I", wd["raw"], 0x24)[0]     # optional frame-address table
            if base is None and not table and not wd["packed"]:
                draw_raw_strip(img, art, wd, s, x, y)
                continue
            cx = x
            for ch in s.decode("ascii", "replace"):
                k = DIGITS.find(ch)
                if k < 0 or (base is None and not table):
                    cx += wd["w"]
                    continue
                if table:
                    fa = sim.r32(table + 4 * k)
                    e = art.index.get(fa)
                    im = art.by_index(e["i"]) if e else art.image(fa, 0, 0, True)
                else:
                    im = art.by_index(base["i"] + k)
                if im is None:
                    cx += wd["w"]
                    continue
                img.paste(im, (cx, y), key_mask(im))
                cx += im.width
        elif t == 3:
            try:
                s = bytes(sim.mu.mem_read(wd["data"], 200)).split(b"\0")[0].decode("utf-8", "replace")
            except UcError:
                s = "?"
            size = 24 if wd["mode"] <= 1 else 16 * wd["mode"]
            col = rgb24(wd["color"]) if wd["color"] else (255, 255, 255)
            if wd["raw"][0x20] and wd["mode"] <= 1 and s.isascii():
                # font 0 as the watch lays it out: stored y = top of the 24 px cell, advance from the
                # app's width table, and nothing below y + h (the band renderer skips the widget there)
                layer = Image.new("RGB", (W, H))
                ld = ImageDraw.Draw(layer)
                cx = x
                for ch in s:
                    ld.text((cx, y + 2), ch, fill=col, font=font(20))
                    cx += FONT0_W[ord(ch) - 32] if 32 <= ord(ch) < 128 else 12
                clip = Image.new("L", (W, H), 0)
                ImageDraw.Draw(clip).rectangle([x, y, W, y + max(wd["h"], 1) - 1], fill=255)
                img.paste(layer, (0, 0), Image.composite(clip, Image.new("L", (W, H), 0), layer.convert("L")))
            else:
                d.multiline_text((x, y), s, fill=col, font=font(max(12, size - 4)))
        elif t == 7:
            n, arr = wd["mode"], wd["data"]
            for k in range(min(n, 64)):
                rx, ry, rw, rh, c = struct.unpack("<hhhhH", bytes(sim.mu.mem_read(arr + 10 * k, 10)))
                if rw <= 0 or rh <= 0:
                    continue
                d.rectangle([rx + dx, ry + dy, rx + dx + rw - 1, ry + dy + rh - 1], fill=s100_ui.rgb(c))
        elif t == 4:
            d.rectangle([x, y, x + 3, y + 3], fill=(255, 128, 0))
        if outline:
            d.rectangle([x, y, x + max(wd["w"], 1) - 1, y + max(wd["h"], 1) - 1], outline=(255, 0, 255))
    return img


def render(name: str, fw: bytes, ui: bytes, replace: Path | None, pokes: dict, outline=False, verbose=False,
           lang=2):
    descs = descriptors(fw)
    if name not in descs:
        raise SystemExit(f"unknown screen {name}; try: list")
    sim = Sim(fw, ui, pokes, verbose, lang)
    sim.enter(descs[name])
    ws = sim.widgets("cur")
    img = draw(sim, Art(ui, replace), ws, outline=outline)
    return img, ws, sim


def apply_mod(fw: bytes, name: str) -> bytes:
    """Apply an s100_mods patch set (checked against the original bytes) without re-hashing."""
    import s100_mods
    data = bytearray(fw)
    patches = s100_mods.MODS[name][1]
    for addr, old, new in (patches() if callable(patches) else patches):
        old_b, new_b = bytes.fromhex(old.replace(" ", "")), bytes.fromhex(new.replace(" ", ""))
        off = addr - FW_BASE
        if data[off:off + len(old_b)] != old_b:
            raise SystemExit(f"{name}: bytes at {addr:#x} don't match the input image")
        if off + len(new_b) > len(data):
            data.extend(bytes(off + len(new_b) - len(data)))
        data[off:off + len(new_b)] = new_b
    return bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["list", "render", "all", "nav"])
    ap.add_argument("screen", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--fw", type=Path, default=FW_BIN)
    ap.add_argument("--mod", help="apply a tools/s100_mods.py patch set to --fw in memory first")
    ap.add_argument("--ui", type=Path, default=UI_BIN)
    ap.add_argument("--replace", type=Path, help="dir of NNNN.png replacement art")
    ap.add_argument("--set", action="append", default=[], help="poke RAM byte ADDR=VAL (hex ok)")
    ap.add_argument("--lang", type=lambda v: int(v, 0), default=2,
                    help="language code (2 English, 0x15 Thai, 0x63 Vietnamese, ...)")
    ap.add_argument("--outline", action="store_true", help="outline every widget")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    fw, ui = a.fw.read_bytes(), a.ui.read_bytes()
    if a.mod:
        fw = apply_mod(fw, a.mod)
    pokes = {int(k, 0): int(v, 0) for k, v in (s.split("=") for s in a.set)}
    if a.cmd == "list":
        for n, d in sorted(descriptors(fw).items(), key=lambda kv: kv[1]):
            print(f"{d:#010x}  {n}")
        return
    if a.cmd == "nav":
        descs = descriptors(fw)
        for n in ([a.screen] if a.screen else sorted(descs)):
            row = []
            for g in list(GESTURES) + ["key short", "key long"]:
                sim = Sim(fw, ui, {**NAV_POKES, **pokes}, a.verbose, a.lang)
                sim.enter(descs[n])
                row.append(f"{g}: {navigate(sim, descs[n], g)}")
            print(n + "\n  " + "\n  ".join(row))
        return
    names = [a.screen] if a.cmd == "render" else sorted(descriptors(fw))
    out = Path(a.out or (f"{a.screen}.png" if a.cmd == "render" else ROOT / "research" / "screens"))
    if a.cmd == "all":
        out.mkdir(parents=True, exist_ok=True)
    for n in names:
        try:
            img, ws, sim = render(n, fw, ui, a.replace, pokes, a.outline, a.verbose, a.lang)
        except Exception as e:                     # keep going in batch mode
            print(f"{n}: FAILED {type(e).__name__}: {e}")
            continue
        path = out if a.cmd == "render" else out / f"{n}.png"
        img.resize((W * 2, H * 2), Image.NEAREST).save(path)
        print(f"{n}: {len(ws)} widgets -> {path}")
        if a.verbose:
            for wd in ws:
                print(f"  #{wd['i']:2} type {wd['type']} ({wd['x']},{wd['y']}) {wd['w']}x{wd['h']} "
                      f"data {wd['data']:#x} mode {wd['mode']} key {wd['key']}")
            for t in sim.touch_areas():
                print(f"  touch ({t[0]},{t[1]}) {t[2]}x{t[3]} cb {t[4]:#x} en {t[5]}")
            if sim.missing:
                print("  unstubbed ROM calls:", {(f"{k:#x}" if isinstance(k, int) else f"null from {k[1]:#x}"): v for k, v in sim.missing.items()})


if __name__ == "__main__":
    main()
