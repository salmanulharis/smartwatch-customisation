"""Interactive firmware preview for the S100 Companion (tools/s100_app.py, "Firmware preview" tab).

Runs a built app image + UI pack in the offline emulator of tools/s100_screens.py: the firmware's own
screen, touch and button code decides what happens, nothing is sent to the watch. Taps, swipes,
button presses and the screen-off timer are fed to the current screen's real handlers; switches and
slides go through the firmware's gui_switch.

Limits (same as s100_screens.py): text uses a stand-in font, sensors / Bluetooth / the custom watch
face in external flash are not emulated (a stock dial is shown), animations are not played.
"""
from __future__ import annotations

import io
import struct
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

import s100_screens as S

ROOT = Path(__file__).resolve().parent.parent
SET = 0x0020BE84
GUI_SWITCH, GUI_UPDATE, SCREEN_OFF_TIMER, SCREEN_OFF = 0x00844B1C, 0x00209642, 0x0084236C, 0x008464FA
SLIDES = (0x00844D2E, 0x00844CF6, 0x00844DB6, 0x00844D6C)        # target in r1 (0 = none)
GESTURE = {"left": 6, "right": 7, "up": 8, "down": 9}             # finger direction
FACE = "WatchScreenD2640001UI"
MASK = Image.new("L", (S.W, S.H), 0)
ImageDraw.Draw(MASK).rounded_rectangle([0, 0, S.W - 1, S.H - 1], radius=40, fill=255)


def builds() -> dict:
    """Firmware images and UI packs that can be previewed, newest first."""
    def files(pattern):
        return sorted((p for p in ROOT.glob(pattern) if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    fws = [str(p.relative_to(ROOT)) for p in files("research/mods/*.bin")] + [str(S.FW_BIN.relative_to(ROOT))]
    uis = [str(p.relative_to(ROOT)) for p in files("research/ui/build/ui_v*.bin")] + [str(S.UI_BIN.relative_to(ROOT))]
    return {"firmware": fws, "ui": uis}


def _inside(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if ROOT.resolve() not in p.parents or p.suffix != ".bin" or not p.is_file():
        raise ValueError(f"not a build file: {rel}")
    return p


class Preview:
    def __init__(self, fw_rel: str, ui_rel: str, data: dict | None = None):
        self.lock = threading.Lock()
        self.fw_rel, self.ui_rel = fw_rel, ui_rel
        fw, ui = _inside(fw_rel).read_bytes(), _inside(ui_rel).read_bytes()
        self.art = S.Art(ui, None)
        self.sim = S.Sim(fw, ui, dict(S.NAV_POKES))
        self.desc = S.descriptors(fw)
        self.names = {v: k for k, v in self.desc.items()}
        self.events: list[str] = []
        self.off = False
        self._stop = False
        mu = self.sim.mu
        mu.hook_add(UC_HOOK_CODE, self._on_switch, begin=GUI_SWITCH, end=GUI_SWITCH)
        mu.hook_add(UC_HOOK_CODE, self._on_off, begin=SCREEN_OFF, end=SCREEN_OFF)
        self._pending: int | None = None
        for a in SLIDES:
            mu.hook_add(UC_HOOK_CODE, self._on_slide, begin=a, end=a)
        self.syms = self._ext_symbols(fw)
        self.t_p = self.syms.get("t_p")
        self.set_data(data or {})
        self._run(lambda: self.sim.enter(self.desc[FACE]))

    # ---- emulator hooks
    def _on_switch(self, mu, *_):
        self.events.append("→ " + self.names.get(mu.reg_read(UC_ARM_REG_R0), hex(mu.reg_read(UC_ARM_REG_R0))))

    def _on_off(self, mu, *_):
        self.off = True
        self.events.append("screen off")
        mu.emu_stop()

    def _on_slide(self, mu, *_):
        tgt = mu.reg_read(UC_ARM_REG_R1)
        if tgt:
            self._pending = tgt                          # finished below with a real gui_switch
        mu.emu_stop()

    def _run(self, fn):
        self._pending = None
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — keep the session alive
            self.events.append(f"(emulation stopped: {type(e).__name__})")
        if self._pending:
            tgt, self._pending = self._pending, None
            self.sim.call(GUI_SWITCH, tgt)

    # ---- state shown on the screens
    def set_data(self, d: dict) -> None:
        sim = self.sim
        t = time.localtime()
        hour, minute = int(d.get("hour", t.tm_hour)), int(d.get("minute", t.tm_min))
        sim.mu.mem_write(0x0020BF16, struct.pack("<HBBBBB", t.tm_year, t.tm_mon, t.tm_mday, hour % 24, minute % 60, 0))
        pokes = {SET + 0x109: int(d.get("battery", 64)), SET + 0xFA: 10, SET + 0x188: 75, SET + 0x11C: 3,
                 0x0020D154 + 0xDC: 1, 0x0020D154 + 0xDB: 1, 0x0020BFC2: int(d.get("temp", 24)) & 0x7F,
                 0x0020BFB1: 3, 0x00210236: 1 if d.get("charging") else 0,
                 SET + 0x2BD: 1 if d.get("aod") else 0, SET + 0x66: 1 if d.get("h12") else 0}
        for a, v in pokes.items():
            sim.mu.mem_write(a, bytes([v & 0xFF]))
        sim.mu.mem_write(SET + 0x14, struct.pack("<I", int(d.get("steps", 6842))))
        # from r1341 our settings are a record (ext.c t_p), not the stock bytes 0x2BC-0x2BF
        if self.t_p:
            rec = sim.call(self.t_p) + 4                     # prefs_t: magic, wake, aod, dock, haptic_off
            sim.mu.mem_write(rec + 1, bytes([1 if d.get("aod") else 0]))

    def _ext_symbols(self, fw: bytes) -> dict:
        """Symbols of firmware/s100_ext/build/ext.elf, only if that build is the one in `fw` (its .tail
        bytes are in the image); else {} (an older image: the legacy settings bytes still apply)."""
        build = ROOT / "firmware" / "s100_ext" / "build"
        tail = build / "tail.bin"
        if not tail.exists():
            return {}
        t = tail.read_bytes()
        off = 0x008974D0 - S.FW_BASE
        if fw[off:off + len(t)] != t:
            return {}
        import subprocess
        nm = Path(r"C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\14.2 rel1\bin\arm-none-eabi-nm.exe")
        try:
            out = subprocess.run([str(nm), str(build / "ext.elf")], capture_output=True, text=True, timeout=20).stdout
        except Exception:  # noqa: BLE001
            return {}
        return {l.split()[2]: int(l.split()[0], 16) for l in out.splitlines() if len(l.split()) == 3}

    # ---- input
    def _cur(self) -> int:
        return self.sim.r32(S.CUR_SCREEN)

    def _wake(self) -> bool:
        if not self.off:
            return False
        self.off = False
        self.events.append("wake")
        self._run(lambda: self.sim.call(GUI_SWITCH, self.desc[FACE]))
        return True

    def tap(self, x: int, y: int, long: bool = False) -> None:
        with self.lock:
            if self._wake():
                return
            ev = struct.pack("<BBhhhhH", 3 if long else 2, 0, 0, 0, S.W - int(x), int(y), 20) + bytes(16)
            self.sim.mu.mem_write(S.EVENT, ev)
            self._run(lambda: self.sim.call(self.sim.r32(self._cur() + 0x10) & ~1, S.EVENT))

    def swipe(self, direction: str) -> None:
        with self.lock:
            if self._wake():
                return
            g = GESTURE[direction]
            dx, dy = {6: (60, 0), 7: (-60, 0), 8: (0, -60), 9: (0, 60)}[g]
            self.sim.mu.mem_write(S.EVENT, struct.pack("<BBhhhhH", g, 0, dx, dy, 120, 140, 20) + bytes(16))
            self._run(lambda: self.sim.call(self.sim.r32(self._cur() + 0x10) & ~1, S.EVENT))

    def button(self, long: bool = False) -> None:
        with self.lock:
            if self._wake():
                return
            fn = self.sim.r32(self._cur() + 0x28) & ~1
            if fn:
                self._run(lambda: self.sim.call(fn, 1 if long else 2, 1))

    def message(self, text: str) -> None:
        """A phone message as the watch receives it (C5 notification text, UTF-16BE, 80 chars):
        NAV|... frames, CFG|... settings, or a plain notification. Needs the matching ext.elf."""
        nav_check = self.syms.get("nav_check")
        if not nav_check:
            raise ValueError("messages need the build this image came from (firmware/s100_ext/build)")
        with self.lock:
            self.off = False
            t = text.encode("utf-16-be")[:160]
            self.sim.mu.mem_write(0x0021A800, bytes([len(t)]) + t)
            self.events.append("msg " + text[:40])
            self._run(lambda: self.sim.call(nav_check, 0x0021A800))

    def timeout(self) -> None:
        """The screen-off timer firing (always-on display when enabled, else screen off)."""
        with self.lock:
            if not self.off:
                self._run(lambda: self.sim.call(SCREEN_OFF_TIMER))

    def go(self, name: str) -> None:
        with self.lock:
            if name not in self.desc:
                raise ValueError(f"unknown screen {name}")
            self.off = False
            self._run(lambda: self.sim.call(GUI_SWITCH, self.desc[name]))

    def update(self, data: dict) -> None:
        with self.lock:
            self.set_data(data)
            if not self.off:
                self._run(lambda: self.sim.call(GUI_UPDATE, self._cur(), 0, 0, 0, 0, 0, 0, 0))

    # ---- output
    def png(self) -> bytes:
        with self.lock:
            if self.off:
                im = Image.new("RGB", (S.W, S.H))
            else:
                im = S.draw(self.sim, self.art, self.sim.widgets("cur"))
            out = Image.new("RGB", (S.W, S.H), (24, 24, 26))
            out.paste(im, (0, 0), MASK)
            buf = io.BytesIO()
            out.resize((S.W * 2, S.H * 2), Image.LANCZOS).save(buf, "PNG")
            return buf.getvalue()

    def status(self) -> dict:
        with self.lock:
            return {"screen": "screen off" if self.off else self.names.get(self._cur(), hex(self._cur())),
                    "events": self.events[-12:], "firmware": self.fw_rel, "ui": self.ui_rel,
                    "messages": bool(self.syms.get("nav_check")),
                    "screens": sorted(self.desc)}
