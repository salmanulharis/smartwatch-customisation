# Test Plan — realme TechLife Watch S100

Last updated: 2026-10-28.

---

## 1. Offline tests (no device needed)

| # | Test | Input | Expected | Status |
|---|------|-------|----------|--------|
| O1 | Firmware file identification | `research/firmware/RH288A_V001319_fw_1660354713_5619.bin` | MP header: `RTL8762C`, size 562,896, flash addr `0x0080E000`, image ID `0x2793` | **Pass** |
| O2 | Firmware SHA-256 matches recorded hash | Above file | `0a162300be59744ec0ee315f41c3e8b0b114128b215ffde6798cb1eafc126fd4` | **Pass** |
| O3 | UI resources file identification | `research/firmware/RH288A_V000957_U0006_ui_1641738154_5635.bin` | Valid MP header, IC `RTL8762D`, size 4,075,524 | **Pass** |
| O4 | UTE text encoding (UTF-16BE) | ASCII + CJK + emoji | BMP chars encoded, non-BMP and control chars dropped, max 160 bytes | **Pass** (unit-level in s100.py) |
| O5 | CRC-16 implementations | Known test vectors | xmodem, arc, telink all produce correct values | Not yet formally tested |
| O6 | Notification packet assembly | 160-byte body | Correctly split into 18-byte C5 chunks with sequence numbers | **Pass** (by inspection) |
| O7 | Weather packet assembly | 7-day forecast with negative temps | Sign-magnitude encoding correct; pages correctly structured | **Pass** (by inspection) |
| O8 | Firmware binary layout parsing | Stock firmware | MP TLV, image header, SHA-256, RSA fields all parseable | **Pass** |

## 2. Stock-device tests (BLE, no firmware modification)

| # | Test | Command | Expected | Status |
|---|------|---------|----------|--------|
| S1 | BLE scan finds device | `openwearota scan` | `TechLife Watch S100` at `78:02:B7:58:FF:9E` | **Pass** |
| S2 | Chipset detection | `openwearota` → 1 → select → cancel | Detected as `realsil (RTL876x)` | **Pass** |
| S3 | GATT service dump | `tools/s100_gatt_dump.py` | All services/chars listed; MTU 247 | **Pass** |
| S4 | Bind + reconnect | `tools/s100.py info` | Bind `33 04 01`, version `RH288AV001319` | **Pass** |
| S5 | Time sync | `tools/s100.py time` | Watch clock updates to PC time | **Pass** |
| S6 | Notification (text, silent) | `tools/s100.py notify "Hello"` | Text shown on watch, no vibration | **Pass** |
| S7 | Navigation text | `tools/s100.py nav "Turn right" 200` | Text shown, no vibration | **Pass** |
| S8 | Vibration | `tools/s100.py vibrate 2` | 2 buzzes felt | **Pass** |
| S9 | 7-day weather + city | `tools/s100.py weather --city Kochi` | Weather page shows 7 days + city name | **Pass** |
| S10 | Music title + state | `tools/s100.py music "Title"` | Music page shows title while connected | **Pass** |
| S11 | Watch → phone buttons | `tools/s100.py listen 60` | `D1 07/09/0E` events received | **Pass** (play/pause, prev, vol down) |
| S12 | Desk-clock keep-awake (2s) | `tools/s100.py deskclock 120 --interval 2` | Screen stays continuously lit for 2 minutes | **Pass** |
| S13 | Car nav demo (2s refresh) | `tools/s100.py cardemo 60` | Speed + direction + distance refreshed; buzz at turn | **Pass** |
| S14 | Screen-off via A9 (60s) | `tools/s100.py screen 60` | Command accepted (`a9` reply) but screen timeout unchanged | **Pass** (expected: no effect) |
| S15 | Reconnection after disconnect | Disconnect + reconnect + bind | Watch re-binds cleanly | **Pass** |
| S16 | Connection loss indication | Kill the script mid-session | Watch eventually shows disconnect state | Not yet tested |
| S17 | Notification accumulation | Send 50+ notifications via deskclock | Check if notification list fills up | Not yet tested |
| S18 | Custom watch face upload | `26 02` → `27` data → `26 03 00` | Watch displays custom face | Not yet tested |
| S19 | Battery level via BLE | Read `2a19` | Returns current battery % | **Pass** (92% on 2026-10-28) |
| S20 | Max screen-off from watch menu | Set to 15s in watch settings, time it | Exactly 15 seconds? Or is there headroom? | Not yet tested |

## 3. Companion app tests (desktop/Android, no firmware modification)

| # | Test | Scope | Expected | Status |
|---|------|-------|----------|--------|
| C1 | Desktop buddy — continuous run (1 hour) | `deskclock` with 2s interval on charger | Screen stays on; no errors; BLE stable | Not yet tested |
| C2 | Car nav — simulated route (10 min) | `cardemo` or real navigation feed | Consistent updates; buzz at turns only | Not yet tested |
| C3 | Connection recovery | Kill + restart script | Re-binds and resumes within 30s | Not yet tested |
| C4 | Multiple feature interleave | Time + weather + music + nav in one session | All features work without conflicts | Not yet tested |
| C5 | Phone companion app (Android) | Kotlin app reading GPS + Maps + media | Sends compact BLE updates to watch | Not yet implemented |
| C6 | Gadgetbridge compatibility test | Pair as "unsupported gadget" in Gadgetbridge | Explore what the GloryFit driver can do | Not yet tested |

## 4. Firmware modification tests (BLOCKED — requires recovery verification)

These tests must NOT be run until the gate checklist in `docs/recovery-plan.md` is complete.

| # | Test | Precondition | Expected | Status |
|---|------|-------------|----------|--------|
| F1 | UART connection to ROM bootloader | Watch opened, pads soldered | MP mode responds to rtltool | Blocked |
| F2 | Full flash dump ×2 | F1 passes | Two identical dumps, hash matches | Blocked |
| F3 | Flash restore → stock boots | F2 passes | Watch boots normally after restore | Blocked |
| F4 | Stock firmware BLE OTA re-flash | F3 passes + AES implemented | Unmodified stock image flashed over BLE; watch boots | Blocked |
| F5 | Patched firmware (screen timeout) | F3 passes | Patch A or B applied; screen stays on > 15s | Blocked |
| F6 | Custom firmware (minimal clock) | F3 passes + SDK setup | Bare-metal clock face renders on display | Blocked |
| F7 | Custom firmware BLE UART | F6 passes | Nordic NUS exposed; PC can connect via `openwearota uart` | Blocked |
| F8 | Custom firmware BLE OTA | F6 + F7 pass | OTA update works; recovery to stock still possible | Blocked |

## 5. Test environment

| Item | Value |
|------|-------|
| OS | Windows 11 Home 10.0.26300 |
| Python | 3.12.10 (venv at `.venv/`) |
| BLE | Built-in laptop Bluetooth, WinRT; bleak 3.0.2 |
| Watch MAC | `78:02:B7:58:FF:9E` |
| Bind ID | `0x00511000` |
| Phone | Disconnected (realme Fit closed / BT off) during all tests |
