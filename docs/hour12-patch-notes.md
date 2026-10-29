# TechLife S100 — 12-hour clock on custom dials (stock V001319)

**Result: no firmware patch needed.** The stock firmware already supports 12-hour time for
dial elements; it is switched by the UTE command **`A0 <unit> <hourFormat>`** with
`hourFormat = 2` → 12-hour (`1` → 24-hour). Send **`A0 01 02`** (metric + 12 h) after binding.
Confidence: **high** (firmware disassembly + app builder agree); not yet tested on the watch.

Image analysed: `research/firmware/RH288A_V001319_fw_1660354713_5619.bin`, mapped at
`0x0080E000` (file offset = address − 0x0080E000 + 0x200). Disassembled with Capstone (Thumb-2).

## 1. Settings/time struct

`0x0020BE84` (same literal as the screen-timeout code: `0x0085FB0A ldr r1,[pc,#0x3e4]` →
literal `0x0085FEF0` = `0x0020BE84`; `+0xFA` = screen timeout).

| Field | Meaning |
|---|---|
| `+0x66` (`0x0020BEEA`) | **12-hour flag** (1 = 12 h) |
| `+0x6B` | unit flag (1 = imperial) **[likely]** |
| `+0x92` u16 | year |
| `+0x94` / `+0x95` | month / day |
| `+0x96` | hour 0–23 |
| `+0x97` / `+0x98` | minute / second |

## 2. Who sets the flag — command `0xA0`

Dispatcher `0x00838588`: `cmp r0,#0xa0 / beq 0x838656` (also opcode `0x01`) →
`bl 0x008366C4`:

```
008366c4  push.w {r4-r8,lr}; mov r8,r1; mov r6,r0      ; r6 = packet, r1 = length
008366cc  cmp r1,#3 / blo exit
008366d0  ldrb r0,[r6,#1]; movs r7,#0; ldr r4,=0x20BE84; movs r5,#1
008366d8  cmp r0,#2 / beq → strb r5,[r4,#0x6b]   (else strb r7,[r4,#0x6b])
008366e0  ldrb r0,[r6,#2]
008366e2  cmp r0,#2 / beq 0x83670e
008366e6  strb.w r7,[r4,#0x66]                    ; byte2 != 2 → 24 h
0083670e  strb.w r5,[r4,#0x66]                    ; byte2 == 2 → 12 h
008366fa  … b 0x8364a4                             ; echo/ack
```

App side: `WriteCommandToBLE.sendUnitToBLE` (sdk/WriteCommandToBLE.java L989–1007):
`{0xA0, metric ? 1 : 2, twentyHourSystem ? 1 : 2}`.

## 3. Dial renderer — hour digits

Element-type switch `0x0085D290` (`ldrh r0,[r4,#0x34c]`; cases 0x39…0x46). Hour digits are
precomputed into a 2-byte buffer at **`0x00214B8C`** (literal `0x00214BA4` − 0x18):

```
0085d22a  ldr  r1,=0x20BE84
0085d22c  ldrb r0,[r1,#0x96]        ; hour
0085d230  cmp  r0,#12 / bls plain   ; hour <= 12 → unchanged
0085d234  ldrb r2,[r1,#0x66]        ; 12-hour flag
0085d238  cbz  r2, plain
0085d23c  subs r0,#12               ; 13..23 → 1..11
0085d23e  … tens → [0x214B8C], units → [0x214B8D]
```

Cases: `0x39` (57) frame = `[0x214B8C] + 3`; `0x3A` (58) frame = `[0x214B8D] % 10 + 3`;
`0x3B/0x3C` minutes from `+0x97`; `0x3D/0x3E` seconds `+0x98`; `0x3F/0x40` month `+0x94`;
`0x41/0x42` day `+0x95`; `0x43–0x46` year `+0x92`. Digit frame = value + 3 (matches the
`-./0123456789:` sprite order).

Quirks in 12-hour mode: hour **0 (midnight) shows "00"**, 12 shows "12", 1–9 show a leading
"0" (e.g. `02:30`). Cosmetic only.

## 4. AM/PM element (type 16)

`0x0085C64A`:

```
0085c64a  ldr  r0,=0x20BE84; ldrb r0,[r0,#0x66]; cmp r0,#0; beq skip   ; hidden in 24 h mode
0085c654  ldr  r0,=lang_ptr; ldr r0,[r0]; ldrb r0,[r0,#0x31]; cmp r0,#1 ; 1 = Chinese
0085c65e  ldrb r0,[sp,#0x50]                                             ; isPM
          Chinese:  frame 0 (上午) / 1 (下午)
          other:    frame 2 (AM)   / 3 (PM)
```

So with English UI and the flag set, frames 2/3 = AM/PM as the custom dial expects.
Weekday (type 15) uses frame + 7 for non-Chinese language (`0x0085C62C…0x0085C640`).

## 5. Optional cosmetic patch (not needed)

Midnight "00" → "12" and blank leading zero would need extra instructions in the
`0x0085D22A` block (no spare bytes in place); would require a code cave. Not proposed.

## 6. Weather elements (types 20, 21, 22)

App names (onlinedial/ConfigType.java L65–67): **20 `CONFIG_WEATHERPIC_TYPE`** (icon),
**21 `CONFIG_WEATHERNUM_TYPE`** (temperature number), **22 `CONFIG_WEATHER_CPIC_TYPE`**
(°C/°F symbol). All three are handled by the stock renderer: low-type compare chain
`0x0085C0C8…` (`cmp r0,#0x14/#0x15/#0x16` at `0x0085C104/108/10C`) → stubs `0x0085C206/208/20A`.

**Data source — `CB 01` handler `0x00837680`** (settings struct `0x0020BE84`, packet = `r0`):

```
00837680  ldrh r1,[r0,#2]; rev16      ; (byte2 << 8) | byte3
00837684  strh r1,[r2,#0x12c]         ; +0x12C u16: high byte = condition code, low = byte3 (00)
008376ae  ldrb r1,[r0,#4] → +0x13E    ; current temperature (sign-magnitude, 0x80 = negative)
008376b4  ldrb r1,[r0,#5] → +0x146    ; max
008376ba  ldrb r1,[r0,#6] → +0x13F    ; min
```

(`CB 01 cond 00 tCur tMax tMin …`, matching TechLife-S100.md §7b.)

**Type 20 — weather icon** (`0x0085C760`):
`ldr r0,=0x20BE84; ldrh r0,[r0,#0x12c]; lsrs r1,r0,#8; b common` → **frame = condition code
directly** (no clamp seen). Codes per app/docs: 1 sunny … 12 wind; 0 = no data. ⇒ provide
**≥ 13 frames, frame *n* = condition code *n*** (frame 0 = "no data/unknown").
Confidence: high for the index; the exact meaning of codes > 12 is unknown (keep extra frames
blank-safe).

**Type 21 — current temperature** (`0x0085C76A`): loads the element's **14 digit frames**
(loop `cmp r8,#0xe`, same `- . / 0–9 :` order as all digit types) and calls `0x008449FC` →
`0x008448BE` with tCur (`+0x13E`) and the condition halfword (`+0x12C`):
- condition halfword = 0 → draws `--` (no weather received yet);
- tCur bit 7 set → negative (sign-magnitude), drawn with a leading `-` frame;
- if `+0x14D` ≠ 0 the value is converted to °F (`×9/5 + 32`, VFP at `0x0084490A`);
- formatted into a **3-character field** (itoa `0x008434FE`), drawn by `0x008435BE`, centred
  around the element x (blank positions skipped). No degree sign is drawn — that is type 22.
⇒ **14 frames, `- . / 0 1 2 3 4 5 6 7 8 9 :`**, frame size = one character; the field is
up to 3 characters wide, so leave ~3 × width of space.

**Exact placement (traced):** caller `0x0085C7CA` passes record x, y, w (frame width,
`+0x34E`), h. `0x008448BE` formats, then calls the string drawer `0x008435BE` with n = 3; its
own centring block (`0x008449AC`) is skipped because the gating stack argument is 0.
- itoa `0x008434FE(v, buf, 3)`: right-aligned, **space-padded**, leading zeros suppressed
  (5 → `"  5"`, 29 → `" 29"`, 105 → `"105"`). Negatives patched in `0x008448BE`:
  −3 → `" -3"`, −12 → `"-12"`; no data → `" --"`.
- `0x008435BE`: b = number of leading spaces (`0x008434E8`), the spaces are stripped,
  start x0 = **record_x + (b·w) >> 1** (`0x0084363E`), advance = **w** per char, y = record_y,
  no extra spacing (`obj+0 = x0`, `obj+2 = y`, `obj+8 = w`, `obj+0xA = h`).

**Formula:** for a visible string of n chars (n = 3 − b), char k (0-based) is drawn at
`x = record_x + ((3 − n)·w >> 1) + k·w`, `y = record_y` — i.e. the string is **centred in a
3·w field starting at record_x** (centre = record_x + 1.5·w), using the frame width.

| Value | String | Char x positions |
|---|---|---|
| 5 | `5` | x + w |
| 29 | `29` | x + w/2, x + 3w/2 |
| −3 | `-3` | x + w/2 (`-`), x + 3w/2 |
| 105 | `105` | x, x + w, x + 2w |

So to centre the reading on screen column C, set **record_x = C − 1.5·w** (not C − w/2).

**Type 22 — unit symbol** (`0x0085C80E`): `ldrb r0,[0x20BE84+0x14D]` → frame index.
`+0x14D` is set by the `A9` settings handler (`0x00836968`): packet byte 17 = 1 → 0 (°C),
= 2 → 1 (°F). ⇒ **2 frames: 0 = °C, 1 = °F**. Confidence: medium-high (value written for
byte17 = 1 is `r2`, assumed 0 from context).

## 7. Battery element (type 8)

Dispatch: compare chain `0x0085C0DC cmp r0,#8` → stub `0x0085C1D6` → case **`0x0085C422`**:

```
0085c422  ldrb r0,[r4,#0x35c]        ; record frame count
0085c426  cmp r0,#10 / bne plain
0085c42a  ldr r0,=flag; ldrb r0,[r0]; cmp r0,#1 / beq +5   ; 10-frame variant: frame = level + 5
0085c432  ldrb r1,[sp,#0x3c]         ; plain: frame = level
0085c436  cmp sb,#2 / bhs rle_path / b 0x85cf4c→0x85d072 → 0x85c6ba
0085c6ba  muls r0,r1,r0 ; data = [r4+0x350] + frame*w*h*2   ; NO bounds check
```

**Level computation** — `0x008439D2` (called from the renderer prologue `0x0085BE6C` with
`&[sp+0x3c]`), battery % at settings struct `0x0020BE84 + 0x109`:

```
level = pct / 10
if pct % 10 and (pct >= 5 or charging): level += 1     ; i.e. ceil(pct/10)
if level > 10: level = 10
if charging and (seconds & 1) == 0 and level: level -= 1  ; blink while charging
```

⇒ **frame index 0…10 → the element needs 11 frames** (0 = empty/≤0 %, 10 = full, one step
per 10 %). Charging needs no extra frames (it blinks between two levels). The 10-frame "+5"
branch is a special layout for a different asset style; don't use it.

`sb` = dial header byte 19 (compat level; ≥ 3 → 0). Our header has `0xFF` → `sb = 0` →
uncompressed path, same as every element that does render, so that is not the problem.

**Our file** `research/dials/nothing.bin`: type-8 record = **86×20 @ (132,230), anim 0,
5 frames**, data offset 1982 (record otherwise valid). With 5 frames any battery > 40 %
selects frame 5…10, which reads **past the battery block** into the next image data
(mostly near-black) — so the battery appears missing. The preview thumbnail is a separate
static image, which is why it shows there.

**Fix (confidence: high):** emit **11 frames** for type 8, frame *i* = battery at *i*×10 %
(0 = empty … 10 = full), same w/h/x/y. No other condition, type, or field is required.
(`tools/s100_dial.py` `battery_frames()` had the same 5-frame bug.)

## 8. Analog hands (types 1, 2, 3)

Names (onlinedial/ConfigType.java L24, L43, L55): **1 `CONFIG_SHIZHEN_TYPE` = hour hand**,
**2 `CONFIG_FENZHEN_TYPE` = minute hand**, **3 `CONFIG_MIAOZHEN_TYPE` = second hand**.
The app's custom-dial builder never creates them (only referenced by the RLE-exclusion range,
PicUtils.java L554); no `DialCustom` APK asset uses them — they come from downloaded online dials.

**Separate pass after the element loop** — `0x0085D3F6`…`0x0085D8xx` (records scanned at
`0x0085D4A6`: `cmp r2,#1/#2/#3`). **One image per hand, rotated at runtime** (float math,
sin/cos helpers `0x00874C5C` / `0x00874CD4`) — not pre-rendered frames.

Angles (radians, constant −π at literal `0x0085D7EC`; 360.0 at `0x0085D7F0`, 1800.0 at
`0x0085D7F4`), time from settings struct `0x0020BE84` (`+0x96` h, `+0x97` m, `+0x98` s):

```
hour   = (h % 12)·π/6 + m·π/360      ; includes minutes   (0x0085D3FA–0x0085D444)
minute = m·π/30 + s·π/1800           ; includes seconds
second = s·π/30
```
(sign negative in screen coordinates = clockwise; 0 = 12 o'clock.)

Per-hand parameters come from the record's **reserved bytes** (record base `+0x34C`):

```
0085d4c8  ldrb r2,[r0,#0x361] → [sp+0]    ; record byte 21
0085d4d0  ldrb r2,[r0,#0x362] → [sp+4]    ; record byte 22
0085d4d8  ldrb r2,[r0,#0x363] → [sp+2]    ; record byte 23
0085d4e0  if dial width (hdr, +0x340) == record width:  pivot = (w/2, h/2)
          else:                                         pivot = record (x, y)
```

Bounding-box code (`0x0085D7B6`…) uses `−byte21`, `byte22 − byte21` and `byte23 / 2`, so
**[medium]**: byte 21 = distance from the image's top (tip) down to the pivot, byte 22 = image
height, byte 23 = image width (pivot horizontally at width/2). All three are u8 → hand images
≤ 255 px. The draw objects for minute/second are given the *hour hand's* pivot
(`0x0085D68C`, `0x0085D6CA`), so **use the same x/y for all three hands**.

Transparency: hands are composited over the already-drawn face; the rotated blit is expected
to skip the key colour `0x0000` **[low–medium, not traced]** → paint everything outside the
hand pure `0x0000` (unlike the other elements, where we avoid `0x0000`). No centre-cap type
exists; draw a cap in the background (it will sit under the hands).

**Build recipe — mini analog clock in a ~54×66 box at (40,212):** pivot (67,245).

| Field | Hour (type 1) | Minute (type 2) | Second (type 3, optional) |
|---|---|---|---|
| record w × h (u16) | 4 × 20 | 4 × 28 | 2 × 30 |
| x, y (u16) | 67, 245 | 67, 245 | 67, 245 |
| anim (u16) / frames (u8) | 0 / 1 | 0 / 1 | 0 / 1 |
| bytes 17–20 | 00 | 00 | 00 |
| byte 21 (tip→pivot) | 17 | 25 | 25 |
| byte 22 (height) | 20 | 28 | 30 |
| byte 23 (width) | 4 | 4 | 2 |

Image: one frame, hand drawn **vertical pointing up**, pivot pixel at (w/2, byte21), RGB565 BE,
background pixels `0x0000`. Background (type 17) carries the dial ring/ticks and centre dot.
Second hand redraws every second (power cost) — omit it for the desk clock.
Confidence: rotation + angle formulas **high**; pivot = record x/y **high**; byte 21/22/23
meaning **medium**; `0x0000` transparency **low–medium** — verify with one test upload
(e.g. make the hand image slightly longer than the box and check alignment).

### Analog hands — multiple sets

1. **Only one set exists; the last record of each type wins.** The scan loop
   (`0x0085D49E`…`0x0085D5D4`, all records up to the count at `+0xA3B`) writes every type-1
   record into the *same* slots: image pointer → draw object `+0x24`, params → `[sp+0/2/4]`,
   pivot → `[sp+0x14/0x16]` (`0x0085D4B8`–`0x0085D4FC`). Type 2 → `+0x50`, `[sp+6/8/0xA]`,
   `[sp+0x18/0x1A]`; type 3 → `+0x94`, `[sp+0xC/0xE/0x10]`, `[sp+0x1C/0x1E]`. Later records
   overwrite earlier ones, and only one draw object per hand type is filled (`0x0085D63A`…).
2. **Every hand is drawn about the hour hand's pivot.** The pivot fields of all three draw
   objects (`+0x2C/+0x2E`, `+0x70/+0x72` at `0x0085D68C`, `+0xB4/+0xB6` at `0x0085D6CA`) are
   stored from the hour pivot `[sp+0x14/0x16]`. The per-hand pivots are only used by the
   bounding-box/dirty-rect loop (`0x0085D78A`…, `sb = sp+0x14`, indexed per hand), so a
   minute-hand record with a different x/y gets the wrong dirty rectangle (smearing or
   clipping) as well as the wrong pivot.
3. Rotation centre in the image = (byte23 / 2, byte21). The bounding box is the rectangle
   x ∈ [−byte23/2, +byte23/2], y ∈ [−byte21, byte22 − byte21], rotated. So a square image with
   byte21 = size//2, byte22 = byte23 = size **does** rotate about its centre; there is no
   narrow-hand requirement apart from u8 sizes (≤ 255, and byte23 + 4 is stored in a byte at
   `+0x1C`). Keep byte22/23 equal to record h/w; the blit uses the record w/h for the pixel
   stride. **The runtime always adds the current local angle**, so hand art must point to
   12 o'clock. Art that is "pre-rotated to the current time" ends up rotated twice.
   Pre-rotation is only valid as a **fixed offset**.
   Pivot rule (`0x0085D4E0`): if record w equals dial width (240), pivot = (w/2, h/2), else
   pivot = record (x, y).
4. **Feasible designs.**
   - (a) Several world clocks: **not possible** with stock firmware. There is one hand set,
     every time element reads the same local time, and no element takes an offset. It would
     need a firmware patch (per-record offset plus a draw-object array).
   - (b) **One extra-timezone analog clock + local digital time: possible.**
     - Use exactly one type-1, one type-2 (and optionally one type-3) record, all with the
       same x/y pivot.
     - Pre-rotate the hand art by the zone offset Δ = hours + minutes:
       hour image rotated by Δh·30° + Δm·0.5°, minute image by Δm·6°.
     - The runtime then adds local time, so the hands show remote time.
     - Square images, with byte21 = size//2 and byte22 = byte23 = size.
     - Local time digital via types 57–60 + 16. Label the zone in the background.
     - Rebuild and re-upload when DST changes.
   Confidence: slot/pivot behaviour **high** (direct from the stores); rotation centre
   **medium–high**; fixed-offset trick **medium**, verify once on the watch.

## 9. Whole-value time elements

**None of the stock time elements uses the whole value as a frame index.** All are digit
strings or single digits drawn from a **14-frame digit sprite** (`- . / 0–9 :`):

| Type | Handler | What it draws |
|---|---|---|
| 4 timehour | `0x0085C19A` → `0x00843680` mode 1 | 2-char zero-padded `"HH"` (12 h flag honoured, same quirk: 0 → `00`, 12 → `12`), left-aligned at record x, advance w (`0x008435BE` mode 2) |
| 5 timemin | `0x0085C29E` → `0x00843680` mode 2 | `"MM"`, same placement |
| 11 timemonth / 13 timeday | `0x0085C49C` / `0x0085C582` → `0x00843680` modes 3/4 | `"MM"` / `"DD"` |
| 25 stepnum | `0x0085C848` → `0x00843FD8` | step-count string |
| 6 / 61 / 62 seconds | `0x0085C32A`; `0x0085D316`/`0x0085D362` | single digits `s/10 + 3`, `s%10 + 3` |
| 57–60 | `0x0085D2CE…` | single digits (tens/units) |

(`0x00843680` builds the string from `+0x96/+0x97` or `+0x94/+0x95` and calls `0x008435BE`
with frame base `data + 6·w·h` = frame `'0'`.) ⇒ a word clock with **one image per hour and per
minute value is not possible with stock elements.** Without patching, the closest is
words-per-digit: type 59 frames as tens words (oh/ten/twenty/…/fifty, 6 used) + type 60 as
units words (one…nine); hours 57/58 can't give eleven/twelve cleanly.

**Minimal firmware patch to make 57 and 59 whole-value** (verified with Capstone; at switch
entry `r1` = `0x0020BE84`, as the minute cases already assume):

| Addr (file off = addr − 0x0080E000 + 0x200) | Original | New | Effect |
|---|---|---|---|
| `0x0085D2CE` | `07 4B` `ldr r3,[pc,#0x1c]` | `0B 46` `mov r3,r1` | |
| `0x0085D2D4` | `18 3B` `subs r3,#0x18` | `96 33` `adds r3,#0x96` | type 57 frame = **raw hour 0–23 + 3** |
| `0x0085D304` | `09 E0` `b 0x85d31a` | `0C E0` `b 0x85d320` | type 59 frame = **minute 0–59 + 3** |

Then type 57 needs **27 frames** (0–2 unused, frame h + 3 for hour h; draw 12-hour words in
the art, e.g. frames for 0 and 12 both "twelve") and type 59 needs **63 frames** (m + 3).
Don't place 58/60 (they still show units digits). AM/PM via type 16 still works.
Caveats: this changes 57/59 for **every** dial (stock dials using them would break); size —
63 + 27 frames must fit 1 MB (e.g. 140×36 px per frame ≈ 10 KB → ~900 KB total; tight, use
smaller word images). Confidence: element analysis **high**; patch correctness **high**
(4 bytes, register use verified), untested on the watch. Re-hash + version bump as usual.

## 10. How to use

```
python tools/s100.py …   # bind first (S100 class does it), then write A0 01 02 on 33f1
```
(`A0 01 02` = metric units + 12-hour.) Reply is an echo via `0x008364A4`.
