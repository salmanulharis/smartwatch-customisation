# OpenWearOTA

Re-purpose e-waste smartwatches via BLE OTA firmware updates. Reverse-engineered from the FitPro Android app (JADX decompile) and vendor SDKs.

## Quick reference

- **Language:** Python 3.10+, async (asyncio + bleak for BLE)
- **License:** GPL-3.0-or-later
- **Entry point:** `openwearota.cli:main` (installed as `openwearota` console script)
- **Single dependency:** `bleak>=0.21` (cross-platform BLE)
- **Version:** `0.0.1a2` (alpha)

## Project layout

```
openwearota/           # main package
  __init__.py          # version string
  cli.py               # CLI + interactive TUI (argparse, ANSI color)
  detect.py            # chip family detection by GATT service UUID
  crc.py               # CRC-16 variants (XMODEM, ARC, Telink)
  aes.py               # pure-Python AES-256-ECB encrypt (RealSil DFU)
  uart.py              # BLE-UART bridge (Nordic NUS)
  drivers/             # one module per chip family
    shb_slb.py         # SHB/SLB (3rd-gen Chinese OTA) + PhyPlus SDK 3.x SHB_OTA mode
    telink.py          # Telink TLSR8xxx
    jieli.py           # JieLi AC695N/AC696x (RCSP protocol)
    beken.py           # Beken BK34xx
    omnicro.py         # OnMicro OM6620 (partial — detect + best-effort only)
    realsil.py         # RealSil RTL876x (two-phase DFU)
    phyplus.py         # PhyPlus PHY62xx (dedicated driver, SDK 3.x)
pyproject.toml         # build config (setuptools)
DOCUMENTATION.md       # full protocol reference (all 7 chip families + UART + auto-detect)
prebuilts/             # prebuilt firmware images by chipset (currently empty placeholder)
docs/                  # TechLife S100 research (all S100-specific)
  TechLife-S100.md     # master research notes + changelog (RTL8762D family, §12b)
  custom-firmware-plan.md  # roadmap + status (Track B = stock-image patching)
  bluetooth-protocol.md    # UTE BLE app protocol (stock firmware)
  custom-dial-format.md    # watch-face ("online dial") binary format + upload protocol
  ui-resource-format.md    # UI resource pack (images/labels/digits) format
  ui-framework-notes.md    # stock GUI map in app V001319 (for moving/adding screens)
  ui-upgrade-plan.md       # CMF UI upgrade: feasibility, phases, P0 results, draft builds (§12)
  hour12-patch-notes.md    # 12-hour time on dials (command A0, no patch needed)
  device-capabilities.md, firmware-feasibility.md, always-on-display.md,
  recovery-plan.md, test-plan.md
tools/                 # standalone helper scripts (not part of the package; dial/UI tools need Pillow)
  s100.py              # TechLife S100 control tool (stock firmware, UTE protocol)
  s100_app.py/.html    # S100 Companion: local browser GUI (faces + controls), 127.0.0.1:8100
  s100_dial.py         # build/upload custom watch faces (desk-clock face + uploader)
  dial_*.py            # face layouts; dial_nothing (dot-matrix Canvas) and dial_widgets/dial_duo
                       #   (shared builders) are bases, others import them; duo2 must import before
                       #   modules that swap dial_duo's background
  s100_mods.py         # rebuild patched firmware (b2_timeout, b5_worldclock, …) from stock image
  s100_ui.py           # export/rebuild the UI pack (in-place images, raw tail strips, --append growth)
  s100_screens.py      # offline previewer: runs real screen build/touch code in Unicorn (render/all/nav)
  s100_preview.py      # interactive emulator session for a built app + UI pack (s100_app "Firmware preview" tab)
  ui_apps_art.py       # app list / grid art (p_*) + SpO2 in-place art
  ui_breathe_art.py    # Breathe screen art, in place (Breathe + unused SpO2 slots)
  ui_dots.py           # dot-matrix digit frames (appended to the pack) + app pointer patches
  ui_pickers.py        # CMF picker/roller strips (raw tail, in place)
  ui_cmf.py, ui_cmf_text.py, ui_labels.json  # CMF-style restyle of the UI pack
  patch_rtl_header.py  # fix ic_type/ctrl_flag in a Realtek OTA header
  rehash_rtl_image.py  # recompute SHA-256 of a patched RTL8762x app image
  ute_fw_query.py      # UTE cloud firmware update query tool
  s100_gatt_dump.py    # read-only GATT/OTA-info dumper
research/dials/        # built face .bin + previews; favourites/ = keepers (tracked)
research/{firmware,mods,ui,jadx-*}/  # stock fw, patched fw, UI exports, decompiled app (git-ignored)
firmwares/             # third-party fw projects, e.g. rtl8762c-ble-uart (git-ignored)
android/               # S100 Companion Android app (Kotlin + Compose): link, notifications, Maps nav,
                       #   weather, music, find phone, faces; build: gradle assembleDebug (SDK in %LOCALAPPDATA%\Android)
firmware/s100_ext/     # C source of the watch feature screens (built by tools/s100_ext.py)
dist/                  # built wheel/sdist and APKs (git-ignored)
.venv/                 # local Python venv (git-ignored)
jadx-1.5.1/            # JADX decompiler (git-ignored)
reference-app/         # companion app APKs (git-ignored, copyrighted)
```

## Architecture

### Detection flow
`detect.py:detect_chip_family()` matches GATT service UUIDs against a fingerprint table (7 families). Priority order handles UUID collisions (RealSil vs Telink share `0000d0ff-…`). For the SHB/SLB family, `detect_shb_slb_mode()` does a second pass on characteristic UUIDs to distinguish SHB_APP / SHB_OTA / SLB_UPGRADE / PhyPlus modes.

### Driver pattern
Each driver in `openwearota/drivers/` exports:
- `identify_<family>_chip(client) -> str | None` — read chip/model ID over BLE
- `run_<family>_upgrade(client, firmware_path, verbose=False) -> bool` — full OTA flow

All drivers are async, use `bleak.BleakClient`, and follow a common pattern: enable notifications on the response characteristic, send commands, wait for acks, stream firmware in chunks, verify. Each protocol has different framing, opcodes, and flow control — see DOCUMENTATION.md for details.

### CLI modes
- **No args:** interactive TUI menu (scan → detect → pick firmware → flash, or UART bridge)
- `openwearota scan` — list BLE devices
- `openwearota flash <address> <firmware> [-y] [-v]` — direct flash
- `openwearota uart <address> [--service-uuid …]` — BLE-UART bridge

### CRC implementations (`crc.py`)
- `crc16_xmodem` — CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) — used by SLB
- `crc16_arc` — CRC-16/ARC (poly 0xA001, init 0) — used by PhyPlus and SHB partition checksums
- `telink_crc16` — per-packet CRC for Telink OTA (poly 0xA001, init 0xFFFF)

## Supported chip families

| Family | Silicon | Driver | Completeness |
|--------|---------|--------|-------------|
| SHB/SLB | YiChip/Ali-BLE / PHY62xx (SDK 2.x) | `shb_slb.py` | SLB: full; SHB_OTA: full; SHB_APP handover: not automated |
| Telink | TLSR8232/8253/82xx | `telink.py` | Full |
| PhyPlus | PHY6222/6252/62xx (SDK 3.x) | `phyplus.py` | Full (single partition) |
| JieLi | AC695N/AC696x | `jieli.py` | Full (with resume support) |
| Beken | BK3431/3432/3266 | `beken.py` | Full |
| OnMicro | OM6620 | `omnicro.py` | Partial (detect + enter OTA only) |
| RealSil | RTL876x | `realsil.py` | Silent OTA (0x12) with AES-256 + buffer-check streaming; verified on TechLife S100 (RTL8762D) with a 562 KB image |

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\Activate.ps1
openwearota --version
```

No test suite exists. The project is verified by flashing real devices.

## Key conventions

- Firmware files are `.bin` or `.hex`; SLB resource files follow `res_<8hex>.bin` naming
- Secure firmware (`*hexe16*`) requires a per-product AES key — not supported
- The `tools/` directory contains standalone scripts for specific watches, not part of the installed package
- `DOCUMENTATION.md` is the authoritative protocol reference — update it alongside driver changes
- `docs/TechLife-S100.md` tracks an ongoing research project for the TechLife S100 watch (RTL8762D family, see §12b)
- `docs/custom-firmware-plan.md` is the phase-by-phase custom firmware roadmap and current status for the S100 — read it first when continuing that work, and update its status/history as phases complete
- Vendor SDKs live in `sdk/` (bee2/RTL8762C, wrong ROM for the S100) and `sdks/` (RTL8762D); both git-ignored

## Safety

- **Never flash without chipset detection confirming a match**
- Telink driver does firmware model-ID verification against the watch's version characteristic
- SLB driver checks the watch's product-ID response before streaming
- JieLi driver has pre-update inquiry + natural resume
- For the TechLife S100 specifically: see `docs/TechLife-S100.md` §6 and §9 — the RealSil driver has known limitations and no BLE flash backup exists
