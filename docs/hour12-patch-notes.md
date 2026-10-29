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

## 8. How to use

```
python tools/s100.py …   # bind first (S100 class does it), then write A0 01 02 on 33f1
```
(`A0 01 02` = metric units + 12-hour.) Reply is an echo via `0x008364A4`.
