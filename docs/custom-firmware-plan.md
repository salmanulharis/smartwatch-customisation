# TechLife S100 — Custom Firmware Plan

Roadmap from "get the right SDK" to a finished custom watch OS. This is the reference for any
future session (human or AI). Facts and evidence live in [TechLife-S100.md](TechLife-S100.md)
(§12b chip/SDK/layout, "Route B" stock-patching notes); this file is the plan and status.

**Status (2026-10-29):** waiting for Realtek's reply to a request for the legacy RTL8762D SDK
(matching ROM patch rev 239). Phase 0 done. **Track B phase B2 PASSED** (v1322 installed).
**B5 world-clock patch built** (v1323) — 130-byte Thumb-2 handler at 0x89491C renders dial
element type 71 as an offset clock digit (4 cities, emulator-tested). Ready to flash + upload `world.bin`.

---

## Favourites

Features the owner marked as favourites (keep them working in every release; add new ones here).

| # | Feature | Since | Where |
|---|---|---|---|
| 1 | **Always-on display** — dims to a minimal dot-matrix screen (time, date, weather, battery, steps) at minimum backlight instead of turning off; also on the charger. Switch on the watch (quick panel tile, Watch settings), in the Android app and in the Windows app | app r1334 (`c7_wake`); redesigned after the reference with its own brightness (4 levels) and wrist-down → AOD in r1335 (`c8_aod`, installed) | `firmware/s100_ext/ext.c` (`aod_*`, `t_aod_body`, `t_dock_timeout`, `t_wrist_down`), screen-off hook 0x84236C, `docs/ui-upgrade-plan.md` §12.10–12.12 |

## Goal

Replace the stock watch UI with our own, removing all stock watch functions. Target features:
always-on desk clock, car navigation display (turn arrow, distance, speed), music controls,
notifications, all fed from a phone/PC over BLE.

## Hard constraints

1. **BLE only.** The watch cannot be opened. No UART/SWD recovery exists.
2. **Every image we flash must keep a working DFU service** (`6287` + OTA service `d0ff`),
   otherwise the watch is stuck on that build forever.
3. **A build that is accepted but crashes = permanent brick.** A build that is *rejected* is
   harmless (bootloader keeps the current image). So: smallest possible steps, verify before flash.
4. Never flash OTA header (`0x2790`), ROM patch (`0x2792`) or secure boot (`0x2791`) images.
   The watch installs one image per reboot (`multi_img = 0`), so multi-image migrations brick.

## Key device facts

| Item | Value |
|---|---|
| BLE MAC | `78:02:B7:58:FF:9E` |
| SoC | RTL8762D family, ic_type `0x09`, ROM UUID `1d6a69f1 2f38ea11 82a76737 0a3ca32e` |
| ROM patch | `0x580EF000` (rev 239) |
| Images on watch | OTA header, FSBL, ROM patch, APP (standalone, single bank); **no upperstack image** |
| App image | ID `0x2793`, base `0x0080E000`, stock 561 KB, BLE upper stack linked inside the app |
| Stock app version | `0x00527000` (rev 1319) |
| Integrity | SHA-256 (crc16 = 0), no RSA signature; coverage known (`tools/rehash_rtl_image.py`) |
| OTA | silent OTA 0x12, AES-256-ECB (UTE key), buffer check on, max buffer 2048 |
| External flash | XTX XT25F64B 8 MB |
| Display | 1.69" 240×280 IPS, ST7789V2 over 8080 parallel (LCDC) **[likely]** |

## Tooling (working)

| Tool | Purpose |
|---|---|
| `openwearota flash <mac> <file> --limit-function -v` | BLE DFU; proven to `ValidateFW 100301` |
| `tools/patch_rtl_header.py` | set ic_type 0x09 / ctrl_flag 0x0901 on SDK-built images |
| `tools/rehash_rtl_image.py` | recompute SHA-256 (+ optional `--version`) after patching stock |
| `tools/s100_gatt_dump.py` | read-only check of installed versions (`ffd3` patch, `ffd4` app) |
| `tools/s100.py` | stock UTE protocol: nav text, music, weather, time |
| ARM GCC 14.2 + GnuWin32 make | add both to PATH before `make` (see TechLife-S100.md §10) |

---

## Decision point: Realtek's reply

```
Realtek reply
├─ Legacy SDK (patch 239, stack linked in app) ──► Track A (full custom firmware)
├─ Only libs / rom_symbol for patch 239 ──────────► Track A, port libs into SDK v1.1.0 tree
└─ No / no reply ─────────────────────────────────► Track B (modded stock firmware)
```

### SDKs checked (2026-10-29)

| SDK in `sdks/` | ROM UUID | Build | Upper stack | Verdict |
|---|---|---|---|---|
| `RTL8762D_SDK_v1.1.0` (2025-11) | match | GCC + Keil | separate image only (1.1.5.0), patch 440 | no drop-in |
| `sbee2-sdk-gcc-v1.0.0` (2024-04) | match | GCC + Keil | separate image (1.0.497/1.0.628); has `#ifndef SUPPORT_ALONE_UPPERSTACK_IMG` remnants + 2021 `bin/gap_utils.a`, but that lib needs `btif_*`/`le_*` stack symbols nobody ships → non-alone build cannot link | **best base** for Track A0' |
| `SBEE2-SDK-UPPERSTACK-IMAGE-V1.0.0` (2025-03) | match | Keil only (`.lib`) | separate image 1.0.66.0 | skip (no GCC libs) |

Findings: the ROM symbol table has no BLE stack, only `upperstack_entry` (RAM hook `0x00200cc4`);
the stack strings (`UpperStackTask`, `btif_*`, `Upperstack Ver`) exist only in upperstack images,
and the stock app image contains an upper stack of its own (not byte-identical to any SDK
version). So the vendor linked a stack into the app; public SDKs don't offer that.

**Track A0' (combined image, offline research first, zero risk):** build one `0x2793` image at
`0x0080E000` holding an SDK upperstack image + our app, with our startup doing what patch 440
normally does (load upperstack data/bss, set `upperstack_entry`, start it). Research needed:
(1) disassemble how the stock app (exe `0x008299CC`) starts its embedded stack under patch 239;
(2) disassemble how patch 440 (`Patch_MP_release_0.0.440.4…bin`) locates/starts the upperstack;
(3) confirm gap_utils wrappers call the upperstack via fixed addresses. Only if all three are
clear does a combined image get built — and its first flash is still the A1 "dangerous step".

Track B can run in parallel while waiting; its phase B1 is useful either way (proves that
non-vendor images install).

### SDK acceptance checklist (do before any build)

- [ ] `inc/platform/rom_uuid.h` equals `1d6a69f1 2f38ea11 82a76737 0a3ca32e`
- [ ] `DEFINED_IC_TYPE` / img header ic_type is `0x09`
- [ ] Samples build **without** `SUPPORT_ALONE_UPPERSTACK_IMG` (stack in app), or a stack library is provided
- [ ] Bundled ROM patch / release notes reference patch rev 239 (or state compatibility)
- [ ] Has `silent_ota` (DFU service) sample with GCC Makefile
- [ ] Default flash map can put APP at `0x0080E000`

---

## Track A — full custom firmware (needs legacy SDK)

Each phase = its own build, flashed over BLE, must pass its exit check before the next.
Every build bumps the app version (`git_ver` revision > previous, start > 1319) and keeps DFU.

### A0. SDK intake
- Unpack into `sdks/<name>/` (ignored by git). Run the acceptance checklist above.
- Create our project under `firmware/s100/` (tracked; build outputs ignored), based on the
  SDK `silent_ota_gcc` sample. Makefile tool paths need `.exe` on Windows.
- **Exit:** builds cleanly; header shows ic `0x09`, image ID `0x2793`, correct ROM UUID,
  image base `0x0080E000`, version > 1319.

### A1. Bare boot (the one dangerous step)
- Minimal app: BLE advertise "S100-OW", DFU + OTA + DIS + BAS services, nothing else.
  No display, no sensors, no DLPS experiments, watchdog enabled.
- Review: linker map (entry, sections inside the app slot), no peripheral init that could hang.
- Flash, wait 20 s, `openwearota scan`.
- **Exit:** "S100-OW" visible and connectable.

### A2. Round-trip proof
- Flash a second A1 build (version +1) **through A1's own DFU service**.
- Then flash stock back (needs version bump via `rehash_rtl_image.py --version N`).
- **Exit:** both directions work → recovery path proven; everything after this is low risk.

### A3. Display on
- Reverse the stock image for the LCD init (LCDC/GDMA setup, pin mux, reset/backlight GPIO,
  ST7789V2 init sequence). Stock LCDC base `0x40024800`.
- Show a solid colour, then a test pattern and text.
- **Exit:** stable image on screen, BLE + DFU still fine.

### A4. UI framework
- Port LVGL (MIT) with a 240×280 RGB565 display driver (partial framebuffer, DMA flush).
- Prototype screens first in the LVGL PC simulator (see "Parallel work").
- **Exit:** LVGL demo screen runs on watch at usable FPS, RAM/flash budget recorded.

### A5. Input
- Side button GPIO (from stock reverse engineering), touch controller if present (I2C).
- Wake on button, screen switching.
- **Exit:** navigate between screens; wake from sleep.

### A6. Feature screens
1. Always-on desk clock (large digits, date, battery).
2. Car navigation: turn arrow, distance to turn, current speed, street name.
3. Music: title/artist, play/pause, next/prev, volume.
4. Notifications: app icon/name, title, text, history list.
- **Exit:** each screen renders from fake data.

### A7. Phone/PC link
- Our own GATT service (e.g. vendor UUID) with simple TLV messages: time sync, nav update,
  media state + control events, notification push.
- Host side: Python first (extend `tools/`), then Android app (or Gadgetbridge device driver).
- **Exit:** live nav/music/notifications from phone.

### A8. Power & polish
- DLPS/sleep, backlight dimming, always-on low-refresh mode, battery ADC + charging state.
- Settings screen (brightness, timeout, AOD on/off), persistent settings in FTL.
- **Exit:** acceptable battery life; daily-usable.

### A9. Release
- Document build + flash in `DOCUMENTATION.md`; tag a version; keep a known-good image
  (and the stock image) in `prebuilts/` only if licensing allows (otherwise instructions only).

---

## Track B — modded stock firmware (no SDK needed)

Keeps the vendor's working stack, display driver and DFU; changes behaviour by binary patching.
Every image: patch bytes → `rehash_rtl_image.py --version N` (N increasing) → flash → verify `ffd4`.

### B1. Prove modified images install *(ready)*
```powershell
python tools\rehash_rtl_image.py research\firmware\RH288A_V001319_fw_1660354713_5619.bin research\mods\stock_v1320.bin --version 1320
openwearota flash 78:02:B7:58:FF:9E research\mods\stock_v1320.bin --limit-function -v
python tools\s100_gatt_dump.py     # ffd4 should read 00 80 52 00
```
- **Exit:** `ffd4 = 00 80 52 00` → bootloader installs re-hashed images. If it stays
  `00 70 52 00`, stop and investigate (second integrity check?) before any code patch.
- **Result 2026-10-29: PASSED.** Needed driver buffer-check mode (plain streaming dropped the
  link at VALIDATE for the 562 KB image). 275 buffers acked, `ValidateFW 100301`, activated,
  `ffd4 = 00 80 52 00`. Installed version is now 1320 → every later image must use ≥ 1321.

### B2. First code patch — unlimited screen timeout
- Patch the ×5 picker at `0x0085FB0C` (file offset `0x51D0C`), see TechLife-S100.md Route B.
  Verified 2026-10-29: bytes `00 eb 80 00` = `add.w r0,r0,r0,lsl #2`, followed by `uxth r0,r0`
  and `strh.w r0,[r1,#0xfa]`. Candidate 4-byte replacements:
  `00 02 00 bf` (`lsls r0,#8; nop` → 256/512/768 s), `80 02 00 bf` (`lsls r0,#10; nop` →
  1024/2048/3072 s), `4f f6 ff 70` (`movw r0,#0xFFFF` → ~18 h for every option).
  Labels in the picker stay "5/10/15 s".
- **Result 2026-10-29:** v1321 (`movw r0,#0xFFFF`, all options ~18 h) installed, screen stays on.
  v1322 replaces the 20 bytes at `0x0085FB0C` with
  `add.w r0,r0,r0,lsl#2; cmp r0,#15; it hs; mvnhs r0,r0; cmp r0,#5; it lo; movlo r0,#5; strh.w r0,[r1,#0xfa]`
  → picker 5 s / 10 s / "15" = always on (65520 s). **v1322 installed and confirmed working by
  user (2026-10-29). B2 PASSED.** Installed version 1322 → next image ≥ 1323. Next: relabel "15" (B4).
- **Exit:** Settings → Screen Timeout gives long/infinite values; everything else unchanged.

### B3. Remove stock functions
- Locate the app/menu table (screen names like `*ScreenUI`), drop entries
  (HR, SpO2, sports, sleep, etc.).
- **Exit:** menus show only kept items; no crashes navigating.

### B4. Reskin
- Goal (2026-10-29): full CMF-Watch-style restyle of every screen, **keeping all stock features**,
  the 240×280 layout and the stock scrolling/list behaviour.
- **Decoded** (2026-10-29): 2,163 row-RLE RGB565 images + ~350 KB raw tail, payload at flash
  `0xACB400`, CRC-32 header; format and reskin rules in `docs/ui-resource-format.md`; exporter
  `tools/s100_ui.py export`.
- Encoder (byte-identical on all stock images) + in-place build done. One-icon test pack
  (Settings gear 1273, UI revision 1) flashed 2026-10-29: `ValidateFW 100301`, watch back up.
  Batch 1 (UI revision 2, 2026-10-29): all 34 app icons (64 px grid set 1144-1160 + 48 px list set
  1258-1274) in CMF style, `ValidateFW 100301`, watch back up.
  Batch 2 (UI revision 3, 2026-10-29): CMF colour theme on every other image (`tools/ui_cmf.py`:
  bright accents → orange, dark tints → grey, neutrals kept; 981 recoloured, 16 left stock). Two
  transfers dropped (62 %, 85 %; BLE "Unreachable"), the watch kept running each time; installed
  on the 4th try (`ValidateFW 100301`).
  Batch 3 (UI revision 4, 2026-10-29): text re-rendered in Bahnschrift (`tools/ui_cmf_text.py`;
  236 labels from `tools/ui_labels.json` = Windows OCR + manual fixes, 35 digit sets), on top of
  icons + theme; first-try install. Next UI pack ≥ 5. Next: layouts + features (UI framework map in
  `docs/ui-framework-notes.md`).
- 2026-10-30: scope widened from reskin to a structural UI upgrade (layout, navigation, motion,
  haptics, new screens); plan and firmware limits in [ui-upgrade-plan.md](ui-upgrade-plan.md).
  Waiting for the owner's go-ahead (P0/P1 first, no flashing).
- **Exit:** new look across screens.

### B5. Custom screens (code injection)
- Find free flash in the app slot; write ARM Thumb-2 at a fixed address that calls stock
  draw/timer functions found by reverse engineering; hook one screen's handler to ours.
- **First target: world-clock digits (dial element type 71).**
  Dial element dispatch at `0x85D290` (cascading CMP/BEQ for types 57-70); time struct pointer in
  r1 (`+0x96` hour, `+0x97` minute, `+0x66` 12 h flag). The record parser at `0x83B2E6` stops at
  the first type > 71 (`cmp r0,#0x47; bhi`) and caps a dial at 71 elements, so **all world
  digits use type 71** (stock never uses it). Record reserved bytes (RAM `r4+0x35D…`): [0]=0,
  [1:3]=signed LE16 minute offset, [3]=digit position (hour tens/units, minute tens/units).
  Hook replaces `ldrh.w r0,[r4,#0x34c]` with `b.w 0x89491C`; the 130-byte handler in zero padding
  computes `(h*60+m+offset) mod 1440`, applies 12 h like stock (`h>12 → h-12`), picks the digit
  and jumps to the stock frame-select at `0x85D320`; other types fall through to `0x85D294`.
  Verified in Unicorn: 4032 cases (both 12/24 h, 7 offsets, all hours, 4 positions), stack balanced.
  Mod `b5_worldclock` in `tools/s100_mods.py` (cumulative with B2) →
  `research/mods/b5_worldclock_v1323.bin`. Face: `tools/dial_world.py` (2×2 grid Mumbai /
  New York / Dubai / London; offsets computed for the build date incl. US/UK DST, so rebuild and
  re-upload after a DST change).
- **Fix, v1324 (`b5b_worldclock`, installed 2026-10-29):** `0x89491C` turned out to be inside the
  flash range `0x8941AC`-`0x8974D0` that startup (`0x829A64`) copies to RAM `0x20BD14` as the initial
  values of RAM variables, so v1323 started RAM `0x20C484`-`0x20C506` (app state) with handler bytes.
  The handler now lives at `0x84D434` in the dead FactoryAgingTest build function (entry `0x84D432`
  = `bx lr`; only caller is the factory screen at `0x84DB56`; no literal loads into the range).
  Hook re-encoded (`b.w 0x84D434`); handler body identical. Next app image ≥ 1325.
- Next: nav/music/notification screens fed by UTE commands (`tools/s100.py`); UI framework map in
  `docs/ui-framework-notes.md`.
- **Exit:** custom screens reachable from the watch, fed live from the PC/phone.

Track B limits: bound to the stock architecture; large UI changes get hard. If Track A becomes
available, move to it after B1 (B1's result still matters: it shows non-vendor images install).

---

## Parallel work (zero risk, any time)

- LVGL PC simulator at 240×280: design and approve all A6 screens before hardware.
- Reverse-engineer stock image for LCD init, button/touch pins, backlight, battery ADC (feeds A3/A5/A8).
- Host app prototype (Python) for the A7 protocol.
- Custom watch faces on stock (dial upload, 240×280) as an interim UI.

## Safety checklist before every flash

- [ ] Image ID `0x2793` only (never 0x2790/0x2791/0x2792/0x279A)
- [ ] ROM UUID `1d6a69f1…`, ic_type `0x09`, image base `0x0080E000`
- [ ] Version revision higher than the currently installed one (`ffd4`)
- [ ] Integrity valid (CRC16 for SDK builds via prepend_header; SHA-256 via rehash tool for stock mods)
- [ ] DFU service present in this build (Track A) / DFU code untouched (Track B)
- [ ] Change set reviewed (map file / disassembly diff) and as small as possible
- [ ] Watch charged > 50 %, close to PC

## History

- 2026-10-28 — BLE DFU fixed end-to-end (`ValidateFW 100301`). Bee2 (RTL8762C) SDK images
  rejected: wrong ROM. Chip confirmed RTL8762D via ROM UUID. SDK v1.1.0 needs a separate
  upperstack image the watch lacks → legacy SDK requested from Realtek. SHA-256 coverage found;
  Track B opened. This plan written.
- 2026-10-29 — Checked `sbee2-sdk-gcc-v1.0.0` and `SBEE2-SDK-UPPERSTACK-IMAGE-V1.0.0`: ROM match,
  but all need a separate upperstack image. Driver switched to buffer-check streaming
  (per-buffer ack + retry). **B1 passed**: modified stock image v1320 installed over BLE.
- 2026-10-29 — **B5 world-clock patch built.** Reverse-engineered dial element type dispatch at
  `0x85D290`, time struct at `0x0020BE84`, found free space at `0x89491C`. Designed and assembled
  130-byte Thumb-2 handler for world-clock digits. First draft used types 71-82, but the dial
  parser drops everything after the first type > 71, so it was reworked to type 71 + digit
  position in reserved[3]; noon-in-12h bug fixed. World dial redesigned to a 2×2 city grid. Fixed `s100_dial.py` CLI argument parsing (positional
  `design` arg was being parsed as output path). Ready for flash + dial upload.
