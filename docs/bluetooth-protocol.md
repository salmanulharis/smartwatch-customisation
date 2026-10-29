# Bluetooth Protocol Reference — realme TechLife Watch S100

Last updated: 2026-10-28. This documents the **UTE BLE protocol** as used by the stock
firmware, confirmed by decompiling realme Fit 1.2.9 and testing against the physical watch.

For the Realtek DFU protocol, see `docs/firmware-feasibility.md` and `DOCUMENTATION.md` §7.

---

## 1. Transport

| GATT service | Characteristics | Purpose |
|-------------|----------------|---------|
| `000055ff-…` | `33f1` (write+read), `33f2` (notify) | UTE command channel (legacy, ≤20 bytes) |
| `000056ff-…` | `34f1` (write-no-rsp + read), `34f2` (notify) | UTE big-data channel (up to `max_len` bytes) |

**34f1 is write-without-response only.** Using write-with-response will fail.

MTU negotiated: 247. `max_len` from reading 34f1: 244 bytes.

## 2. Connection sequence

1. Enable CCCD on `33f2` and `34f2` (notifications)
2. Read `33f1` → 20-byte function bitmap
3. Read `34f1` → 2-byte max length (big-endian)
4. **Bind:** write `33 02 <account_id u32 BE>` to `33f1`
   - Reply `33 04 01` = bound OK
   - Reply `33 04 03` = new account, confirm on watch → `33 04 02` accepted (resets user data)
   - Reply `33 04 04` = confirm on watch
   - Reply `33 04 05` = cancelled
5. Sync time: `A3 yyHi yyLo MM dd HH mm ss`
6. Query version: `A1` → reply `A1` + ASCII version string

The watch ignores all commands until bound. Bind is required on every connection.

Our account ID: `0x00511000`. Our version reply: `RH288AV001319`.

## 3. Confirmed commands

### 3.1 Notifications (`C5` — on 33f1)

Push text to the watch screen. No vibration unless explicitly requested via `AB`.

```
Packet:  C5 <seq> <payload_chunk_18B>
Final:   C5 FD
```

Payload structure: `<app_type u8> <body_len u8> <body UTF-16BE>`

| App type | Meaning |
|----------|---------|
| 0 | Call |
| 1 | QQ |
| 2 | WeChat |
| 3 | SMS |
| 4 | Other (generic — used for nav/desk-clock) |
| 5 | Facebook |
| 6 | Twitter |
| 7 | WhatsApp |
| 24 | Telegram |

Watch acks: `C5 <seq>` (ok), `C5 FF` (resend), `C5 FD` (done).

Max body: 160 bytes (function list flag). Text encoding: UTF-16BE, BMP only.

**Verified:** text shown on watch, no vibration, screen wakes from sleep.

### 3.2 Vibration (`AB` — on 33f1)

```
AB 00 00 00 01 <count> 07 01
```

Watch replies `AB 00`. **Verified:** felt on device.

### 3.3 Time sync (`A3` — on 33f1)

```
A3 <year_hi> <year_lo> <month> <day> <hour> <minute> <second>
```

Watch replies `A3` + echo. **Verified.**

### 3.4 Weather (`CB` — 33f1 for data pages, 34f1 for city name)

Three data pages, then optional city name:

```
Page 1: CB 01 <condition> 00 <current_temp> <max_temp> <min_temp> <pm25_hi> <pm25_lo> <aqi_hi> <aqi_lo> + 8 zero bytes
Page 2: CB 02 + 4×(condition 00 max min) for days 2–5
Page 3: CB 03 + 2×(condition 00 max min) for days 6–7
City:   CB FF <name_len> <name_utf8>   (on 34f1)
```

Temperature: unsigned magnitude; set bit 7 (0x80) for negative.

| Condition code | Meaning |
|---------------|---------|
| 1 | Sunny |
| 2 | Cloudy |
| 3 | Overcast |
| 4 | Shower |
| 5 | Thunder |
| 6 | Sleet |
| 7 | Light rain |
| 8 | Heavy rain |
| 9 | Snow |
| 10 | Dust |
| 11 | Fog/haze |
| 12 | Wind |

**Verified:** all 7 days + city shown on watch.

### 3.5 Music info (`3A` — on 34f1)

```
State:  3A 01 <state> + FF×10 padding     (1=playing, 2=paused)
Title:  3A 06 <len> <title_utf8>
Commit: 3A FA
```

Watch acks `3A FA 55`. **Verified:** title shown while BLE connected.

### 3.6 Watch → phone events (`D1` — notifications on 33f2)

| Byte 1 | Meaning |
|--------|---------|
| 0x07 | Play/pause |
| 0x08 | Next track |
| 0x09 | Previous track |
| 0x0D | Volume up |
| 0x0E | Volume down |
| 0x0A | Find phone |
| 0x12 | Mute |

**Verified:** play/pause, previous, volume down observed. Next and volume up not yet seen
(may require the music screen to be in a specific state).

### 3.7 Settings (`A9` — on 33f1)

19-byte packet setting profile fields:

```
A9 00 <height_cm> 00 <weight_kg> <screen_off_s> <step_goal 4B BE>
   <raise_to_wake> FF 00 <age> <sex> 00 <language> <temp_unit> 00
```

**Important:** byte 5 (screen-off seconds) is **accepted but ignored** by the firmware. The
A9 handler's disassembled code stores height, weight, step goal, age, sex, and other
fields — but does not read byte 5 or byte 10 (raise-to-wake). Screen timeout is set only
from the watch's own settings menu.

### 3.8 Dial config query (`26` — on 33f1)

```
Query:  26 01
Reply:  26 01 <dial_id 4B> <width 2B BE> <height 2B BE> <screen_type> 00
        <max_size 4B BE> 00 <compat_level> + padding
```

Our watch: dial `FFFFFFFF` (none custom), **240×280**, max 1 MB, compat 1 (no RLE).

### 3.9 Version query (`A1` — on 33f1)

```
Query:  A1
Reply:  A1 <ascii_version_string>
```

Our watch: `RH288AV001319`.

## 4. Commands NOT found in the protocol

| Feature | Status |
|---------|--------|
| Brightness control | No command found |
| Always-on display toggle | No command found |
| Screen timeout override | A9 byte 5 is ignored |
| Navigation arrows/icons | No dedicated command; text-only via notifications |
| Map rendering | Not supported |
| Custom watch face push | `26 02` / `27` documented but not yet tested |

## 5. Implementation

All verified commands are implemented in [tools/s100.py](../tools/s100.py).

The `S100` class provides async methods matching each command above. Usage:

```python
async with S100() as w:
    await w.sync_time()
    await w.notify("Hello")
    await w.weather(days, current=29, city="Kochi")
    await w.music("Song title")
    await w.vibrate(2)
    await w.deskclock(120, interval=2)
    await w.car_demo(60)
```
