# Recovery Plan — realme TechLife Watch S100

Last updated: 2026-10-28.

---

## 1. Current recovery status: **NOT VERIFIED**

No recovery procedure has been tested on this watch. The stock firmware cannot currently be
restored if it is overwritten or corrupted.

**Do not write to this watch's firmware until a recovery path is proven.**

---

## 2. Available recovery routes

### 2.1 Wired UART / ROM bootloader (primary — not yet tested)

**Mechanism:** Realtek RTL8762C has a mask ROM bootloader that cannot be overwritten. When
the LOG pin (P0_3) is held low at power-on, the chip enters "MP mode" and accepts flash
programming commands over UART.

**Tools:**
- `rtltool` (open source, GitHub: `wuwbobo2021/rtltool`) — confirmed RTL8762C support
- Realtek MPTool (vendor tool) — needs "Debug mode" enabled via RegistrySet.exe

**Requirements:**
- Physical access to the main board (watch must be opened from the front)
- Identify TX, RX, GND, LOG pads from the 6-pad header (FCC photos show labeling)
- 3.3V USB-UART adapter (CP2102 or CH340)
- Soldering iron + fine wire (30 AWG or enameled)

**Status:** Not tested. Watch has not been opened.

**Confidence:** **[likely]** — ROM bootloader is a hardware feature of RTL8762C; the 6-pad
header exists on the board; tools exist. But nothing has been confirmed hands-on.

### 2.2 BLE OTA re-flash (secondary — not yet implemented)

**Mechanism:** Use the Realtek DFU service (already present in normal mode) to re-flash the
stock firmware image over BLE.

**Blockers:**
1. AES-256-ECB encryption of every data block is mandatory (key known but not implemented)
2. OpenWearOTA's RealSil driver lacks `--limit-function`, >100KB skip, protocol 0x12 support
3. Even if implemented, this path has never been tested — a failed attempt could brick the
   watch with no wired backup to fall back on
4. If the new firmware crashes before BLE initializes, the DFU service won't be available

**Status:** Not implemented. Not safe to attempt without wired recovery as backup.

**Confidence:** **[likely feasible in principle]** — the protocol is understood, the key is
known, the firmware is unencrypted and unsigned (RSA block zeroed). But "feasible in
principle" is not "tested and working."

### 2.3 Companion app re-flash (unknown)

**Mechanism:** Use the official realme Fit app to push the stock firmware to the watch.

**Blockers:**
1. The app downloads firmware from UTE's server at update time — it does not bundle images
2. If the watch is running custom firmware that doesn't implement the UTE protocol, the
   app cannot connect to it
3. If the watch's Realtek DFU service is unavailable (custom firmware crash), the app has
   no way to reach the device

**Status:** Not tested. Unlikely to work as a recovery route for custom firmware scenarios.

---

## 3. Stock firmware preservation

| Asset | Status |
|-------|--------|
| Firmware binary `RH288A_V001319_fw_1660354713_5619.bin` (562,896 bytes) | Downloaded from UTE S3; SHA-256 `0a162300…` |
| UI resources `RH288A_V000957_U0006_ui_1641738154_5635.bin` (4,075,524 bytes) | Downloaded from UTE S3; SHA-256 `3b3290fa…` |
| Firmware matches device | App version `00 70 52 00` in header = `ffd4` on watch **[confirmed]** |
| Full flash dump (internal + external) | **Not taken** — requires opening the watch |
| Device configuration / bonding data | **Not preserved** — exists only on-device |

**The downloaded firmware file is NOT a complete flash image.** It is a Realtek MP pack
containing one app-code partition. A complete backup requires a raw flash dump via UART.

---

## 4. Gate checklist (from docs/TechLife-S100.md §9)

| # | Step | Status |
|---|------|--------|
| 0 | No BLE writes to OTA/DFU characteristics | **In effect** |
| 1 | Open watch; photograph both board sides | Not started |
| 2 | Identify TX/RX/LOG/GND pads; confirm 3.3V | Not started |
| 3 | Wire USB-UART adapter (TX→RX, RX→TX, GND→GND) | Not started |
| 4 | Hold LOG low at boot → confirm ROM MP mode responds | Not started |
| 5 | Dump full flash ×2, compare hashes, restore, confirm stock boots | Not started |
| 6 | Custom firmware (wired first; BLE OTA only once proven) | Not started |

---

## 5. Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Display flex tears during disassembly | Medium | Use heat + plastic tools; watch YouTube teardowns of similar realme watches first |
| Pad identification wrong → shorts | Low | Measure with multimeter before connecting anything; FCC photos provide a reference |
| ROM bootloader doesn't respond | Low | RTL8762C ROM bootloader is in mask ROM; cannot be disabled. Most likely cause: wrong pin or wrong baud rate |
| Flash dump fails / is incomplete | Low | Dump twice, compare. Try both rtltool and MPTool. |
| Restore fails → watch bricked | Very low | If dump + restore is the test, failure means the ROM bootloader itself doesn't work → stop before custom firmware |
| BLE OTA bricks watch before wired backup | **High if attempted** | **Do not attempt.** This is the scenario the gate checklist exists to prevent. |

---

## 6. Decision

**Recovery is unverified. No firmware writes are authorized.**

Safe work continues: stock-firmware companion app (UTE protocol), documentation, offline
firmware analysis, and BLE OTA tooling development (tested against other devices, not this one).
