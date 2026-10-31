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
    "b5_worldclock": (1323, [
        # B2 timeout patch (cumulative — includes the always-on fix)
        (0x0085FB0C, "00eb8000 80b2 a1f8fa00 0528 02d2 0520 a1f8fa00",
                     "00eb8000 0f28 28bf c043 0528 38bf 0520 a1f8fa00"),
        # Hook: replace ldrh.w at dial dispatch entry with b.w to our handler
        (0x0085D290, "b4f84c03",
                     "37f044bb"),
        # World-clock handler at 0x0089491C (130 bytes in zero-padded free space).
        # Element type 71 = world-clock digit (the stock parser at 0x83B2E6 stops at the first
        # type > 71, so every world digit uses 71). Record reserved bytes (RAM r4+0x35D..):
        #   [0]=0 (digit flag), [1:3]=signed LE16 minute offset from local time, [3]=position
        #   (0 hour tens, 1 hour units, 2 minute tens, 3 minute units).
        # Computes (h*60+m+offset) mod 1440, applies the 12 h flag like stock (h>12 -> h-12),
        # picks the digit and jumps to the stock frame-select at 0x85D320. Other types fall
        # through to the original dispatch at 0x85D294.
        (0x0089491C, "00" * 130,
         "b4f84c03 47283ad1 94f86003 00bf 00f00300 01b5"
         "91f89620 91f89730 3c204243 d218"
         "b4f95e33 d218 40f2a053 002a00da d218"
         "9a4200d3 d21a 3c20 b2fbf0f3 00fb1322"
         "91f86600 10b1 0c2b00d9 0c3b"
         "bde80140 022804d2 1946 10f0010f 08d103e0"
         "1146 10f0010f 03d1 0a20 b1fbf0f1 04e0"
         "0a20 b1fbf0f2 00fb1211"
         "c8f7c3bc c8f77bbc"),
    ], "B2 timeout + world-clock digits (dial type 71, offset + position in reserved bytes)"),
    "b5b_worldclock": (1324, [
        # Same as b5_worldclock, with the handler moved out of 0x0089491C. That address lies in
        # the flash range 0x8941AC-0x8974D0 that startup (0x829A64) copies to RAM 0x20BD14 as the
        # initial values of RAM variables, so v1323 started 130 bytes of app state (RAM
        # 0x20C484-0x20C506) with handler code instead of zeros. See docs/ui-framework-notes.md.
        (0x0085FB0C, "00eb8000 80b2 a1f8fa00 0528 02d2 0520 a1f8fa00",
                     "00eb8000 0f28 28bf c043 0528 38bf 0520 a1f8fa00"),
        (0x0085D290, "b4f84c03",
                     "f0f7d0b8"),                     # b.w 0x84D434
        # Cave: FactoryAgingTest build function 0x84D432 (only caller: the factory test screen at
        # 0x84DB56, opened by a factory command). Its entry becomes "bx lr" so it returns at once
        # if ever called; the handler follows. No literal loads point into 0x84D432-0x84D4BA.
        (0x0084D432, "2de9f04f97b00446aff21b0b4ff48c72f0218de8060890f8351000231a46f548f7f7f3fd616af1484ff0010a81f821a0d0f8600d0a21b0fbf1f201fb1200ee4900eb400001eb80001f2281681a20cde900020f236922606af6f774ff06466ff07f451021e648ecf77adfdff89483d8f80000c0688047e14f70b1d8f800000069804748b1",
         "7047"
         "b4f84c03 47283ad1 94f86003 00bf 00f00300 01b5"
         "91f89620 91f89730 3c204243 d218"
         "b4f95e33 d218 40f2a053 002a00da d218"
         "9a4200d3 d21a 3c20 b2fbf0f3 00fb1322"
         "91f86600 10b1 0c2b00d9 0c3b"
         "bde80140 022804d2 1946 10f0010f 08d103e0"
         "1146 10f0010f 03d1 0a20 b1fbf0f1 04e0"
         "0a20 b1fbf0f2 00fb1211"
         "0ff037bf 0ff0efbe"),
    ], "b5_worldclock with the handler in a real code cave (fixes RAM init data of v1323)"),
}

# UI upgrade (docs/ui-upgrade-plan.md, phase P3): layout/navigation patches, cumulative on b5b.
# DRAFT — previewed with tools/s100_screens.py only, not flashed.
UI_LAYOUT = [
    # App list (MainMenuListScreenUI): 3 rows of 93 px instead of 4 x 70. The builder derives icon
    # and label positions from r7 (row height); touch rows, scroll snap and the scroller's
    # rows-per-screen must change with it.
    (0x00851E7C, "4627", "5d27"),                  # builder: movs r7,#70 -> #93
    (0x00851F10, "4622", "5d22"),                  # builder: row touch height 70 -> 93
    (0x00851EAA, "4ff48c61", "4ff4ba61"),          # scrollbar: scroll range 16*70 -> 16*93
    (0x008524A6, "c0f38f01", "5d2100bf"),          # touch: snap row = (280-margins)/4 -> 93
    (0x008524CA, "8010", "5d20"),                  # touch: row for scroll-mod = .../4 -> 93
    (0x00852532, "0423", "0323"),                  # touch: scroller rows_per_screen 4 -> 3
    # Navigation (per-screen templates {t0..t6 screens, t7 key actions} at 0x88A7F4.., see
    # ui-upgrade-plan §3.1; t3 = finger right->left, t4 = left->right, t5 = down, t6 = up).
    # Face: down = quick panel, up = notifications, R->L = widgets, L->R = music, button = apps.
    (0x0088A804, "30e02000", "98dd2000"),          # face t4: StatusBar -> MusicControl
    (0x0088A808, "e4dd2000", "30e02000"),          # face t5: NotificationList -> StatusBar
    (0x0088A80C, "10dd2000", "e4dd2000"),          # face t6: MainMenuList -> NotificationList
    (0x0088A810, "0a000900", "0a000e00"),          # face key: short 9 (screen off) -> 14 (apps)
    (0x0088A890, "d0e12000", "00000000"),          # StatusBar: leave by swiping up, not R->L
    (0x0088A89C, "00000000", "d0e12000"),
    (0x0088AAB8, "d0e12000", "00000000"),          # NotificationList: leave by swiping down
    (0x0088AAB4, "00000000", "d0e12000"),
    # Widget chain: face -> HomeStatus -> HeartRate -> Sleep -> Weather (Temperature and Music out)
    (0x0088A920, "14e12000", "e4db2000"),          # HomeStatus t3: Temperature -> HeartRate
    (0x0088A968, "24e32000", "34df2000"),          # HeartRate t3: Weather -> Sleep
    (0x0088A96C, "34df2000", "1cdc2000"),          # HeartRate t4: Sleep -> HomeStatus
    (0x0088AE0C, "e4db2000", "24e32000"),          # Sleep t3: HeartRate -> Weather
    (0x0088AE10, "14e12000", "e4db2000"),          # Sleep t4: Temperature -> HeartRate
    (0x0088AA1C, "98dd2000", "00000000"),          # Weather t3: Music -> end of chain
    (0x0088AA20, "e4db2000", "34df2000"),          # Weather t4: HeartRate -> Sleep
    (0x0088A944, "00000000", "d0e12000"),          # Music t3: -> face (opened from the face's left)
    (0x0088A948, "24e32000", "00000000"),          # Music t4: Weather -> none
    (0x0088A8D8, "34df2000", "00000000"),          # Temperature t3: Sleep -> none (now an app)
    (0x0088A8DC, "1cdc2000", "10dd2000"),          # Temperature t4: HomeStatus -> app list
]
MODS["c1_layout"] = (1325, MODS["b5b_worldclock"][1] + UI_LAYOUT,
                     "DRAFT, not flashed: b5b + UI layout/navigation patches (ui-upgrade-plan P3)")

# c1_layout + dot-matrix numerals: frame pointers moved to digit frames appended to the UI pack.
# The app image is paired with one specific pack build (its .append.json map); install that pack
# FIRST (the old app never reads the appended bytes), then this app image.
DOTS_MAP = ROOT / "research" / "ui" / "build" / "ui_v5_draft.append.json"
if DOTS_MAP.exists():
    import json as _json
    from ui_dots import table_patches as _table_patches
    _amap = {k: int(v, 16) for k, v in _json.loads(DOTS_MAP.read_text()).items()}
    MODS["c1_full"] = (1326, MODS["c1_layout"][1] + _table_patches(STOCK.read_bytes(), _amap),
                       f"DRAFT, not flashed: c1_layout + dot numerals (pairs with {DOTS_MAP.stem})")


# Feature screens (desk clock, navigation, watch settings, quick-panel tiles, tap tick), built from
# firmware/s100_ext by tools/s100_ext.py. Pairs with UI pack research/ui/build/ui_v8.bin (install first).
FEATURE_PACK = ROOT / "research" / "ui" / "build" / "ui_v8.bin"   # installed with v1328
FEATURE_PACK_V9 = ROOT / "research" / "ui" / "build" / "ui_v9.bin"
FEATURE_PACK_V10 = ROOT / "research" / "ui" / "build" / "ui_v10.bin"
FEATURE_PACK_V11 = ROOT / "research" / "ui" / "build" / "ui_v11.bin"
FEATURE_PACK_V12 = ROOT / "research" / "ui" / "build" / "ui_v12.bin"
FEATURE_PACK_V13 = ROOT / "research" / "ui" / "build" / "ui_v13.bin"
if FEATURE_PACK.with_suffix(".append.json").exists():
    def _c2():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK)
    MODS["c2_features"] = (1328, _c2, "c1_layout + desk clock, navigation, watch settings, quick panel, "
                           "tap tick (pairs with ui_v8; built from the CURRENT ext.c)")
if FEATURE_PACK_V9.with_suffix(".append.json").exists():
    def _c3():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK_V9)
    MODS["c3_dock"] = (1330, _c3, "c1_layout + features + charging dock / AOD styles + CMF restyle (pairs with ui_v9)")
if FEATURE_PACK_V10.with_suffix(".append.json").exists():
    def _c4():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK_V10)
    MODS["c4_panel"] = (1331, _c4, "c3 + quick panel rebuilt: 3x3 tile set, header date, brightness level (pairs with ui_v10)")
if FEATURE_PACK_V11.with_suffix(".append.json").exists():
    def _c5():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK_V11)
    MODS["c5_panel"] = (1332, _c5, "c4 + quick panel: keep-list (no stray stock date items), 68 px grid (pairs with ui_v11)")
if FEATURE_PACK_V12.with_suffix(".append.json").exists():
    def _c6():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK_V12)
    MODS["c6_text"] = (1333, _c6, "c5 + text widgets drawn (font flag +0x20), squarer watch / phone glyphs (pairs with ui_v12)")
if FEATURE_PACK_V13.with_suffix(".append.json").exists():
    def _c7():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK_V13)
    MODS["c7_wake"] = (1334, _c7, "c6 + usable while charging, wake options, AOD on timeout incl. charger, "
                       "settings sync (CFG/0x7E); app image grows (tail code) (pairs with ui_v13)")
FEATURE_PACK_V15 = ROOT / "research" / "ui" / "build" / "ui_v15.bin"
FEATURE_PACK_V16 = ROOT / "research" / "ui" / "build" / "ui_v16.bin"
if FEATURE_PACK_V15.with_suffix(".append.json").exists():
    # back to the stock 4 x 70 px app list (the reference's row density): drop c1's 93 px row patches
    _LIST93 = {0x00851E7C, 0x00851F10, 0x00851EAA, 0x008524A6, 0x008524CA, 0x00852532}

    def _c9():
        from s100_ext import build as _ext_build
        return [p for p in MODS["c1_layout"][1] if p[0] not in _LIST93] + _ext_build(FEATURE_PACK_V15)
    MODS["c9_apps"] = (1336, _c9, "c8 + app list / grid after the reference (pill rows, 4 per screen; "
                       "rounded tiles), SpO2 ring / Measure button, quick-panel battery % at 100 % (pairs with ui_v15)")
    MODS["c10_prefs"] = (1337, _c9, "c9 + watch-side preferences saved (on change at screen-off and on power "
                         "off), button opens the grid when the menu style is grid (pairs with ui_v15)")
    MODS["c11_grid"] = (1338, _c9, "c10 + app grid rows every 76 px like the columns (uniform 12 px gaps, "
                        "three rows centred) (pairs with ui_v15)")
    MODS["c12_inset"] = (1339, _c9, "c11 + Settings list icons 10 px inside their rows (pairs with ui_v15)")
    MODS["c13_gridscroll"] = (1340, _c9, "c12 + grid drag / momentum use the 76 px row step too (no jump "
                              "while scrolling) (pairs with ui_v15)")
FEATURE_PACK_V14 = ROOT / "research" / "ui" / "build" / "ui_v14.bin"
if FEATURE_PACK_V14.with_suffix(".append.json").exists():
    def _c8():
        from s100_ext import build as _ext_build
        return MODS["c1_layout"][1] + _ext_build(FEATURE_PACK_V14)
    MODS["c8_aod"] = (1335, _c8, "c7 + text cut-off fix (box 56), AOD after the reference with its own "
                      "backlight level, wrist-down -> AOD, quick panel from every side page, two-page "
                      "watch settings (pairs with ui_v14)")

if FEATURE_PACK_V16.with_suffix(".append.json").exists():
    def _c14():
        from s100_ext import build as _ext_build
        return [p for p in MODS["c1_layout"][1] if p[0] not in _LIST93] + _ext_build(FEATURE_PACK_V16)
    MODS["c14_nav"] = (1341, _c14, "c13 + navigation: text fitted (two street lines, ellipsis), unit beside "
                       "the distance, 16 arrows (sharp / keep / merge / exit / U-turn right) (pairs with ui_v16)")


def grow_image(data: bytearray) -> None:
    """Fix the size fields of an app image that grew past the stock end (same layout as the UI pack:
    MP header TLVs 0x04/0x14 = image size, control header +8 = payload length). The body is padded
    to 16 bytes (the DFU rejects a body that does not end on a word boundary). The SHA-256 is
    recomputed afterwards by rehash_rtl_image.py. The running firmware's DFU code checks the size
    against the app bank, so an image that does not fit is refused, not written."""
    import struct
    data.extend(bytes((-(len(data) - 0x20C)) % 16))
    image_size = len(data) - 0x200
    for tlv in (0x04, 0x14):
        i = 0
        while i < 0x200:
            t, n = struct.unpack_from("<HB", data, i)
            if t == tlv:
                struct.pack_into("<I", data, i + 3, image_size)
                break
            i += 3 + n
        else:
            raise SystemExit(f"MP header TLV {tlv:#x} not found")
    struct.pack_into("<I", data, 0x208, len(data) - 0x600)


def build(name: str, stock: Path, version: int | None) -> Path:
    default_ver, patches, _ = MODS[name]
    if callable(patches):                       # built on demand (needs the compiler)
        patches = patches()
    data = bytearray(stock.read_bytes())
    stock_len = len(data)
    for addr, old, new in patches:
        old_b, new_b = bytes.fromhex(old.replace(" ", "")), bytes.fromhex(new.replace(" ", ""))
        off = MP + addr - BASE
        if data[off:off + len(old_b)] != old_b:
            raise SystemExit(f"{name}: bytes at {addr:#x} don't match stock — wrong input image?")
        if off + len(new_b) > len(data):             # code appended after the stock image
            data.extend(bytes(off + len(new_b) - len(data)))
        data[off:off + len(new_b)] = new_b
    if len(data) > stock_len:
        grow_image(data)
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
