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
PACK = ROOT / "research" / "ui" / "build" / "ui_v16.bin"
FW_BASE = 0x0080DE00
GCC_DIR = Path(r"C:\Program Files (x86)\Arm GNU Toolchain arm-none-eabi\14.2 rel1\bin")

# caves (dead factory code; docs/ui-upgrade-plan.md §12.7). 0x84D432-0x84D4B6 = world-clock handler.
TRAMP = (0x0084D4B8, 0x0084D600)          # hook trampolines
TEXT = (0x0084D600, 0x0084E36C)           # C code
RODATA = (0x0084FCC4, 0x00850294)         # C constants (HeartCheckLightLeakage code)
SPARE = (0x0085F460, 0x0085FAF8)          # C code, part 2 (FactoryTpTest code)
# Code and constants appended after the end of the stock app image (the image grows; size fields and
# SHA-256 are fixed by tools/s100_mods.py). Not copied to RAM at boot (startup copy sizes are fixed).
TAIL = (0x008974D0, 0x0089A4D0)          # 12 KB; the image grows only by what is used

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
    nav = [next(v for n, v in amap.items() if n.startswith(f"e_nav{k}_")) for k in range(8)]
    nav += [amap[n] for n in sorted(n for n in amap if n.startswith("r_nav"))]
    # frame tables for the dock / AOD / charging screens (generated header, included by ext.c)
    def table(prefix):
        names = sorted(n for n in amap if n.startswith(prefix))
        return "{" + ", ".join(f"{amap[n]:#x}u" for n in names) + "}"
    from ui_apps_art import spo2_octant_boxes, spo2_widths
    import math
    import ui_breathe_art as br_art
    from s100_ui import UI_BIN, payload, walk
    spo2_w, spo2_oct = spo2_widths(), spo2_octant_boxes()
    stock_images, _ = walk(payload(UI_BIN.read_bytes()))
    br_slots = br_art.frame_slots({i: stock_images[i][1] for i in br_art.SLOTS_120 + br_art.SLOTS_170})

    def img(i):
        return int(idx[i]["flash"], 16)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "art.h").write_text("\n".join([
        "/* generated by tools/s100_ext.py from the UI pack's .append.json */",
        f"static const uint32_t DIG_BOLD_W[11] = {table('f_bw')};",
        # navigation arrows in ext.c NAV_DIRS order: e_nav0-7, then r_nav08-15
        "static const uint32_t NAV_IMG[16] = {" + ", ".join(f"{v:#x}u" for v in nav) + "};",
        f"static const uint32_t NAVD[11] = {table('s_navd')};",
        # SpO2 screen (rev 16)
        f"#define SPO2_CARD {amap['v_spo2_a_card']:#x}u",
        f"#define SPO2_HEAD {amap['v_spo2_a_head']:#x}u",
        f"static const uint32_t SPO2_D[10] = {table('v_spo2_b_d')};",
        "static const uint8_t SPO2_DW[10] = {" + ", ".join(map(str, spo2_w["val"])) + "};",
        f"#define SPO2_PCT {amap['v_spo2_c_pct']:#x}u",
        f"#define SPO2_PCT_W {spo2_w['pct']}",
        f"#define SPO2_DASH {amap['v_spo2_c_dash']:#x}u",
        f"#define SPO2_DASH_W {spo2_w['dash']}",
        f"#define SPO2_TRACK {amap['v_spo2_d_track']:#x}u",
        f"#define SPO2_DOT {amap['v_spo2_d_dot']:#x}u",
        f"static const uint32_t SPO2_OCT[8] = {table('v_spo2_d_oct')};",
        "static const uint8_t SPO2_OCTB[8][4] = {" + ", ".join(
            "{" + ", ".join(map(str, b)) + "}" for b in spo2_oct) + "};",
        f"#define SPO2_SEG_ON {amap['v_spo2_e_seg_on']:#x}u",
        f"#define SPO2_SEG_OFF {amap['v_spo2_e_seg_off']:#x}u",
        f"static const uint32_t SPO2_ST[3] = {table('v_spo2_f_st')};",
        # Breathe screen (stock slots redrawn in place by tools/ui_breathe_art.py)
        *[f"#define BR_{n} {img(i):#x}u" for n, i in (
            ("CHEVRON", 605), ("TITLE", 598), ("PANEL", 1566), ("HERO", 1565), ("CARD_L", 1539),
            ("CARD_R", 1540), ("MIN", 600), ("START", 1536), ("LBL_READY", 624), ("LBL_DONE", 621),
            ("LBL_HOLD", 1555), ("LBL_IN", 639), ("LBL_OUT", 638), ("DOT_ON", 626), ("DOT_OFF", 625))],
        "static const uint32_t BR_DIGIT[10] = {" + ", ".join(f"{img(606 + k):#x}u" for k in range(10)) + "};",
        "static const uint32_t BR_PACE_IMG[3] = {" + ", ".join(f"{img(i):#x}u" for i in (601, 602, 599)) + "};",
        "static const uint32_t BR_FRAME[20] = {" + ", ".join(f"{img(i):#x}u" for i in br_slots) + "};",
        f"#define BR_BIG {sum(1 << k for k, i in enumerate(br_slots) if i in br_art.SLOTS_170):#x}u",
        "static const uint8_t BR_EASE[18] = {" + ", ".join(
            str(round(19 * (1 - math.cos(math.pi * k / 17)) / 2)) for k in range(18)) + "};",
        # built-in face slot 3 (Grid): its builder's frame table = time frames (14) then, 0x38 bytes on,
        # the date frames (stock 14 at 0x88A294); referenced only by the patched literal 0x8469D8
        "const uint32_t DIAL3_TAB[28] __attribute__((used)) = {" + ", ".join(
            [f"{amap['s_navd00']:#x}u"] * 3 +                                     # '-' '.' '/' unused
            [f"{amap[f's_navd{k:02d}']:#x}u" for k in range(10)] + [f"{amap['u_dial3_d13']:#x}u"] +
            [f"{struct.unpack_from('<I', fw, 0x0088A294 - FW_BASE + 4 * k)[0]:#x}u" for k in range(14)]) + "};",
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
                                 plug=0x832008, touch=0x83D4E0, raise_off=0x83226E, hr_next=0x850BD2,
                                 apps_go=0x8433AE).items()}

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
    # key action 14 (open apps; the face's button) always switched to the list: honour the menu style
    # (settings +0x220 == 1: grid), as the stock slide code does for swipes (0x844D74 / 0x844F6E)
    add_tramp("apps", """
        movw r1, #0xC0A4
        movt r1, #0x20
        ldrb r1, [r1]
        movw r0, #0xDD10
        movt r0, #0x20
        cmp r1, #1
        bne go
        movw r0, #0xE5E0
        movt r0, #0x20
    go: b.w 0x8433AE""")
    # app grid row y (replaces "subs r0, r6, #1; mul fp, r0, r7" at 0x865458): rows start 26 px lower
    # so that, with 76 px rows, three rows of 64 px tiles sit centred (32 px margins); the touch cells use
    # the same y, so they move with the tiles
    add_tramp("gridy", """
        subs r0, r6, #1
        mul fp, r0, r7
        add.w fp, fp, #26
        bx lr""")
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
    patch(0x0083C2D6, bytes.fromhex("1028"), bytes.fromhex("1928"))   # < 16 -> 50 (was < 25)
    # backlight_apply sends 1 + n edges and the driver wraps after 16: cap n at 14, not 15 (0x83C36C/70)
    patch(0x0083C36C, bytes.fromhex("0e2c"), bytes.fromhex("0f2c"))
    patch(0x0083C370, bytes.fromhex("0e24"), bytes.fromhex("0f24"))
    # stock charging screen (BatteryCharging, also the powered-off charge state): positions only, no
    # code. Clock 209 -> 16 (top); ring 46 -> 81 (centred: 81-199); percentage digits 91 -> 126 and
    # '%' 95 -> 130 (moved with the ring). Builder 0x8496F6.
    for addr, old, new in [(0x00849726, 0x2E, 0x51), (0x00849788, 0x2E, 0x51), (0x00849756, 0x5B, 0x7E),
                           (0x008497AE, 0x5F, 0x82), (0x008497C8, 0xD1, 0x10)]:
        reg = rd(fw, addr, 2)[1]
        patch(addr, bytes([new, reg]), bytes([old, reg]))
    # ---- built-in face slot 3 -> "Grid" (builder 0x846612; art tools/ui_dials_art.py): new 36 x 52 time
    # digits centred in the dot-ring disc, date below. Data / constants only, no code on the face.
    if "u_dial3_d13" in amap:
        patch(0x008469D8, struct.pack("<I", syms["DIAL3_TAB"]))           # frame table (time + date)
        patch(0x008469DC, struct.pack("<I", amap["s_navd00"]))            # '0' frame
        patch(0x008469E0, struct.pack("<I", amap["u_dial3_d13"]))         # ':' frame
        patch(0x00846678, asm("mov.w r8, #44", 0x00846678), asm("mov.w r8, #0x27", 0x00846678))    # h
        patch(0x00846680, asm("mov.w sb, #32", 0x00846680), asm("mov.w sb, #0x1e", 0x00846680))    # w
        patch(0x00846684, asm("mov.w sl, #100", 0x00846684), asm("mov.w sl, #0x31", 0x00846684))    # time y
        for addr, old, new in [(0x00846688, 0x34, 52), (0x008466B8, 0x69, 104), (0x008466B6, 0x2C, 100),
                               (0x008466D6, 0x80, 124), (0x00846712, 0x6C, 154)]:   # hh x, ':' x/y, mm x, date y
            reg = rd(fw, addr, 2)[1]
            patch(addr, bytes([new, reg]), bytes([old, reg]))
    # ---- built-in face slot 1 -> "Dashboard" (builder 0x84792E): white dot time (the 40 x 60 always-on
    # digits), weekday on top, heart-rate card, activity-rings tile, steps / kcal card
    if "m_aod_a_w0" in amap:
        # the builder reaches the weekday (-0x1C), ring (-0x74 / -0xA0 / -0x48) and heart-rate (+0x38)
        # tables from the time table's address, so the time table (14 words, "- . / 0-9 :") is
        # rewritten in place instead of moved
        dots = [amap["m_aod_a_w0"]] * 3 + [amap[f"m_aod_a_w{k}"] for k in range(10)] + [amap["m_aod_a_w0"]]
        for k, a in enumerate(dots):
            patch(0x0088A784 + 4 * k, struct.pack("<I", a))
        patch(0x00847D54, struct.pack("<I", amap["m_aod_a_w0"]))          # '0' frame
        patch(0x00847994, asm("mov.w sl, #60", 0x00847994), asm("mov.w sl, #0x38", 0x00847994))    # h
        patch(0x0084799E, asm("mov.w fp, #40", 0x0084799E), asm("mov.w fp, #0x2b", 0x0084799E))    # w
        patch(0x008479A2, asm("mov.w sb, #56", 0x008479A2), asm("mov.w sb, #0x94", 0x008479A2))    # time y
        patch(0x00847A68, asm("mov.w r8, #234", 0x00847A68), asm("mov.w r8, #0x6d", 0x00847A68))   # steps / kcal y
        for addr, old, new in [(0x008479A6, 0x1A, 30), (0x008479D8, 0x84, 130),     # hh x, mm x
                               (0x00847A2E, 0xA7, 40), (0x00847A2C, 0x32, 166),     # heart rate x, y
                               (0x00847A72, 0x2F, 40), (0x00847A98, 0xA1, 132),     # steps x, kcal x
                               (0x00847ADA, 0x13, 139), (0x00847AD6, 0x0F, 125),    # ring 76: x, y
                               (0x00847B24, 0x1C, 148), (0x00847B20, 0x17, 133),    # ring 59
                               (0x00847B52, 0x25, 157), (0x00847B4C, 0x20, 142),    # ring 41
                               (0x00847B70, 0x31, 40), (0x00847B6E, 0x80, 216),     # "steps" label
                               (0x00847B90, 0xA3, 132), (0x00847B8E, 0x80, 216),    # "kcal" label
                               (0x00847BBA, 0x29, 14), (0x00847BB4, 0xE5, 12)]:     # weekday
            reg = rd(fw, addr, 2)[1]
            patch(addr, bytes([new, reg]), bytes([old, reg]))
    # SpO2 screen: build wrapped (descriptor init 0x895DD0: +0x1C build, +0x33 capacity 18 -> 32)
    patch(0x00895DD0 + 0x1C, struct.pack("<I", S["t_spo2_build"]), struct.pack("<I", 0x0084A9D3))
    patch(0x00895DD0 + 0x33, bytes([32]), bytes([18]))
    # face picker ring (WatchPreview1-3 + WatchOnlinePreview for an uploaded face). Stock splices the
    # uploaded face into the ring by replacing *both* of preview 2's neighbours (0x85E29C: left == P1
    # -> Online, right == P3 -> Online), so swiping right went 1 2 Online 3 and swiping left 1 3 2 Online:
    # faces repeated / came at the wrong time. Now 1 <-> 2 <-> 3 <-> Online <-> 1 both ways: P1's left
    # (P3) and P3's right (P1) become Online, and Online's own left / right are P3 / P1 (swapped loads).
    for addr, old, new in [(0x0085E2B6, "ldr r1, [pc, #0x2c8]", "ldr r1, [pc, #0x2d0]"),   # left == P3
                           (0x0085E2C2, "ldr r1, [pc, #0x2c4]", "ldr r1, [pc, #0x2bc]"),   # right == P1
                           (0x0085E16E, "ldr r0, [pc, #0xd8]", "ldr r0, [pc, #0xdc]"),     # Online left = P3
                           (0x0085E172, "ldr r1, [pc, #0xd8]", "ldr r1, [pc, #0xd4]")]:    # Online right = P1
        patch(addr, asm(new, addr), asm(old, addr))
    # Breathe screen: build wrapped (descriptor init 0x895E0C +0x1C); breath timer at twice the rate
    # and twice the count per phase (22 ticks: same phase length, smoother animation): event handler
    # 0x84B700 (period per pace, toggle at count 21) and enter 0x84B7EA (period when resuming)
    patch(0x00895E0C + 0x1C, struct.pack("<I", S["t_breath_build"]), struct.pack("<I", 0x0084B9CB))
    for addr, old, new in [(0x0084B7A0, "mov.w r1, #0x320", "mov.w r1, #0x190"),     # Calm 800 -> 400 ms
                           (0x0084B7BC, "mov.w r1, #0x3e8", "mov.w r1, #0x1f4"),     # Slow 1000 -> 500 ms
                           (0x0084B7C2, "mov.w r1, #0x1f4", "mov.w r1, #0xfa"),      # Fast 500 -> 250 ms
                           (0x0084B7B0, "cmp r0, #0xa", "cmp r0, #0x15"),           # 11 -> 22 ticks a phase
                           (0x0084B92A, "mov.w r1, #0x320", "mov.w r1, #0x190"),
                           (0x0084B94A, "mov r1, r5", "lsrs r1, r5, #1"),           # r5 = 1000
                           (0x0084B94E, "mov.w r1, #0x1f4", "mov.w r1, #0xfa")]:
        patch(addr, asm(new, addr), asm(old, addr))
    # every settings save also writes our record (ext.c t_save_settings)
    patch(0x00830654, asm(f"b.w {syms['t_save_settings']:#x}", 0x00830654), bytes.fromhex("10b5ff4c"))
    # unplugged / charge complete with the display on: always-on instead of off (bl 0x8464FA)
    patch(0x00830FA8, asm(f"bl {syms['t_charger_off']:#x}", 0x00830FA8), asm("bl 0x8464FA", 0x00830FA8))
    patch(0x008433A4, asm(f"b.w {tramp['apps']:#x}", 0x008433A4), bytes.fromhex("424802e0"))
    # app grid: rows every 76 px like the columns (64 px tiles, 12 px gaps both ways; stock 92 px rows
    # left 28 px between rows). Builder row height, tile offset in the row, rows drawn per frame (5 -> 6:
    # no empty strip at the bottom while scrolling), and the scroller's height (3 rows per screen ->
    # 3 x 76 = 228 instead of 276) in the snap math and the scroll call
    patch(0x00865404, bytes.fromhex("4c27"), bytes.fromhex("5c27"))
    patch(0x00865458, asm(f"bl {tramp['gridy']:#x}", 0x00865458) + bytes.fromhex("00bf"),
          bytes.fromhex("701e00fb07fb"))
    patch(0x00865486, asm("add.w sb, fp, #6", 0x00865486), bytes.fromhex("0bf11409"))
    patch(0x0086555A, bytes.fromhex("062e"), bytes.fromhex("052e"))
    # every "(276 - margins) / 3" row step of the grid: snap on release (0x865940/66), finger drag
    # (0x865A82), the momentum timer (0x865626, 0x86571E) and the other release cases (0x865BEC/C12).
    # (r1 and r0 forms; 0x865C5C, the tap zone 0..276, is not a row step and stays)
    for addr in (0x00865940, 0x00865966, 0x00865BEC, 0x00865C12):
        patch(addr, asm("rsb.w r0, r0, #0xe4", addr), bytes.fromhex("c0f58a70"))
    for addr in (0x00865626, 0x0086571E, 0x00865A82):
        patch(addr, asm("rsb.w r1, r1, #0xe4", addr), bytes.fromhex("c1f58a71"))
    patch(0x008659EC, asm("mov.w r0, #0xe4", 0x008659EC), bytes.fromhex("4ff48a70"))
    # Settings list (FunctionList): row icon 4 px inside its row background (x 14 in a row at x 10) ->
    # x 20, the 10 px inset of the other list screens (Workout list); the label stays at x 70
    patch(0x0084F3CE, bytes.fromhex("1422"), bytes.fromhex("0e22"))
    # power off: save changed preferences first (bl 0x83162C at 0x831664)
    patch(0x00831664, asm(f"bl {syms['t_power_off']:#x}", 0x00831664), asm("bl 0x83162C", 0x00831664))
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
