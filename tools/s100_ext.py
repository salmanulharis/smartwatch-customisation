"""Build the S100 feature extensions (firmware/s100_ext) into patches for the stock app image.

    python tools/s100_ext.py [--pack research/ui/build/ui_v8.bin]   # build + print a summary

The C code is compiled with arm-none-eabi-gcc and linked into dead factory-test code (caves);
the hook trampolines are assembled with Keystone at fixed addresses. tools/s100_mods.py turns the
result into mod "c2_features" (= c1_layout + these patches). The app image is paired with the UI
pack whose .append.json gave the image addresses: install that pack first.
See docs/ui-upgrade-plan.md §12.7 for what each hook does and why it is safe.
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
from pathlib import Path

from keystone import KS_ARCH_ARM, KS_MODE_THUMB, Ks

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "firmware" / "s100_ext"
OUT = SRC / "build"
STOCK = ROOT / "research" / "firmware" / "RH288A_V001319_fw_1660354713_5619.bin"
PACK = ROOT / "research" / "ui" / "build" / "ui_v15.bin"
FW_BASE = 0x0080DE00
GCC_DIR = Path(r"C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\14.2 rel1\bin")

# caves (dead factory code; docs/ui-upgrade-plan.md §12.7). 0x84D432-0x84D4B6 = world-clock handler.
TRAMP = (0x0084D4B8, 0x0084D600)          # hook trampolines
TEXT = (0x0084D600, 0x0084E36C)           # C code
RODATA = (0x0084FCC4, 0x00850294)         # C constants (HeartCheckLightLeakage code)
SPARE = (0x0085F460, 0x0085FAF8)          # C code, part 2 (FactoryTpTest code)
# Code and constants appended after the end of the stock app image (the image grows; size fields and
# SHA-256 are fixed by tools/s100_mods.py). Not copied to RAM at boot (startup copy sizes are fixed).
TAIL = (0x008974D0, 0x008994D0)

D_CLOCK, D_NAV, D_WATCHSET = 0x0020DA1C, 0x0020DA54, 0x0020E35C
INIT = {D_CLOCK: 0x00895EB4, D_NAV: 0x00895EEC, D_WATCHSET: 0x008967F4, 0x0020DBA8: 0x00896040}
SLOTS = {0x0C: "key0c", 0x10: "touch", 0x14: "enter", 0x18: "exit", 0x1C: "build", 0x20: "event", 0x28: "key"}


def rd(fw: bytes, addr: int, n: int) -> bytes:
    return fw[addr - FW_BASE:addr - FW_BASE + n]


def asm(code: str, addr: int) -> bytes:
    """Keystone mis-encodes conditional wide branches to absolute targets: use only short
    conditional branches to local labels and unconditional b.w / bl for far targets (checked by
    verify_branches)."""
    enc, _ = Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(code, addr)
    return bytes(enc)


def verify_branches(code: bytes, addr: int, allowed: set[int]) -> None:
    from capstone import CS_ARCH_ARM, CS_MODE_MCLASS, CS_MODE_THUMB, Cs
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    for i in md.disasm(code, addr):
        if i.mnemonic.startswith("b") and i.op_str.startswith("#"):
            tgt = int(i.op_str[1:], 0)
            if not (addr <= tgt < addr + len(code)) and tgt not in allowed:
                raise SystemExit(f"{i.address:#x}: {i.mnemonic} {i.op_str} -> unexpected target")


def stock_symbols() -> str:
    """Linker definitions for the stock functions declared in stock.h with "/* @0xADDR */"."""
    import re
    syms = re.findall(r"^[\w \*]+?\b(\w+)\([^;\n]*\);[ \t]*/\*\s*@(0x[0-9A-Fa-f]+)", (SRC / "stock.h").read_text(),
                      re.M)
    return "".join(f"{name} = {int(addr, 16) | 1:#x};\n" for name, addr in syms)


def compile_c(defines: dict[str, int]) -> tuple[dict[str, int], dict[str, tuple[int, bytes]]]:
    OUT.mkdir(parents=True, exist_ok=True)
    ld = OUT / "ext.ld"
    ld.write_text(stock_symbols() + f"""
MEMORY {{
  TEXT (rx) : ORIGIN = {TEXT[0]:#x}, LENGTH = {TEXT[1] - TEXT[0]:#x}
  TEXT2 (rx) : ORIGIN = {SPARE[0]:#x}, LENGTH = {SPARE[1] - SPARE[0]:#x}
  RODATA (r) : ORIGIN = {RODATA[0]:#x}, LENGTH = {RODATA[1] - RODATA[0]:#x}
  TAIL (rx) : ORIGIN = {TAIL[0]:#x}, LENGTH = {TAIL[1] - TAIL[0]:#x}
}}
SECTIONS {{
  .tail : {{ *(.text.t_*) *(.rodata*) }} > TAIL
  .text2 : {{ *(.text.ws_*) *(.text.qp_*) *(.text.tap_*) *(.text.aod_screen_off) *(.text.aod_toggle) }} > TEXT2
  .text : {{ *(.text*) }} > TEXT
  .rodata : {{ *(.rodata*) }} > RODATA
  .data : {{ *(.data*) }} > RODATA
  .bss : {{ *(.bss*) *(COMMON) }} > RODATA
  /DISCARD/ : {{ *(.ARM.*) *(.comment) }}
}}
""")
    elf = OUT / "ext.elf"
    cmd = [str(GCC_DIR / "arm-none-eabi-gcc.exe"), "-mcpu=cortex-m4", "-mthumb", "-Os", "-ffreestanding",
           "-fno-builtin", "-nostdlib", "-nostartfiles", "-Wall", "-Wextra", "-Werror", "-fno-common",
           "-fno-jump-tables", "-ffunction-sections", "-T", str(ld), f"-Wl,-Map={OUT / 'ext.map'}", "-Wl,--no-warn-rwx-segments",
           "-o", str(elf), str(SRC / "ext.c")]
    cmd[1:1] = [f"-D{k}={v:#x}" for k, v in defines.items()] + [f"-I{OUT}"]
    subprocess.run(cmd, check=True)
    nm = subprocess.run([str(GCC_DIR / "arm-none-eabi-nm.exe"), str(elf)], check=True, capture_output=True,
                        text=True).stdout
    syms = {}
    for line in nm.splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    secs = {}
    for name in (".text", ".text2", ".tail", ".rodata", ".data", ".bss"):
        b = OUT / f"{name[1:]}.bin"
        subprocess.run([str(GCC_DIR / "arm-none-eabi-objcopy.exe"), "-O", "binary", f"--only-section={name}",
                        str(elf), str(b)], check=True)
        data = b.read_bytes()
        if data:
            secs[name] = (syms.get(f"__{name[1:]}_start", 0), data)
    if secs.get(".data") or secs.get(".bss"):
        raise SystemExit("ext.c must not have .data/.bss (there is no startup code to initialise them)")
    # section addresses from the ELF section headers
    hdr = subprocess.run([str(GCC_DIR / "arm-none-eabi-objdump.exe"), "-h", str(elf)], check=True,
                         capture_output=True, text=True).stdout
    for line in hdr.splitlines():
        p = line.split()
        if len(p) > 4 and p[1] in secs:
            secs[p[1]] = (int(p[3], 16), secs[p[1]][1])
    return syms, secs


def tile_table(amap: dict[str, int]) -> str:
    names = sorted(n for n in amap if n.startswith("l_qp_") and not n.startswith("l_qp_m_"))
    assert len(names) == 12, names
    return "{" + ", ".join(f"{amap[n]:#x}u" for n in names) + "}"


def qs_weekday_widths() -> list[int]:
    from ui_apps_art import qs_weekday_widths as w
    return w()


def build(pack: Path = PACK) -> list[tuple[int, str, str]]:
    """Patch list (address, original hex, new hex) on top of stock, for tools/s100_mods.py."""
    fw = STOCK.read_bytes()
    amap = {k: int(v, 16) for k, v in json.loads(pack.with_suffix(".append.json").read_text()).items()}
    idx = json.loads((ROOT / "research" / "ui" / "index.json").read_text())["images"]
    defines = {
        "IMG_ROW_BG": int(idx[756]["flash"], 16),             # 220x80 settings row background
        **{f"IMG{i}": int(idx[i]["flash"], 16) for i in range(888, 895)},   # stock quick-panel tiles
        "DIGIT_TABLE": 0x0088A63C, "DIGIT_W": 37, "DIGIT_H": 44,   # 37x44 digit set (IMG73-86)
        "IMG_TILE_AOD_OFF": amap["a_tile_aod_off"], "IMG_TILE_AOD_ON": amap["a_tile_aod_on"],
        "IMG_TILE_FIND": amap["b_tile_find"], "IMG_TILE_WATCHSET": amap["c_tile_watchset"],
        "IMG_TILE_CLOCK": amap["d_tile_clock"],
    }
    for k in range(8):
        defines[f"IMG_NAV{k}"] = next(v for n, v in amap.items() if n.startswith(f"e_nav{k}_"))
    # frame tables for the dock / AOD / charging screens (generated header, included by ext.c)
    def table(prefix):
        names = sorted(n for n in amap if n.startswith(prefix))
        return "{" + ", ".join(f"{amap[n]:#x}u" for n in names) + "}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "art.h").write_text("\n".join([
        "/* generated by tools/s100_ext.py from the UI pack's .append.json */",
        f"static const uint32_t DIG_BOLD_W[11] = {table('f_bw')};",
        f"static const uint32_t DIG_BOLD_O[11] = {table('g_bo')};",
        f"static const uint32_t RING[11] = {table('j_ring')};",
        f"#define IMG_BOLT {amap['k_bolt']:#x}u",
        f"#define IMG_BATTERY {amap['k_battery']:#x}u",
        f"static const uint32_t WX_ICON[4] = {table('k_wx')};",
        # quick panel: 12 tiles (dnd, dnd_on, bright, aod, aod_on, raise, raise_on, torch, find,
        # watchset, dock, settings) and 4 brightness level bars
        f"static const uint32_t QP_TILE[12] = {tile_table(amap)};",
        f"static const uint32_t QP_LEVEL[4] = {table('l_qp_m_level')};",
        f"static const uint32_t AOD_W[10] = {table('m_aod_a_w')};",
        f"static const uint32_t AOD_O[10] = {table('m_aod_b_o')};",
        # always-on layout after the owner's reference (rev 14): word images, sprite digits, icons
        f"static const uint32_t AOD_DAY[7] = {table('o_aod_a_day')};",
        f"static const uint32_t AOD_MON[12] = {table('o_aod_b_mon')};",
        f"static const uint32_t AOD_SW[14] = {table('o_aod_c_sw')};",
        f"static const uint32_t AOD_SG[14] = {table('o_aod_d_sg')};",
        f"#define AOD_PCT {amap['o_aod_e_pct']:#x}u",
        f"#define AOD_DEG {amap['o_aod_e_deg']:#x}u",
        f"static const uint32_t AOD_WX2[4] = {table('o_aod_f_wx')};",
        f"#define AOD_STEPS2 {amap['o_aod_g_steps']:#x}u",
        f"#define AOD_DIV2 {amap['o_aod_g_div']:#x}u",
        f"#define AOD_COLON2 {amap['o_aod_h_colon']:#x}u",
        f"static const uint32_t AOD_BAT2[5] = {table('o_aod_i_bat')};",
        f"#define IMG_WS_ROW {amap['n_ws_row']:#x}u",
        # quick-panel status bar text (rev 15): digits "-./0-9:", %, weekday words + their ink widths
        f"static const uint32_t QS_DIG[14] = {table('q_qs_a_d')};",
        f"#define QS_PCT {amap['q_qs_b_pct']:#x}u",
        f"static const uint32_t QS_WD[7] = {table('q_qs_c_wd')};",
        "static const uint8_t QS_WDW[7] = {" + ", ".join(map(str, qs_weekday_widths())) + "};",
        ""]))
    syms, secs = compile_c(defines)
    patches: list[tuple[int, str, str]] = []

    def patch(addr: int, new: bytes, old: bytes | None = None):
        cur = rd(fw, addr, len(new))
        if old is not None and cur != old:
            raise SystemExit(f"{addr:#x}: stock bytes {cur.hex()} != expected {old.hex()}")
        patches.append((addr, cur.hex(), new.hex()))

    for name, (addr, data) in secs.items():
        lo, hi = {".text": TEXT, ".text2": SPARE, ".rodata": RODATA, ".tail": TAIL}[name]
        assert lo <= addr and addr + len(data) <= hi, (name, hex(addr), len(data))
        patch(addr, data)

    S = {k: v | 1 for k, v in syms.items()}                   # Thumb function addresses
    # ---- trampolines
    t = TRAMP[0]
    tramp = {}
    far = {k: v for k, v in dict(c5a=0x836D48, c5b=0x836C9E, tap=0x84347A, ok=0x844B7E, no=0x844C06,
                                 plug=0x832008, touch=0x83D4E0, raise_off=0x83226E, hr_next=0x850BD2).items()}

    def add_tramp(name: str, code: str):
        nonlocal t
        b = asm(code, t)
        verify_branches(b, t, set(far.values()) | {syms[n] for n in ("nav_check", "tap_tick", "t_touch_wake",
                                                                       "t_raise_on", "t_hr_down")})
        tramp[name] = t
        patch(t, b)
        t += (len(b) + 3) & ~3
        assert t <= TRAMP[1]

    # C5 notification handler, after the ack (r4 = type, r5 = length-prefixed UTF-16BE text)
    add_tramp("c5", f"""
        mov r0, r5
        bl {syms['nav_check']:#x}
        cmp r0, #0
        bne done
        cmp r4, #3
        beq done
        b.w 0x836D48
    done: b.w 0x836C9E""")
    # touch hit test, tap path: tick, then the original `movs r0,#0; b 0x84347A`
    add_tramp("tap", f"""
        push {{r0, r1, r2, r3, r12, lr}}
        bl {syms['tap_tick']:#x}
        pop {{r0, r1, r2, r3, r12, lr}}
        movs r0, #0
        b.w 0x84347A""")
    # gui_switch charger gate: also allow the desk clock and navigation screens
    # gui_switch charger gate: once booted (d154+0xDB != 0) every screen is allowed while charging;
    # the powered-off charge-only state keeps the stock rule
    add_tramp("gate", f"""
        movw r0, #0xD22F
        movt r0, #0x20
        ldrb r0, [r0]
        cbnz r0, ok
        cmp r4, r7
        beq ok
        movw r0, #{D_CLOCK & 0xFFFF:#x}
        movt r0, #{D_CLOCK >> 16:#x}
        cmp r4, r0
        beq ok
        movw r0, #{D_NAV & 0xFFFF:#x}
        movt r0, #{D_NAV >> 16:#x}
        cmp r4, r0
        beq ok
        b.w 0x844C06
    ok: b.w 0x844B7E""")
    # touch message while the screen is dark (0x83D4CE, the unused +0xA6D path): touch to wake
    add_tramp("touch", f"""
        push {{r0, r1, r2, r3, r12, lr}}
        bl {syms['t_touch_wake']:#x}
        pop {{r0, r1, r2, r3, r12, lr}}
        b.w 0x83D4E0""")
    # wrist raised (0x832252, leaf; r2 = display-on flag): display on -> our always-on check
    add_tramp("raise", f"""
        cbz r2, off
        b.w {syms['t_raise_on']:#x}
    off: b.w 0x83226E""")
    # heart-rate page swipe down (r1 = its view flag, r4 = event): quick panel from the first view
    add_tramp("hr", f"""
        mov r0, r1
        mov r1, r4
        bl {syms['t_hr_down']:#x}
        b.w 0x850BD2""")
    # ---- hooks in stock code
    patch(0x00836D44, asm(f"b.w {tramp['c5']:#x}", 0x00836D44), bytes.fromhex("032caad0"))
    patch(0x0084341E, asm(f"b.w {tramp['tap']:#x}", 0x0084341E), bytes.fromhex("00202be0"))
    patch(0x00844B7A, asm(f"b.w {tramp['gate']:#x}", 0x00844B7A), bytes.fromhex("bc4243d1"))
    # charger plug/unplug: C decides (dock / stay / stock handler 0x832008)
    patch(0x0083DDBC, asm(f"bl {syms['charger_change']:#x}", 0x0083DDBC), bytes.fromhex("f4f724f9"))
    patch(0x00859012, asm(f"b.w {syms['qp_build']:#x}", 0x00859012), bytes.fromhex("fff7e6bb"))
    # screen-off timer path: always-on display instead of screen off when enabled
    patch(0x0084236C, asm(f"b.w {syms['aod_screen_off']:#x}", 0x0084236C), bytes.fromhex("04f0c5b8"))
    # wake options: button (tail call of the dark-screen short press), touch, raise while always-on
    patch(0x0083D486, asm(f"b.w {syms['t_button_wake']:#x}", 0x0083D486), bytes.fromhex("05f06bbe"))
    patch(0x0083D4CE, asm(f"b.w {tramp['touch']:#x}", 0x0083D4CE), bytes.fromhex("e64890f8"))
    patch(0x0083226A, asm(f"b.w {tramp['raise']:#x}", 0x0083226A), bytes.fromhex("002a0bd1"))
    # wrist-down on an exempt screen (id 0x36): also reset the gesture state (beq 0x835C1C), else
    # raise stays dead until a key press
    patch(0x00835C46, bytes.fromhex("e9d0"), bytes.fromhex("ebd0"))
    # wrist lowered -> always-on screen instead of off when enabled (bl 0x8464FA at 0x835C6C)
    patch(0x00835C6C, asm(f"bl {syms['t_wrist_down']:#x}", 0x00835C6C), asm("bl 0x8464FA", 0x00835C6C))
    # backlight_apply: only 0 counts as "unset" (stock: < 25 -> 50), so the always-on screen can use
    # the two dimmest LED driver steps (ext.c aod_dim); the normal levels stay 25-100 %
    patch(0x0083C2D6, bytes.fromhex("0128"), bytes.fromhex("1928"))
    patch(0x00850BCC, asm(f"b.w {tramp['hr']:#x}", 0x00850BCC) + bytes.fromhex("00bf"),
          bytes.fromhex("0878" "00b1" "0e70"))
    # swipe down opens the quick panel from every side page too (navigation templates, word 5 =
    # swipe-down target, was 0): activity, heart rate, sleep, weather, music
    for tpl in (0x0088A914, 0x0088A95C, 0x0088AE00, 0x0088AA10, 0x0088A938):
        patch(tpl + 20, struct.pack("<I", 0x0020E030), struct.pack("<I", 0))
    # usable while charging: wake goes to the face, not the charging screen (0x851548 str -> nop)
    patch(0x00851548, bytes.fromhex("00bf"), bytes.fromhex("8760"))
    # stock charging screen: button -> face / power-off dialog when booted (+0x28 in its init image)
    patch(0x00895D80, struct.pack("<I", S["t_charge_key"]), struct.pack("<I", 0x008496A5))
    # touch IC "sleep" method: keep it able to wake the watch when touch to wake is on
    patch(0x00895ABC, struct.pack("<I", S["t_tp_sleep"]), struct.pack("<I", 0x0083F289))
    # quick panel: brightness tile cycles 25/50/75/100 % in place (callback 0x858634, 32 bytes)
    patch(0x00858634, bytes.fromhex("68b910b5dff8004494f888011930642888bf192084f88801e3f73efe10bd7047"))
    # quick panel layout: 3 x 3 grid of 64 px tiles, x 16/88/160, y 52/124/196; date in the top bar
    for addr, old, new in [
        (0x00858816, 0x11, 16), (0x00858814, 0x69, 52),      # DND tile
        (0x0085882E, 0x5F, 46), (0x00858822, 0x4F, 72),      # DND touch y, w/h of the top-row touches
        (0x00858846, 0x69, 52), (0x00858862, 0x5F, 46),      # brightness tile y, touch y
        (0x00858886, 0x69, 52), (0x008588A0, 0xA1, 160), (0x0085889E, 0x5F, 46),   # raise-to-wake
        (0x008588B8, 0x34, 88), (0x008588B6, 0xBF, 124),     # flashlight tile -> middle
        (0x008588DA, 0x1E, 80), (0x008588D8, 0xB0, 118), (0x008588C8, 0x64, 72),
        (0x008588F2, 0x7C, 160), (0x008588F0, 0xBF, 196),    # settings tile -> bottom right
        (0x0085890E, 0x78, 160), (0x0085890C, 0xB0, 190),
        (0x00858950, 0x39, 22), (0x00858952, 0x6C, 72),      # date: y 57 -> 22, x 108 -> 72
    ]:
        reg = rd(fw, addr, 2)[1]
        patch(addr, bytes([new, reg]), bytes([old, reg]))
    # ---- app launcher after the owner's reference (art: tools/ui_apps_art.py, rev 15)
    # list: icon + label tables -> pill halves; grid: icon table -> rounded tiles (both 18 entries)
    if "p_apps_a_icon00" in amap:
        for k in range(18):
            for table, name in ((0x0088B718, "a_icon"), (0x0088B7A8, "b_label"), (0x0088CE3C, "c_grid")):
                patch(table + 4 * k, struct.pack("<I", amap[f"p_apps_{name}{k:02d}"]))
        # list rows (stock 70 px; tools/s100_mods.py c9 drops c1's 93 px rows): icon 55 x 55 at x 8,
        # label 165 x 55 at x 63 for every English label (the special 145 px case is bypassed)
        patch(0x00851F5A, asm("sub.w r1, r7, #0x37", 0x00851F5A), bytes.fromhex("a7f13001"))
        patch(0x00851F5E, bytes.fromhex("3722"), bytes.fromhex("3022"))
        patch(0x00851F7C, bytes.fromhex("0822"), bytes.fromhex("0e22"))
        patch(0x0085200E, bytes.fromhex("00bf"), bytes.fromhex("1fd1"))
        patch(0x00852014, bytes.fromhex("a523"), bytes.fromhex("9123"))
        patch(0x0085202E, bytes.fromhex("3f22"), bytes.fromhex("4d22"))
    # ---- screen descriptors (initial values in the .data image): functions, capacity, id
    impl = {D_CLOCK: "clock", D_NAV: "nav", D_WATCHSET: "t_ws"}
    for desc, init in INIT.items():
        for off, slot in SLOTS.items():
            fn = "ext_nop" if desc not in impl or slot == "key0c" else f"{impl[desc]}_{slot}"
            patch(init + off, struct.pack("<I", S[fn]))
        if desc in impl:
            patch(init + 0x33, bytes([24]))                   # widget capacity
    patch(INIT[D_NAV] + 0x30, struct.pack("<H", 0x36), struct.pack("<H", 0x37))   # id 0x36: no wrist-down off
    # UTE factory commands -> plain echo path, so no factory screen or test code can be reached
    for addr, old, new in [(0x00837B74, "41d0", "6dd0"), (0x00837B80, "74d0", "67d0"),
                           (0x00837B86, "7be0", "64e0"), (0x00837B8E, "6cd0", "60d0")]:
        patch(addr, bytes.fromhex(new), bytes.fromhex(old))
    return patches


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pack", type=Path, default=PACK)
    a = ap.parse_args()
    if not shutil.which("arm-none-eabi-gcc") and not GCC_DIR.exists():
        raise SystemExit("arm-none-eabi-gcc not found")
    p = build(a.pack)
    n = sum(len(new) // 2 for _, _, new in p)
    print(f"{len(p)} patches, {n} bytes")
    for line in (OUT / "ext.map").read_text().splitlines():
        if line.startswith((".text", ".rodata", ".tail")):
            print(line)


if __name__ == "__main__":
    main()
