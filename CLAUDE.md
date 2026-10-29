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
docs/TechLife-S100.md  # research notes for the realme TechLife Watch S100 (RTL8762C)
tools/                 # standalone helper scripts (not part of the package)
  s100.py              # TechLife S100 control tool (stock firmware, UTE protocol)
  s100_app.py/.html    # S100 Companion: local browser GUI (faces + controls), 127.0.0.1:8100
  ute_fw_query.py      # UTE cloud firmware update query tool
  s100_gatt_dump.py    # read-only GATT/OTA-info dumper
dist/                  # built wheel/sdist (git-ignored)
.venv/                 # local Python venv (git-ignored)
jadx-1.5.1/            # JADX decompiler (git-ignored)
reference-app/         # companion app APKs (git-ignored, copyrighted)
research/              # decompiled code, firmware dumps (git-ignored)
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
