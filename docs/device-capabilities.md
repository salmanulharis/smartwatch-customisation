# Device Capabilities — realme TechLife Watch S100 (RMW2103)

Last updated: 2026-10-28. Confidence tags: **[confirmed]** = read from device or
primary source; **[likely]** = strong evidence; **[unverified]** = inference only.

---

## 1. Hardware summary

| Component | Value | Confidence |
|-----------|-------|------------|
| SoC | **Realtek RTL8762C** (firmware header string `RTL8762C`; FCC photo marking `…8762?K` → RTL8762CK package) | **[confirmed]** (firmware header); package variant **[likely]** |
| CPU | ARM Cortex-M4F, up to 40 MHz (RTL8762C datasheet) | **[likely]** — based on chip ID, not directly measured |
| RAM | 256 KB SRAM (RTL8762C spec) | **[likely]** |
| Internal flash | 360 KB usable for app code (RTL8762C spec); dual-bank OTA layout | **[likely]** |
| External flash | XTX XT25F64B — 64 Mbit (8 MB) SPI NOR; stores watch faces, fonts, UI resources | **[likely]** (FCC photo marking) |
| Display | 1.69" IPS LCD, 240×280 px, ~218 ppi, 530 nits peak | **[confirmed]** (specs + dial config `26 01` reply) |
| Display controller | Unknown — likely ST7789-class SPI/QSPI | **[unverified]** |
| Touch | Capacitive touch panel | **[confirmed]** (observed) |
| Buttons | 1 side button | **[confirmed]** (observed) |
| Battery | 260 mAh Li-ion, pouch, soldered | **[likely]** (GSMArena + FCC photo) |
| Radio | BLE only, 2402–2480 MHz | **[confirmed]** (FCC grant) |
| Sensors | Accelerometer, PPG HR/SpO2 (sensor flex `SUB_VC32R21`), skin temperature | **[likely]** |
| Vibration | Coin motor | **[confirmed]** (tested via `AB` command) |
| Charging | 2 pogo pins on case back — charging only | **[likely]** |
| Board | `RH288_V01`, dated 20211120 | **[confirmed]** (FCC photo) |
| Test pads | 6 through-hole pads near SoC: `TX RX L … P` — factory UART/LOG header | **[likely]** |

## 2. Stock firmware identity

| Field | Value | Source |
|-------|-------|--------|
| Watch-reported version | `1.3.0.017` (About screen) | **[confirmed]** |
| UTE version string | `RH288AV001319` (A1 reply) | **[confirmed]** |
| btname / versionname | `RH288A` / `V001319` | **[confirmed]** |
| Firmware file | `RH288A_V001319_fw_1660354713_5619.bin`, 562,896 bytes | **[confirmed]** |
| Firmware SHA-256 | `0a162300be59744ec0ee315f41c3e8b0b114128b215ffde6798cb1eafc126fd4` | **[confirmed]** |
| UI resources file | `RH288A_V000957_U0006_ui_1641738154_5635.bin`, 4,075,524 bytes | **[confirmed]** |
| Firmware header IC | `RTL8762C` | **[confirmed]** |
| UI header IC | `RTL8762D` (firmware header is authoritative → chip is 8762C) | **[confirmed]** |
| App version field | `00 70 52 00` (matches `ffd4` on device) | **[confirmed]** |
| Flash address | `0x0080E000` (MP header field 0x0013) | **[confirmed]** |
| Image ID | `0x2793` (MP header field 0x0012) | **[confirmed]** |
| Encrypted? | No — readable ARM Thumb code + ASCII strings, entropy ~7.0 | **[confirmed]** |

## 3. BLE / GATT services (stock firmware)

MTU negotiated: 247. Full table in `docs/TechLife-S100.md` §4.

| Service | Purpose | Status |
|---------|---------|--------|
| `0000d0ff-3c17-…` | Realtek OTA (normal mode); `ffd1` = enter-OTA, `ffd2` = BD addr, `ffd3`/`ffd4` = versions | Present **[confirmed]** |
| `00006287-3c17-…` | Realtek DFU; `6387` data, `6487` control point | **Present in normal mode** (unusual — most Realtek devices only expose this after enter-OTA reboot) **[confirmed]** |
| `000055ff-…` | UTE private protocol: `33f1` (cmd write/read), `33f2` (notify) | **[confirmed]** |
| `000056ff-…` | UTE big-data: `34f1` (write-no-rsp, read), `34f2` (notify) | **[confirmed]** |
| `0000180f` | Battery service (`2a19` = 92%) | **[confirmed]** |
| `1800`/`1801` | Generic Access / Attribute | **[confirmed]** |
| Nordic NUS | Not present | **[confirmed]** |

## 4. Verified stock-firmware capabilities (via UTE protocol)

All tested 2026-10-28 via `tools/s100.py`. See `docs/TechLife-S100.md` §7b.7 for the
protocol command reference.

| Feature | Command | Verified? |
|---------|---------|-----------|
| Bind to app account | `33 02 <id>` → `33 04 01` | **Yes** |
| Time sync | `A3` | **Yes** |
| Version query | `A1` → `RH288AV001319` | **Yes** |
| Notifications (text, silent) | `C5` packets, type 4 | **Yes** — text shown, no vibration |
| Navigation text (as notification) | `C5` with direction + distance | **Yes** — shown, no vibration |
| On-demand vibration | `AB 00 00 00 01 n 07 01` | **Yes** — felt |
| 7-day weather + city name | `CB 01/02/03` + `CB FF` on 34f1 | **Yes** — shown |
| Music title / play state | `3A 01/06/FA` on 34f1 | **Yes** — shown while connected |
| Watch → phone music buttons | `D1 07/08/09/0D/0E/0A` | **Yes** — play/pause, prev, vol down observed |
| Screen-off setting (A9 byte 5) | `A9` packet | **Accepted but ignored** — firmware disassembly confirms A9 handler does not read byte 5 |
| Desk-clock keep-awake | Repeated notifications at 2s interval | **Yes** — screen stays continuously lit |
| Car nav display | `car_frame()` at 2s interval | **Yes** — speed + direction + distance + street; font has no arrow glyphs → use words |
| Dial config query | `26 01` | **Yes** — 240×280, max 1 MB, compat 1 |

## 5. Display behavior

- **Screen timeout** is controlled only by the watch's own settings menu (5/10/15 seconds).
  The `A9` BLE command does not change it. The firmware stores the value at `[settings + 0xFA]`
  as a u16 in seconds, read by ~156 timer-setup sites.
- **Notification wake**: sending a `C5` notification wakes the screen from sleep. At 2-second
  intervals, the screen stays continuously lit (no dark gap). At 4 seconds, brief dark gaps
  appear between popups.
- **No always-on display** in stock firmware — the LCD backlight turns off after the
  timeout, and there is no setting to prevent it.
- **No brightness BLE command** found in the UTE protocol. Brightness is set only via
  the watch's quick-panel.

## 6. Realtek OTA characteristics (raw values)

| Char | Raw | Interpretation |
|------|-----|---------------|
| `ffd2` | `78 02 b7 58 ff 9e` | BD address |
| `ffd3` | `00 f0 0e 58` | Patch version |
| `ffd4` | `00 70 52 00` | App version (matches firmware header) |
| `ffd5` | (empty) | Patch-extension version |
| `ffe0` | `01 00 00 01 00 20 00 00 00 f0 0e 58 00 70 52 00` | Device info block; bytes 8–15 repeat ffd3+ffd4; bytes 0–7 include IC type / OTA spec / mode flags — not fully decoded |
| `fff1` | `09 01 00 07 00 08 00 00 f0 0f 00 00` | Image/section info — not fully decoded |
| `fff3` | `12 00` | OTA protocol type = **0x12** |
