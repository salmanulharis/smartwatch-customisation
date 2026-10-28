"""Read-only GATT dump for the realme TechLife Watch S100 (see docs/TechLife-S100.md).

Connects, lists every service/characteristic, reads the Generic Access strings, the
battery level and the Realtek OTA info characteristics. It never writes, subscribes
or pairs — safe to run against the stock firmware at any time.

Usage (from the repo root, venv active, watch disconnected from the phone):
    python tools/s100_gatt_dump.py [MAC]
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime

from bleak import BleakClient

DEFAULT_ADDR = "78:02:B7:58:FF:9E"
OTA_INFO_CHARS = ["ffd2", "ffd3", "ffd4", "ffd5", "ffe0", "fff1", "fff3", "2a19"]


def _u16(short: str) -> str:
    return f"0000{short}-0000-1000-8000-00805f9b34fb"


async def main(addr: str) -> None:
    print(f"# S100 GATT dump  {datetime.now().isoformat(timespec='seconds')}  {addr}")
    async with BleakClient(addr, timeout=20) as c:
        print(f"connected, mtu {c.mtu_size}")
        for s in c.services:
            print("SVC", s.uuid, s.description)
            for ch in s.characteristics:
                val = ""
                if "read" in ch.properties and s.uuid.startswith("00001800"):
                    try:
                        raw = bytes(await c.read_gatt_char(ch))
                        val = " = " + repr(raw.decode("utf-8", "replace"))
                    except Exception as e:
                        val = f" (read err {e})"
                print("   CHR", ch.uuid, ch.properties, ch.description, val)
        print("\n# Realtek OTA info + battery (raw hex)")
        for x in OTA_INFO_CHARS:
            try:
                print(x, bytes(await c.read_gatt_char(_u16(x))).hex(" "))
            except Exception as e:
                print(x, "ERR", e)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDR))
