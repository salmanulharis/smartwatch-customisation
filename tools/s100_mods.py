"""Rebuild the patched S100 firmware images from the stock realme image.

The stock image (RH288A_V001319_fw_*.bin, vendor copyright) is not in git; download it with
tools/ute_fw_query.py. Patches are byte-exact and verified against the original bytes.
See docs/custom-firmware-plan.md (Track B) for what each one does.

Usage:
    python tools/s100_mods.py list
    python tools/s100_mods.py build b2_timeout [--stock PATH] [--version N]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "research" / "firmware" / "RH288A_V001319_fw_1660354713_5619.bin"
OUT = ROOT / "research" / "mods"
BASE = 0x0080E000
MP = 512

# name -> (default version, [(address, original hex, new hex)], description)
MODS = {
    "stock": (1320, [], "unchanged stock, version bump only (B1 test)"),
    "b2_always_on": (1321, [
        (0x0085FB0C, "00eb8000", "4ff6ff70"),
    ], "screen timeout: every option ~18 h"),
    "b2_timeout": (1322, [
        (0x0085FB0C, "00eb8000 80b2 a1f8fa00 0528 02d2 0520 a1f8fa00",
                     "00eb8000 0f28 28bf c043 0528 38bf 0520 a1f8fa00"),
    ], "screen timeout picker: 5 s / 10 s / '15' = always on (installed 2026-10-29)"),
}


def build(name: str, stock: Path, version: int | None) -> Path:
    default_ver, patches, _ = MODS[name]
    data = bytearray(stock.read_bytes())
    for addr, old, new in patches:
        old_b, new_b = bytes.fromhex(old.replace(" ", "")), bytes.fromhex(new.replace(" ", ""))
        off = MP + addr - BASE
        if data[off:off + len(old_b)] != old_b:
            raise SystemExit(f"{name}: bytes at {addr:#x} don't match stock — wrong input image?")
        data[off:off + len(new_b)] = new_b
    ver = version or default_ver
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f"_{name}.tmp"
    out = OUT / f"{name}_v{ver}.bin"
    tmp.write_bytes(data)
    subprocess.run([sys.executable, str(ROOT / "tools" / "rehash_rtl_image.py"), str(tmp), str(out),
                    "--version", str(ver)], check=True)
    tmp.unlink()
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    pb = sub.add_parser("build")
    pb.add_argument("name", choices=sorted(MODS))
    pb.add_argument("--stock", type=Path, default=STOCK)
    pb.add_argument("--version", type=int, help="git_ver revision; must exceed the installed one")
    a = p.parse_args()
    if a.cmd == "list":
        for n, (v, _, d) in MODS.items():
            print(f"{n:14} v{v}  {d}")
    else:
        print(build(a.name, a.stock, a.version))


if __name__ == "__main__":
    main()
