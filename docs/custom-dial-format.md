# TechLife S100 — custom watch face ("online dial") format and upload protocol

Extracted from the realme Fit 1.2.9 APK (UTE/YC SDK), decompiled at
`research/jadx-techlife-1.2.9/sources`. Paths below are relative to
`.../sources/com/yc/pedometer/`. **[confirmed]** = read directly in code;
**[likely]** = strong inference; **[unverified]** = not checked against the watch.

Watch facts (from `26 01`, TechLife-S100.md §7b): 240×280, screen type 1, max dial size
1 MB (`0x00100000`), compatibility level **1** → no RLE compression.

---

## 1. Byte helpers used by the app

The app's naming is confusing; the effective byte orders are:

| Helper (onlinedial/Rgb.java) | Effective encoding |
|---|---|
| `bytes2HLExchange(intToBytes2L(x))` (L45–47, L226–236) | **u16 little-endian** |
| `bytes4HLExchange(intToBytes4L(x))` (L49–55, L214–224) | **u32 little-endian** |
| RGB565 pixels (`bitmapToRgb565Byte`, L188–200) | **big-endian** (high byte first) |

All header/table fields are little-endian; only pixel data is big-endian.

## 2. File layout

```
offset 0                      : 24-byte watch header            (record 0)
offset 24                     : N × 24-byte element records     (sorted by type ascending)
offset 24 + N*24              : 2 bytes 00 00                    (table terminator)
offset (N+1)*24 + 2           : image data blocks (absolute offsets stored in records)
```

- Table end: `stitchingArrays` appends 2 extra bytes after the last record
  (Rgb.java L419–420); first data offset = `(N+1)*24 + 2` (PicUtils.java L1275).
  The parser does the same (Rgb.java L330). **[confirmed]**
- Records are sorted by element type (`Collections.sort`, PicUtils.java L695–697;
  `compareTo` = type difference, PicTypeConfigInfo.java L88–90). Data blocks are laid out in
  the same order. **[confirmed]**
- Identical image blocks are stored once; later records point to the first copy's offset
  (`assignedAddress`, PicUtils.java L1258–1309; `removeDuplicate`, Rgb.java L639–648). **[confirmed]**

### 2.1 Watch header (24 bytes) — PicUtils.java L672–706, Rgb.java L294–304

| Off | Size | Field | Value written by app |
|---|---|---|---|
| 0 | 4 | snNo | `FF FF FF FF` (`SnNo()`, Rgb.java L250–256) |
| 4 | 4 | fileSize (u32 LE) | **total file length − 24** (PicUtils.java L702–703) |
| 8 | 4 | fileCrc (u32 LE) | CRC-32 (see 2.4), written last (L704–706) |
| 12 | 2 | pixelWidth (u16 LE) | screen width (240) |
| 14 | 2 | pixelHeight (u16 LE) | screen height (280) |
| 16 | 1 | screenType | `PicUtils.screenType` = **0** (field never changed, L47/L677) **[confirmed; meaning unverified]** |
| 17 | 1 | hasBg | 1 if a background element (type 17) exists, else 0 (L238–242, L678) |
| 18 | 1 | isWatchValid | `0xFF` (L679) |
| 19 | 5 | reserved | `FF FF FF FF FF` (`watchReserved()`, Rgb.java L242–248); byte 19 is overwritten with the compatibility level **only when level ≥ 2** (L707–709) |

### 2.2 Element record (24 bytes) — PicUtils.java L640–649, Rgb.java L310–319

| Off | Size | Field |
|---|---|---|
| 0 | 2 | type (u16 LE), see §3 |
| 2 | 2 | width of one frame (u16 LE) |
| 4 | 4 | data start offset, **absolute from file start** (u32 LE) |
| 8 | 2 | height of one frame (u16 LE) |
| 10 | 2 | x (u16 LE) |
| 12 | 2 | y (u16 LE) |
| 14 | 2 | animationTime (u16 LE) = 0 (L470) |
| 16 | 1 | frame count (`animaitonCnt`) = number of sprite images (L627) |
| 17 | 7 | reserved = 7 × `00` (`picReserved()`, Rgb.java L57–59) |

x/y are clamped so the element fits on screen (L460–463).

### 2.3 Image data (compatibility level 1)

- Each element's block = `count` frames concatenated, each `width × height × 2` bytes,
  **RGB565 big-endian**, row-major, no padding (block size = w·h·2·count, PicUtils.java L632).
  **[confirmed]**
- Frame order = sprite files sorted **numerically** by file name (`sortListString`,
  PicUtils.java L1790–1805). **[confirmed]**
- RGB888→565: `R>>3 <<11 | G>>2 <<5 | B>>3` (Rgb.java L76–78).
- **No alpha channel.** The app pre-blends each sprite onto the background at the element's
  (x, y). Semi-transparent pixels are mixed with the background pixel underneath; opaque pixels
  are kept; **fully transparent pixels keep their own RGB** (normally black → `0x0000`)
  (`antiAliasingDefault`, Rgb.java L814–856). Blended results darker than (16,8,16) are forced to
  (17,9,17), i.e. never `0x0000` (L839–843). ⇒ **`0x0000` is very likely the watch's transparency
  key**; use `0x0841`-ish for visible black. **[likely]**
- Background (type 17) = the 240×280 picture itself, same encoding (`antiAliasingBg`,
  Rgb.java L858–904).
- Level ≥ 2 uses per-row RLE (`addHeadBeForeCompress` + `picDataCompress`, Rgb.java L924–1012,
  applied to all types except digit-arc types 1–3, 35–70; PicUtils.java L549–566). **Not needed
  for this watch (level 1); not fully documented here.**

### 2.4 CRC

`uteDataCrc32` (Rgb.java L680–686): table-driven reflected CRC-32 (poly 0xEDB88320,
init 0xFFFFFFFF, final XOR) = **`zlib.crc32(file[24:])`**. It covers everything after the
24-byte header and is computed **after** fileSize is filled in; stored u32 LE at offset 8.
**[confirmed]** (table starts `0, 0x77073096, …` = standard CRC-32)

## 3. Element types

From `ConfigType.java` and the asset-folder mapping in `PicUtils.defaultAssetPicToData`
(PicUtils.java L196–387). Sprite contents checked visually from the APK assets
`assets/DialCustom/dial_2_square_240x240/*`.

| Type | Asset folder | Frames | Meaning / frame order |
|---|---|---|---|
| 7 | `hour2min` | 1 | colon between HH and MM |
| 8 | `battery` | **11** | battery level: firmware uses frame `ceil(battery%/10)` (0–10) with **no bounds check** (renderer `0x0085C422`, level `0x008439D2`); the app's 5-frame asset is wrong for this watch — fewer frames make the battery read garbage/black above 40 % **[confirmed on watch 2026-10-29]** |
| 9 | `iconbluetooth` | 2 | BT state (which frame = connected **[unverified]**) |
| 10 | `preview` | 1 | dial preview/thumbnail (see §5) |
| 14 | `day2month` | 1 | separator between month and day |
| 15 | `week` | 14 | 0–6 = 周日…周六, 7–13 = SUN MON TUE WED THU FRI SAT |
| 16 | `ampm` | 4 | 上午, 下午, AM, PM |
| 17 | `background` | 1 | full-screen background (sets header hasBg = 1) |
| 24 | `iconstep` | 1 | step icon |
| 32 | `stepproccess` | 11 | step-goal progress 0…10 |
| 35–37 | `heartnum1..3` | 14 | heart-rate digits |
| 38–42 | `stepnum1..5` | 14 | step-count digits |
| **57 / 58** | `timehour1/2` | 14 | **hour tens / hour units** |
| **59 / 60** | `timemin1/2` | 14 | **minute tens / minute units** |
| 63 / 64 | `timemonth1/2` | 14 | month tens / units |
| 65 / 66 | `timeday1/2` | 14 | day tens / units |
| 4, 5, 11, 13, 25 | `timehour`, `timemin`, `timemonth`, `timeday`, `stepnum` | — | older multi-digit variants (mapped, not in current assets) |

**14-frame digit sprite order** (all digit types): `-` `.` `/` `0 1 2 3 4 5 6 7 8 9` `:`
(i.e. frame = ASCII − 0x2D; digit *d* is frame *d* + 3). **[confirmed from assets]**

Other `ConfigType` IDs (analog hands 1–3, weather 20–22, kcal 29–31/43–46, distance 47–56,
year 27/28/67–70, seconds 6/61/62, etc.) exist but are not used by the custom-dial builder.

**Minimal clock:** 17 (background) + 57, 58, 59, 60 (digits) + 7 (colon).
Optional: 15 (weekday), 63/64 + 14 + 65/66 (date), 8 (battery), 16 (AM/PM), 9 (BT), 10 (preview).

## 4. Upload protocol

Characteristics (utils/UUIDUtils.java L10, L24): commands `26 xx` → **33f1**
(`writeChara`, sdk/WriteCommandToBLE.java L230); data `27 …` → **34f1**, write-without-response
(`writeCharaBle5`, L333). Replies `26 …` arrive on the legacy notify (33f2 **[likely]**) and are
parsed by `dealWithOnlineDial` (sdk/BluetoothLeService.java L6192–6247). Prerequisite: bound
session (`33 02 <id>` → `33 04 01`), as in `tools/s100.py`.

| Step | Host → watch | Watch → host | Ref |
|---|---|---|---|
| 1 | `26 01` (33f1) | `26 01 <dialId u32 BE> <w u16 BE> <h u16 BE> <screenType> <maxSize u32 BE> <compatLevel>`; dialId `FFFFFFFF` = no online dial shown | WCB L2052–2055; onlinedial/OnlineDialUtil.java L73–122 |
| 2 | `26 02` (33f1) | `26 02` = ready to receive | WCB L2057–2060; BLS L6201–6205 |
| 3 | data packets on 34f1 (below) | `26 03 04` after each 4096-byte boundary | WCB L2114–2175; BLS L6225–6232 |
| 4 | after the last packet wait **3000 ms**, then `26 03 00` (33f1) | result (below) | WCB L166, L2151–2154, L2062–2065, L2179–2187 |

**Data packet:** `27 <seq u16 BE> <payload>`; payload = next `maxLen − 3` bytes of the dial
file, where `maxLen` = value read from 34f1 (this watch: 244 → **241 bytes/packet**);
`seq` counts packets from 0; last packet carries the remainder (WCB L2120–2148, L2188–2197).
No per-packet or per-section CRC — only the file CRC in the header. **[confirmed]**

**Pacing (app behaviour):** after sending packet *i*, if `floor((i+1)·241 / 4096)` changed
(a 4 KB flash sector boundary was crossed) **wait for `26 03 04`** (app timeout 3 s, then it
continues anyway — onlinedial/OnlineDialTimeOut.java L15, L38–42); otherwise send the next packet
immediately, except every 10th packet waits 40 ms (`DELAY_SEND_ONLINE_DIAL_TIME`,
OnlineDialUtil.java L38). Slow mode uses 100 ms per packet after >2 resend requests
(L41; BLS L6239–6245).

**Final replies** to `26 03 00` (BLS L6209–6247; meanings from onlinedial/CustomDialActivity.java L101–133):

| Reply | Meaning |
|---|---|
| `26 03 00` | success |
| `26 03 01` | CRC check failed |
| `26 03 02` | dial data too large |
| `26 03 03 <seq u16 BE>` | resend starting at packet `seq` |
| `26 03 04` | 4 KB section written, send next (during transfer) |

**Activation:** no separate "select dial" command exists in this flow; the app treats
`26 03 00` as done. The watch is expected to switch to the uploaded dial by itself.
**[unverified]**

## 5. Preview element (type 10)

For custom dials the app always inserts/replaces a type-10 record before sending
(`compositePreviewToByte`, Rgb.java L728–741; PicUtils.java L1883–1889) using template record
`0a 00 f0 00 2e 16 00 00 f0 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00` (240×240 at 0,0,
1 frame), then recomputes the CRC. If a type-10 record already exists, its size is kept.
Whether the watch needs it, and the right size for a 240×280 screen, is **[unverified]**
(the app's 240×280 templates are downloaded at runtime, not in the APK).

## 6. Worked example — minimal digital clock (solid background)

Elements, sorted by type: 7 colon (16×60 @ 112,110), 17 background (240×280 @ 0,0),
57/58/59/60 digits (40×60, 14 frames, @ 32/72/128/168, 110).
N = 6 → table = 24 + 6×24 = 168, +2 terminator → first data offset **170**.
With a solid background all four digit blocks are identical → stored once.

| Block | Offset | Size |
|---|---|---|
| type 7 colon | 170 (0xAA) | 16·60·2·1 = 1 920 |
| type 17 background | 2 090 (0x82A) | 240·280·2 = 134 400 |
| type 57 digits (58/59/60 point here) | 136 490 (0x2152A) | 40·60·2·14 = 67 200 |
| **file end** | 203 690 | fileSize field = 203 666 |

```
Header:   FF FF FF FF | 92 1B 03 00 | <crc32(file[24:]) LE> | F0 00 | 18 01 | 00 | 01 | FF | FF FF FF FF FF
Rec 7:    07 00 | 10 00 | AA 00 00 00 | 3C 00 | 70 00 | 6E 00 | 00 00 | 01 | 00×7
Rec 17:   11 00 | F0 00 | 2A 08 00 00 | 18 01 | 00 00 | 00 00 | 00 00 | 01 | 00×7
Rec 57:   39 00 | 28 00 | 2A 15 02 00 | 3C 00 | 20 00 | 6E 00 | 00 00 | 0E | 00×7
Rec 58:   3A 00 | 28 00 | 2A 15 02 00 | 3C 00 | 48 00 | 6E 00 | 00 00 | 0E | 00×7
Rec 59:   3B 00 | 28 00 | 2A 15 02 00 | 3C 00 | 80 00 | 6E 00 | 00 00 | 0E | 00×7
Rec 60:   3C 00 | 28 00 | 2A 15 02 00 | 3C 00 | A8 00 | 6E 00 | 00 00 | 0E | 00×7
Term:     00 00
Data:     colon RGB565BE | background RGB565BE | 14 digit frames "-./0123456789:" RGB565BE
```

Upload: 203 690 bytes → 846 packets of 241 bytes (`27 00 00 …` … `27 03 4D …`),
49 waits for `26 03 04`, then 3 s pause and `26 03 00`.

## 6b. Upload size quirk (found on the watch 2026-10-29)

A valid 524 190-byte dial (size mod 4096 = 3998) failed every upload with `26 03 01`
("CRC check failed") although its CRC was correct; the same file with 200 trailing zero bytes
(size and CRC updated) uploaded fine. Files whose last 4 KB sector is within one 241-byte
packet of full trip the watch. `tools/s100_dial.py build` now pads such files. **[confirmed]**

## 7. Open gaps

1. Whether the watch requires a type-10 preview, and its size for 240×280 (§5).
2. Header screenType: the custom builder writes 0 although `26 01` reports 1 — likely fine
   (the app does it for every watch), unverified.
3. Which notify characteristic carries `26 …` replies (33f2 assumed).
4. Whether `0x0000` is truly rendered as transparent (only matters for non-full backgrounds).
5. Activation after upload (§4) and how to return to a stock dial (probably via the watch's
   dial menu).
6. RLE format for compatibility level ≥ 2 (not needed here).

## Firmware limits and the type-71 world-clock extension

- The record parser (app `0x83B2E6`, stock v1319) copies records until type 0 **or the first type
  above 71**, and at most 71 records. Anything after a type > 71 is silently dropped.
- The renderer is tighter: it fills a draw list of **34 sprites** per frame (`cmp r6,#0x21; bhi`
  at `0x85D3DC`; multi-character elements such as temperature use one slot per character).
  Elements past that are skipped, and since records are sorted by type, the highest types are
  lost first. Bake anything static (colons, separators, units) into the background.
- Type 71 is unused by stock. With firmware mod `b5_worldclock` (v1323+, see
  custom-firmware-plan.md B5) it renders a world-clock digit: 14-frame digit sprite like 57-60,
  reserved[0] = 0, reserved[1:3] = signed LE16 minute offset from the watch's local time,
  reserved[3] = digit position (0 hour tens, 1 hour units, 2 minute tens, 3 minute units).
  12 h mode follows the stock rule (hour > 12 → hour − 12). Used by `tools/dial_world.py`.

## Battery: exact percentage (type 33) and the charging flag

- Battery percent lives at settings `0x20BE84 + 0x109` (u8). Every battery display reads it: the
  charging screen (`BatteryChargingScreenUI`, `0x84973E`), the status bar (`StatusBarScreenUI`,
  `0x858976`), the face battery icon and the BLE `A2` reply (`A2 <percent>`, used by tools/s100_app.py).
- **Type 8** (icon) goes through `0x8439D2`: level = percent/10, +1 if there is a remainder and
  percent ≥ 5, capped at 10. While the flag byte at RAM `0x210236` is 1 (charging) the level drops
  by one on odd seconds, so the icon blinks while charging. It is coarse by design, not wrong.
- **Type 33 (`BATNUM`)** draws the exact percent as digits (`0x85CA62` → `0x84404A`: itoa of
  `+0x109`, 3 chars, leading spaces stripped). Same sprite base (frame 3) and drawer (`0x8435BE`)
  as the temperature (type 21), so: 14-frame digit sprite, number centred in a 3-character field,
  char k at `x + ((3 − n)·w >> 1) + k·w`. Uses one draw slot per digit. No "%" is drawn (r2 = 0);
  bake it into the background. Static analysis only, not yet shown on the watch.
- Type 34 (`BATPERCENT`) branches into the battery-icon path (`0x85C41C`); purpose not traced.
