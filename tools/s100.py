"""Drive the realme TechLife Watch S100 on its STOCK firmware via the UTE BLE protocol.

Protocol reference: docs/TechLife-S100.md §7b.7 (recovered from realme Fit 1.2.9).
Nothing here touches firmware or OTA characteristics — only the app-level commands the
official companion app itself sends.

Usage (venv active, phone Bluetooth off so realme Fit doesn't grab the watch):
    python tools/s100.py info
    python tools/s100.py time
    python tools/s100.py notify "Hello from the PC"
    python tools/s100.py nav right 200 "MG Road" --speed 48 --eta "14:45"   (needs app >= 1328)
    python tools/s100.py speed 48
    python tools/s100.py vibrate
    python tools/s100.py weather --city Kochi
    python tools/s100.py music "Song title"
    python tools/s100.py listen 60
"""
from __future__ import annotations
import argparse
import asyncio
import datetime

from bleak import BleakClient

ADDRESS = "78:02:B7:58:FF:9E"
ACCOUNT_ID = 0x00511000          # our app's bind ID (see docs §7b.7 / §11)

CMD_CHAR = "000033f1-0000-1000-8000-00805f9b34fb"
CMD_NOTIFY = "000033f2-0000-1000-8000-00805f9b34fb"
BIG_CHAR = "000034f1-0000-1000-8000-00805f9b34fb"
BIG_NOTIFY = "000034f2-0000-1000-8000-00805f9b34fb"

# Notification app types (WriteCommandToBLE.getAppType)
TYPE_CALL, TYPE_SMS, TYPE_OTHER = 0, 3, 4
MAX_TEXT_BYTES = 160             # function list 6 lacks 0x400000 → 160 bytes


def encode_text(text: str) -> bytes:
    """GBUtils.string2unicode: UTF-16BE, BMP only, control chars and C1 range dropped."""
    out = bytearray()
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp > 0xFFFF or cp < 32 or 127 <= cp <= 159 or cp in (8197, 9924, 9748):
            continue
        if i == len(text) - 1 and cp <= 32:
            continue
        out += cp.to_bytes(2, "big")
    return bytes(out[:MAX_TEXT_BYTES])


class S100:
    def __init__(self, address: str = ADDRESS, verbose: bool = False):
        self.client = BleakClient(address, timeout=20)
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.verbose = verbose

    async def __aenter__(self):
        for attempt in range(4):
            try:
                await self.client.connect()
                break
            except Exception as e:  # watch asleep / not advertising yet
                if attempt == 3:
                    raise
                print(f"connect failed ({e}); retrying…")
                await asyncio.sleep(3)
        await self.client.start_notify(CMD_NOTIFY, self._on_notify)
        await self.client.start_notify(BIG_NOTIFY, self._on_notify)
        self.functions = bytes(await self.client.read_gatt_char(CMD_CHAR))
        self.max_len = int.from_bytes(bytes(await self.client.read_gatt_char(BIG_CHAR))[:2], "big")
        status = await self.bind()
        if status != 0x01:
            raise RuntimeError(f"bind failed, status {status!r} (confirm on the watch and retry)")
        return self

    async def __aexit__(self, *exc):
        await self.client.disconnect()

    def _on_notify(self, _sender, data: bytearray):
        data = bytes(data)
        if self.verbose:
            print("  <-", data.hex(" "))
        self.queue.put_nowait(data)

    async def write(self, data: bytes, big: bool = False):
        if self.verbose:
            print("  ->", data.hex(" "))
        # 34f1 only supports write-without-response
        await self.client.write_gatt_char(BIG_CHAR if big else CMD_CHAR, data, response=not big)

    async def expect(self, prefix: bytes, timeout: float = 5.0) -> bytes | None:
        """Wait for a notification starting with `prefix`, discarding others."""
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while (left := end - loop.time()) > 0:
            try:
                msg = await asyncio.wait_for(self.queue.get(), left)
            except asyncio.TimeoutError:
                break
            if msg.startswith(prefix):
                return msg
        return None

    async def bind(self) -> int | None:
        await self.write(bytes([0x33, 0x02]) + ACCOUNT_ID.to_bytes(4, "big"))
        reply = await self.expect(b"\x33\x04", timeout=20)
        return reply[2] if reply and len(reply) > 2 else None

    async def sync_time(self, now: datetime.datetime | None = None):
        now = now or datetime.datetime.now()
        await self.write(bytes([0xA3, now.year >> 8, now.year & 0xFF, now.month, now.day,
                                now.hour, now.minute, now.second]))
        await self.expect(b"\xa3")

    async def units(self, twelve_hour: bool, metric: bool = True):
        """A0 <unit 1=metric/2=imperial> <hours 1=24h/2=12h> (sendUnitToBLE)."""
        await self.write(bytes([0xA0, 1 if metric else 2, 2 if twelve_hour else 1]))
        return await self.expect(b"\xa0")

    async def version(self) -> str:
        await self.write(b"\xa1")
        reply = await self.expect(b"\xa1")
        return reply[1:].decode("ascii", "replace") if reply else ""

    async def notify(self, text: str, app_type: int = TYPE_OTHER) -> bool:
        """Push a notification (WriteCommandToBLE.sendTextToBle). No vibration is requested."""
        body = encode_text(text) or encode_text("unknown")
        payload = bytes([app_type, len(body)]) + body
        for seq, off in enumerate(range(0, len(payload), 18)):
            await self.write(bytes([0xC5, seq]) + payload[off:off + 18])
            ack = await self.expect(b"\xc5")
            if ack is None or ack[1:2] == b"\xff":
                return False
        await self.write(b"\xc5\xfd")
        await self.expect(b"\xc5\xfd", timeout=3)
        return True

    async def vibrate(self, times: int = 1):
        """Find-watch style buzz (`AB 00 00 00 01 n 07 01`)."""
        await self.write(bytes([0xAB, 0x00, 0x00, 0x00, 0x01, times & 0xFF, 0x07, 0x01]))

    async def weather(self, days: list[tuple[int, int, int]], current: int, city: str = "",
                      pm25: int = 0, aqi: int = 0):
        """7-day weather (syncWeatherToBLEForXiaoYang). days = 7 × (condition, max, min).

        Conditions: 1 sunny, 2 cloudy, 3 overcast, 4 shower, 5 thunder, 6 sleet,
        7 light rain, 8 heavy rain, 9 snow, 10 dust, 11 fog/haze, 12 wind.
        """
        t = lambda v: (abs(v) | 0x80) if v < 0 else v
        days = (list(days) + [days[-1]] * 7)[:7]
        c0, hi0, lo0 = days[0]
        page1 = bytes([0xCB, 0x01, c0, 0, t(current), t(hi0), t(lo0),
                       pm25 >> 8 & 0xFF, pm25 & 0xFF, aqi >> 8 & 0xFF, aqi & 0xFF]) + bytes(8)
        page2 = bytes([0xCB, 0x02]) + b"".join(bytes([c, 0, t(h), t(l)]) for c, h, l in days[1:5])
        page3 = bytes([0xCB, 0x03]) + b"".join(bytes([c, 0, t(h), t(l)]) for c, h, l in days[5:7])
        for page in (page1, page2, page3):
            await self.write(page)
            await self.expect(b"\xcb", timeout=3)
        if city:
            name = city.encode()[:100]
            await self.write(bytes([0xCB, 0xFF, len(name)]) + name, big=True)
            await self.expect(b"\xcb\xff", timeout=3)

    async def music(self, title: str, playing: bool = True):
        """Song info (sendSongInformationToBle): state 1 playing / 2 paused, then UTF-8 title."""
        await self.write(bytes([0x3A, 0x01, 1 if playing else 2]) + b"\xff" * 10, big=True)
        name = title.encode()[:52]
        await self.write(bytes([0x3A, 0x06, len(name)]) + name, big=True)
        await self.write(b"\x3a\xfa", big=True)
        await self.expect(b"\x3a\xfa", timeout=3)

    async def settings(self, screen_off_s: int = 5, raise_to_wake: bool = True, height_cm: int = 170,
                       weight_kg: int = 65, step_goal: int = 10000, age: int = 30, male: bool = True,
                       fahrenheit: bool = False):
        """`A9` profile packet (sendStepLenAndWeightToBLE). Overwrites ALL these fields at once.

        Byte 2 is height (function list 2 has 0x1000 on this watch); HR alarms off,
        language English (2), temperature unit byte 17 (1 °C, 2 °F). The firmware ignores
        bytes 5 (screen-off) and 10 (raise-to-wake).
        """
        pkt = bytes([0xA9, 0x00, height_cm & 0xFF, 0x00, weight_kg & 0xFF, screen_off_s & 0xFF]) \
            + step_goal.to_bytes(4, "big") \
            + bytes([1 if raise_to_wake else 0, 0xFF, 0x00, age & 0xFF, 1 if male else 2, 0x00, 0x02,
                     2 if fahrenheit else 1, 0x00])
        await self.write(pkt)
        reply = await self.expect(b"\xa9", timeout=3)
        return reply is not None

    async def listen(self, seconds: float):
        """Print watch → phone events (music buttons, find phone, …)."""
        names = {0x07: "play/pause", 0x08: "next", 0x09: "previous", 0x0D: "volume up",
                 0x0E: "volume down", 0x0A: "find phone", 0x12: "mute"}
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        while (left := end - loop.time()) > 0:
            try:
                msg = await asyncio.wait_for(self.queue.get(), left)
            except asyncio.TimeoutError:
                break
            label = names.get(msg[1]) if msg[:1] == b"\xd1" and len(msg) > 1 else None
            print(f"{datetime.datetime.now():%H:%M:%S}  {msg.hex(' ')}  {label or ''}")


    async def deskclock(self, seconds: float, interval: float = 10.0, weather_line: str = ""):
        """Desk-buddy prototype: refresh a time/date(/weather) notification on an interval.

        Also probes the keep-awake question — whether repeated notifications keep the
        screen lit. Reports whether each push was acked; the user must observe the screen.
        """
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        pushes = 0
        while loop.time() < end:
            now = datetime.datetime.now()
            text = now.strftime("%H:%M  %a %d %b")
            if weather_line:
                text += f"  {weather_line}"
            ok = await self.notify(text)
            pushes += 1
            print(f"{now:%H:%M:%S}  push #{pushes}: {'ok' if ok else 'FAILED'}  \"{text}\"")
            await asyncio.sleep(max(1.0, min(interval, end - loop.time())))
        print(f"done: {pushes} pushes over {seconds:.0f}s — did the screen stay lit?")


    async def car_frame(self, speed_kmh: int, direction: str, dist_m: int,
                        street: str, eta: str = "", remaining_km: float | None = None) -> bool:
        """One frame for the navigation screen of firmware mod c2_features (app >= 1328): the watch
        shows it on its own screen (arrow, distance, street, speed, ETA) instead of a popup, without
        storing it in the notification history. It goes back to the face after 90 s without frames."""
        if remaining_km is not None:
            eta = f"{remaining_km:.1f} km  {eta}".strip()
        return await self.notify(nav_text(direction, dist_m, street, f"{speed_kmh} km/h", eta), app_type=TYPE_OTHER)

    async def car_demo(self, seconds: float):
        """Simulated approach-to-turn so the car-display UI can be judged on-device."""
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        dist, speed, remaining = 800, 52, 12.4
        steps = [("right", "MG Road"), ("straight", "Ring Road"), ("left", "NH-66")]
        si = 0
        while loop.time() < end:
            direction, street = steps[si % len(steps)]
            ok = await self.car_frame(speed, direction, dist, street, remaining_km=remaining)
            print(f"{datetime.datetime.now():%H:%M:%S}  {speed}km/h {direction} {dist}m {street}  {'ok' if ok else 'FAIL'}")
            dist -= 100
            if dist <= 0:
                await self.vibrate(1)          # buzz only at the turn itself
                si += 1; dist = 700; remaining = max(0.1, remaining - 0.7)
            speed = max(0, speed + (5 if dist % 200 else -8))
            await asyncio.sleep(2)
        print("car demo done")


NAV_DIRS = {"straight": "S", "left": "L", "right": "R", "slight-left": "l", "slight-right": "r",
            "uturn": "U", "uturn-right": "u", "arrive": "A", "roundabout": "O",
            "sharp-left": "<", "sharp-right": ">", "keep-left": "k", "keep-right": "K", "merge": "M",
            "exit-left": "e", "exit-right": "E"}


def nav_text(direction: str, distance_m: float, street: str, speed: str = "", eta: str = "") -> str:
    """'NAV|dir|dist|street|speed|eta', read by the c2_features navigation screen (ext.c nav_check)."""
    d = NAV_DIRS.get(direction.lower(), direction[:1] or "S")
    dist = f"{distance_m / 1000:.1f} km" if distance_m >= 1000 else f"{int(round(distance_m, -1))} m"
    speed, eta = speed[:15], eta[:23]
    room = max(0, min(47, 80 - len(f"NAV|{d}|{dist}|||{speed}|{eta}")))   # the watch keeps 80 chars
    return f"NAV|{d}|{dist}|{street[:room].rstrip()}|{speed}|{eta}"


async def main():
    p = argparse.ArgumentParser(description="TechLife S100 stock-firmware control")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("time")
    pn = sub.add_parser("notify"); pn.add_argument("text"); pn.add_argument("--type", type=int, default=TYPE_OTHER)
    pv = sub.add_parser("nav", help="show one frame on the navigation screen (app >= 1328)")
    pv.add_argument("direction", choices=sorted(NAV_DIRS)); pv.add_argument("distance_m", type=float)
    pv.add_argument("street"); pv.add_argument("--speed", default=""); pv.add_argument("--eta", default="")
    ps = sub.add_parser("speed"); ps.add_argument("kmh", type=float)
    pb = sub.add_parser("vibrate"); pb.add_argument("times", type=int, nargs="?", default=1)
    pw = sub.add_parser("weather", help="demo forecast")
    pw.add_argument("--city", default="Kochi"); pw.add_argument("--now", type=int, default=29)
    pm = sub.add_parser("music"); pm.add_argument("title"); pm.add_argument("--paused", action="store_true")
    pl = sub.add_parser("listen"); pl.add_argument("seconds", type=float, nargs="?", default=60)
    pcar = sub.add_parser("cardemo", help="simulated navigation display (speed + next turn), refreshed to stay lit")
    pcar.add_argument("seconds", type=float, nargs="?", default=60)
    pk = sub.add_parser("deskclock", help="refresh a clock/date notification on an interval (keep-awake probe)")
    pk.add_argument("seconds", type=float, nargs="?", default=120)
    pk.add_argument("--interval", type=float, default=10.0)
    pk.add_argument("--weather", default="")
    pc = sub.add_parser("screen", help="set screen-off seconds (also resets profile fields to defaults)")
    pc.add_argument("seconds", type=int); pc.add_argument("--no-raise", action="store_true")
    ph = sub.add_parser("hours", help="set 12- or 24-hour clock (metric units)")
    ph.add_argument("format", choices=["12", "24"])
    pd = sub.add_parser("demo", help="time + weather + music, then stay connected and log buttons")
    pd.add_argument("seconds", type=float, nargs="?", default=90)
    args = p.parse_args()

    async with S100(verbose=args.verbose) as w:
        if args.cmd == "info":
            print("version:", await w.version())
            print("functions:", w.functions.hex(" "), "max_len:", w.max_len)
        elif args.cmd == "time":
            await w.sync_time()
        elif args.cmd == "notify":
            print("ok" if await w.notify(args.text, args.type) else "failed")
        elif args.cmd == "nav":
            print("ok" if await w.notify(nav_text(args.direction, args.distance_m, args.street, args.speed,
                                                   args.eta)) else "failed")
        elif args.cmd == "speed":
            print("ok" if await w.notify(f"Speed {args.kmh:.0f} km/h") else "failed")
        elif args.cmd == "vibrate":
            await w.vibrate(args.times)
        elif args.cmd == "weather":
            demo = [(2, 31, 24), (7, 30, 24), (8, 28, 23), (5, 29, 24), (1, 32, 25), (3, 31, 24), (4, 30, 24)]
            await w.weather(demo, args.now, args.city)
        elif args.cmd == "music":
            await w.music(args.title, not args.paused)
        elif args.cmd == "hours":
            reply = await w.units(args.format == "12")
            print(f"{args.format}-hour set" + (f" (reply {reply.hex(' ')})" if reply else " (no reply)"))
        elif args.cmd == "screen":
            print("ok" if await w.settings(args.seconds, not args.no_raise) else "no reply")
        elif args.cmd == "demo":
            await w.sync_time()
            demo = [(2, 31, 24), (7, 30, 24), (8, 28, 23), (5, 29, 24), (1, 32, 25), (3, 31, 24), (4, 30, 24)]
            await w.weather(demo, 29, "Kochi")
            await w.music("Kesariya - Arijit Singh", True)
            print(f"connected for {args.seconds:.0f}s — check weather + music screens, press music buttons")
            await w.listen(args.seconds)
        elif args.cmd == "cardemo":
            await w.car_demo(args.seconds)
        elif args.cmd == "deskclock":
            await w.deskclock(args.seconds, args.interval, args.weather)
        elif args.cmd == "listen":
            print(f"listening {args.seconds:.0f}s — press buttons on the watch's music screen")
            await w.listen(args.seconds)


if __name__ == "__main__":
    asyncio.run(main())
