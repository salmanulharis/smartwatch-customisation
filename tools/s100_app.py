"""Local GUI for the realme TechLife Watch S100: watch faces + stock-firmware controls.

Opens a browser UI served only on 127.0.0.1. Everything it sends to the watch is a command that
has been verified on this watch with tools/s100.py / tools/s100_dial.py (see
docs/TechLife-S100.md §7b). It never writes to the firmware-update (DFU/OTA) service; it only
reads the installed app revision from it.

Usage (venv active, phone Bluetooth off so realme Fit doesn't hold the watch):
    python tools/s100_app.py [--port 8100] [--no-browser]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime
import io
import json
import math
import re
import struct
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bleak import BleakClient, BleakScanner
from PIL import Image

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from s100 import ADDRESS, S100, TYPE_CALL, TYPE_OTHER, TYPE_SMS  # noqa: E402
from s100_dial import DIGIT_CHARS, H, W, paste_hand, send_dial  # noqa: E402

FAV_DIR = TOOLS.parent / "research" / "dials" / "favourites"
HTML = TOOLS / "s100_app.html"
CONFIG = Path.home() / ".s100_app.json"

BATTERY_POLL_S = 60
APP_VERSION_CHAR = "0000ffd4-0000-1000-8000-00805f9b34fb"   # Realtek OTA service, read-only use
WORLD_CLOCK_TYPE = 71
WORLD_CLOCK_MIN_REV = 1323                                    # firmware mod b5_worldclock
MAX_RECORDS = 71                                              # stock parser limit (0x83B2E6)
BUTTONS = {0x07: "play/pause", 0x08: "next", 0x09: "previous", 0x0D: "volume up",
           0x0E: "volume down", 0x0A: "find phone", 0x12: "mute"}
MEDIA_VK = {0x07: 0xB3, 0x08: 0xB0, 0x09: 0xB1, 0x0D: 0xAF, 0x0E: 0xAE, 0x12: 0xAD}
DEFAULTS = {"address": ADDRESS, "twelve_hour": False, "media_keys": False, "city": "",
            "profile": {"height_cm": 170, "weight_kg": 65, "age": 30, "male": True,
                        "step_goal": 10000, "fahrenheit": False}}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(CONFIG.read_text(encoding="utf-8"))
        for k in cfg:
            if k in saved:
                cfg[k] = {**cfg[k], **saved[k]} if isinstance(cfg[k], dict) else saved[k]
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- watch faces

class Face:
    """A dial file: validated header/records and decoded sprites for the live preview."""

    def __init__(self, path: Path, title: str = "", notes: str = ""):
        self.path, self.name = path, path.stem
        self.title, self.notes = title or path.stem, notes
        self.blob = path.read_bytes()
        self.problems: list[str] = []
        self.records: list[tuple] = []
        self._frames: dict[int, list[Image.Image]] = {}
        self._check()

    @property
    def needs_mod(self) -> bool:
        return any(r[0] == WORLD_CLOCK_TYPE for r in self.records)

    def _check(self) -> None:
        b = self.blob
        if len(b) < 72:
            self.problems.append("file too short"); return
        size, crc = struct.unpack_from("<II", b, 4)
        w, h = struct.unpack_from("<HH", b, 12)
        if (w, h) != (W, H):
            self.problems.append(f"made for {w}x{h}, watch is {W}x{H}")
        if size != len(b) - 24:
            self.problems.append("size field does not match the file")
        if zlib.crc32(b[24:]) & 0xFFFFFFFF != crc:
            self.problems.append("CRC mismatch (file damaged)")
        for i in range(MAX_RECORDS + 1):
            if 24 + (i + 1) * 24 > len(b):
                self.problems.append("record table runs past the end of the file"); return
            rec = struct.unpack_from("<HHIHHHHB7s", b, 24 + i * 24)
            t, rw, off, rh, n = rec[0], rec[1], rec[2], rec[3], rec[7]
            if t == 0:
                break
            if i == MAX_RECORDS:
                self.problems.append(f"more than {MAX_RECORDS} elements"); return
            if t > MAX_RECORDS:
                self.problems.append(f"element type {t} > 71: the watch ignores it and everything after it")
                return
            if off + rw * rh * 2 * max(n, 1) > len(b):
                self.problems.append(f"element {i} image data runs past the end of the file"); return
            self.records.append(rec)

    def frames(self, i: int) -> list[Image.Image]:
        if i not in self._frames:
            t, w, off, h, *_, n, _rsv = self.records[i]
            out = []
            for k in range(max(n, 1)):
                raw = self.blob[off + k * w * h * 2: off + (k + 1) * w * h * 2]
                px = struct.unpack(f">{w * h}H", raw)
                rgba = bytearray()
                for v in px:
                    r, g, bl = (v >> 11) << 3, ((v >> 5) & 0x3F) << 2, (v & 0x1F) << 3
                    rgba += bytes((r | r >> 5, g | g >> 6, bl | bl >> 5, 0 if v == 0 else 255))
                out.append(Image.frombytes("RGBA", (w, h), bytes(rgba)))
            self._frames[i] = out
        return self._frames[i]


def _digit(frames, ch):
    return frames[DIGIT_CHARS.index(ch)] if ch in DIGIT_CHARS and len(frames) == 14 else None


def render(face: Face, live: dict) -> bytes:
    """Draw the face the way the stock renderer does, using the watch's current values.

    Values the watch does not report over BLE (steps, heart rate) are drawn as the watch shows
    them with no data: steps 0, heart rate blank.
    """
    now: datetime.datetime = live["now"]
    twelve = live["twelve_hour"]
    hour = now.hour - 12 if twelve and now.hour > 12 else now.hour
    digits = {57: f"{hour:02d}"[0], 58: f"{hour:02d}"[1], 59: f"{now.minute:02d}"[0],
              60: f"{now.minute:02d}"[1], 63: f"{now.month:02d}"[0], 64: f"{now.month:02d}"[1],
              65: f"{now.day:02d}"[0], 66: f"{now.day:02d}"[1]}
    steps = f"{live['steps']:5d}"
    digits.update({38 + k: steps[k] for k in range(5)})
    battery = live["battery"]
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    hands = []
    order = sorted(range(len(face.records)), key=lambda i: face.records[i][0] != 17)   # background first
    for i in order:
        rec = face.records[i]
        t, w, _off, h, x, y, _z, n, rsv = rec
        if t == 10 or t in (35, 36, 37):
            continue
        fr = face.frames(i)
        if t in (1, 2, 3):
            hands.append((t, x, y, fr[0], rsv[4]))
            continue
        img = None
        if t in digits:
            img = _digit(fr, digits[t])
        elif t == WORLD_CLOCK_TYPE:
            off_min, pos = struct.unpack_from("<h", rsv, 1)[0], rsv[3]
            hh, mm = divmod((now.hour * 60 + now.minute + off_min) % 1440, 60)
            if twelve and hh > 12:
                hh -= 12
            img = _digit(fr, f"{hh:02d}{mm:02d}"[pos & 3])
        elif t == 15:
            img = fr[(7 + (now.isoweekday() % 7)) % len(fr)]
        elif t == 16:
            img = fr[min((2 if now.hour < 12 else 3), len(fr) - 1)]
        elif t == 8:
            lvl = 10 if battery is None else min(10, math.ceil(battery / 10))
            img = fr[min(lvl, len(fr) - 1)]
        elif t == 9:
            img = fr[min(1 if live["connected"] else 0, len(fr) - 1)]
        elif t == 20:
            img = fr[min(live["weather"][0] if live["weather"] else 1, len(fr) - 1)]
        elif t in (21, 33):          # temperature / exact battery %: one text object, 3-char field
            if t == 21:
                temp = live["weather"][1] if live["weather"] else None
                s = "--" if temp is None else str(temp)[-3:]
            else:
                s = "" if battery is None else str(min(battery, 100))
            for k, ch in enumerate(s):
                g = _digit(fr, ch)
                if g:
                    canvas.alpha_composite(g, (x + ((3 - len(s)) * w >> 1) + k * w, y))
            continue
        elif t == 22:
            img = fr[min(1 if live["fahrenheit"] else 0, len(fr) - 1)]
        elif t == 32:
            img = fr[0]
        else:
            img = fr[0]
        if img is not None:
            canvas.alpha_composite(img, (x, y))
    face_rgb = canvas.convert("RGB")
    angles = {1: (now.hour % 12 + now.minute / 60) * 30, 2: (now.minute + now.second / 60) * 6, 3: now.second * 6}
    for t, x, y, im, tip in sorted(hands):
        paste_hand(face_rgb, im.convert("RGB"), x, y, tip, angles[t])
    buf = io.BytesIO()
    face_rgb.save(buf, "PNG")
    return buf.getvalue()


def load_faces() -> dict[str, Face]:
    notes = {}
    readme = FAV_DIR / "README.md"
    if readme.exists():
        for line in readme.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*(.+?)\s*\|\s*`([^`]+\.bin)`\s*\|\s*(.+?)\s*\|\s*$", line)
            if m:
                notes[m.group(2)] = (m.group(1), re.sub(r"\*\*|`", "", m.group(3)))
    faces = {}
    for p in sorted(FAV_DIR.glob("*.bin")):
        title, note = notes.get(p.name, (p.stem, ""))
        faces[p.stem] = Face(p, title, note)
    return faces


# ---------------------------------------------------------------- watch link

class Busy(Exception):
    pass


class WatchLink(S100):
    """S100 session that routes watch-initiated events (d1 xx) and settings reports (7e) away from
    command replies."""

    def __init__(self, address: str, on_event, on_disconnect, on_settings=None):
        super().__init__(address)
        self.client = BleakClient(address, timeout=20, disconnected_callback=lambda _c: on_disconnect())
        self.on_event = on_event
        self.on_settings = on_settings

    def _on_notify(self, _sender, data: bytearray):
        data = bytes(data)
        if data[:1] == b"\xd1":
            self.on_event(data)
        elif data[:2] == b"\x7e\x01" and self.on_settings:
            self.on_settings(data)
        else:
            self.queue.put_nowait(data)


# Watch settings report (firmware c7, ext.c t_report): 7E 01 aod tap raise press dock h12 vib battery
# [aod_level] (the last byte from firmware c8 / r1335: always-on backlight 0 dimmest - 3)
WATCH_KEYS = {"aod": 2, "tw": 3, "rw": 4, "bw": 5, "h12": 7, "vib": 8}


def parse_watch_settings(d: bytes) -> dict | None:
    if len(d) < 10 or d[:2] != b"\x7e\x01":
        return None
    out = {k: bool(d[i]) for k, i in WATCH_KEYS.items()}
    out["dock"] = d[6]
    out["battery"] = d[9]
    out["ab"] = d[10] if len(d) > 10 else None
    return out


class Manager:
    """Owns the asyncio loop thread, the single BLE connection and the shared UI state."""

    def __init__(self):
        self.cfg = load_config()
        self.faces = load_faces()
        self.fw_preview = None                     # s100_preview.Preview: built firmware in the emulator
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.link: WatchLink | None = None
        self.op_lock = threading.Lock()          # one watch operation at a time
        self.mu = threading.Lock()
        self.log_seq = 0
        self.logs: collections.deque = collections.deque(maxlen=200)
        self.st = {"status": "disconnected", "battery": None, "battery_at": None, "app_rev": None, "version": "",
                   "busy": None, "progress": None, "last_event": None, "weather": None, "watch": None}
        self.log("Ready. Turn off phone Bluetooth so realme Fit doesn't hold the watch.")

    # --- state helpers
    def log(self, msg: str, level: str = "info") -> None:
        with self.mu:
            self.log_seq += 1
            self.logs.append({"id": self.log_seq, "t": time.strftime("%H:%M:%S"), "level": level, "msg": msg})

    def set(self, **kw) -> None:
        with self.mu:
            self.st.update(kw)

    def snapshot(self, after: int) -> dict:
        with self.mu:
            return {**self.st, "address": self.cfg["address"], "twelve_hour": self.cfg["twelve_hour"],
                    "media_keys": self.cfg["media_keys"], "city": self.cfg["city"],
                    "profile": self.cfg["profile"], "logs": [l for l in self.logs if l["id"] > after]}

    def live_values(self) -> dict:
        with self.mu:
            return {"now": datetime.datetime.now(), "twelve_hour": self.cfg["twelve_hour"],
                    "battery": self.st["battery"], "connected": self.st["status"] == "connected",
                    "weather": self.st["weather"], "fahrenheit": self.cfg["profile"]["fahrenheit"],
                    "steps": 0}

    # --- running operations
    def run(self, name: str, coro_fn, timeout: float = 120, need_link: bool = True):
        """Run one watch operation on the loop thread; reject if another is in progress."""
        if not self.op_lock.acquire(blocking=False):
            raise Busy(f"busy: {self.st['busy']}")
        try:
            if need_link and self.link is None:
                raise RuntimeError("not connected")
            self.set(busy=name)
            fut = asyncio.run_coroutine_threadsafe(coro_fn(), self.loop)
            return fut.result(timeout)
        finally:
            self.set(busy=None)
            self.op_lock.release()

    def start_background(self, name: str, coro_fn) -> None:
        """Like run(), but returns at once; used for the long face transfer."""
        if not self.op_lock.acquire(blocking=False):
            raise Busy(f"busy: {self.st['busy']}")
        if self.link is None:
            self.op_lock.release()
            raise RuntimeError("not connected")
        self.set(busy=name)

        async def wrapper():
            try:
                await coro_fn()
            except Exception as e:  # noqa: BLE001 — reported to the UI
                self.log(f"{name} failed: {e}", "error")
            finally:
                self.set(busy=None, progress=None)
                self.op_lock.release()
        asyncio.run_coroutine_threadsafe(wrapper(), self.loop)

    # --- BLE callbacks (loop thread)
    def _on_disconnect(self) -> None:
        if self.link is not None:
            self.link = None
            self.set(status="disconnected")
            self.log("Watch disconnected.", "warn")

    def _on_settings(self, data: bytes) -> None:
        """The watch's own settings (source of truth): sent on CFG|get and after any change on it."""
        ws = parse_watch_settings(data)
        if ws is None:
            return
        self.set(watch=ws)
        if self.cfg["twelve_hour"] != ws["h12"]:
            self.cfg["twelve_hour"] = ws["h12"]
            save_config(self.cfg)

    def _on_event(self, data: bytes) -> None:
        code = data[1] if len(data) > 1 else -1
        label = BUTTONS.get(code, f"event {data.hex(' ')}")
        self.set(last_event={"label": label, "t": time.time()})
        self.log(f"Watch: {label}")
        if self.cfg["media_keys"] and code in MEDIA_VK and sys.platform == "win32":
            import ctypes
            vk = MEDIA_VK[code]
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

    # --- operations (coroutines run on the loop thread)
    async def _read_battery(self) -> None:
        """UTE `A2` → `A2 <percent>`, the same query realme Fit sends (sendToReadBLEBattery)."""
        await self.link.write(b"\xa2")
        reply = await self.link.expect(b"\xa2", timeout=5)
        if not reply or len(reply) < 2:
            raise RuntimeError("watch did not report its battery")
        self.set(battery=min(reply[1], 100), battery_at=time.strftime("%H:%M:%S"))

    async def _poll(self, link: WatchLink) -> None:
        """Refresh the battery every minute; skipped while another operation holds the watch."""
        while True:
            await asyncio.sleep(BATTERY_POLL_S)
            if self.link is not link:
                return
            if not self.op_lock.acquire(blocking=False):
                continue
            try:
                await self._read_battery()
            except Exception as e:  # noqa: BLE001
                self.log(f"battery refresh failed: {e}", "warn")
            finally:
                self.op_lock.release()

    async def _refresh(self) -> None:
        await self._read_battery()
        self.set(version=await self.link.version())
        self.log(f"Refreshed: battery {self.st['battery']}%.")

    async def _connect(self):
        if self.link is not None:
            return
        self.set(status="connecting")
        self.log(f"Connecting to {self.cfg['address']} … (accept the pairing prompt on the watch if shown)")
        link = WatchLink(self.cfg["address"], self._on_event, self._on_disconnect, self._on_settings)
        try:
            await link.__aenter__()
        except Exception as e:
            self.set(status="disconnected")
            try:
                await link.client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"could not connect: {e}") from e
        self.link = link
        self.set(status="connected")
        try:
            await self._read_battery()
        except Exception as e:  # noqa: BLE001
            self.log(f"battery read failed: {e}", "warn")
        try:
            v = struct.unpack("<I", bytes(await link.client.read_gatt_char(APP_VERSION_CHAR))[:4])[0]
            self.set(app_rev=(v >> 12) & 0x7FFF)
        except Exception as e:  # noqa: BLE001
            self.log(f"firmware revision read failed: {e}", "warn")
        self.set(version=await link.version())
        await link.sync_time()
        try:
            await link.notify("CFG|get")                   # firmware c7+: replies with a 7E report
        except Exception as e:  # noqa: BLE001
            self.log(f"settings read failed: {e}", "warn")
        self._poll_task = asyncio.create_task(self._poll(link))
        self.log(f"Connected. Firmware {self.st['version'] or '?'} (app revision {self.st['app_rev']}), "
                 f"battery {self.st['battery']}%. Time synced.")

    async def _disconnect(self):
        link, self.link = self.link, None
        if link is not None:
            await link.client.disconnect()
        self.set(status="disconnected")
        self.log("Disconnected.")

    async def _apply_face(self, face: Face):
        self.log(f"Sending face '{face.title}' ({len(face.blob) // 1024} KB). Keep the watch close.")
        self.set(progress={"sent": 0, "total": 1})

        def progress(sent, total):
            self.set(progress={"sent": sent, "total": total})
        ok = await send_dial(self.link, face.blob, progress=progress, log=lambda m: self.log(m))
        if ok:
            self.log(f"Face '{face.title}' is on the watch.", "ok")
        else:
            self.log("Face transfer was not accepted; the watch reported a problem (see above).", "error")

    # --- public API (HTTP threads)
    def connect(self, address: str | None):
        if address:
            if not re.fullmatch(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", address):
                raise ValueError("address must look like 78:02:B7:58:FF:9E")
            self.cfg["address"] = address.upper()
            save_config(self.cfg)
        self.run("connecting", self._connect, timeout=150, need_link=False)

    def disconnect(self):
        self.run("disconnecting", self._disconnect, timeout=20, need_link=False)

    def scan(self) -> list[dict]:
        if self.link is not None:
            raise RuntimeError("disconnect first")

        async def go():
            found = await BleakScanner.discover(timeout=6)
            return [{"name": d.name, "address": d.address} for d in found
                    if d.name and "S100" in d.name]
        return self.run("scanning", go, timeout=20, need_link=False)

    def apply_face(self, name: str):
        face = self.faces.get(name)
        if face is None:
            raise ValueError("unknown face")
        if face.problems:
            raise ValueError("face file failed checks: " + "; ".join(face.problems))
        if face.needs_mod:
            rev = self.st["app_rev"]
            if rev is None or rev < WORLD_CLOCK_MIN_REV:
                raise ValueError(f"this face needs firmware mod b5_worldclock (revision ≥ {WORLD_CLOCK_MIN_REV}); "
                                 f"the watch reports {rev}")
        self.start_background("sending face", lambda: self._apply_face(face))

    def vibrate(self, times: int):
        self.run("vibrating", lambda: self.link.vibrate(max(1, min(times, 5))))
        self.log("Find watch: vibrate sent.")

    def sync_time(self):
        self.run("syncing time", lambda: self.link.sync_time())
        self.log("Time synced from this PC.")

    def notify(self, text: str, kind: str):
        text = text.strip()
        if not text:
            raise ValueError("message is empty")
        app_type = {"call": TYPE_CALL, "sms": TYPE_SMS}.get(kind, TYPE_OTHER)
        ok = self.run("sending message", lambda: self.link.notify(text[:80], app_type))
        if not ok:
            raise RuntimeError("watch did not acknowledge the message")
        self.log(f"Message sent: {text[:80]}")

    def weather(self, city: str, current: int, days: list[tuple[int, int, int]]):
        self.run("sending weather", lambda: self.link.weather(days, current, city))
        self.set(weather=(days[0][0], current))
        self.log(f"Weather sent: {city or 'no city'} {current}°C.")

    def music(self, title: str, playing: bool):
        self.run("sending music info", lambda: self.link.music(title.strip()[:52] or "Unknown", playing))
        self.log(f"Music info sent: {title.strip()[:52]} ({'playing' if playing else 'paused'}).")

    def hour_format(self, twelve: bool):
        self.watch_set("h12", twelve)

    def watch_set(self, key: str, on: bool):
        """One display / wake setting on the watch; the watch answers with its full report."""
        if key not in WATCH_KEYS:
            raise ValueError(f"unknown setting {key}")
        ok = self.run("changing a watch setting", lambda: self.link.notify(f"CFG|{key}={1 if on else 0}"))
        if not ok:
            raise RuntimeError("watch did not acknowledge the setting")

    def aod_level(self, level: int):
        """Always-on backlight level on the watch (0 dimmest - 3), separate from the normal brightness."""
        level = _clamp(level, 0, 3)
        if not self.run("changing the always-on brightness", lambda: self.link.notify(f"CFG|ab={level}")):
            raise RuntimeError("watch did not acknowledge the setting")

    def dock(self, style: int, show: bool = False):
        style = _clamp(style, 0, 3)
        cmd = f"CFG|show={style}" if show else f"CFG|dock={style}"
        if show and style > 2:
            raise ValueError("nothing to show for 'off'")
        if not self.run("changing the charger screen", lambda: self.link.notify(cmd)):
            raise RuntimeError("watch did not acknowledge the setting")

    def profile(self, p: dict):
        clean = {"height_cm": _clamp(p.get("height_cm"), 100, 250), "weight_kg": _clamp(p.get("weight_kg"), 20, 250),
                 "age": _clamp(p.get("age"), 5, 120), "step_goal": _clamp(p.get("step_goal"), 1000, 99999),
                 "male": bool(p.get("male", True)), "fahrenheit": bool(p.get("fahrenheit", False))}
        ok = self.run("saving profile", lambda: self.link.settings(**clean))
        if not ok:
            raise RuntimeError("watch did not acknowledge the profile")
        self.cfg["profile"] = clean
        save_config(self.cfg)
        self.log("Profile saved to the watch.")

    def set_media_keys(self, on: bool):
        self.cfg["media_keys"] = bool(on) and sys.platform == "win32"
        save_config(self.cfg)


def _clamp(v, lo, hi) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        raise ValueError(f"expected a number between {lo} and {hi}") from None


# ---------------------------------------------------------------- weather lookup (Open-Meteo, no key)

def _wmo_to_watch(code: int) -> int:
    """Open-Meteo WMO weather code → watch condition (1 sunny … 12 wind)."""
    if code == 0:
        return 1
    if code in (1, 2):
        return 2
    if code == 3:
        return 3
    if code in (45, 48):
        return 11
    if code in (66, 67):
        return 6
    if code in (65, 82):
        return 8
    if 51 <= code <= 63:
        return 7
    if code in (80, 81):
        return 4
    if 71 <= code <= 77 or code in (85, 86):
        return 9
    if code >= 95:
        return 5
    return 2


def fetch_weather(city: str) -> tuple[str, int, list[tuple[int, int, int]]]:
    def get(url):
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.load(r)
    name, _, region = (s.strip() for s in city.partition(","))
    geo = get("https://geocoding-api.open-meteo.com/v1/search?count=10&name=" + urllib.parse.quote(name))
    results = geo.get("results") or []
    if region:
        r = region.lower()
        results = [g for g in results if any(str(g.get(k, "")).lower().startswith(r)
                                             for k in ("country", "country_code", "admin1"))]
    if not results:
        raise ValueError(f"'{city}' not found — try 'City, Country'")
    g = results[0]
    place = ", ".join(p for p in (g["name"], g.get("admin1"), g.get("country")) if p)
    q = urllib.parse.urlencode({"latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
                                "forecast_days": 7, "current": "temperature_2m,weather_code",
                                "daily": "weather_code,temperature_2m_max,temperature_2m_min"})
    fc = get("https://api.open-meteo.com/v1/forecast?" + q)
    d = fc["daily"]
    days = [(_wmo_to_watch(c), round(hi), round(lo))
            for c, hi, lo in zip(d["weather_code"], d["temperature_2m_max"], d["temperature_2m_min"])]
    days[0] = (_wmo_to_watch(fc["current"]["weather_code"]), days[0][1], days[0][2])
    return place, g["name"], round(fc["current"]["temperature_2m"]), days


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    mgr: Manager
    port: int

    def log_message(self, *_):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _host_ok(self) -> bool:
        # Blocks DNS-rebinding: only our own origin may talk to the watch.
        return self.headers.get("Host", "") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        m = self.mgr
        if url.path == "/":
            return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/state":
            return self._json(m.snapshot(int(q.get("after", ["0"])[0] or 0)))
        if url.path == "/api/faces":
            return self._json([{"name": f.name, "title": f.title, "notes": f.notes, "size": len(f.blob),
                                "elements": len(f.records), "needs_mod": f.needs_mod, "problems": f.problems}
                               for f in m.faces.values()])
        face = m.faces.get(q.get("face", [""])[0])
        if url.path == "/api/preview" and face:
            try:
                return self._send(200, render(face, m.live_values()), "image/png")
            except Exception as e:  # noqa: BLE001
                return self._json({"error": f"preview failed: {e}"}, 500)
        if url.path.startswith("/api/fwpreview/"):
            try:
                import s100_preview                       # needs unicorn (offline emulator)
                if url.path == "/api/fwpreview/builds":
                    return self._json(s100_preview.builds())
                pv = m.fw_preview
                if pv is None:
                    return self._json({"error": "start a preview first"}, 404)
                if url.path == "/api/fwpreview/screen.png":
                    return self._send(200, pv.png(), "image/png")
                if url.path == "/api/fwpreview/status":
                    return self._json(pv.status())
            except ImportError as e:
                return self._json({"error": f"preview needs the emulator packages: {e}"}, 500)
        if url.path == "/api/thumb" and face:
            png = face.path.with_suffix(".png")
            if png.exists():
                return self._send(200, png.read_bytes(), "image/png")
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        # The custom header forces a CORS preflight, which we never answer, so other sites can't post.
        if not self._host_ok() or self.headers.get("X-S100") != "1":
            return self._send(403, b"forbidden", "text/plain")
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 65536)) or b"{}")
        except ValueError:
            return self._json({"error": "bad JSON"}, 400)
        m, path = self.mgr, urllib.parse.urlparse(self.path).path
        try:
            result = None
            if path == "/api/connect":
                m.connect(body.get("address"))
            elif path == "/api/disconnect":
                m.disconnect()
            elif path == "/api/scan":
                result = m.scan()
            elif path == "/api/apply":
                m.apply_face(str(body.get("face", "")))
            elif path == "/api/vibrate":
                m.vibrate(int(body.get("times", 2)))
            elif path == "/api/refresh":
                m.run("reading watch", m._refresh, timeout=20)
                result = {"battery": m.st["battery"], "at": m.st["battery_at"]}
            elif path == "/api/time":
                m.sync_time()
            elif path == "/api/notify":
                m.notify(str(body.get("text", "")), str(body.get("kind", "other")))
            elif path == "/api/weather":
                query = str(body.get("city", "")).strip()[:60]
                if body.get("manual"):
                    cond = _clamp(body.get("condition"), 1, 12)
                    cur, hi, lo = (_clamp(body.get(k), -40, 60) for k in ("current", "high", "low"))
                    days = [(cond, hi, lo)] * 7
                    place = label = query.partition(",")[0].strip()
                else:
                    if not query:
                        raise ValueError("enter a city")
                    place, label, cur, days = fetch_weather(query)
                m.cfg["city"] = query
                save_config(m.cfg)
                m.weather(label, cur, days)
                result = {"city": place, "current": cur, "days": days}
            elif path == "/api/music":
                m.music(str(body.get("title", "")), bool(body.get("playing", True)))
            elif path == "/api/watch":
                if "dock" in body:
                    m.dock(body.get("dock"), bool(body.get("show")))
                elif "ab" in body:
                    m.aod_level(body.get("ab"))
                else:
                    m.watch_set(str(body.get("key", "")), bool(body.get("on")))
            elif path == "/api/fwpreview/start":
                import s100_preview
                m.fw_preview = s100_preview.Preview(str(body.get("firmware", "")), str(body.get("ui", "")),
                                                    body.get("data") or {})
            elif path == "/api/fwpreview/input":
                pv = m.fw_preview
                if pv is None:
                    raise ValueError("start a preview first")
                kind = body.get("kind")
                if kind in ("tap", "long"):
                    pv.tap(_clamp(body.get("x"), 0, 239), _clamp(body.get("y"), 0, 279), long=kind == "long")
                elif kind == "swipe":
                    if body.get("dir") not in ("left", "right", "up", "down"):
                        raise ValueError("bad swipe direction")
                    pv.swipe(body["dir"])
                elif kind in ("button", "button_long"):
                    pv.button(long=kind == "button_long")
                elif kind == "timeout":
                    pv.timeout()
                elif kind == "go":
                    pv.go(str(body.get("name", "")))
                elif kind == "data":
                    pv.update(body.get("data") or {})
                else:
                    raise ValueError("unknown input")
                result = pv.status()
            elif path == "/api/hour_format":
                m.hour_format(bool(body.get("twelve_hour")))
            elif path == "/api/profile":
                m.profile(body)
            elif path == "/api/media_keys":
                m.set_media_keys(bool(body.get("on")))
            else:
                return self._json({"error": "not found"}, 404)
            return self._json({"ok": True, "result": result})
        except Busy as e:
            return self._json({"error": str(e)}, 409)
        except (ValueError, RuntimeError) as e:
            m.log(str(e), "error")
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 — BLE / network errors
            m.log(f"{type(e).__name__}: {e}", "error")
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    Handler.mgr = Manager()
    Handler.port = a.port
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"S100 app running at {url}  (Ctrl+C to quit)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mgr = Handler.mgr
        if mgr.link is not None:
            asyncio.run_coroutine_threadsafe(mgr._disconnect(), mgr.loop).result(10)


if __name__ == "__main__":
    main()
