# realme TechLife Watch S100 — Research Notes

Living notes for repurposing a spare TechLife S100 into a custom-firmware desk clock /
car navigation display. Update this file as new information comes in; add an entry to the
[changelog](#changelog) at the bottom each time.

Confidence tags used below: **[confirmed]** = read directly from the device or a primary
source; **[likely]** = strong evidence but not fully verified; **[unverified]** = guess or
secondary source only.

---

## 1. Device identity

| Field | Value | Source |
|---|---|---|
| Marketed name | realme TechLife Watch S100 | Watch "About" screen |
| Model | **RMW2103** | Watch regulatory screen **[confirmed]** |
| Serial number | 2202235621030004230 | Watch regulatory screen |
| Manufacturer | Realme Chongqing Mobile Telecommunications Corp., Ltd. | Watch regulatory screen |
| Stock firmware | **1.3.0.017** | Watch "Software Version" screen **[confirmed]** |
| BLE MAC | `78:02:B7:58:FF:9E` | Watch screen + BLE `ffd2` characteristic **[confirmed]** |
| BLE advertised name | `TechLife Watch S100` | BLE scan **[confirmed]** |
| FCC ID | **2AUYFRMW2103** | FCC filing **[confirmed]** |
| Release | March 2022 | [GSMArena](https://m.gsmarena.com/realme_techlife_watch_s100-11420.php) |
| Companion app | **realme Fit** (not realme Link) | [91mobiles review](https://www.91mobiles.com/hub/realme-techlife-watch-s100-review/), [Geekman review](https://www.geekman.in/realme-techlife-watch-s100-review/) |

---

## 2. Hardware

### 2.1 Summary

| Part | Value | Confidence / Source |
|---|---|---|
| SoC | **Realtek RTL8762-series**; package marking looks like `RTL8762DK` (last letters blurry) | Family **[confirmed]** (BLE services + Realtek logo in FCC photo); exact variant **[likely]** |
| External flash | **XTX XT25F64B** (64 Mbit = 8 MB SPI NOR) — probably watch faces / fonts / images | **[likely]** (FCC photo marking) |
| Main board | `RH288_V01`, dated `20211120` | **[confirmed]** (FCC photo silkscreen) |
| Display module | Label `KPS-RH288-BT-V0.6`; 1.69" IPS **LCD**, 240×280, ~218 ppi, 530 nits | Label **[confirmed]** (FCC photo); specs from [GSMArena](https://m.gsmarena.com/realme_techlife_watch_s100-11420.php) |
| Display controller | **ST7789V2** via RTL8762C LCDC (8080 parallel interface, not SPI); firmware has `LCDC base 0x40024800` + GDMA refs | **[likely]** — universal in 240×280 1.69" IPS smartwatch panels; no explicit controller string in firmware binary |
| Touch | Yes (capacitive) | Observed |
| Buttons | 1 side button | Observed |
| Battery | 260 mAh Li-ion (pouch, soldered wires to B+/B− pads) | [GSMArena](https://m.gsmarena.com/realme_techlife_watch_s100-11420.php) + FCC photo |
| Sensors | Accelerometer, PPG heart rate / SpO2 (sensor flex labeled `SUB_VC32R21`, `C2151`), skin/body temperature | GSMArena + FCC photo + watch menus |
| Vibration | Coin vibration motor | FCC photo |
| Charging | 2 pogo pins on case back → appear to be **charging only** | **[likely]** (FCC photo shows them in the case, not on the UART header) |
| Radio | BLE, 2402–2480 MHz | FCC grant **[confirmed]** |

### 2.2 Test pads (critical for recovery)

From the FCC internal photos (main board, SoC side):

- A row of **6 through-hole pads** along the board edge next to the SoC. Silkscreen under
  them reads approximately **`• TX RX L … P`**. **[likely]**
  - `TX` / `RX` → SoC UART (factory programming / log port).
  - `L` → probably the Realtek **LOG** pin (P0_3), which selects ROM "MP mode" when held
    low at power-on. **[unverified — must confirm on real board]**
  - `P` → possibly power/VBAT. **[unverified]**
- Separate labeled pads: **`GND`**, **`VDD`**, **`B+`**, **`B−`** (battery), `RF` (antenna feed).
- 3 small pads at the top-left on the other side of the board (purpose unknown).

> ⚠️ Pad mapping must be confirmed with a close-up photo of the actual board and a
> multimeter **before** soldering anything. Logic level expected to be **3.3 V**.

### 2.3 Disassembly notes (from FCC photos)

- Opens from the **front**: the display is glued to the case (adhesive residue visible).
- Order: display → battery (under display) → main board + sensor flex.
- Display ribbon/board-to-board connector sits on the main board — find it before fully
  lifting the screen.

### 2.4 FCC photo crops

| | |
|---|---|
| ![Board front (SoC side)](img/techlife-s100/fcc-board_front.png) | ![Board back (flash side)](img/techlife-s100/fcc-board_back.png) |
| Board — SoC side, 6-pad header top right | Board — flash side, `RH288_V01`, GND/VDD/B+/B− |
| ![UART pads](img/techlife-s100/fcc-pads_front.png) | ![SoC marking](img/techlife-s100/fcc-chip_front.png) |
| 6-pad header, silkscreen `TX RX L … P` | SoC marking (Realtek logo, `…8762?K`) |
| ![Display + battery](img/techlife-s100/fcc-page2.png) | ![Case + board](img/techlife-s100/fcc-page4.png) |
| Display label `KPS-RH288-BT-V0.6`, battery, open case | Board in case; board removed with sensor flex |

---

## 3. FCC filing (2AUYFRMW2103)

| Field | Value |
|---|---|
| Grantee | Realme Chongqing Mobile Telecommunications Corp., Ltd. (grantee code 2AUYF) |
| Device description | Smart Watch with BT |
| Equipment class | JBP — Part 15 Class B Computing Device Peripheral; DTS (15C) |
| Frequency / output | 2402–2480 MHz, 0.0012 W |
| Grant date | 2022-04-01 (TCB: PHOENIX TESTLAB GmbH) |
| Test firm | Shenzhen Morlab Communications Technology Co., Ltd. |
| Short-term confidentiality | Yes, until 2022-09-29 (internal/external photos now public) |
| Long-term confidentiality | Yes — **Block Diagram, Schematics, Operational Description, BOM are confidential** (metadata only) |

Public exhibits: User Manual, **Internal Photos**, External Photos, Label, Test Setup Photos,
test reports (EMC, BLE DTS, RF exposure), cover letters.

Links (open in a browser; they block automated fetches):
- https://fcc.report/FCC-ID/2AUYFRMW2103
- https://fccid.io/2AUYFRMW2103

---

## 4. BLE / GATT profile (stock firmware 1.3.0.017)

Read-only dump taken 2026-10-28 with `bleak` from Windows. MTU negotiated: **247**.

| Service | Characteristics (properties) | Notes |
|---|---|---|
| `1801` Generic Attribute | `2a05` (indicate) | Service Changed |
| `1800` Generic Access | `2a00` (read) = `TechLife Watch S100`; `2a01` (read); `2a04` (read) = all zeros; `2aa6` (read) = `00` | |
| `000055ff-…` Vendor | `33f1` (write, read); `33f2` (notify) | realme private app protocol **[likely]** |
| `0000180f` Battery | `2a19` (notify, read) = `0x5c` (92 %) | |
| **`0000d0ff-3c17-d293-8e48-14fe2e4da212`** Realtek OTA | `ffd1` (write-no-rsp) — enter-OTA; `ffd2` (read) BD addr; `ffd3` (read); `ffd4` (read); `ffd5` (read, empty); `ffd8` (write-no-rsp); `fff1` (read); `fff2` (write); `ffe0` (read); `fff3` (read) | Normal-mode OTA service |
| `000056ff-…` Vendor | `34f1` (write-no-rsp, read); `34f2` (notify) | realme private protocol **[likely]** |
| **`00006287-3c17-d293-8e48-14fe2e4da212`** Realtek DFU | `6387` (write-no-rsp) data; `6487` (write, notify) control point | DFU service is **already exposed in normal firmware** |

No Nordic UART Service (`6e400001-…`) — the `openwearota uart` bridge has nothing to talk to on stock firmware.

### 4.1 Realtek OTA info characteristic values (raw)

| Char | Raw bytes | Interpretation |
|---|---|---|
| `ffd2` | `78 02 b7 58 ff 9e` | BD address **[confirmed]** |
| `ffd3` | `00 f0 0e 58` | Patch version **[likely]** |
| `ffd4` | `00 70 52 00` | App version **[likely]** |
| `ffd5` | (empty) | Patch-extension version |
| `ffe0` | `01 00 00 01 00 20 00 00 00 f0 0e 58 00 70 52 00` | Device info block; bytes 8–15 repeat ffd3+ffd4. **Not** used by parseX0012 (icType=1 doesn't match) |
| `fff1` | `09 01 00 07 00 08 00 00 f0 0f 00 00` | **Decoded** via `parseX0012`: icType=9, specVer=1, mode=0x07 (AES on, mode 1, no buf-check), maxBufChk=2048 |
| `fff3` | `12 00` | Protocol type **0x12** → `ProcessorX0012S` (silent OTA) **[confirmed]** |

> `fff1` is the actual device info characteristic read by `u()` for protocol 0x12 (`parseX0012`).
> Mode byte 0x07 = AES enabled + encrypt all blocks + no buffer check.
> See `docs/firmware-feasibility.md` §3.5 for full decode.

---

## 5. Stock firmware features (observed)

- Watch faces ("Dial"), Brightness, **Screen Timeout**, Vibration Strength, Do Not Disturb,
  Raise to Wake. **No always-on display option.**
- Music control page: prev / play-pause / next + volume (shows "Not connected" until paired).
- Notifications (read/clear only, no reply), weather, heart rate (with history graph),
  SpO2, skin/body temperature, sleep, steps/kcal/active minutes, workouts, breathing,
  timer, stopwatch, alarm, flashlight, camera remote, find phone.
- Quick panel: DND, brightness, raise-to-wake, flashlight, settings.

---

## 6. OpenWearOTA status for this watch

- `openwearota` detects it as **`realsil` (RealSil RTL876x)** via DFU service `6287`. **[confirmed]**
- `identify_realsil_chip()` returns nothing (no model ID).
- **Do NOT flash this watch with OpenWearOTA.** Current RealSil driver limitations
  (`openwearota/drivers/realsil.py`):
  1. Always does phase-1 handover (writes `0x01` to `ffd1`) then returns False, asking for
     `--limit-function` — but the CLI has **no such flag**. On this watch the DFU service is
     already present in normal mode, so phase 1 is likely unnecessary.
  2. `START_DFU` metadata is sent **unencrypted**; Realtek SDK uses AES-256-ECB (default key
     in DOCUMENTATION.md §7.5). A realme production device may require AES and/or a
     per-product key / signed image.
  3. The >100 KB "big image" skip (DOCUMENTATION.md §7.8) is not implemented.
- There is no BLE way to back up the stock firmware → any BLE flash is effectively irreversible.

---

## 7. Software ecosystem research

| Topic | Finding | Source |
|---|---|---|
| Gadgetbridge support | **None found** for realme / Dizo watches | Gadgetbridge site/search |
| Gadgetbridge navigation | Works only on some watches (PineTime/InfiniTime, Bangle.js, Fossil); OsmAnd via API, Google Maps via parsing its persistent notification (disable Maps "Live Updates"); text only, no map | [Gadgetbridge navigation docs](https://gadgetbridge.org/basics/integrations/navigation/), [Espruino forum](https://forum.espruino.com/comments/16419406/incontext) |
| Custom firmware for RTL8762 watches | **None published** | Web search |
| RTL8762 dev resources | Vendor SDK (registration); GCC examples [cyber-murmel/rtl8762c-gcc-examples](https://github.com/cyber-murmel/rtl8762c-gcc-examples); BLE-UART example [wuwbobo2021/rtl8762c-ble-uart](https://github.com/wuwbobo2021/rtl8762c-ble-uart); UART programmer [wuwbobo2021/rtltool](https://github.com/wuwbobo2021/rtltool) (RTL8762C; D support unknown) | GitHub |
| ROM programming mode | LOG pin (P0_3) held **low at power-on** → ROM "MP mode"; programmed over UART with Realtek MPTool (Debug mode enabled via RegistrySet.exe) | [RTL87x2x Quick Start Guide](https://www.manualslib.com/guide/4427583/rtl87x2x-quick-start-user-guide.html) |
| Flash read-back / backup procedure | **Not found documented** — must be verified hands-on | — |
| Related reverse-engineering (other chips) | FitPro LT715 / Telink TLSR8232 full RE + custom FW: [e-labInnovations/FitPro-LT715-TLSR8232](https://github.com/e-labInnovations/FitPro-LT715-TLSR8232); $3 Telink watch MicroPython port ([Hackaday](https://hackaday.com/2024/06/26/3-smartwatch-can-run-python)); ATCwatch for nRF52 Da Fit watches ([CNX](https://www.cnx-software.com/?p=78937)) | — |
| Misattributed chip | One spec site lists MediaTek MT2523 — **wrong** (BLE + FCC photos show Realtek) | [Digit](https://www.digit.in/wearable-devices/realme-techlife-watch-s100-price-286825.html) |

---

## 7b. Companion app analysis (realme Fit APK)

**Constraint (2026-10-28): the watch cannot be opened.** Everything must be done over BLE,
so the companion app is the main source of protocol / OTA knowledge.

### 7b.1 The APK

| Field | Value |
|---|---|
| App | realme Fit 1.2.9 (versionCode 29), package **`com.techlife.wear`** |
| Source | [APKMirror](https://apkmirror.com/apk/realme-mobile/realme-fit/realme-fit-1-2-9-release) |
| Local file | `reference-app/com.techlife.wear_1.2.9-29_minAPI21(arm64-v8a,armeabi,armeabi-v7a)(nodpi)_apkmirror.com.apk` (git-ignored — copyrighted) |
| SHA-256 | `37fd9d124b1a97dc3cf69426e230e73f4df27c384261e69f30c9e13e52b221d4` |
| Size | 61,372,961 bytes, 4,546 zip entries, 3 dex files |

### 7b.2 What it's built on

| Component | Evidence | Meaning |
|---|---|---|
| **UTE / YC SDK** (`com.yc.pedometer`, ~2,500 class strings; also `com.ute.camera`, `com.yc.server`) | dex string table | realme Fit is a re-skin of UTE's white-label watch platform (same family as the **GloryFit** app, `com.yc.gloryfit`). The watch's private protocol (`55ff`/`56ff`, `33f1/33f2`, `34f1/34f2`) is the UTE protocol. |
| **Realtek DFU SDK** (`com.realsil.sdk.dfu.*`, `com.realsil.android.blehub.dfu.*`, `com.realsil.ota.*`) | dex string table | Firmware updates use Realtek's official Android DFU library |
| **`libRtkAesJni.so`** (native, all ABIs) | APK `lib/` | Realtek AES for DFU → OTA metadata is AES-encrypted, as in Realtek's SDK |
| `libAMapSDK_MAP` (AMap/Gaode maps), `libJni_wgs2gcj.so` | APK `lib/` | Map features (workout routes); not relevant to the watch display |
| `assets/DialCustom/dial_1_circle_240x240/`, `dial_2_square_240x240/` (248 files each) | APK assets | **Custom watch faces are composed on the phone and uploaded to the watch.** Element positions are encoded in file names, e.g. `hour2min/config_32x45_104x45.txt` = 32×45 px digits at (104,45). Custom graphics without firmware change. |
| No firmware `.bin` bundled | APK assets | Firmware is downloaded from UTE's server at update time |

### 7b.3 BLE UUIDs referenced by the app

Watch-relevant: `000055ff`/`33f1`/`33f2`, `000056ff`/`34f1`/`34f2` (UTE protocol);
`0000d0ff-3c17-…`, `ffd0`–`ffd5`, `ffd8`, `fff0`–`fff3`, `fff6` (Realtek OTA);
`00006287`/`6387`/`6487`/**`6587`**`-3c17-d293-8e48-14fe2e4da212` (Realtek DFU; `6587` not
seen on our watch); `000002fd-3c17-…`; `fea1`/`fea2`/`fee7` (WeChat-style), `fef5`.

### 7b.4 Server endpoints (UTE cloud)

| Purpose | Endpoint |
|---|---|
| Watch-face store | `https://apsouth.uteasy.com/ci-yc/index.php/api/client/{getWatchClass,getWatchs,getWatchZips,issetWatch,addWatch,getProtocolVersion,hasxindian}` |
| **Firmware update queries** (host/params built in code — not yet known) | `/api/client/getBtVersionUpdate`, `getBtImgUpdate`, `getBtUIVersionUpdate`, `getPatchlicationUpdate`, `getApplicationUpdate`, `getOnlineConfiguration` |
| User account | `https://apsouth.uteasy.com/ci3/index.php/api/user/...` |
| Legal pages | `https://app.uteasy.com/privacy-policy/realme.html`, `https://app.ute-tech.com.cn/open-source-license/com.techlife.wear.html` |

The split into BtVersion / BtImg / BtUIVersion / Patch / Application suggests the firmware
ships as separate parts (app code, patch/stack, UI image resources) — consistent with an
RTL8762 + 8 MB external flash layout. **[likely]**

### 7b.5 Related open-source work

- **Gadgetbridge has a "GloryFit" driver** (same UTE/YC platform): tested on Oukitel BT103;
  supports activity/HR/SpO2/sleep sync; **missing weather, notifications, firmware upload**.
  [Device page](https://gadgetbridge.org/gadgets/wearables/gloryfit/). Not yet checked whether
  its UUIDs/commands match the S100. Gadgetbridge allows "pair unsupported gadget" for testing.
- No realme-specific reverse engineering found.

### 7b.6 Analysis method / status

- String tables extracted with a pure-Python dex parser (no app code executed) →
  `research/dex-strings.tsv` (184,376 strings; git-ignored).
- Full decompilation with **jadx 1.5.1** was **blocked by the Claude Code permission system**
  (running a downloaded tool). To do it manually:
  ```powershell
  # download https://github.com/skylot/jadx/releases/download/v1.5.1/jadx-1.5.1.zip, unzip, then:
  .\jadx-1.5.1\bin\jadx.bat -d research\jadx-techlife-1.2.9 -j 8 --show-bad-code --no-res `
    "reference-app\com.techlife.wear_1.2.9-29_minAPI21(arm64-v8a,armeabi,armeabi-v7a)(nodpi)_apkmirror.com.apk"
  ```
  (Java 21 is installed.) Output goes to `research/` (git-ignored).
- Needed from decompiled code: firmware-API host + request params, UTE command set
  (notifications, weather, music, screen timeout, dial upload), Realtek DFU flow + AES key.

### 7b.7 Decompiled-code findings (jadx 1.5.1, 2026-10-28)

Decompiled by the user-provided `jadx-1.5.1/` (git-ignored) into
`research/jadx-techlife-1.2.9/` (7,925 Java files, 4 non-fatal errors). Paths below are
under `research/jadx-techlife-1.2.9/sources/`.

#### Firmware download (UTE cloud) — **[confirmed in code]**

- Base URL hardcoded: `https://apsouth.uteasy.com/ci-yc/index.php`
  (`com/yc/pedometer/update/Updates.java:203,378`; paths in `com/yc/server/yc_sdk/common/Constants.java`).
- `POST …/api/client/getBtVersionUpdate` (firmware image), `getPatchlicationUpdate` (patch),
  `getBtUIVersionUpdate` (UI resources), `getBtImgUpdate`, `getApplicationUpdate` (APK).
- Body: form field `content` = **RSA-encrypted JSON** (`RSA/ECB/PKCS1Padding`, public key in
  `com/yc/pedometer/wechat/RSAUtils.java:14`, 32-char chunks → base64)
  for BtVersion/Patch/UI; plaintext JSON for BtImg / OnlineConfiguration.
- JSON fields: `appkey`, `btname`, `versionname` (or `versioncode` for patch), `debug=1`, `language`.
  No MAC, token or signature.
- `appkey` = manifest meta-data `YCAPPKEY` → **`acd3e73149ae3ab48cf8775dc4afa9fc`** **[likely — value
  adjacent to the key in the binary manifest string pool]**.
- `btname` / `versionname` come from the watch's **`A1` reply** (ASCII, e.g. `RM07V000000` →
  btname `RM07`, versionname `V000000`). App default for realme: `RM07V000000`
  (`Updates.java:254`). Our watch's real string is **not yet read** (see below).
- Response: `flag` (>0 = has result), `fileurl[] {urlname, urladdress}`, `versionname`,
  `forceupdate`, `description`. Download = plain unauthenticated GET of `urladdress`.
  Version compare is client-side (`String.compareTo` after "V") → reporting an older
  `versionname` should return the current file URL **[inferred]**.
- Realtek ("RK") platform → `FirmwareActivity.startOtaProcess8762C()` → Realtek
  `GattDfuAdapter.startOtaProcedure()`.

#### Realtek OTA as used by the app — **[confirmed in code; partial — analysis cut short]**

- Uses only `com.realsil.sdk.dfu` (not the older blehub DFU). Entry:
  `com/yc/pedometer/FirmwareActivity.java:938`.
- `setVersionCheckEnabled(false)`; OTA work mode **16 = silent OTA** whenever DFU service
  `6287` is present in normal mode (true for our watch; `sdk/BluetoothLeService.java:525`).
  Silent OTA writes the new image while the old one keeps running **[Realtek design; implies
  dual-bank / backup area — not yet verified for this watch]**.
- `fff3 = 12 00` → Realtek OTA protocol type **0x12** → processor class `dfu/n/e.java`.
- AES key: 32 bytes hardcoded at `FirmwareActivity.java:309` — Realtek's default SDK key
  with bytes 5–10 replaced by ASCII **`UTE_RK`** (UTE-customised). Native AES in `libRtkAesJni.so`.
- Not yet extracted: full decode of `ffe0`/`fff1`, image pack format, complete opcode
  sequence for protocol 0x12.

#### UTE BLE protocol — **[confirmed in code]**

Builders: `com/yc/pedometer/sdk/WriteCommandToBLE.java` (WCB); parser/state machine:
`sdk/BluetoothLeService.java` (BLS). Same codebase as **GloryFit** (`com.yc.gloryfit`).

- **33f1** write = legacy commands; **34f1** write = large/new commands (dials, song info,
  weather extras). Notifies: 33f2, 34f2. One write in flight at a time. App never requests MTU.
- **Connect order:** enable CCCD 33f2 + 34f2 → read 33f1 (20-byte function bitmap) → read 34f1
  (max length) → auth/bind → `A3` time → `A1` version. Watch names containing
  "TechLife Watch" get an OS-level `createBond()`.
- **Our watch (read 2026-10-28):** 33f1 = `08 00 00 00 01 6c 19 4f 7d 67 ff fe 59 2b 00 5f 78 cb 65 0c`;
  34f1 = `00 f4` → **max length 244**. Lists (big-endian): L1 `0xcb650c` (bytes 17–19),
  L2 `0x5f78`, L3 `0xfe592b`, L4 `0x7d67ff`, L5 `0x6c194f`, L6 `0x000001`, L7 `0x0800`.
  Masks (`column/GetFunctionList.java`): L1&0x2 = 0 → **no password**; L1&0x4 → full font
  (UTF-16) **[likely]**; L1&0x2000 → **7-day weather**; L5&0x4 → **account-ID bind required**;
  L5&0x1 and L5&0x1000 → **new music protocol**; L6&0x400000 = 0 → notification text max 160 B.
- **Bind:** `33 02 <id u32 BE>` → watch `33 04 st` (01 OK, 03/04 confirm on watch, 05 cancelled).
- **Time:** `A3 yyHi yyLo MM dd HH mm ss`.
- **Version:** `A1` → reply `A1` + ASCII version string.
- **Notifications:** `[type][len]+UTF-16BE text` split into `C5 seq <18 B>` packets; watch acks
  `C5 seq` / `C5 FF` (resend) / `C5 FD` (done). Single string (no title field). Vibration is a
  separate command `AB 00 00 00 01 n 00 00` → **silent text updates possible [inferred]**.
  Types: 0 call, 1 QQ, 2 WeChat, 3 SMS, 4 other, 5 Facebook, 6 Twitter, 7 WhatsApp, … 24 Telegram.
  **No navigation command exists.**
- **Weather (7-day):** `CB 01 cond 00 tCur tMax tMin pm25(2) aqi(2) city…`, watch requests pages
  `CB 02`/`CB 03`; temps sign-magnitude (0x80 = negative); codes 1 sunny … 12 wind; city name
  `CB FF len utf8` on 34f1.
- **Music → watch (34f1):** `3A 01 state …`, `3A 06 len utf8 title`, `3A FA` (state 1 play, 2 pause).
  **Watch → phone:** `D1 07` play/pause, `D1 08` next, `D1 09` prev, `D1 0D`/`0E` vol ±, `D1 0A` find phone.
- **Settings `A9` (19 bytes):** byte[5] = **screen-off seconds** (app UI offers 5/10/15 only —
  real watch limit unknown), byte[10] = raise-to-wake, plus profile/goal fields.
  **No brightness command found.**
- **Custom dials:** `26 01` (read config: dial id, w, h, screen type, max size, compat level) →
  `26 02` → data `27 secHi secLo …` on 34f1 (4096-byte sections, wait `26 03 04`) → `26 03 00`.
  File = 24-byte LE header (CRC32 over payload) + 24-byte element table + **RGB565 BE** images
  (RLE if compat ≥ 2). Element positions from `assets/DialCustom/*/config_WxH_XxY.txt` names.
  Online dials (`getWatchZips`) are sent raw.

#### Live tests on the watch (2026-10-28)

- Reads of 33f1/34f1 succeeded (values above).
- `A1` query written to 33f1 twice (once with only 33f2 notify, once with 33f2+34f2 enabled
  and both reads done): **no reply** → watch ignores commands until bound.
- **Bind (user-approved):** `33 02 00 51 10 00` (our app's account ID `0x00511000`).
  Watch replied `33 04 03` (new account → confirm/reset) then `33 04 02` (accepted, watch
  resets user data and disconnects). Reconnect + same bind → `33 04 01` (**bound OK**).
  No OS-level pairing was needed on Windows.
- `A3` time sync → echoed `a3 07 ea 0a 1c 0c 2b 09` (2026-10-28 12:43:09).
- **`A1` → `RH288AV001319`** → UTE `btname` = **`RH288A`**, `versionname` = **`V001319`**
  (stock firmware shown as 1.3.0.017 on the watch). `RH288` matches the FCC board name.
- **`26 01` (dial config) →** `26 01 ff ff ff ff 00 f0 01 18 01 00 10 00 00 01 00 00 00 00`:
  current dial id none (`FFFFFFFF`), **240×280**, screen type 1, **max dial size 0x00100000 = 1 MB**,
  compatibility level 1 (→ no RLE compression).

#### Stock-firmware control tool — verified features (2026-10-28)

`tools/s100.py` (bleak). Notes learned while testing: 34f1 is **write-without-response only**;
the watch needs the bind (`33 02 <id>` → `33 04 01`) on every connection; music page shows
"Not connected" unless a central stays connected.

| Feature | Command | Status |
|---|---|---|
| Navigation text (notification, silent) | `nav "<instruction>" <metres> --remaining <km>` | ✅ shown, **no vibration** |
| Desk-clock / keep-awake | `deskclock <s> --interval 2 --weather "<x>"` | ✅ **screen stays continuously lit at 2 s interval while connected; wakes from dark; no buzz** (user confirmed 2026-10-28) |
| Car nav display | `cardemo <s>` | ✅ speed + direction + distance + street, refreshed 2 s, stays lit, buzz only at the turn. **Font has NO arrow glyphs (↱↑ render blank) → use words RIGHT/LEFT/STRAIGHT** (verified 2026-10-28) |
| On-demand vibration | `vibrate <n>` | ✅ felt |
| Time sync | `time` | ✅ echoed |
| 7-day weather + city | `weather --city <name>` | ✅ shown |
| Music title / state | `music "<title>"` | ✅ shown while connected |
| Watch music buttons → PC | `listen <s>` / `demo <s>` | ✅ play/pause, previous, volume down seen (next / volume up not yet observed) |
| Speed | `speed <kmh>` (notification) | implemented, not yet tested |

#### Firmware query tool

`tools/ute_fw_query.py` reproduces realme Fit's update request (stdlib-only RSA PKCS#1 v1.5,
32-char chunks). Usage: `python tools/ute_fw_query.py RH288A V000000 getBtVersionUpdate`
(also `getPatchlicationUpdate`, `getBtUIVersionUpdate`). It only prints the server reply.
First attempt from Claude Code was blocked by the permission system; it was run on the
user's explicit request on 2026-10-28.

#### Stock firmware obtained (2026-10-28) — **[confirmed]**

Server replies for `btname=RH288A`, reported `versionname=V000000`:

| Endpoint | Result | Version | Published | URL |
|---|---|---|---|---|
| `getBtVersionUpdate` | flag 1 | **V001319** (= watch's current `RH288AV001319`) | 2022-08-13 09:39:07 | `https://uteap.s3.ap-south-1.amazonaws.com/ble/acd3e73149ae3ab48cf8775dc4afa9fc/RH288A/1660354713_5619.bin` |
| `getBtUIVersionUpdate` | flag 1 | V000957_U0006 | 2022-01-09 22:22:53 | `https://uteap.s3.ap-south-1.amazonaws.com/bleui/acd3e73149ae3ab48cf8775dc4afa9fc/RH288A/1641738154_5635.bin` |
| `getPatchlicationUpdate` | flag -1 | no patch | — | — |

Description (Chinese): "优化系统已知问题" / "优化已知问题" = "optimise known issues". Files are
public S3 objects (plain GET). Saved (git-ignored) in `research/firmware/`:

| File | Size | SHA-256 |
|---|---|---|
| `RH288A_V001319_fw_1660354713_5619.bin` | 562,896 | `0a162300be59744ec0ee315f41c3e8b0b114128b215ffde6798cb1eafc126fd4` |
| `RH288A_V000957_U0006_ui_1641738154_5635.bin` | 4,075,524 | `3b3290fa2fa522fc32757066a33acf63c3176d466ee3c25473712ffb7a19b293` |

First look (read-only):
- Both start with a Realtek MP pack header containing the IC name string.
  **Firmware header: `RTL8762C`**; UI header: `RTL8762D`. The code package is authoritative →
  SoC is most likely **RTL8762C** (FCC marking "…8762?K" → **RTL8762CK**) **[likely]**.
  This matters: rtltool and the GCC examples target RTL8762C.
- Firmware header contains app version `00 70 52 00` = watch's `ffd4` → **this is exactly the
  image running on the watch**.
- **Not encrypted:** readable strings (`sdk#####`, `1.0.127.0`, `Upperstack Ver: %s, GCID…`,
  `l2c_default`, …), entropy ~7.0 (ARM Thumb code). UI file entropy ~5 (image/font data).
- Next: parse the pack header/sub-images, disassemble to find display controller init,
  pin mapping and the OTA/boot layout.

#### Route B — patching stock firmware for unlimited screen-on (analysis log)

Goal chosen by user 2026-10-28: patch the stock image so the screen can stay on indefinitely.

**Why the protocol route failed:** `A9` byte[5] = 60 s was accepted (`a9` reply) but the screen
still turned off after 5–15 s. Disassembly shows the firmware's `A9` handler (`0x0083690E`)
stores height (b2 → `[+0x68]`), weight (b4 → `+0x69`), step goal (b6–9 → `+0x2C`), b12 → `+0x6E`,
age (b13 → `+0x6C`), sex (b14 → `+0x6D`), temperature unit (b17) — **it never reads byte 5
(screen-off) or byte 10 (raise-to-wake)**. Screen timeout is only set from the watch's own menu.

**Package / image layout** (`RH288A_V001319_fw_…bin`):
- 512-byte MP header (TLV `id u16, len u8, value`): 0x0001 = `00 03`; 0x0002 version
  `0x00527000`; 0x0003 part number `RTL8762C`; 0x0004 / 0x0014 image size 562,384;
  0x0012 image id `0x2793`; **0x0013 flash address `0x0080E000`**; 0x0016 version; 0x0022 = 2.
- Image (562,384 B) = 1024-byte Realtek header + 561,360-byte payload. Ctrl header:
  ic_type `0x09`, secure_version 0, ctrl_flag `0x0901`, image_id `0x2793`, **crc16 = 0 (unused)**,
  payload_len `0x890D0`. Header +0x1C exe/load base `0x008299CC`; +0x28 `0x0080E000`;
  +0x60 version + `sdk#####`.
- **Integrity = SHA-256 at header offset 0x174** (Realtek SDK `BaseBinInputStream.parseImageHeaderEx`:
  offset 360 after the 12-byte ctrl header). **No 256-byte RSA signature block present**
  (0x194–0x2DF zero, 0x2E0–0x3FF `FF`). **SHA-256 coverage found (2026-10-28):** header bytes
  12–371 + 404–751 + 1008..(1024 + payload_len), per SDK `slient_dfu_check_sha256`; reproduces the
  stored hash of V001319 exactly. `tools/rehash_rtl_image.py` recomputes it after patching
  (optional `--version` revision bump). **[confirmed]**
- Realtek SDK code references **active/inactive bank images** → dual-bank OTA layout likely
  (`sdk/dfu/u/k.java`). Not yet verified for this watch.

**Code map (image mapped at 0x0080E000, Thumb):**
- UTE command dispatcher ≈ `0x00838540`: packet at `[sp+8]`; chain of `cmp r0,#cmd` →
  `0xA9`/`0x05` → `bl 0x0083690E`; `0xAA` builds a status reply; etc.
- Timer setup at `0x0084A21C` / `0x0084A3A8`: picks **30000 / 5000 / 10000 ms** from two flag
  bytes (`[+0x24]`, `[+0x1A]`) — purpose not yet identified (may not be the screen timer).
- 15000 ms immediate only at `0x0084104E`, `0x0084A810`.
- Tooling: Capstone 5.0.7 installed in `.venv`.

**Screen-timeout mechanism — found (2026-10-28):**
- Setting = **u16 seconds at `[settings + 0xFA]`**; every screen timer is created/restarted with
  `ldrh rX,[…,#0xFA]; mov.w r0,#1000; muls` (156 reads in total, e.g. flashlight `0x0084EFF0`,
  settings screen `0x0085FB6E`, `0x0085FFDE`). Timer API: `bl 0x000134D2` (create, name string in r1),
  `0x0001353A` (change period).
- Firmware strings give screen names (`SettingDisplayTimeScreenUI`, `FlashLightScreenUI`, …) and timer
  names (`display picture timer`, `page switch timer`, …).
- **Writer in the watch's Settings → Screen Timeout page** (`SettingDisplayTimeScreenUI` module):
  ```
  0085FB04  bl    0x846310          ; get picker index (1..3) into [sp]
  0085FB08  ldr   r0,[sp]
  0085FB0A  ldr   r1,=settings
  0085FB0C  00 eb 80 00   add.w r0,r0,r0,lsl #2   ; ×5  → 5/10/15
  0085FB10  80 b2         uxth  r0,r0
  0085FB12  strh.w r0,[r1,#0xFA]
  0085FB16  cmp r0,#5 / bhs / movs r0,#5 / strh   ; minimum 5 s, no maximum
  ```
  Location of `0x0085FB0C`: image offset `0x51B0C` (= address − 0x0080E000), package-file
  offset `0x51D0C` (image starts after the 512-byte MP header).
- Other writers (`0x0083D4B0`, `0x0083D54A`, `0x0083D5A2`) are inside an internal event handler
  that restores a saved value — **not** phone-controllable. The `A9` BLE command does not touch it.
- **Candidate patch A (6 bytes, no code cave):** replace `add.w r0,r0,r0,lsl#2; uxth r0,r0` with
  `movw r2,#0x5555; muls r0,r2,r0` → options become **21,845 s (6 h) / 43,690 s (12 h) /
  65,535 s (18.2 h)**; r2 is free at this point (clobbered by the preceding `bl`). Loses the
  short 5/10/15 s options. Timer period max 65,535,000 ms (fits 32-bit). **[proposed, not applied]**
- **Candidate patch B:** keep 5/10 s and map option 3 → 65,535 s via a branch to a code cave
  (needs free flash space + branch encoding). **[not designed yet]**

**Remaining work before any flash:** (1) locate the watch-menu screen-timeout option table /
timer; (2) determine SHA-256 coverage (or confirm the bootloader doesn't check it);
(3) implement Realtek OTA protocol 0x12 + UTE AES in Python; (4) **prove the OTA path by
re-flashing the unmodified stock image**; only then (5) flash the patched image.

---

## 8. Project goals

Custom firmware (stock firmware is expendable) providing:

1. Always-on clock / "desktop buddy" face (time, date, weather, phone battery).
2. Car navigation display: turn arrow, distance in km, street name, ETA / remaining distance.
3. Speed display (km/h from phone GPS).
4. Music controls (play/pause, next/prev, volume).
5. Notifications.
6. Built-in BLE UART console + BLE OTA so later updates don't need wires.
7. *(Stretch)* Low-res mini-map streamed from the phone.

Architecture: watch firmware (C, Realtek RTL8762 SDK, GCC) + Android companion app (Kotlin)
reading Google Maps/OsmAnd navigation, GPS speed, media session and notifications, sending
compact packets over BLE.

Constraints: LCD → always-on means backlight on → hours, not days, on 260 mAh; intended
use is on a dock / car charger. Mount out of direct sun; don't charge in a hot parked car.

---

## 9. Safety plan — gates before any write

**Rule: nothing is written to the watch until (1) the ROM bootloader answers over wires and
(2) a full flash backup has been dumped, verified, and successfully restored.**

| # | Step | Read-only? | Stop if… | Status |
|---|---|---|---|---|
| 0 | No BLE writes (`ffd1`, `6387`, `6487`, OpenWearOTA flash) | — | — | ✅ in effect |
| 1 | Open from the front (heat, plastic tools, mind display flex & battery); photograph both board sides | Yes | Screen/flex tears | ☐ |
| 2 | Identify TX / RX / LOG / GND pads; measure logic level = 3.3 V | Yes | Pads can't be identified | ☐ |
| 3 | Wire 3.3 V USB-UART (CP2102 preferred): adapter TX→watch RX, RX→TX, GND→GND; **don't** connect adapter VCC while battery attached | Yes | — | ☐ |
| 4 | Hold LOG low at power-on → confirm ROM MP mode responds (rtltool / MPTool) | Yes | No response | ☐ |
| 5 | Dump full flash **twice**, compare hashes, store 2 copies; restore it and confirm stock boots | Restore writes identical data | Read blocked / restore fails → **no custom FW** | ☐ |
| 6 | Custom firmware, flashed over UART first; BLE OTA only once proven | No | — | ☐ |

Tools needed: 3.3 V USB-UART adapter (CP2102/CH340, ~₹150–300), multimeter, fine soldering
iron + 30 AWG / enameled wire, plastic pry tools, hair dryer / gentle heat.

---

## 10. Entry points (how to reproduce)

All commands run from the repo root in PowerShell, with the watch **disconnected from the
phone** (close realme Fit / turn phone Bluetooth off) and within ~1 m of the PC.

### 10.1 Environment setup (Windows)

Host system used for all work so far:

| Item | Value |
|---|---|
| OS | Windows 11 Home Single Language, build 10.0.26300 |
| Python | 3.12.10 (venv at `.venv/`) |
| BLE stack | Built-in laptop Bluetooth via WinRT; `bleak` 3.0.2 |
| Shell | PowerShell 5.1 (Git Bash also available) |
| Repo path | `C:\Users\salma\OneDrive\Desktop\techbysh\OpenWearOTA` |

```powershell
cd C:\Users\salma\OneDrive\Desktop\techbysh\OpenWearOTA
python -m venv .venv                      # Python 3.12.10 used
.\.venv\Scripts\python.exe -m pip install -e .   # installs openwearota + bleak 3.0.2
# one-time, to allow venv activation scripts:
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

If activation is blocked, call `.\.venv\Scripts\openwearota.exe` / `.\.venv\Scripts\python.exe` directly.

### 10.2 Read-only commands (safe on stock firmware)

| Purpose | Command | Writes to watch? |
|---|---|---|
| BLE scan (find MAC, RSSI) | `openwearota scan` | No |
| Chipset detection | `openwearota` → `1` (Flash firmware) → pick watch → **press Enter at the firmware prompt to cancel** | No (connect + read services only) |
| Full GATT dump + Realtek OTA info | `python tools/s100_gatt_dump.py` (optional MAC argument) | No (reads only; no notify/pair) |

### 10.3 Commands that must NOT be used on this watch (yet)

| Command / action | Why |
|---|---|
| `openwearota flash 78:02:B7:58:FF:9E <file>` or typing `YES` in the interactive flash flow | Would write `0x01` to `ffd1` (reboot into OTA) and attempt an unverified RealSil DFU — no backup exists |
| Any write to `ffd1`, `ffd8`, `fff2`, `6387`, `6487` | Realtek OTA/DFU control — can start an update |
| Writes to `33f1` / `34f1` | realme private protocol — unknown effects |
| Connecting anything to the 2 charging pins other than the stock charger | Unknown wiring |

### 10.4 Key UUIDs

| Role | UUID |
|---|---|
| Realtek OTA service (normal mode) | `0000d0ff-3c17-d293-8e48-14fe2e4da212` |
| Enter-OTA (write `0x01`) — **don't** | `0000ffd1-0000-1000-8000-00805f9b34fb` |
| Realtek DFU service | `00006287-3c17-d293-8e48-14fe2e4da212` |
| DFU data / control point | `00006387-…` / `00006487-3c17-d293-8e48-14fe2e4da212` |
| realme private protocol | `000055ff-…` (`33f1` w/r, `33f2` notify), `000056ff-…` (`34f1` w/r, `34f2` notify) |

---

## 11. Watch interaction log

Every action performed against the physical watch. **Changes to the watch so far: none** —
all interactions have been read-only (connect, service discovery, characteristic reads).
Stock firmware 1.3.0.017 is untouched.

| Date | Action | Entry point | Result | Changed watch? |
|---|---|---|---|---|
| 2026-10-28 | BLE scan | `openwearota scan` | Found `TechLife Watch S100` `78:02:B7:58:FF:9E` at −82 dBm, then −58 dBm when moved closer | No |
| 2026-10-28 | Chipset detection | `openwearota` → 1 → select watch → cancelled at firmware prompt | Connected; detected **RealSil (RTL876x)**; no model ID | No |
| 2026-10-28 | GATT service dump | ad-hoc bleak script (now `tools/s100_gatt_dump.py`) | Service table in §4; MTU 247 | No |
| 2026-10-28 | Realtek OTA info reads | ad-hoc bleak script (now `tools/s100_gatt_dump.py`) | Raw values in §4.1; battery 92 % | No |
| 2026-10-28 | Verification run of the dump tool | `python tools/s100_gatt_dump.py` | Identical values to the earlier reads; battery still 92 % | No |
| 2026-10-28 | Read UTE function bitmap + max length | bleak read of `33f1`, `34f1` | 20-byte bitmap, max length 244 (§7b.7) | No |
| 2026-10-28 | UTE version query (first writes ever sent) | write `A1` to `33f1` ×2 (33f2/34f2 notify enabled) | No reply — bind likely required | No (query command only; no state change observed) |
| 2026-10-28 12:41 | **Bind to our app** (user-approved) | write `33 02 00 51 10 00` to `33f1` | `33 04 03` → `33 04 02` (accepted, watch reset user data, disconnected) | **Yes — bound to account ID 0x00511000; stored activity/user data likely cleared.** Reversible by re-pairing realme Fit / factory reset |
| 2026-10-28 12:42 | Re-bind, time sync, version, dial config | `33 02 …` → `33 04 01`; `A3 …`; `A1`; `26 01` | Bound OK; clock set to PC time; version `RH288AV001319`; dial config read | Yes — clock set (harmless) |
| 2026-10-28 12:46 | Firmware check + download (no watch contact) | `tools/ute_fw_query.py RH288A V000000 …`; curl of the 2 S3 URLs | Stock FW V001319 + UI V000957_U0006 saved in `research/firmware/` | No |
| 2026-10-28 | Navigation notification test ×2 | `tools/s100.py nav …` (C5 packets, type 4) | Watch acked all packets (`c5 fd 04 5c`); **text shown on watch, no vibration** (user confirmed) → silent nav updates work | No (notification only) |
| 2026-10-28 | On-demand vibration test | `tools/s100.py vibrate 2` → `ab 00 00 00 01 02 07 01` | Watch replied `ab 00`; **user felt 2 buzzes** → on-demand vibration works | No |
| 2026-10-28 13:01 | Weather + music demo, stayed connected 90 s | `tools/s100.py demo 90` (A3, CB 01/02/03, CB FF on 34f1, 3A 01/06/FA on 34f1) | All acked (`cb 01/02/03`, `3a fa 55`). **User confirmed weather (29°, cloudy, Kochi) and song title shown.** Music page only shows the song while the PC stays connected. Watch → PC events received: `d1 07` play/pause, `d1 09` previous, `d1 0e` volume down | No (data push only) |
| 2026-10-28 | **Settings write: screen-off 60 s** | `tools/s100.py screen 60` → `a9 00 aa 00 41 3c 00 00 27 10 01 ff 00 1e 01 00 02 01 00` | Watch replied `a9` (accepted); user test pending | **Yes — profile set to defaults: 170 cm, 65 kg, goal 10000, age 30, male, raise-to-wake on, HR alarms off, English, °C; screen-off 60 s.** Reversible with another `screen` command |
| 2026-10-28 | Keep-awake / desk-clock probe (intervals 10/4/2 s) | `tools/s100.py deskclock …` (repeated `C5` notifications) | **Notification wakes screen from dark, no buzz; at 2 s interval screen stays continuously lit. At 4 s it goes dark between popups.** Pending check: whether notifications accumulate in the list | No (notifications only) |
| 2026-10-28 | Photos of watch menus / exterior by user | — | Stock features in §5 | No |
| — | Attempted execution-policy change by assistant | `Set-ExecutionPolicy` | Blocked by Claude Code permission system; user to run it | No (PC only) |

> Add a row for **every** future interaction, especially anything that writes (flash
> dumps, restores, firmware flashes). Note the exact command, file names/hashes, and outcome.

---

## 12. Repository changes made during this work

Changes to OpenWearOTA itself (PC-side code; nothing to do with the watch's contents). Uncommitted as of 2026-10-28.

| File | Change |
|---|---|
| `openwearota/cli.py` | Fixed OnMicro import (`.drivers.onmicro` → `.drivers.omnicro`) that crashed every flash |
| `openwearota/cli.py` | `cmd_flash_direct` now unpacks `(family, chip_id)` from `_detect_and_report` (flash subcommand never reached a driver) |
| `openwearota/cli.py` | `_list_prebuilts` looks in `prebuilts/<family>/` (CWD and repo root) instead of a name built from `FAMILY_NAMES` |
| `openwearota/cli.py` | `main()` reconfigures stdout/stderr to UTF-8 (Windows cp1252 crash on ⚠ ✓ ▓ ─ when output is redirected) |
| `openwearota/cli.py`, `openwearota/__init__.py` | `--version` reads `__version__`; version aligned to `0.0.1a2` (matches `pyproject.toml`) |
| `openwearota/detect.py` | RealSil SDK note no longer claims DFU is unimplemented; points to DOCUMENTATION.md §7 |
| `tools/s100_gatt_dump.py` | New read-only GATT/OTA-info dump tool for this watch |
| `docs/TechLife-S100.md`, `docs/img/techlife-s100/` | These notes + FCC photo crops |

Known remaining issues (not fixed): RealSil driver limitations in §6; PhyPlus is reached via
`shb_slb` / `SHB_OTA` (by design, see DOCUMENTATION.md §3).

---

## 12b. Chip, SDK and image layout (2026-10-28)

- **SoC is RTL8762D-family.** Stock app ROM UUID `1d6a69f1 2f38ea11 82a76737 0a3ca32e`
  (ic_type 0x09) equals `DEFINE_rom_uuid` in `sdks/RTL8762D_SDK_v1.1.0/inc/platform/rom_uuid.h`.
  The bee2/RTL8762C GCC SDK in `sdk/` targets a different ROM (`6d67def1…`, ic 0x05); the
  bootloader rejects its images (validate passes, stock keeps booting). **[confirmed]**
- `fff1` decoded with SDK `T_DFU_DEVICE_INFO`: ic 9, OTA ver 1, mode 0x07 (buffer check on,
  AES on, AES mode 1), max buffer 2048, img_indicator `0x00000FF0` → OTA header, FSBL, ROM patch,
  app present, all standalone single-bank; **no separate upperstack image (0x279a)**. **[confirmed]**
- Watch ROM patch version `0x580ef000` (rev 239); SDK v1.1.0 ships patch rev 440 + a separate
  upperstack image and every sample is built with `SUPPORT_ALONE_UPPERSTACK_IMG`.
- Stock app (img_base `0x0080E000`, 561 KB) contains the BLE upper stack itself
  (`UpperStackTask`, `btif_*`, "Upperstack Ver:" strings). **[confirmed]**
- Consequence: SDK v1.1.0 cannot build a drop-in app for this watch. Using it would require
  replacing the ROM patch and OTA header and adding an upperstack image over BLE (stock DFU
  likely rejects image ID 0x279a), with no wired recovery. Needed instead: an older RTL8762D SDK
  matching patch rev 239 with the upper stack linkable into the app.
- BLE DFU transfer itself is proven: `ValidateFW` returns `100301` after the driver fixes
  (image ID `0x2793` in opcodes 06/02/03, packet size dividing 1020, plaintext AES tail,
  LE32 version/offset parse).

## 13. Open questions

- [x] Exact SoC variant — RTL8762D family (ROM UUID match, §12b).
- [ ] Exact pad mapping of the 6-pad header (`TX RX L … P`).
- [ ] Does ROM MP mode respond? Which tool (rtltool vs Realtek MPTool) supports this variant?
- [ ] Can the internal + external flash be read back (read protection / secure boot)?
- [ ] Display controller IC and interface (SPI/QSPI/8080), touch controller IC, button GPIO.
- [ ] Decode `ffe0` / `fff1` OTA info (AES required? OTA spec version?).
- [ ] Longest stock Screen Timeout value (useful as zero-risk desk clock).

---

## Changelog

- **2026-10-28** — Initial notes: BLE scan/detect, GATT dump + OTA info values, stock feature
  survey from photos, FCC filing + internal photo analysis (SoC, flash, board ID, UART pads),
  ecosystem research, goals and safety gates.
- **2026-10-28** — Added entry points (§10), watch interaction log (§11), repo change list
  (§12); added `tools/s100_gatt_dump.py`.
- **2026-10-28** — Added host system details (§10.1). Repo re-initialised with fresh history and
  pushed to https://github.com/salmanulharis/smartwatch-customisation (upstream:
  HackSucks/OpenWearOTA; old `.git` backed up locally). `.gitignore` added; `dist/` and
  `*.egg-info/` build artifacts no longer tracked.
- **2026-10-28** — User cannot open the watch → BLE-only. Added §7b: realme Fit APK analysis
  (UTE/YC SDK + Realtek DFU SDK + RtkAes, custom-dial assets, UTE firmware/dial API endpoints,
  Gadgetbridge GloryFit lead). `reference-app/` and `research/` git-ignored. jadx run blocked
  by permissions — manual command documented.
- **2026-10-28** — User supplied jadx; APK decompiled. Added §7b.7: UTE firmware API (RSA body,
  appkey, A1-derived btname), Realtek silent OTA + UTE AES key location, full UTE command set,
  custom dial format, live bitmap read, A1 query (no reply → bind needed).
- **2026-10-28** — Bound watch to our app (user-approved; user data likely reset). Firmware ID
  `RH288AV001319`; dial config 240×280 / 1 MB. Added `tools/ute_fw_query.py`; running it was
  blocked by the permission system — left for the user to run.
- **2026-10-28** — On user request ran the firmware check: obtained **stock firmware V001319
  (matches watch) + UI resources V000957_U0006**, unencrypted Realtek packs; firmware header
  says **RTL8762C**.
- **2026-10-28** — Added `tools/s100.py`; verified on the watch: silent navigation text,
  on-demand vibration, time, 7-day weather + city, music title, watch music buttons → PC.
- **2026-10-28** — Screen-off via `A9` (60 s) ignored by watch. Route B (patch stock FW) started:
  firmware layout + SHA-256 header field documented; `A9` handler disassembled (screen byte unused);
  command dispatcher and candidate timers located. See "Route B" section.
- **2026-10-28** — Added §12b: SoC confirmed RTL8762D family via ROM UUID; image layout decoded
  from `fff1`; RTL8762D SDK v1.1.0 needs a separate upperstack image the watch doesn't have.
