# Firmware Feasibility Report — realme TechLife Watch S100

Last updated: 2026-10-28.

---

## 1. Executive summary

Custom firmware for this RTL8762C watch is **technically feasible**.

**Software blockers resolved (2026-10-28):**
- AES-256-ECB encryption implemented (pure Python, `openwearota/aes.py`)
- `--limit-function` CLI flag added (skip phase-1 handover when DFU already present)
- Big-image skip (body bytes 104,000–143,360) implemented for >100 KB images

**Remaining blocker: no verified recovery path.** Without proven flash backup + restore,
any BLE OTA attempt is a one-way door. The safest path forward is **wired UART access**
(opening the watch to reach the factory programming pads).

**Stock-firmware companion work** (desktop buddy and car nav via the UTE BLE protocol) is
safe and already functional.

---

## 2. Chip and development target

| Item | Finding | Confidence |
|------|---------|------------|
| SoC | Realtek RTL8762C | **[confirmed]** — firmware header string |
| Package | RTL8762CK (FCC photo, last letter blurry) | **[likely]** |
| Architecture | ARM Cortex-M4F, 40 MHz, 256 KB SRAM, ~360 KB app flash | **[likely]** — based on RTL8762C datasheet |
| SDK | Realtek Bee2 SDK (RTL8762C); registration required from Realtek | **[confirmed]** — SDK references in firmware strings |
| GCC toolchain | arm-none-eabi-gcc; community examples at `cyber-murmel/rtl8762c-gcc-examples` | **[confirmed]** — GitHub repos exist |
| BLE UART example | `wuwbobo2021/rtl8762c-ble-uart` | **[confirmed]** — GitHub |
| UART programmer | `wuwbobo2021/rtltool` (RTL8762C; RTL8762D support unknown) | **[confirmed]** — GitHub |

The RTL8762C is a known, documented chip with community tooling. Custom firmware is technically
within reach if hardware access is available.

## 3. BLE OTA path — analysis

### 3.1 Protocol

The watch uses Realtek's DFU protocol, accessed through:
- **OTA reset service** `0000d0ff-3c17-…` with enter-OTA char `ffd1` (normal mode)
- **DFU service** `00006287-3c17-…` with data `6387` and control point `6487`

Unusual: the DFU service is **already exposed in normal firmware mode**. The companion app
uses this as evidence for "silent OTA" (work mode 16) — the new image is written to the
inactive bank while the device continues running.

### 3.2 OTA protocol type

`fff3` = `12 00` → protocol type **0x12** (decimal 18). This dispatches to Realtek SDK
class `com.realsil.sdk.dfu.n.e` (silent mode) or `n.d` (normal mode).

### 3.3 AES encryption — **mandatory**

The decompiled realme Fit APK confirms:

- **AES-256-ECB encryption is applied to both the 16-byte START_DFU metadata header AND
  every 16-byte block of firmware data** during transfer.
- The AES key is Realtek's default SDK key with bytes 5–10 replaced by ASCII `UTE_RK`:
  ```
  4E 46 F8 C5 09 55 54 45 5F 52 4B 0C D1 F6 10 FB
  1F 67 63 DF 80 7A 7E 70 96 0D 4C D3 11 8E 60 1A
  ```
  (Source: `FirmwareActivity.java:309`, confirmed in decompiled code.)
- Native AES implemented in `libRtkAesJni.so` (shipped with the APK for all ABIs).
- `setVersionCheckEnabled(false)` — version checking is disabled.

### 3.4 RealSil driver status (updated 2026-10-28)

| Item | Status |
|------|--------|
| AES-256-ECB encryption (UTE key) | **Implemented** — `openwearota/aes.py` + wired into `realsil.py` |
| `--limit-function` CLI flag | **Implemented** — skips phase-1 handover |
| >100 KB big-image skip | **Implemented** — body bytes 104,000–143,360 removed before streaming |
| Protocol type 0x12 specifics | **Investigated** — compatible with current driver (see §3.5) |

### 3.5 Protocol 0x12 analysis (updated 2026-10-28)

Protocol 0x12 = `ProcessorX0012S` (silent OTA). Decompiled from `com.realsil.sdk.dfu.n.e`.

**Device info** decoded from `fff1` characteristic (`09 01 00 07 00 08 00 00 f0 0f 00 00`):

| Field | Value | Meaning |
|-------|-------|---------|
| icType | 0x09 | RTL8762C — matches firmware header |
| specVersion | 1 | No additional image-version query needed (would need ≥2) |
| secureVersion | 0 | — |
| mode byte | 0x07 (0b00000111) | AES enabled, mode 1 (all blocks), no buffer check |
| maxBufferCheckSize | 2048 | — |
| otaTempBufferSize | 0 | — |

**AES encrypt mode 1** = encrypt ALL 16-byte blocks in each packet. Our driver encrypts the
entire body in 16-byte blocks before chunking into packets — equivalent result.

**Silent OTA** = the DFU service (`6287`) is already present in normal firmware, so no phase-1
handover is needed. Use `--limit-function` to skip the enter-OTA step. The device writes the
new image to the inactive bank while the current firmware continues running (dual-bank).

**No buffer check** = simple fire-and-forget streaming (no per-buffer CRC validation). Our
driver's streaming loop is correct.

**Driver compatibility**: the current OpenWearOTA RealSil driver with `--limit-function` and
default AES key is protocol-compatible with this watch's 0x12 silent OTA. No code changes
needed for protocol-type-specific behavior.

### 3.6 What remains for BLE OTA

1. ~~Implement AES-256-ECB encryption.~~ Done.
2. ~~Add `--limit-function`.~~ Done.
3. ~~Implement >100 KB big-image skip.~~ Done.
4. ~~Investigate protocol 0x12 specifics.~~ Done — compatible.
5. **Crucially: prove the path is safe by re-flashing the unmodified stock image first.**

All software blockers are resolved. BLE OTA remains a one-way door without a verified
restore path.

## 4. Firmware image integrity

| Check | Finding |
|-------|---------|
| CRC-16 field | `0x0000` — unused |
| SHA-256 at header +0x174 | Present: `bfc1f0d2 6b8349d9 d74f1383 67930973 908e4dd1 2e3fca32 3c6269cd 5f3cdbd2` |
| RSA signature at +0x194 | 256 bytes, all zero — **no signature** |
| Encryption | None — readable ARM Thumb code, ASCII strings, entropy ~7.0 |

The image is **not signed** (RSA block zeroed) but **has a SHA-256 hash**. The exact byte
range the hash covers is **not yet determined** despite exhaustive offline testing:

Tested and eliminated:
- Payload only (561,360 bytes after 1024-byte header)
- Full image (header + payload), with hash field zeroed / FF'd
- All single-byte start offsets 0–1024 hashing to end of image
- Header[0:0x174] + payload (skipping hash and rest of header)
- Header[0:0x174] + header[0x194:] + payload (skipping hash+RSA)
- Header[0:0x174] + header[0x294:] + payload (skipping hash+RSA+padding)
- Full file (MP header + image) with hash field zeroed
- Payload with big-image skip applied
- Word-reversed hash interpretation

The hash is likely computed by Realtek's image build tools with proprietary padding or
context data not present in the binary. **Resolution requires** either the Bee2 SDK's
image packing tool source, or ROM bootloader disassembly (via UART).

If the bootloader validates this hash before accepting an OTA image, any patch must
recompute it correctly. Alternatively, the DFU bootloader may not check the hash at all
(it may only be checked at boot time from flash).

## 5. Wired (UART) path — the safe route

### 5.1 What we know

- 6 through-hole pads on the main board: silkscreen reads `TX RX L … P` (FCC photos).
- `L` is likely the Realtek **LOG pin (P0_3)** — held low at power-on, it enters ROM "MP mode"
  for factory programming.
- `rtltool` (GitHub) supports RTL8762C flash read/write over UART.
- Realtek MPTool (vendor tool) supports the same via "Debug mode" (enabled with RegistrySet.exe).

### 5.2 What this enables

1. **Full flash dump** — read the entire SPI NOR (8 MB) + internal flash.
2. **Verified restore** — write the dump back and confirm the watch boots stock.
3. **Direct firmware load** — flash custom firmware without BLE OTA, bypassing AES entirely.
4. **ROM bootloader as recovery** — if custom firmware bricks the app, the ROM bootloader
   (which cannot be overwritten) can always reflash via UART.

### 5.3 Requirements

- Open the watch (heat + pry from the front; mind the display flex).
- Identify and solder to TX, RX, GND, and LOG pads (30 AWG wire).
- 3.3V USB-UART adapter (CP2102 or CH340, ~₹150–300).
- Multimeter to confirm pad mapping and voltage levels.

## 6. Risk assessment

| Path | Risk level | Justification |
|------|-----------|---------------|
| Stock firmware companion (UTE protocol) | **None** | Read-only + app-level commands the official app sends |
| BLE OTA with AES (if implemented) | **High** | No backup/restore proven; interrupted transfer = potential brick; no independent recovery |
| Wired UART after flash dump + verified restore | **Low** | ROM bootloader is hardware-level recovery; full backup exists |

## 7. Recommendation

**Phase 1 (now, no risk):** Build the desktop buddy and car nav companion using the stock
firmware's UTE BLE protocol. All required features (time, weather, notifications, music,
vibration, keep-awake via 2s notification interval) are already verified working.

**Phase 2 (when watch can be opened):** Open the watch, identify UART pads, dump flash,
verify restore, then develop custom firmware over wired UART.

**Phase 3 (optional):** Once a working custom firmware exists and is proven over UART,
implement the BLE OTA path (with AES) so future updates don't require opening the watch.

Do not attempt BLE firmware modification until Phase 2 is complete.
