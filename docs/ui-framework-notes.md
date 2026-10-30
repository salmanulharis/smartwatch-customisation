# TechLife S100: stock UI framework map (app V001319)

This is an offline reverse-engineering map of the GUI in
`research/firmware/RH288A_V001319_fw_1660354713_5619.bin`, written 2026-10-29. Its purpose is to let
us **move or resize elements** on stock screens and **add new screens** by binary patching
(Track B4/B5, see [custom-firmware-plan.md](custom-firmware-plan.md)).

How the facts were established: Capstone 5 (Thumb-2, M-class) linear sweep of the whole image,
literal-pool and `bl` cross-references, and a small constant-propagation tracker that resolves
the register and stack arguments at each draw call. Image indices come from `research/ui/index.json`
(flash = `0xACB400 + payload offset`). Nothing was flashed or sent over BLE.

Confidence tags: **[high]** means read directly from the code. **[medium]** means a consistent
interpretation of the code that has not been tested on the watch. **[low]** means a guess.

Address conventions:
- File offset = address − `0x0080DE00`, which is the same as address − `0x0080E000` + `0x200`.
- `0x00200000`–`0x00224000` is data RAM (144 KB).
- `0x00ACB400` and above is the UI pack in external flash.

---

## 0. ⚠ Startup memory map, and a problem with the B5 code cave

Startup routine at `0x00829A64` **[high]**:

```
memcpy(0x00208400, 0x00890898, 0x3914)   ; RAM code + early data   (flash 0x890898–0x8941AC)
memcpy(0x0020BD14, 0x008941AC, 0x3324)   ; .data (RW init image)   (flash 0x8941AC–0x8974D0 = end of image)
memset(0x0020F038, 0, 0xA4E4)            ; .bss → ends 0x0021951C
(second, empty region at 0x00224000, size 0)  ; initial MSP 0x00203400
```

So **RAM = flash − `0x00688498`** for every flash address in `0x890898`–`0x8974D0`.
The GUI core (send-update, band renderer, image blitters) runs from RAM `0x2084xx`–`0x20Bxxx`.

**The B5 world-clock handler at `0x0089491C` is inside the `.data` init image.** The bytes there
are not padding. They are the zero initial values of RAM `0x0020C484`–`0x0020C506`, which is
`0x0020C154 + 0x330 … +0x3B2` in the big app-state struct. The code is still reachable through
XIP flash, so the branch target works. But at every boot those 130 bytes are copied into live
variables, which then start non-zero. Fields seen in use in that range include:
- `+0x330`: byte counter, read-modify-write at `0x008517CA`
- `+0x334`: word read at `0x00837D2C`
- `+0x338`: word written at `0x00837E92`
- `+0x33C`: word compared with `+0xA40` at `0x0083B324`
- `+0x346`: byte

**Recommendation: do not flash `b5_worldclock_v1323` as built.** Move the handler to a real cave
(see §8) and re-test in the emulator. **[high]** for the mechanism. The effect on the watch is unknown.

---

## 1. Screen (menu) framework

This is the Realtek "wristband" GUI (`rtl_gui_*` style) wrapped by UTE (`..\ute\gui\gui_screens\ute_gui_screen_*.c`).

### 1.1 Screen descriptor (`UI_MenuTypeDef`, 0x38 bytes) **[high]**

68 descriptors live in RAM `0x0020D74C`–`0x0020E77C`. Their initial values are in flash
`0x00895BE4`–`0x00896C14`, and the screen names are at `0x0088FFCC`. The full list is in the appendix.

| Off | Field | Evidence |
|---|---|---|
| +0x00 | `const char *name` | e.g. `"MusicControlScreenUI"` |
| +0x04 | parent | runtime; in instances it is the left neighbour drawn at dx−240 |
| +0x08 | sub / next | `gui_switch` writes the new screen here before the destructor; in instances it is the right neighbour drawn at dx+240 |
| +0x0C | **key (side-button) handler** `(int type)` | e.g. app list `0x00852444`: type 0 → go to watch face |
| +0x10 | **touch handler** `(touch_evt *)` | called from `0x0083F0EA` (`cur->+0x10`) |
| +0x14 | **constructor / enter** `(r0=4, r1=0)` | creates timers, sets +0x34 = 1, calls `gui_update` |
| +0x18 | **destructor / exit** | deletes timers, clears +0x34 |
| +0x1C | **display_info / build** `(instance*, arg)` | copies +0x33, clears the widget list, fills widgets (the "draw" callback) |
| +0x20 | event / timer message handler `(msg*)` | `msg+0` = type (1/2/3 timers), `msg+4` = screen name (strncmp) |
| +0x24 | `widget *pWidgetList` | set in the runtime instances only |
| +0x28 | show/init helper | copies a 0x20-byte template from rodata `0x0088Axxx`, calls `0x0084329C` (transition type switch) **[medium]** |
| +0x30 | u16 screen id; bit 15 = interrupting popup (caller is saved in `0x0020C154+0xD4C`) | `0x00844B4C`/`0x00844C28` |
| +0x32 | u8 (set to 4 by the watch-face enter) | **[low]** |
| +0x33 | u8 **widget capacity** (max 37 = 0x25) | `display_info` memsets `cap × 0x44` |
| +0x34 | u8 active (timers running) | |
| +0x35 | u8 is-current (touch areas enabled) | set by `gui_update` |

### 1.2 Globals **[high]**

| RAM | Meaning |
|---|---|
| `0x00210760` | `UI_MenuTypeDef *cur_screen` (descriptor of the shown screen) |
| `0x0020D698` / `0x0020D6D0` / `0x0020D708` | runtime instances `g_cur_menu` / `g_sub_menu` / `g_par_menu` (copies the build fills in) |
| `0x00211F44` / `0x00212918` / `0x002132EC` | widget arrays of those three instances (37 × 0x44 bytes each) |
| `0x0020D694` | `→ 0x0021076C` line-band buffer (0x780 = 240 px × 4 lines × 2 B, double-buffered via `0x00210758+0xC`) |
| `0x00213CC0` | touch-area array: 15 × 16 B `{s16 x,y,w,h; void(*cb)(int); u8 enable}` |
| `0x0020C154` | big app-state struct (notification buffers, `+0xD54` = "return-to" screen, …) |
| `0x0020D154` | app/music state struct (`+0x90` music title, `+0x26` play state, `+0xE4` …) |
| `0x0020BE84` | settings struct (known from earlier work: `+0xFA` timeout, `+0x66` 12 h, …) |
| `0x0020FBE8` | `→` current language/string table (byte +1 = language code; +0xA9 used) |

### 1.3 Lifecycle **[high]**

- **Enter a screen:** `gui_switch(desc)` = **`0x00844B1C`**. It filters popups and locks, then runs
  `cur->sub = desc; cur->destructor(); cur_screen = desc; desc->constructor(4, 0)`.
  Typical caller: `ldr r1,=0x20C154; str.w <this desc>,[r1,#0xD54]; ldr r0,=<target desc>; b.w 0x844B1C`
  (app-list callbacks `0x00851CE8…`).
- **Redraw:** `gui_update(cur, cur_arg, sub, sub_arg, [sp]=par, [sp+4]=par_arg, [sp+8]=dx, [sp+0xC]=dy)`
  = **RAM `0x00209642`**. It calls each descriptor's `+0x1C` build into the g_* instance
  (`+0x2C`/`+0x2E` = dx/dy), then renders. Constructors call it with all zeros. Swipes call it
  through `0x00842238` with offsets, which makes neighbour screens slide.
- **Render:** RAM `0x00208E74`. For each 4-line band it walks the widget list of cur/sub/par
  (x offsets 0, +240, −240) and switches on the widget type (`+0x1D`):

| Type | Draw routine | Constructor(s) |
|---|---|---|
| 1 | RAM `0x0020AAD4` (fill/solid) **[medium]** | `0x00846612` (inline) |
| 2 | RAM `0x0020A5D6` image blit (variants by `+0x1C`: >0x80, >0x40) | `0x008443A4`, `0x00844376`, `0x00844566` |
| 3 | `0x00841938` text | `0x0084505C` (via `0x00845BDE`, `0x00845096`, `0x00845AD0`) |
| 4 | RAM `0x0020970C` rotated image (hands; floats at +0x38/+0x3C) | dial code |
| 5 | `0x00841824` sprite-digit string | `0x008435BE` (`0x00844330`, `0x0084434E`) |
| 7 | RAM `0x0020AA74` | `0x008452F2` |

### 1.4 Widget struct (0x44 bytes) **[high]** for offsets 0–0x1D, **[medium]** for the rest

`+0` s16 x · `+2` s16 y · `+8` u16 w · `+0xA` u16 h · `+0xC` data ptr (image flash address or string) ·
`+0x18` colour (text, 0x00RRGGBB) · `+0x1C` text size / image mode · `+0x1D` type ·
`+0x1F` per-widget flag (set to 1 before many draws) · `+0x20` "use font tables" flag ·
`+0x21` image flag set by `0x008443A4` (compressed pack image **[medium]**) ·
`+0x24`, `+0x2C`/`+0x2E`, `+0x32`/`+0x34` clip, `+0x38/+0x3C` float angle, `+0x40` font index,
`+0x41`, `+0x42`.

Widget *i* of an instance = `inst->+0x24 + i*0x44`. Builders keep a running index (`r5`/`r4`)
and compute it with `add.w r0,r5,r5,lsl#4` followed by `…lsl#2` (×68).

---

## 2. Draw API (calling conventions) **[high]**

| Function | Args | Notes |
|---|---|---|
| **`0x008443A4` add_image** | `r0` widget, `r1` image flash addr (must be > `0x970000`), `r2` x, `r3` y, `[sp]` w, `[sp+4]` h | sets `+0x21=1`, then `0x00844376`. Returns 1 (builders add it to the index). Used 303× |
| `0x00844376` add_image_raw | same | no `+0x21`; type = 2 unless already 1 |
| **`0x00845BDE` add_text** | `r0` widget, `r1` align (1 = centre in box, 2 = left), `r2` UTF-8 str, `r3` len, `[sp]` x0, `[sp+4]` x1, `[sp+8]` y, `[sp+0xC]` box h, `[sp+0x10]` size (1), `[sp+0x14]` colour | measures (12 px per half-width char at size 1, 24 px per full-width char), centres between x0..x1, then `0x0084505C` |
| `0x00845AD0` add_text_ex | `r0`, `r1` align, `r2` encoding (2), `r3` str, `[sp]` len, then same as add_text | |
| `0x00845096` add_text_box | `r0` widget, `r1` str, `r2` x, `r3` y, `[sp]` w, `[sp+4]` h, `[sp+8]` size | white; multi-line box (notification body) |
| `0x0084505C` text core | `r0`, `r1` str, `r2` x, `r3` y, `[sp]` w, `[sp+4]` h, `[sp+8]` size, `[sp+0xC]` colour | type 3 |
| `0x008435BE` digit_string | `r0` widget, `r1` mode (2 = left-aligned), `r2` ASCII str, `r3` n (≤ 20), `[sp]` sprite base (frame '-'), `[sp+4]` x, `[sp+8]` y, `[sp+0xC]` w, `[sp+0x10]` h | frames `- . / 0-9 :` (see hour12 notes) |
| `0x0084434E` / `0x00844330` | wrappers of `0x008435BE` / `0x00843A54` that set `+0x21=1` | used for clocks and numbers |
| **`0x0084503C` add_touch_area** | `r0` area (`0x213CC0 + 16*i`), `r1` enable (= `inst->+0x35`), `r2` x, `r3` y, `[sp]` w, `[sp+4]` h, `[sp+8]` callback | `cb(0)` = tap |
| `0x008433B6` touch hit test | `r0` areas, `r1` count (15), `r2` event, … | called from touch handlers |

Patch note: almost every coordinate is a `movs rN,#imm8` (2 bytes `ii 2N`; the first byte is
the value) or a `mov.w rN,#imm` / `add.w`. A value of 0–255 can be changed by rewriting one
byte. Several calls **share** a register (e.g. the music buttons all take w/h from
`r8`/`sb`), so check the defining instruction before patching. The tracker gives the defining
address for each argument.

---

## 3. Text and fonts

- Glyph lookup **`0x0087E070`** `(out*, ucs2 char, font idx)` **[high]**. It handles Latin, Latin-1,
  Latin Extended-A, Cyrillic `0x410–0x44F` and Vietnamese `0x1EA0…`. It returns
  `{u8 height, u8 width}` and a flash pointer `= offset[i] + base`.

  | Font idx | Offset table | Width table | Base (RAM) | Height |
  |---|---|---|---|---|
  | 0 | `0x0088E4F8` (file `0x806F8`) | `0x0088E38C` | `[0x20EC00+8]` | (not decoded) |
  | 1 | `0x0088EC14` (file `0x80E14`) | `0x0088EAA8` | `[0x20EC00+4]` | 16 |
  | 2 | `0x0088DDDC` (file `0x7FFDC`) | `0x0088DC70` | `[0x20EC00+0xC]` | 32 |

  The font base is set by `0x0087E020(0xF30000, 0xF30000, 0xF30000)` at `0x00830BC2`, so the
  bitmaps are in external flash at **`0xF30000`** (font file). The enable flag is `[0x20EC00]`. **[high]**
- Text widget renderer `0x00841938` **[high]**:
  - converts UTF-8 to UCS-2 (`0x008427C2`);
  - Thai `0x0E00–0x0E7F` is shaped by `0x0087A914`;
  - characters that pass `0x0087D2B4` (when `+0x20` is set) use the font tables with index `+0x40`;
  - other characters (CJK etc.) use a fixed 12×24 (half) / 24×24 cell drawn by RAM `0x00209F60`.
- Size argument 1 = 24 px line, 12 px half-width advance (`fp*24/2` in `0x00845AD0`). **[medium]**
- Font tables have **no arrow glyphs**, which matches the field test noted in TechLife-S100.md.

---

## 4. Input, lists, scrolling

- Touch controller: I²C address `0x15`, chip-id `0x20/0xB4/0xB5/0xB6` (CST816 family) at `0x0083F084`.
  **[medium]** for the part number.
- Touch event struct **[high]**: `+0` type, `+2` s16 dx, `+4` s16 dy, `+6` x, `+8` y.
  - Types 2/3 are press/tap (hit-tested against the touch areas).
  - Types 4…10 are drag/swipe/fling, dispatched by `0x00844E32`
    (`4` → `0x00844DE8` horizontal drag, `5` → `0x00844E0E` vertical, `6` → `0x00844CF6`, …).
  - `0x00844F2E` is the left/right swipe to parent/sub screen.
- Key handler (`+0x0C`): `r0` = press type (0 = short press). **[medium]**
- **List scrolling** (app list, settings, notification list, …) **[high]**:
  - State is a static struct placed **just before the list's descriptor** (`desc − 0x14`).
    Examples: app list `0x0020DCFC`, grid `0x0020E5CC`. Fields:
    - `+2` s16 scroll_y (≤ 0)
    - `+4` velocity
    - `+6` overscroll target
    - `+0xA`/`+0xC` top/bottom margins
    - `+0xE` scroll mod row (scrollbar)
  - Scroller `0x008456AC(state, evt, n_items, rows_per_screen, [sp]…, [sp+8]=280)`. Row height
    = (280 − margins) / rows_per_screen.
  - Fling step `0x0084566A` (snap to a row multiple), run by the "list animation timer"
    `0x00214A48` every 20 ms.
  - The watch-face enter resets the app list and grid with `strh 0,[0x20DCFC+2]` / `[0x20E5CC+2]`
    (`0x0085BD94`).

---

## 5. Key screens: draw call sites

Generated with the argument tracker, so every value has the address of the instruction that
sets it. "IMGn" = index in `research/ui/index.json`.

### 5.1 MusicControlScreenUI. Desc `0x0020DD98`, build `0x008531AA` (called from `+0x1C` `0x00853658`) **[high]**

| Call | What | Value (patch insn) |
|---|---|---|
| `0x008531CE` add_image | IMG725 panel 208×250 | x 16 (`0x8531C8 movs r2,#0x10`), y 18 (`0x8531C6 movs r3,#0x12`), w/h (`0x8531BA`/`0x8531B8`) |
| `0x00853210` add_text | **song title** `0x0020D1E4`, centred | x0 24 (`0x853200 movs r1,#0x18`), x1 216 (`0x8531FE movs r2,#0xD8`), y 64 (`0x8531FA mov.w ip,#0x40`), box h 56 (`0x8531F4 movs r2,#0x38`), size 1, white |
| `0x008532BE` / `0x008532CC` | header: IMG701/704/… (167×25 at 36,35) by language, or a language string (x 0–240, y 26) | branches at `0x85322E`–`0x8532B6` |
| `0x00853306` add_image | play/pause IMG723 32×39 | x 107 (`0x853302 movs r2,#0x6B`), y 125 (`0x8532FC movs r3,#0x7D`) |
| `0x0085332C` touch | play/pause area | x 80 (r8 `0x853310`), y 105 (`0x853324 movs r3,#0x69`), w 79 (sb `0x85330C`), h 80 (r8), cb `0x00852FFC` |
| `0x00853350` / `0x0085336C` | prev IMG721 26×26 at (29,131) / area (0,105,79,80) cb `0x0085304E` | x `0x853348`, y `0x85333A` |
| `0x00853390` / `0x008533AC` | next IMG720 at (185,131) / area (160,105) cb `0x008530A0` | x `0x853388`, y `0x85337A` |
| `0x008533E0` | volume bar (table `0x0088B8D4[vol]`, 112×5 at 61,239) | `0x8533DE`/`0x8533D0` |
| `0x00853458`/`0x00853472` | vol+ IMG719 20×15 at (187,234), area (150,200) cb `0x008530F2` | |
| `0x00853492`/`0x008534AA` | vol− IMG722 at (31,234), area (0,200) cb `0x0085313E` | |

Button callbacks send `0x0082AD3C(state+0xE4, code)` with code 2 = play/pause, 4 = prev,
3 = next, 5 = vol+, 6 = vol−, which become the `D1 xx` events to the phone.

### 5.2 PhoneAppsNotificationScreenUI (popup; **also shows the "nav text"**). Desc `0x0020DE1C`, build `0x0085442E` **[high]**

The type at `0x0020C154+0xD15` selects the path. Type 0 = incoming call (answer/reject areas, IMG982).

| Call | What | Value (patch insn) |
|---|---|---|
| `0x00854484` add_image | app icon `0x0088BC20[type]` 24×24 | x 8 (`0x854482 movs r2,#8`), y 20 (`0x85447A movs r3,#0x14`) |
| `0x008544D0` add_text_ex | app name `0x0088BC98 + type*12`, left | x0 36, x1 240, y 20, h 64 (`0x8544A4`–`0x8544B0`) |
| `0x00854652` digit_string | time "HH:MM" (`0x00214A94`), sprite IMG948 11×14 | x 170 (`0x85463A movs r1,#0xAA`), y 25 (`0x854634 movs r0,#0x19`) |
| `0x008546A6` / `0x00854728` add_text_box | **notification body** `0x0020CC6A` | x 8 (`0x85469E movs r2,#8`), y 56 (`0x854686` / `0x854708 movs r3,#0x38`), w 224 (`0x854694` / `0x854716 movs r2,#0xE0`), h 160 (`0x854692` / `0x854714 movs r1,#0xA0`) |
| `0x008546DE` / `0x0085475C` | IMG976 200×60 "clear/OK" button at (20,212) + area (0,200,…,80) cb `0x0085437C` | |

### 5.3 App list (MainMenuListScreenUI). Desc `0x0020DD10`, build `0x00851E56` **[high]**

- Rows are **70 px** (`0x851E7C movs r7,#0x46`). **This must match** `rows_per_screen = 4` in the
  touch handler (`0x852532 movs r3,#4`, 280/4).
- 18 items. The first visible item = −scroll_y / 70.
- Per row:
  - touch (0, y, 240, 70), callback table **`0x0088B6D0[18]`**
  - icon table **`0x0088B718[18]`** (IMG1202, 1258–1273) at x 14 (`0x851F7C`), y = row + 11
  - label:
    - language code 2: image table `0x0088B7A8` (IMG1200, 1224–1240), 145×55 at x 77
      (`0x85202E`), w 0x91/0x9D/0x87 (`0x852014`)
    - code 0x15: table `0x0088B760` (IMG1201, 1241–1257)
    - otherwise: text from string id `0x0088B7F0[i]` at x0 73 (`0x851FF4 movs r2,#0x49`), x1 240
- Scrollbar: IMG2069 4×48 + IMG2068 4×6 at x 232 (`0x851ECA`).
- Item → screen:

  | Item | Screen | Item | Screen | Item | Screen |
  |---|---|---|---|---|---|
  | 1 | Temperature | 7 | SleepTimeDisplay | 13 | CountDown |
  | 2 | TrainingList | 8 | NotifycationList | 14 | StopwatchSub |
  | 3 | SportHistoryList | 9 | WeatherToday | 15 | TakePhoto |
  | 4 | HeartRate | 10 | BreathTraining | 16 | FlashLight |
  | 5 | BloodOxygen | 11 | MusicControl | 17 | FindPhone |
  | 6 | ActivityList | 12 | AlarmList | 18 | FunctionList (= Settings) |

### 5.4 App grid (GridLayoutScreenUI). Desc `0x0020E5E0`, build `0x008653FC` **[high]**

- Rows are **92 px** (`0x865404 movs r7,#0x5C`), 3 columns.
- Icons are 64×64 at x **12 / 88 / 164** (`0x86549A movs r2,#0xC`, `0x8654EE movs r2,#0x58`,
  `0x865548 movs r2,#0xA4`), y = row·92 + 20 (`0x865486 add.w sb,fp,#0x14`).
- Touch cells are (0/80/160, row, 80/79/79, 92).
- Order table `u16 0x0088CE84[18]` = app ids {19,0,16,2,4,1,6,9,7,17,8,10,11,12,18,14,13,15}.
- Icons `0x0088CE3C[18]` (IMG1203, 1144–1160).
- id → callback via `0x00845E6C(id, 0x0088CEA8, 20)` (`{u32 id; fn}` pairs).

### 5.5 Other screens (short form)

- **HeartRateScreenUI** (`0x0020DBE4`):
  - icon IMG1475 at (190,72) `0x8502C0`/`0x8502BE`
  - graph IMG449/450 192×127 at (24,95) `0x850306`/`0x850302`
  - labels IMG1494/1495 at y 251
  - type-7 widget at `0x008505CE`
- **FunctionListScreenUI** (Settings): rows 93 px, IMG756 220×80 row background at x 10,
  40×40 icon at x 14, text x0 66.
- **NotifycationListScreenUI** (`0x0020DDE4`):
  - row background IMG976 200×60 at x 20 and IMG1902 220×98 at x 10
  - text x0 52
  - history records come from external flash `0x0097E000` (8 × 171 B, written by `0x00834C96`)
- **WatchMainScreenUI** (`0x0020E1D0`): its enter `0x0085BD52` picks the dial by `settings+0x11C`
  (1 → D2687001, 2 → D2638001, 3 → D2640001, else WatchOnlineUI `0x0020E20C` = custom dial
  renderer `0x0085BE0A…`).

---

## 6. String buffers (music / notification / "navigation")

| Data | RAM | Writer | Confidence |
|---|---|---|---|
| **Music title** (UTF-8, max 52 B) | **`0x0020D1E4`** (`0x0020D154+0x90`) | `3A 06 len text` → `0x00838390` (`0x00842AF0(src,len,dst,0x34)`) | [high] |
| Music play state / misc | `0x0020D154+0x26` (0 = play, 1 = pause from `3A 01 1/2`), `+0xCC`, `+0x28`, `+0xC4`/`+0xC8` (times) | `0x008382F0` | [high] for +0x26, [medium] for the rest |
| Notification RX (UTF-16BE) | type `0x0020CBC3` (+0xA6F), len `+0xA70`, buffer `0x0020CBC6` (+0xA72, 0xA3 B) | `C5` handler `0x00836C0C` (truncates at 160 B with "...") | [high] |
| Current notification | type `0x0020CE69` (+0xD15), len `+0xD16`, UTF-16 `0x0020CD69` | `C5 FD` → copy, then `gui_switch(0x20DE1C)` (`0x00836DD8`) | [high] |
| **Displayed notification text (UTF-8)** | len `0x0020CC69`, text **`0x0020CC6A`** | `0x0084510A` (UTF-16 → UTF-8, Thai reorder) | [high] |
| Nav text | **same as notification**: `tools/s100.py nav` sends `C5` type 4, which ends up in `0x0020CC6A` on the popup. The firmware has no separate nav screen or command. | | [high] |

---

## 7. How to change or add things

**Move/resize:** patch the immediates listed in §5 (re-hash and bump the version as usual).
- Keep image w/h equal to the pack image size. The blitter strides by the widget w.
- For list rows, change the builder row height **and** the `rows_per_screen` / 280 used by the
  scroller together.

**Add a screen (proposal) [medium]:**
1. Re-use an unused descriptor, e.g. **FactoryAgingTestScreenUI** (`0x0020DA1C`, init image at
   file-addr `0x00895EB4`; capacity byte `+0x33` = 0x0E). Point its `+0x1C` build / `+0x10`
   touch / `+0x0C` key (and keep its `+0x14`/`+0x18` or use simple ones) to injected code by
   patching the **init image** words. That changes RAM at boot on purpose.
2. Reach it by changing an app-list entry: callback `0x0088B6D0[k]` → a 6-instruction stub
   `ldr r1,=0x20C154; ldr r0,=0x20DD10; str.w r0,[r1,#0xD54]; ldr r0,=0x20DA1C; b.w 0x844B1C`.
   Also change icon `0x0088B718[k]` and label `0x0088B7A8[k]`.
3. The build function receives the instance in r0. It must:
   - `strb cap,[inst,#0x33]` and memset `inst->+0x24` (copy the pattern at `0x0084DB2C`);
   - fill widgets with `0x008443A4` / `0x00845BDE` / `0x0084503C`.
   Refresh with `gui_update(0x20DA1C,0,0,0,0,0,0,0)` (`0x00209642`), e.g. from a timer handler (`+0x20`).
4. The factory screen is otherwise only entered by UTE factory commands (refs `0x00837C3A`–`0x00837CAC`).

---

## 8. Free space

**Flash inside the app image [high]:** the code/rodata region `0x0080E400`–`0x00890898` has
**no usable padding**:
- the largest zero run is `0x00890721`–`0x008907A4`, which is the high half of the ctype table and is in use;
- the zero areas in `0x0080E000`–`0x0080E400` are image-header fields covered by the SHA and
  possibly interpreted by the bootloader, so avoid them.

All large zero runs are in the RAM-code and `.data` init images (§0), so they are copied to RAM.

Usable options:
1. **Dead factory-test code** **[medium]**. FactoryAgingTest build `0x0084D432`–`0x0084D968`
   (1,334 B). Only that module and its descriptor reference it (checked: no outside `bl`/`b` or
   literal refs). First re-point or disable descriptor `0x0020DA1C`, and possibly the UTE
   factory command at `0x00837C7C`.

   FactoryTpTest (`~0x0085F460`–`0x0085FA78`, ~1.5 KB) and HeartCheckLightLeakage
   (`0x0084FA12`–`0x0085025E`) are similar candidates **[low]**: their bounds still need checking.
2. **Append after `0x008974D0`** (grow the image; update payload_len `0x890D0` and SHA).
   The startup copy sizes are fixed, so appended bytes are not copied to RAM. The OTA bank/temp
   capacity and what is in flash after the image are **unknown**. The first flash addresses the
   code uses beyond the image are `0x00971000`–`0x0097F000` (user data). **[low]**
3. Relocating B5: move the 130-byte handler into option 1 and restore `0x0089491C` to zeros.

**RAM [medium]:** `.bss` ends at `0x0021951C`. `0x0021951C`–`0x00224000` (~43 KB) is the OS heap
(SDK layout: 144 KB data RAM, app globals start at `0x00208400`), so there is **no statically
free RAM**. Options:
- heap allocation (ROM `os_mem_alloc`; not yet located);
- small state in an unused descriptor's runtime fields;
- re-use the factory-screen statics.

---

## 9. Open questions

- The meaning of `+0x28` / `0x0084329C` (transition engine; 16 animation types) and of `+0x32`.
- Widget types 1 and 7 in detail. The `+0x1C` image modes (>0x40, >0x80: alpha?) in blit `0x0020A5D6`.
- Font 0 height. The exact font file layout at flash `0xF30000`.
- Key-handler event codes (short/long press). Exact touch types 6–10.
- OTA app-bank size (needed to grow the image).
- Whether the 359 pack images with no direct pointer are reached through tables such as
  `0x0088B8D4` (volume bar) and per-language label tables.

---

## Appendix: all screen descriptors (RAM / init-image file-addr, id = +0x30, cap = +0x33, functions)

| Name | RAM | init @ | id | cap | +0C key | +10 touch | +14 enter | +18 exit | +1C build | +20 event | +28 show |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WatchScreenD2640001UI | 20d74c | 895be4 | 0000 | 28 | 846926 | 846928 | 84680a | 846888 | 8468dc | 846778 | 846732 |
| WatchScreenD2638001UI | 20d784 | 895c1c | 0000 | 36 | 847850 | 847852 | 847696 | 8477b0 | 847804 | 847612 | 8475cc |
| WatchScreenD2687001UI | 20d7bc | 895c54 | 0000 | 28 | 847e56 | 847e58 | 847c9e | 847d1e | 847e0c | 847c1a | 847bd4 |
| AboutSubScreenUI | 20d804 | 895c9c | 0016 | 28 | 84844c | 84844e | 8482dc | 8483c6 | 848414 | 848262 | 84821a |
| AlarmListScreenUI | 20d850 | 895ce8 | 0000 | 36 | 848f88 | 848fae | 848d68 | 848ee6 | 848f54 | 848c24 | 848bde |
| AlarmNotifyScreenUI | 20d888 | 895d20 | 8007 | 7 | 849584 | 849586 | 849480 | 8494f8 | 84954c | 8493fe | 84930a |
| BatteryChargingScreenUI | 20d8c0 | 895d58 | 800b | 10 | 84998e | 849990 | 84988e | 849908 | 849956 | 84980c | 8496a4 |
| BindingScreenUI | 20d8fc | 895d94 | 800a | 18 | 84a38c | 84a38e | 84a1d2 | 84a276 | 84a358 | 84a0fc | 84a070 |
| BloodOxygenScreenUI | 20d938 | 895dd0 | 005b | 18 | 84aa0a | 84aa16 | 84a8dc | 84a972 | 84a9d2 | 84a762 | 84a45a |
| BreathTrainingScreenUI | 20d974 | 895e0c | 0091 | 28 | 84ba06 | 84ba08 | 84b7ea | 84b954 | 84b9ca | 84b700 | 84b664 |
| BrightnessScreenUI | 20d9ac | 895e44 | 0013 | 8 | 84c1dc | 84c202 | 84bfe4 | 84c08e | 84c1a4 | 84bf4a | 84bdac |
| CountDownScreenUI | 20d9e4 | 895e7c | 0066 | 20 | 84d1a6 | 84d1a8 | 84cfe4 | 84d0f8 | 84d16c | 84cf18 | 84ce82 |
| FactoryAgingTestScreenUI | 20da1c | 895eb4 | 0036 | 14 | 84db84 | 84db86 | 84da5c | 84dad6 | 84db24 | 84d9c2 | 84d96a |
| FactoryBatteryTestScreenUI | 20da54 | 895eec | 0037 | 10 | 84e274 | 84e276 | 84e160 | 84e1ee | 84e23c | 84e072 | 84e018 |
| FactoryResetYesOrNoScreenUI | 20dab4 | 895f4c | 0000 | 5 | 84e6ae | 84e6b0 | 84e5b4 | 84e62e | 84e676 | 84e536 | 84e4f0 |
| FindPhoneScreenUI | 20daec | 895f84 | 0014 | 8 | 84ed02 | 84ed04 | 84eb5a | 84ec7c | 84ecca | 84eab8 | 84e81a |
| FlashLightScreenUI | 20db24 | 895fbc | 0089 | 2 | 84f0d6 | 84f0d8 | 84efba | 84f038 | 84f09e | 84ef44 | 84ee9e |
| FunctionListScreenUI | 20db70 | 896008 | 0000 | 30 | 84f96c | 84f992 | 84f828 | 84f8c2 | 84f934 | 84f6de | 84f5b4 |
| HeartCheckLightLeakageDisplayScreenUI | 20dba8 | 896040 | 006f | 8 | 8501b8 | 8501de | 850020 | 85009a | 850180 | 84ff4c | 84ff06 |
| HeartRateScreenUI | 20dbe4 | 89607c | 0005 | 28 | 850a3c | 850a3e | 8507e6 | 85099a | 850a04 | 85062e | 8505d8 |
| HomeStatusScreenUI | 20dc1c | 8960b4 | 0007 | 30 | 85122e | 851230 | 8510ee | 85118a | 8511de | 851062 | 850fd0 |
| IdleScreenUI | 20dc54 | 8960ec | 0000 | 1 | 851494 | 851600 | 85142a | 85146e | - | 851416 | 8513d0 |
| LogoScreenUI | 20dc8c | 896124 | 0039 | 2 | 8518d8 | 8518da | 8517d6 | 851852 | 8518a6 | 85172e | 8516e8 |
| LowPowerNotifyScreenUI | 20dcc4 | 89615c | 8008 | 6 | 851bee | 851bf0 | 851aee | 851b68 | 851bb6 | 851a6a | 851988 |
| MainMenuListScreenUI | 20dd10 | 8961a8 | 0000 | 25 | 852444 | 85246a | 852304 | 85239a | 85240c | 8521b6 | 852170 |
| MoreListWeatherScreenUI | 20dd5c | 8961f4 | 0000 | 37 | 852d0a | 852d30 | 852bd6 | 852c6c | 852cd8 | 852a66 | 852a1e |
| MusicControlScreenUI | 20dd98 | 896230 | 0071 | 15 | 853692 | 853694 | 853590 | 85360a | 853658 | 85350e | 8534c8 |
| NotifycationListScreenUI | 20dde4 | 89627c | 0000 | 37 | 853fd8 | 853ffe | 853e82 | 853f26 | 853fa0 | 853d2a | 853ce4 |
| PhoneAppsNotificationScreenUI | 20de1c | 8962b4 | 8005 | 12 | 854aa4 | 854aa6 | 8548f0 | 854a10 | 854a64 | 854840 | 8547c4 |
| PowerOffYesOrNoScreenUI | 20de54 | 8962ec | 0000 | 12 | 854fa2 | 854fa4 | 854ea8 | 854f22 | 854f6a | 854e2a | 854dc0 |
| SedentarinessNotifyScreenUI | 20de8c | 896324 | 8006 | 4 | 8553f0 | 8553f2 | 8552c8 | 85534c | 8553a0 | 855246 | 855140 |
| ShowOtaPictureFailScreenUI | 20dec4 | 89635c | 0000 | 10 | 85585a | 85585c | 85576a | 8557d4 | 855822 | 8556e6 | 8554f6 |
| SilentOtaScreenUI | 20defc | 896394 | 800a | 10 | 855dec | 855dee | 855c6e | 855ce6 | 855dba | 855bd4 | 855b76 |
| SleepTimeDisplayScreenUI | 20df34 | 8963cc | 0072 | 30 | 85637e | 8563a4 | 856270 | 8562f2 | 856346 | 8561a4 | 85614e |
| SportDetialScreenUI | 20df6c | 896404 | 0067 | 35 | 856fe8 | 856fea | 856e8e | 856f42 | 856fae | 856d94 | 856564 |
| sportendListScreenUI | 20dfb8 | 896450 | 0000 | 37 | 857bc0 | 857be6 | 857a1c | 857af2 | 857b66 | 85787c | 85780e |
| SportPausedScreenUI | 20dff4 | 89648c | 0070 | 18 | 85854e | 858550 | 85842c | 8584c2 | 858516 | 8583ae | 8582d4 |
| StatusBarScreenUI | 20e030 | 8964c8 | 006c | 37 | 859018 | 859024 | 858f00 | 858f90 | 858fde | 858e94 | 85879c |
| StopwatchSubScreenUI | 20e06c | 896504 | 0011 | 18 | 85968a | 85968c | 85957c | 8595f4 | 859652 | 859494 | 859124 |
| TakePhotoScreenUI | 20e0a4 | 89653c | 007f | 10 | 859cba | 859cbc | 859aa8 | 859b2e | 859b94 | 859a10 | 8598b8 |
| TargetCompeledScreenUI (name shared with Kcal…; step?) | 20e0dc | 896574 | 8009 | 10 | 85a0f0 | 85a0f2 | 859ff8 | 85a06a | 85a0b8 | 859f76 | 859f1c |
| TemperatureScreenUI | 20e114 | 8965ac | 0081 | 18 | 85aba0 | 85aba2 | 85a9d2 | 85aa66 | 85aad0 | 85a946 | 85a8f0 |
| TemperatureWaringScreenUI | 20e14c | 8965e4 | 0082 | 18 | 85b0a0 | 85b0b2 | 85af96 | 85b01a | 85b068 | 85af0a | 85aec4 |
| TrainingListScreenUI | 20e198 | 896630 | 0000 | 22 | 85b9b2 | 85b9d8 | 85b86a | 85b908 | 85b97a | 85b714 | 85b4ea |
| WatchMainScreenUI | 20e1d0 | 896668 | 0001 | 0 | - | - | 85bd52 | - | 85bda2 | - | 85bd0c |
| WatchOnlineUI | 20e20c | 8966a4 | 0000 | 37 | 85de02 | 85de04 | 85dce8 | 85dd74 | 85ddc8 | 85dc38 | 85be0a |
| WatchOnlinePreview | 20e244 | 8966dc | 0000 | 10 | 85e144 | 85e146 | 85e04a | 85e0be | 85e10c | 85dffe | 85df18 |
| WatchPreview1 | 20e27c | 896714 | 0000 | 10 | 85e4da | 85e4dc | 85e3a6 | 85e41a | 85e468 | 85e33a | 85e2de |
| WatchPreview2 | 20e2b4 | 89674c | 0000 | 10 | 85e7e8 | 85e7ea | 85e6b4 | 85e728 | 85e776 | 85e668 | 85e60c |
| WatchPreview3 | 20e2ec | 896784 | 0000 | 10 | 85eae8 | 85eaea | 85e9b4 | 85ea28 | 85ea76 | 85e968 | 85e90c |
| WeatherTodayScreenUI | 20e324 | 8967bc | 000c | 35 | 85f2de | 85f2e0 | 85f1de | 85f258 | 85f2a6 | 85f15c | 85ebf8 |
| FactoryTpTestScreenUI | 20e35c | 8967f4 | 0000 | 9 | 85f9d2 | 85f9f8 | 85f89c | 85f940 | 85f99a | 85f7d2 | 85f460 |
| SettingDisplayTimeScreenUI | 20e394 | 89682c | 008c | 10 | 85ff96 | 85ffbc | 85fda8 | 85fe4a | 85feb4 | 85fd10 | 85fb84 |
| WatchOnlineUpdateScreenUI | 20e3cc | 896864 | 800a | 4 | 8603e2 | 8603e4 | 8602d8 | 860360 | 8603b0 | 86023c | 8601e0 |
| SportHistoryListScreenUI | 20e418 | 8968b0 | 0000 | 37 | 860e8a | 860eb0 | 860c24 | 860dce | 860e3a | 860ac8 | 860a74 |
| LegalPolicyDescriptionScreenUI | 20e468 | 896900 | 0093 | 18 | 8616a6 | 8616cc | 8614ce | 86156c | 861674 | 8613d2 | 86138a |
| SettingMotorVibrationScreenUI | 20e4a0 | 896938 | 0013 | 8 | 861df0 | 861e16 | 861bee | 861ca8 | 861d12 | 861b54 | 861a1a |
| SettingTurnTheWristScreenUI | 20e4d8 | 896970 | 0000 | 10 | 86221e | 862220 | 862124 | 86219e | 8621e6 | 8620a6 | 862060 |
| ActivityListScreenUI | 20e524 | 8969bc | 0000 | 37 | 863612 | 863638 | 86340e | 86353c | 8635c6 | 8632ea | 8632a4 |
| SettingNoDisturbScreenUI | 20e55c | 8969f4 | 00ab | 20 | 864b34 | 864b36 | 8649f8 | 864a8a | 864afa | 86495e | 8648da |
| SettingMainmenuTypeScreenUI | 20e594 | 896a2c | 0013 | 8 | 8650f8 | 86511e | 864fb2 | 865056 | 8650c0 | 864f18 | 864dde |
| GridLayoutScreenUI | 20e5e0 | 896a78 | 00aa | 30 | 8658e6 | 86590c | 86576a | 86581e | 8658ae | 8655ac | 865566 |
| DrinkWaterNotifyScreenUI | 20e618 | 896ab0 | 8006 | 4 | 865f96 | 865f98 | 865e6e | 865ef2 | 865f46 | 865dec | 865c9c |
| SportTimeTargetCompeledScreenUI | 20e650 | 896ae8 | 800c | 10 | 8663b4 | 8663b6 | 8662bc | 86632e | 86637c | 86623a | 8661e0 |
| KcalTargetCompeledScreenUI | 20e688 | 896b20 | 800c | 10 | 8667f6 | 8667f8 | 8666fe | 866770 | 8667be | 86667c | 866622 |
| StandingTimeTargetCompleteScreenUI | 20e6c0 | 896b58 | 800c | 10 | 866c3a | 866c3c | 866b42 | 866bb4 | 866c02 | 866ac0 | 866a66 |
| HeartInformationListScreenUI | 20e70c | 896ba4 | 0000 | 25 | 86746a | 867490 | 867328 | 8673c0 | 867432 | 8671da | 867194 |
| AlarmTimeSettingScreenUI | 20e744 | 896bdc | 00ae | 37 | 8687f4 | 8687f6 | 8686c2 | 868754 | 8687c0 | 86862a | 8685ba |

Function addresses are Thumb entry points without the low bit. "init @" is the flash address of
the descriptor's initial value in the `.data` image (file offset = value − `0x80DE00`).

---

## Additions and corrections (2026-10-30)

Found while preparing [ui-upgrade-plan.md](ui-upgrade-plan.md) (§3, §12 there has the details).

- **§1.1 `+0x28` / `0x0084329C` is not a transition engine.** `+0x28` copies a 9-word navigation
  template (`0x0088A7F4`–`0x0088B0AC`: back, two alternates, the four swipe neighbours, key actions)
  and `0x0084329C` dispatches 16 action codes. The only screen transition is the 4-way slide
  (40 ms timer id 3, 7/8 easing, ~4 frames). `+0x32` = entry direction of the slide.
- **§1.3 widget types:** 1 = raw image with clip window; 2 = image, black is the transparent key
  unless `+0x1F` = 1, modes 0x41–0x80 / > 0x80 are a tinted 1-bpp mask scaled (both axes /
  horizontally); 7 = array of solid rectangles `{x, y, w, h, rgb565}`. No alpha blending anywhere.
- **Type 5 digit widgets:** string pointer at `+0x14`; optional frame-address table at `+0x24`
  (14 words, `- . / 0-9 :`); raw strips use `+0x2C` frame height.
- **§4 input:** touch types 0/1 drag, 2 tap, 3 long press, 4/5 short drag, 6/7 swipe finger
  R→L / L→R, 8/9 up / down; no touch-down event. Hit test uses x = 240 − touch x. Key: short press
  on release, long press after 20 × 50 ms; `+0x28(class 2 short / 1 long, button 1)`.
- **§8 RAM correction:** `0x0021951C`–`0x0021C400` (12,004 B) after `.bss` is unreferenced; the
  heap is `0x0021C400`–`0x00224000`.
- **§8 cave correction:** HeartCheckLightLeakage code is `0x0084FCC4`–`0x00850294` (not from
  `0x0084FA12`; `0x0084F992`–`0x0084FCC3` is FunctionList's touch handler). FactoryAging + Battery
  `0x0084D41E`–`0x0084E36C`, FactoryTpTest `0x0085F460`–`0x0085FAF8`.
- **Settings:** struct `0x0020BE84`, 0x2D0 bytes, saved by `0x00830654` to `0x0097A000`
  (the `0x00972000` block is the bind/identity block).
- **Watchdog:** ~4 s, kicked from the app task only (see ui-upgrade-plan §12.2).

## Additions (2026-10-30, release c8)

- **Text widgets:** `add_text` (`0x845AD0` mode 2) stores `y + 12·size` and height `box / 2`; the glyph
  blitter `0x8415CC` draws from the stored y down. The band renderer `0x841938` skips a widget whose
  `[y, y + h)` misses the band, so the height must cover the 24 px font-0 cell (box ≥ 48; stock uses ≥ 56).
  Wrapped lines below `y + h` are not drawn (truncation). Font 0 widths: table `0x88E38C`, height 24;
  font 1: 16; font 2: 32 (`0x87E070`). Widget `+0x40` = font index.
- **Instance capacity:** builds set `+0x33`; the renderer draws that many widgets. Slots past it keep the
  previous screen's widgets.
- **Backlight** `0x83C2CC`: one-wire pulse LED driver, `16 − S_BRIGHT·13/100` pulses clamped to 15 (more
  pulses = dimmer); `S_BRIGHT < 25` reset to 50 (stock).
- **Navigation templates** (9 words): back, alt, alt, swipe R→L, swipe L→R, **swipe down**, **swipe up**,
  key actions, 0. Heart rate (`0x850A3E`) handles swipe types 8/9 itself (flag `0x214480`).
- **Wrist down → screen off** at `0x835C6C` (`bl 0x8464FA`), outside the screen-off timer path `0x84236C`.
- `add_digits` `0x844330`: `(w, str, n, sprite = table[3], x, y, w, h, table)`; sets `+0x21 = 1`, `+0x24 = table`.
