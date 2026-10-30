# TechLife S100: full UI upgrade plan (CMF-inspired)

Status (2026-10-30): **P0 done, P1 drafts built offline, nothing flashed.** Owner approved P0/P1 with
the recommended defaults (§11). Results and draft builds: §12. The next step (first flash) needs the
owner's confirmation.

This replaces the "B4 reskin" scope in [custom-firmware-plan.md](custom-firmware-plan.md) with a
structural upgrade. B4 so far (UI revisions 1–4) only changed pixels inside the stock images:
icons, colours and label typeface. This plan also covers layout, navigation, interaction,
motion, haptics and new screens. For each change it says what the firmware actually allows.

Source of truth: app `RH288A_V001319` and UI pack `V000957_U0006` in `research/firmware/`.
All facts below come from offline disassembly of those files (Capstone + Unicorn), with
addresses. Confidence tags: **[high]** means read from code, **[medium]** means a consistent
interpretation, **[low]** means an estimate or guess.
Earlier maps: [ui-framework-notes.md](ui-framework-notes.md) and [ui-resource-format.md](ui-resource-format.md).

---

## 1. Summary

**What can realistically be achieved** while keeping the stock firmware's BLE stack, sensors,
DFU and every stock feature:

| Area | Verdict |
|---|---|
| Visual design of every screen (cards, buttons, digits, rollers, rings, backgrounds) | **Fully achievable.** Pixels are free as long as each image keeps its size. Proven pipeline |
| Layout: positions, row heights, list density, grid shape, button placement | **Fully achievable** for existing elements, by patching immediates in the app image |
| Navigation structure: swipe chain, side-button actions, app order, settings order, menu trimming | **Fully achievable.** It is data (tables), not code |
| Motion: tuning the slide speed and easing, elastic/overshoot slides, slide-in popups | **Achievable** with small code patches |
| Frame animations (charging, loading, toggles, icon bloom, success ticks) | **Achievable** with the stock timer + frame-swap mechanism. Costs pack space and a full redraw per frame |
| Haptic feedback on taps, short "tick" pattern | **Achievable** (the motor API is known) |
| New screens (dedicated navigation, desk clock, extra settings, widget stack) | **Partially achievable.** Up to 4 new screens fit in reusable factory-test slots with ~7 KB of code space |
| Cross-fades, blur, translucency, zoom/scale transitions, true 60 fps | **Restricted.** No alpha blending, no colour scaling, no framebuffer; only pre-rendered fakes |
| Typeface of dynamic text (notification bodies, names, non-English text) | **Restricted.** The font sits outside the DFU-writable area |
| More than one stored custom dial, animated watch faces | **Restricted** |

The main constraint is the renderer. It has **no framebuffer**: every frame is rebuilt and
redrawn in full, in 4-line bands sent by DMA to the LCD. So CMF-style *motion* has to be short
and cheap: slides and small frame swaps, not continuous effects.

---

## 2. How the firmware can be changed

| Lever | What it changes | Proven? | Risk if wrong |
|---|---|---|---|
| **R: UI pack, in-place art** | Any of the 2,163 compressed images; w×h fixed, encoded size ≤ stock | Yes (UI rev 1–4) | Low. A bad image draws wrong; a dropped transfer breaks only the images in one 4 KB sector, and the watch kept running each time |
| **R+: UI pack growth** | New images appended after the stock pack end | No. The DFU size check allows it (§3.4) | Low–medium. The old app never references the new bytes |
| **D: app data/immediate patches** | Table entries, navigation templates, coordinates, row heights, timer periods, constants | Yes (B2 used code bytes; same process) | Medium. A wrong table pointer crashes the screen that uses it |
| **C: code injection** | New Thumb-2 logic in dead factory-code caves | Yes (B5 world clock, v1323/v1324) | High if the code is reached at boot, medium otherwise (§9) |
| **N: new screen** | Reuse one of 4 factory screen descriptors: its init image words point to new build/touch/key functions (C + D) | No | Medium–high. First one must be tested on a screen reached only on purpose |
| **Dial upload** | Watch face via the stock online-dial protocol | Yes (many faces) | None (no firmware change) |

Every app image needs a SHA-256 re-hash and a version bump (next ≥ **1325**). Every UI pack
needs CRC-32 + SHA-256 and a revision bump (next ≥ **5**).

---

## 3. New firmware facts used by this plan

These were found for this plan and correct or extend earlier docs.

### 3.1 Navigation is a per-screen template (data) [high]
Each screen's `+0x28` function copies a 9-word template from rodata `0x0088A7F4`–`0x0088B0AC`:
`{t0 back, t1 alt, t2 alt, t3, t4, t5, t6 = swipe neighbours, t7/t8 = side-button action codes}`.
- **Swipes:** touch events 6/7/8/9 go to t3/t4/t6/t5 via `0x00844E32`. The slide functions are
  `0x844D2E`/`0x844CF6`/`0x844D6C`/`0x844DB6`. The left/right sign convention is [medium].
- **Side button:** the key scanner `0x0083DF14` posts msg 7 (short press, on release) or msg 8
  (long press, after 20 polls). The dispatcher `0x0084329C` maps them through `0x008431DC`
  (high half of t7 = short, low half = long).
- **Action codes:** 0 none, 2 back, 3 → t1, 4–7 slide to t3–t6, 8 → t2, 9 screen off,
  10 power-off dialog, 11 watch face, 12 TrainingList, 13 max brightness, 14 app list, 15 Settings.
- **Watch face template** `0x0088A7F4`: one side → StatusBar (quick panel), the other → HomeStatus;
  down → NotificationList; up → MainMenuList (or Grid when `settings+0x220` says grid);
  short press = screen off, long press = power-off dialog.
- **Widget chain** (one swipe direction from the face): HomeStatus → Temperature →
  SleepTimeDisplay → HeartRate → WeatherToday → MusicControl. WeatherToday swipe up → 7-day list.
- **Lists:** the app list callbacks `0x0088B6D0[18]`, the grid order `u16 0x0088CE84[18]` and the
  settings rows `0x0088B3D0` (10 rows; callbacks, icons, Thai/English label images, string ids)
  are tables too.

**Consequence:** reordering, trimming, re-wiring swipes and remapping the button are data patches.
No new code is needed.

### 3.2 Motion engine [high]
- The **only transition is a 2-D slide** (4 directions).
  - **Drag:** while dragging, neighbours are rebuilt and drawn live at ±240/±280 on every touch-move event (`0x00844F2E`).
  - **Release:** `0x00842238`, state at `0x00213F40`.
  - **Timer:** per screen, timer id 3, **40 ms**.
  - **Easing:** each step does three halvings, so it moves 7/8 of the remaining distance per frame. That is about **3 frames ≈ 120 ms + render time**.
  - **End:** the slide ends at |x| ≥ 239 / |y| ≥ 278.
  - Descriptor `+0x32` = entry direction passed to the new screen.
- **Frame animations:** the screen constructor creates timer id 2 ("dynamic picture"). The `+0x20`
  handler calls `gui_update`, increments the counter `0x20C154+0xD60`, and the build function picks
  `table[counter % N]`.
  - Charging: 500 ms, IMG989–993 (118×118).
  - Find phone: 300 ms, IMG657–664 (112×112).
  - Breathing: 1000 ms.
- **List physics** already exist: fling, snap to row (`0x0084566A`, 20 ms timer `0x00214A48`) and overscroll target.

### 3.3 Renderer limits [high unless noted]
- **No framebuffer.** `gui_update` rebuilds all three instances and redraws 70 bands × 4 lines.
  Each band is memset, every widget is walked, and the band goes out by **GDMA → LCDC FIFO `0x40024818`**.
  Rendering the next band overlaps the DMA of the current one. There are no dirty regions.
- **Frame time:** not measured. Estimate **30–60 ms** [low] at **90 MHz** CPU (`0x0082A422`) with a quad-I/O XIP flash.
- **Widget types:**
  - **1:** raw full-screen image with a clip window (face backgrounds).
  - **2:** image. RGB565 with **black `0x0000` as the only transparency key**. Mode `+0x1C` 0x41–0x80 is a 1-bpp mask, **integer nearest-neighbour upscaled and tinted**; mode > 0x80 stretches horizontally only.
  - **3:** text.
  - **4:** rotated raw RGB565 image with anti-aliased edges (hands).
  - **5:** sprite digits.
  - **7:** an array of solid rectangles (bars and graphs; no arcs, rounded shapes or lines).
- **No alpha blending and no scaling of colour images.** Fades and zooms are only possible as pre-rendered frames.

### 3.4 Space budget
| Resource | Available | Source |
|---|---|---|
| UI pack growth | **532,988 B** (pack end `0xEADE04` → font `0xF30000`). The DFU check `0x0082C272` limits image `0xFFFE` to bank 5 = `0x465000` from `0xACB000` | [high] |
| Code caves (dead factory code) | ~**6.9 KB** free: FactoryAging+Battery `0x84D41E–0x84E36C` (3,918 B, 130 used by B5), HeartCheckLightLeakage `0x84FCC4–0x850294` (1,488 B), FactoryTpTest `0x85F460–0x85FAF8` (1,688 B) | [high] for refs checked |
| Static RAM | **12,004 B** at `0x21951C–0x21C400` (after `.bss`, before the heap; unreferenced). Corrects ui-framework-notes §8 | [medium-high] |
| Free user-data flash | 20 KB `0x975000`, 4 KB `0x980000`, 4 KB `0x98F000`, 196 KB `0x99A000–0x9CB000` | [medium] |
| App image growth | Unknown. It depends on the OEM flash layout at `0x801000`, which is not in our files. Do not grow the app | — |
| Reusable screen descriptors | 4 factory screens: AgingTest `0x20DA1C`, BatteryTest `0x20DA54`, TpTest `0x20E35C`, HeartCheckLightLeakage `0x20DBA8` (all reached only by UTE factory commands at `0x837C3A`–`0x837CAC`) | [high] |
| Online dial | 1 slot, 1 MiB at `0x9CB000`; ≤ 71 records, ≤ 34 sprites per frame | [high] |

**Correction to ui-framework-notes §5.5/§8:** HeartCheckLightLeakage starts at `0x84FCC4`, not
`0x84FA12`. The range `0x84F992–0x84FCC3` is FunctionList's touch handler.

### 3.5 Other facts
- **Haptics:** `motor_vibrate(count, pattern)` = `0x0083EE8C`. Patterns (RAM `0x20D600`, initial
  values in the `.data` image) are 900/450/200 ms on/off. Strength is set by PWM duty
  `settings+0x1F5`. The music buttons already call `(1, 2)` as tap feedback. It is suppressed by DND,
  by battery < 10 % and on some screens. [high]
- **Text:** menu, settings and sport labels are **pre-rendered images (English + Thai)**. Other
  languages, and all dynamic text, use the font at `0xF30000`. That font lies **outside** bank 5 (the
  UI pack area ends exactly at `0xF30000`), and no known DFU image id writes it. [medium]
- **Languages:** 6 string tables of 211 strings (`0x895864[code]`): English, Thai, Vietnamese,
  Filipino, and two that are probably Indonesian and Malay [medium]. There is no on-watch language setting.

---

## 4. Complete inventory of the stock UI

68 screen descriptors (full table in ui-framework-notes appendix). User-facing ones:

| Group | Screen | Content / options (from code) |
|---|---|---|
| **Face** | WatchMain → D2687001 / D2638001 / D2640001 / WatchOnlineUI | 3 built-in faces (IMG371 rings, IMG168 complications, IMG343 digital) + uploaded dial. Selected by `settings+0x11C` = 1/2/3/100 |
| | WatchPreview1/2/3, WatchOnlinePreview | Face carousel. Opened by long-pressing the face or Settings → Dial; swipe, then tap to select |
| **Quick panel** | StatusBarScreenUI | BT link icon, battery % + icon, date/weekday text; buttons DND, Brightness, Raise-to-wake, Flashlight, Settings |
| **Widget pages** | HomeStatus | Steps, kcal, active minutes, standing hours |
| | Temperature (+ TemperatureWaring) | Skin / body temperature, °C/°F, tips; high-temperature warning variant |
| | SleepTimeDisplay | Total hr/min, bedtime, wake time |
| | HeartRate → HeartInformationList | Current bpm, 24 h graph 50–180, max/min; (i) → 6 HR zones |
| | WeatherToday → MoreListWeather | Icon, condition, temperature, low/high; 7-day list |
| | MusicControl | Title (≤ 52 B), play/pause, prev/next, volume ±, volume bar |
| **Notifications** | NotifycationList | History (8 records in flash `0x97E000`), "No Notifications" |
| | PhoneAppsNotification (popup) | Call (name + hang up) or message (29 app icons/names, time, body ≤ 160 B, delete). Also the current "navigation" display |
| **Apps** | MainMenuList (list, 70 px rows) / GridLayout (3 columns, 92 px rows) | 18 apps; style chosen in Settings → Theme |
| **Health** | BloodOxygen | Start button, "Measuring...", result %, tips |
| | ActivityList | Rings page, steps/kcal 24 h charts, active/standing charts |
| | BreathTraining | Duration roller, rhythm toggle, Breathe/Exhale animation, summary |
| **Sport** | TrainingList | **24 sports** (Outdoor Run … Free Training); starts immediately, no countdown |
| | SportDetial / SportPaused / sportendList / SportHistoryList | Live time/bpm/kcal/steps/distance/pace/count; resume/stop; "too little data"; BT-lost variant; summary; history |
| **Tools** | AlarmList / AlarmTimeSetting | ≤ 8 alarms [medium]; cards with time, toggle, repeat; hour/minute rollers, AM/PM, weekday checkboxes, delete |
| | CountDown | Presets 1/3/5/10/15/30/60 min + custom HH:MM:SS rollers; pause/stop; "Time out" + restart |
| | StopwatchSub | Start/pause, reset, MM:SS.cs |
| | TakePhoto, FlashLight, FindPhone | Shutter; full-screen light (tap toggles, long press exits); ring phone + radar animation |
| **Settings** | FunctionList (10 rows) | Dial, Brightness (25/50/75/100 %), Screen timeout (5/10/"always", B2 mod), Theme (list/grid), Vibration (3 levels), DND (now + schedule with rollers), Raise to wake, Power off, Reset, About (→ Legal/regulatory) |
| **System popups** | AlarmNotify, Sedentariness, DrinkWater, LowPower, BatteryCharging, 4 goal popups, Binding, SilentOta, WatchOnlineUpdate, ShowOtaPictureFail, PowerOff/FactoryReset Yes-No | Mostly icon + one line + tap to dismiss; no snooze found [medium] |
| **Boot / idle** | LogoScreenUI, IdleScreenUI | Boot logo; screen-off pseudo-screen [low] |
| **Not user-facing** | FactoryAgingTest, FactoryBatteryTest, FactoryTpTest, HeartCheckLightLeakage | Reached only by factory commands → **free slots for new screens** |

**Phone-only settings** (no screen on the watch): language, 12/24 h, units, goals, sedentary and water
reminders, HR auto-measure, notification filters. The firmware also contains strings with no screen
behind them (Female health, Altitude, Dialpad, Call records, Honeycomb, Swimming, Treadmill) [medium].

---

## 5. CMF-inspired design system, mapped to the hardware

| Token | Proposal | Implementation |
|---|---|---|
| Colour | True black `#000` base (also the transparency key), off-white `#F5F5F5` text, greys `#282828` / `#8C8C8C`, one accent orange `#FF5A1E` (already used by `tools/ui_cmf.py`); semantic red only for HR and alerts | R. Any RGB565 colour is free |
| Typography | Bahnschrift-style condensed sans for labels (done in rev 4); **dot-matrix digits** for big numbers (time, bpm, steps), echoing CMF/Nothing faces; mono-spaced small digits | R. Digit sprite sets are 14-frame strips per size (`- . / 0-9 :`); redraw each set in its stock w×h. Dynamic text stays in the stock font (restricted) |
| Shapes | Large-radius cards (16–24 px), full pills for buttons and toggles, circular icon chips, 2 px outline rings | R. Anti-alias edges against black (black is transparent, so antialias toward the card colour, never toward the background) |
| Layout | Fewer, larger items: 3 list rows instead of 4, one key number per page, generous 12–16 px margins, consistent title bar at y≈20 | D (row height + rows_per_screen together; immediates in §5 of ui-framework-notes) |
| Iconography | Monoline 2 px glyphs, one orange detail per icon (done for 34 app icons in rev 2); extend to every in-screen glyph | R |
| Motion | Short, decisive: slide with soft overshoot (~180 ms), popups slide down from the top, small frame-swap micro-animations (toggle, check, ring fill); no long ambient animation | D/C (§7) |
| Haptics | Short tick on taps and toggles, double tick on confirm, existing long patterns for alarms | C (new short pattern) |

A dot-matrix look suits this renderer well. Dots are cheap compressed images, black gaps are free
(transparent), and the dial format already supports them (`tools/dial_nothing.py`).

---

## 6. Screen-by-screen plan

Legend: **F** = fully achievable, **P** = partially achievable, **X** = restricted.
Mechanisms: R, R+, D, C, N (see §2). Complexity: S/M/L.

### 6.1 Watch faces and face picker
| Change | Class | How | Cx |
|---|---|---|---|
| CMF faces (dot-matrix, widgets, world clock, …) | F | Dial upload (existing tools) | S |
| Re-art the 3 built-in faces (IMG371/168/343 and their digits) in CMF style | F | R; element positions are immediates in each face's build (`0x8468DC`, `0x847804`, `0x847E0C`) → D if moved | M |
| Face picker as a CMF carousel (card + name + dots indicator) | F | R for the preview images; D for positions | S |
| Seconds hand / animated face elements | X/P | The dial renderer has no animation timer. An injected timer on the face would wake the CPU every frame and **drain the battery**, and it sits on the boot path (§9). Not recommended | — |
| More than one stored uploaded face | X | One 1 MiB slot, no index [high] | — |

### 6.2 Quick panel (StatusBar)
| Change | Class | How | Cx |
|---|---|---|---|
| CMF control centre: large battery % in dot digits, date header, 5 pill tiles in a 2-column grid | F | R (tile art, digits) + D (coordinates of the 5 images and their touch areas in builder `0x8587E2`) | M |
| On/off state colours for the DND and raise-to-wake tiles (already 2 images: IMG891/892) | F | R | S |
| Brightness as an inline 4-segment bar instead of opening a roller screen | P | C: a touch area that cycles `settings+0x188` (25→50→75→100) and calls the existing apply function (`0x84BCCC`) | M |
| New tiles (always-on toggle using the B2 timeout, vibration level, find phone) | P | C: extra widgets + touch areas; capacity byte `+0x33` is 37, enough | M |
| Swipe direction (open from the top like CMF instead of from the side) | F | D: swap entries in the face template (t5 ↔ t3/t4). The notification list then moves to the side | S |

### 6.3 Widget pages (HomeStatus → Temperature → Sleep → HR → Weather → Music)
| Change | Class | How | Cx |
|---|---|---|---|
| Reorder or trim the chain (e.g. Activity → HR → Weather → Music, drop Temperature) | F | D: neighbour words in each template; keep chains symmetric (back links) | S |
| Add existing apps to the chain (ActivityList, BloodOxygen, Alarm) | F | D (same) | S |
| CMF card styling for each page: one hero number in dot digits, small caption, accent ring/bar | F | R (background, digits, icons) + D (positions) | M per page |
| HomeStatus as 4 concentric or 2×2 rings | P | The ring progress art exists as 11–12 step frames → re-art the frames (R); positions D. Smooth arcs are impossible at runtime (no arc primitive) | M |
| HR / activity graphs in a dot-matrix bar style | P | Graphs are type-7 rectangles; colours/widths are constants in the build code (D). Real dots need code (C) | M |
| A **vertical widget stack** of mini-cards (CMF-like) as one scrolling screen | P | N: new screen reusing the list scroller `0x008456AC` and existing data getters. Costs one of the 4 slots | L |

### 6.4 Notifications
| Change | Class | How | Cx |
|---|---|---|---|
| CMF notification card: app chip (24 px icon on a circle), app name, time, body on a rounded card, pill "Clear" | F | R (IMG976 200×60, IMG1902 220×98, app icons `0x88BC20`) + D (coords in `0x85442E`, list `0x853FA0`) | M |
| Popup slides down from the top instead of appearing instantly | P | C: popups use `gui_switch`; call the slide engine (`0x844DB6` path) from the popup show path. Popups can interrupt any screen, including the face, so test on a non-boot path first | M |
| Larger, wrapped body text with a different typeface | X/P | Box size is D (x 8, y 56, w 224, h 160). Typeface: restricted (§3.5) | S |
| Haptic per app type | P | C (vibration call already in the notify path; add a pattern choice) | M |
| Call screen with large name + round accept/decline | P | R + D; there is no accept action in stock (only hang up) [medium] | M |

### 6.5 App launcher (list and grid)
| Change | Class | How | Cx |
|---|---|---|---|
| App order, hide apps (e.g. merge Training/History), custom grid order | F | D: tables `0x88B6D0`/`0x88B718`/`0x88B7A8` and `0x88CE84`; item count immediate | S |
| List: 3 pill rows of 93 px with large icons and labels | F | D: row height `0x851E7C` + rows_per_screen `0x852532` together; R for the row art | M |
| Grid: 2 columns of large circular icons, or 3 columns with more spacing | F | D: x positions `0x86549A/0x8654EE/0x865548`, row height `0x865404`, touch cells; icon size stays 64×64 | M |
| Honeycomb / staggered grid (CMF Watch Pro style) | P | C: the grid builder computes positions; staggering odd rows needs a small code change | M |
| Fisheye or curved list (icons scale toward the centre) | X | No colour image scaling. A fake with 2–3 pre-rendered icon sizes is possible but costly (R+ and C) and not recommended | — |
| Scrollbar as a thin orange pill | F | R (IMG2068/2069) | S |
| "Bloom" app-open animation (icon grows to fill the screen) | P | R+ (3–4 pre-rendered frames per app, or one shared generic circle sequence) + C (play frames before `gui_switch`). Shared circle frames ≈ a few KB; per-app frames ≈ 18 × ~20 KB | M–L |

### 6.6 Settings
| Change | Class | How | Cx |
|---|---|---|---|
| CMF settings list: grouped cards, icon chip, value shown on the right ("50 %", "10 s") | P | R (row background IMG756 220×80, icons, labels) + D (row 93 px, coords). Showing the current value needs C | M |
| Reorder or remove rows | F | D: table `0x88B3D0` (+ count) | S |
| Brightness / Vibration / Timeout pickers as a CMF segmented slider instead of the roller | P | Pickers use raw-tail images (`0xE8157C`, `0xE89EBC`, `0xE8733C` …). Re-art is R once the raw-tail sizes are decoded (§8 P0); the input behaviour stays a roller unless C | M |
| Theme screen with real previews of list vs grid | F | R (`0xE77F7C`, `0xE7CA7C`, 19,200 B each) | S |
| DND schedule with CMF time rollers | F | R (roller digit strips) + D | M |
| Power off / Reset dialogs as CMF confirm sheets | F | R (IMG844 etc.) | S |
| **New "Watch" settings page**: 12/24 h, screen-always-on toggle, wrist raise, haptic level, language | P | N: new screen writing known settings fields (`settings+0x66` 12 h, `+0xFA` timeout, `+0x1BA` raise). **Settings persistence**: the save function for the 0x110-byte block at `0x972000` is not located yet → P0 | L |
| About page with CMF typography | F | R | S |

### 6.7 Health
| Screen | Proposal | Class | How |
|---|---|---|---|
| Heart rate | Hero bpm in dot digits, coloured zone bar, dot-matrix 24 h graph, min/max chips | P | R + D; dot graph = C |
| HR zones | Coloured zone pills | F | R |
| Blood oxygen | Large round start button that becomes a measuring ring (frame swap), result in hero digits | P | R + C (frame animation on the existing timer) |
| Temperature | Hero value + small trend chip; warning variant in orange/red | F | R + D |
| Sleep | Bedtime/wake on a horizontal timeline card, total in hero digits | F | R + D |
| Activity | Three concentric CMF rings, chart pages in dot bars | P | R (ring frames) + D; dot bars C |
| Breathing | CMF expanding circle animation (frames), minimal text | P | Raw-tail frames re-art (R after P0 decode); more frames = R+ + D (table) |

### 6.8 Sport
| Change | Class | How | Cx |
|---|---|---|---|
| 24-sport list as CMF pill rows with mono icons | F | R + D | M |
| Live workout screen: one hero metric + 2 secondary, orange HR | P | Layout varies per sport in `0x856618`; D per layout, many call sites | L |
| 3-2-1 countdown before start | P | N or C: insert a frame sequence before `0x835C7C(type,1)`. Needs a timer → best as a new screen | M |
| Pause screen with large round resume/stop | F | R (IMG1855/1856) + D | S |
| Summary and history as cards | F | R + D | M |

### 6.9 Tools
| Screen | Proposal | Class | How |
|---|---|---|---|
| Alarms | Cards with large time, pill toggle, weekday dots; "+" as a floating orange button | F | R + D |
| Alarm edit | CMF rollers (selected value large, others dim) | F | R (roller strips in the raw tail; P0 decode) |
| Timer | Preset chips in a 2-column grid, running ring (frames), large digits | P | R + D; ring animation C |
| Stopwatch | Dot-matrix digits, lap-style layout (no lap feature in stock) | F (look) / X (laps) | R + D |
| Camera | Big round shutter, connection chip | F | R |
| Flashlight | Keep (functional); CMF exit hint | F | R |
| Find phone | Radar frames in CMF style (8 frames, 112×112) | F | R |
| Weather | Hero temperature, condition icon set redrawn, 7-day list as rows with mini bars | F | R + D |
| Music | Now-playing card: title, large round play/pause, prev/next, segmented volume bar | F | R (IMG719–725, volume table `0x88B8D4`) + D (coords listed in ui-framework-notes §5.1) |

### 6.10 System screens
| Screen | Proposal | Class |
|---|---|---|
| Boot logo | Custom logo / dot-matrix wordmark (R; boot path but art only) | F |
| Charging | CMF ring filling (5 frames today; more frames = R+ + D table `0x88B140` and modulo) | F / P |
| Low battery, goals, sedentary, water, alarm ring | CMF full-screen cards with one icon, one line, pill button | F |
| Binding, OTA, dial sync | Progress ring + %, CMF style | F |
| Alarm snooze | Not in stock [medium] | P (C, needs alarm state RE) |

### 6.11 New screens (uses the 4 free factory slots)
| Candidate | Value | Data source | Cx |
|---|---|---|---|
| **Navigation** (turn arrow images, distance, street, speed) | High (owner goal) | Parse the existing `C5` type-4 text (e.g. `R|200 m|MG Road|48`) already received into `0x20CC6A`; arrows as R+ images | L |
| **Desk clock / always-on view** | High (owner goal) | Time struct, battery, weather; uses B2 always-on timeout | M |
| **Watch settings page** (12/24 h, always-on, haptics) | Medium | Settings struct (§6.6) | L |
| **Widget stack** (scrolling cards) | Medium | Existing getters | L |

More than 4 new screens needs new descriptors in free RAM, initialised from a boot hook. That puts
new code on the boot path, so it is **not recommended**.

---

## 7. Motion and interaction plan

| Effect | Class | Implementation | Cost |
|---|---|---|---|
| Faster or slower slides | F | D: the number of halvings in the step `0x00842370`/`0x00842264` (3 → 2 gives ~5 frames), timer period 40 ms | None |
| Overshoot / spring slide (CMF feel) | P | C: replace the step with a table-driven easing curve (offsets per frame, ≤ 8 frames), keeping the end condition | Each frame = full redraw |
| Popup slide-down | P | C (§6.4) | 3–5 redraws |
| Pressed state on buttons | P | C: needs a touch-down event; only tap (type 2) and long press (type 3) are confirmed → P0 | — |
| Toggle switch animation | P | C + R+: 3-frame knob slide on the existing timer | 3 redraws |
| Success check / ring fill | P | Timer + frame swap (stock pattern §3.2) | Frames in pack |
| Cross-fade, blur, translucency, zoom | X | No alpha, no scaling (§3.3) | — |
| Haptic tick on tap/toggle | P | C: add a ~30–40 ms pattern (patterns in `.data` at `0x20D600`), call `motor_vibrate(1, n)` from touch callbacks | Battery: negligible |
| Rubber-band list overscroll | F | Exists; tune via the scroller state | None |

**Performance rule:** each animation frame is a full 240×280 redraw (estimated 30–60 ms, P0 must
measure it). Keep every animation under ~250 ms or under ~6 frames. Avoid more than 2 large
images per frame. Never run an animation timer while the screen is idle.

---

## 8. Implementation phases

Each step is its own build and its own flash. App and pack versions are bumped every time.

| Phase | Steps | Depends on | Cx | Risk |
|---|---|---|---|---|
| **P0 Research & measurement (no flash)** | (1) Measure frame time: film a stock swipe at 240 fps and count frames. (2) RE the HardFault/watchdog behaviour: does a crash reboot? (3) Locate the settings-save function for `0x972000`. (4) Decode raw-tail image sizes and add raw-tail support to `tools/s100_ui.py`. (5) Confirm a touch-down event type. (6) Confirm the swipe sign convention. (7) Build a **PC screen previewer** that draws each screen from pack images + known coordinates, so every design is approved before flashing | — | M | None |
| **P1 Design system & mockups** | 240×280 mockups of every screen in §6 (PNG); owner review | P0 (7) | M | None |
| **P2 Full art pass (R)** | Redraw backgrounds, cards, buttons, rollers, digit sets, ring frames, popups, raw-tail images in place; pack rev ≥ 5. Can be split into 2–3 packs by screen group | P1, P0 (4) | L | Low |
| **P3 Structure (D)** | One app image: navigation templates (swipe chain, quick-panel direction, button actions), app/grid/settings order, list row heights, grid layout, coordinates for the new art, slide easing; app ≥ 1325 | P1 | M | Medium. Each change is a byte table patch, verified by disassembly diff + emulator run of the affected build functions |
| **P4 Pack growth proof (R+)** | Flash a pack with appended unused images only; confirm the watch is unchanged | P2 | S | Low–medium |
| **P5 Interaction code (C)** | Haptic tick, spring slide, popup slide-down, toggle/ring frame animations, inline brightness tile; one feature per image, emulator-tested | P3, P4 | M | Medium–high (§9) |
| **P6 New screens (N)** | First slot: a trivial screen (static image + back) reached from an app-list entry, to prove the descriptor method. Then Navigation, Desk clock, Watch settings, widget stack, each separately | P5, P0 (2, 3) | L | High for the first, medium after |
| **P7 Validation & battery** | Full navigation walk-through, alarms/notifications/sport sessions, 24 h battery comparison with stock | P2–P6 | M | None |

---

## 9. Compatibility and safety

**Brick model (BLE only, no UART):** a rejected image is harmless; an accepted image that
crashes before BLE comes up is permanent. Rules:

1. **Keep new code off the boot path.** Logo, WatchMain + the selected face, StatusBar
   initialisation and the startup routine run at every boot. A bug there could prevent DFU from
   coming up. New code goes first into screens the user must open on purpose. A crash there should
   reboot to a working face with DFU available (to be confirmed by P0 (2)).
2. **Popups are semi-boot-path.** Notification, alarm and charging popups open on their own, so
   they get changes only after the same code has been proven on an opt-in screen.
3. **Never persist a setting that selects new code at boot** (e.g. a face id that points to new code).
4. **One change set per flash.** Disassembly diff review, Unicorn emulation of every patched
   function, and SHA/CRC self-checks before each flash.
5. **Rollback ready:** before every app flash, build the previous known-good image with version
   N+1 (`tools/s100_mods.py` + `rehash_rtl_image.py`). For UI packs, keep the last good pack with a
   higher revision.
6. **Ordering:** pack before app. Appended images are invisible to the old app, so a pack
   that adds images is safe to install first.
7. Battery > 50 %, watch close to the PC, the existing safety checklist in custom-firmware-plan.md.
8. **Do not touch:** DFU/OTA code, BLE stack, flash driver, the RAM-init ranges `0x890898–0x8974D0`
   (never use zero runs there as caves), image header fields.

**Memory and performance budget:**
- Code: ≤ 6.9 KB in caves. Rough per-feature cost: haptic tick ~60 B, spring slide ~150 B,
  popup slide ~120 B, each new screen 300–800 B. That is enough for P5 + ~4 screens; leave ~1 KB spare.
- RAM: new state in the free 12 KB at `0x21951C` (confirm by a no-op flash that the area stays
  unused: [medium-high]). The GUI does not use the heap; don't start.
- Pack: 520 KB growth. Budget ~150 KB for animation frames, ~100 KB for navigation arrows and new
  screens; leave the rest.
- CPU/battery: screen-on time and backlight dominate power use. Animations add only during
  transitions. Haptic ticks are ~30 ms pulses. Always-on views must not run timers faster than 1 s.

**Recovery status:** BLE re-flash of the app (B1–B5) and UI pack (rev 1–4) is proven, including
recovery from dropped pack transfers. [recovery-plan.md](recovery-plan.md) predates this and still
says "not verified". It should be updated separately.

---

## 10. Open questions (resolved in P0)

- Real frame time and touch report rate.
- Crash behaviour (HardFault handler / watchdog reset).
- Settings save routine and which fields are synced to the phone.
- Raw-tail image dimensions (pickers, breathing, alarm rollers).
- Touch-down event, swipe direction signs, long-press duration.
- Breathing frames, per-sport SportDetail layouts, alarm snooze.

## 11. Decisions for the owner

1. Which 4 new screens get the free slots (proposal: Navigation, Desk clock, Watch settings, widget stack).
2. The swipe map around the face (proposal: down = quick panel, up = notifications, side = widgets, button = apps, like CMF).
3. Default launcher: list (3 large rows) or grid (2 large columns / staggered).
4. Whether to drop rarely used pages from the widget chain (e.g. Temperature).
5. Go-ahead for P0 + P1 (no flashing), then a review before any flash.

---

## 12. P0 results and P1 drafts (2026-10-30)

All offline (disassembly + Unicorn emulation of the stock code). Nothing was sent to the watch.

### 12.1 Tools added

| Tool | What it does |
|---|---|
| `tools/s100_screens.py render/all` | Runs each screen's **real constructor and build function** in Unicorn (ROM helpers stubbed, LCD skipped) and draws the resulting widget list with pack art. Works for 63 of 68 screens. `--mod NAME` applies an `s100_mods.py` patch set first, `--ui` takes a modded pack, so a preview shows exactly what a build would draw. Galleries: `research/screens/rev4/` (installed look) and `research/screens/v5_draft/` (draft) |
| `tools/s100_screens.py nav` | Feeds each screen's real touch / key handler a synthetic swipe or button press and reports the target screen. Reproduces stock navigation exactly; used to verify every navigation patch |
| `tools/s100_ui.py` | Now exports/rebuilds the 19 uncompressed tail strips (`raw_XXXXXX.png`; round trip byte-identical) and grows the pack (`build --append DIR`: images appended after the tail, size fields + CRC + SHA fixed, `<out>.append.json` = flash address map) |
| `tools/ui_dots.py` | Dot-matrix (5×7, CMF style) digit frames for chosen digit sets, appended to the pack, and the app pointer patches that switch the screens to them |
| `tools/s100_mods.py` | Draft mods `c1_layout` (layout + navigation) and `c1_full` (+ dot numerals, paired with `research/ui/build/ui_v5_draft.bin`) |

### 12.2 Findings (answers to §10)

| Question | Answer | Confidence |
|---|---|---|
| Crash behaviour | Watchdog enabled in ROM (OTP: 1024 Hz, 4095 ticks ≈ **4 s**, reset all), kicked only by a 2 s hardware timer → message `0x19` → `WDG_Restart` in the **app task**. The GUI, BLE callbacks and DFU all run in that one task. A hang or fault anywhere stops the kicks → reset after ~4 s. App fault handlers are `b .` loops; the ROM HardFault end is unknown, but the watchdog resets either way | high (hang), medium (fault) |
| Boot path | power-on `0x830E36`: battery ADC, settings load, Logo, then WatchMain (bound) or Binding. A fault in the Logo / face / first-screen code would **reset every ~4 s = brick** (a 4 s window is not enough for DFU) | medium |
| Settings persistence | `save_settings()` = `0x830654` (erase sector `0x97A000`, write the 0x2D0-byte struct from RAM `0x20BE84`). Settings screens only write RAM; saving happens every 10 min (if bound), before OTA reboot and at factory reset. A new settings screen writes RAM and may call `0x830654` | high |
| Frame time | measured in emulation (instruction counts), converted with an assumed cycle model: **12–23 ms** for full-screen RLE or a slide, 9–18 ms for mostly black (LCD = ST7789 over 8080 bus at 15 MHz, overlapped with rendering) → 45–60 fps possible. Slides are timer-paced: 40 ms steps, 4 frames ≈ 160 ms | instructions high, time medium |
| Touch events | 0/1 drag, 2 tap (on release), 3 long press (≈1.4 s), 4/5 short drag (snap back), 6–9 swipes. **No touch-down event**, so pressed-button states need code in the touch driver path — reclassified from P to **P (driver hook, higher risk)** | high |
| Swipe directions | 6 = finger right→left (t3), 7 = left→right (t4), 8 = up (t6), 9 = down (t5). Stock face: R→L widgets, L→R quick panel, down notifications, up apps; button short = screen off, long (1.0 s) = power-off dialog | high (code) |
| Raw tail | 19 strips, big-endian RGB565: breathing duration/speed, timer/DND rollers, menu style, brightness (25/50/75/100), timeout (5/10/15), vibration (High/Medium/Low), alarm rollers. Same-size replacement is always possible | high |
| Dot numerals | **None of the 52 large digit sets fit their stock slots as dots** (stock condensed digits RLE-compress to ~6 B/row). Dots need pack growth (R+) plus app pointer patches (D): ~11 KB per set, ~160 KB for the 14 sets in the draft. 53 sets are reached only through frame tables / literal pools, so the switch is pure data | high |

### 12.3 Draft builds (not flashed)

- **`c1_layout` (app v1325)** = installed v1324 (`b5b_worldclock`) plus:
  - **Navigation** (25 template words). Face: swipe down = quick panel, up = notifications,
    R→L = widget chain Activity → Heart rate → Sleep → Weather, L→R = Music, button = app list,
    long press = power-off dialog (unchanged). Quick panel closes by swiping up, notifications by
    swiping down. Temperature leaves the chain (still in the app list).
    Verified with `s100_screens.py nav` on every affected screen, also with grid style set.
    Note: the button opens the **list** launcher even when Theme = grid (action 14 always opens the
    list). Making the button follow the Theme setting needs a small code patch (P5).
  - **App list:** 3 rows of 93 px instead of 4 × 70 (6 instruction patches: row height, touch
    height, scrollbar range, scroll snap ×2, rows-per-screen). Verified at several scroll positions.
- **`c1_full` (app v1325)** = `c1_layout` + 247 pointer words (219 rodata frame-table words, 28 literal
  pool words; each one checked to be a real table entry or an `ldr`-loaded literal) moving 14 digit
  sets to dot frames: heart rate, weather, stopwatch/alarm, charging, low power, sleep, activity,
  workout, goal popups. **Watch-face digit sets are deliberately not converted** (boot path).
- **`research/ui/build/ui_v5_draft.bin` (UI pack)** = rev-4 art + 196 appended dot frames
  (+158 KB, limit +533 KB). Must be installed **before** `c1_full`.

### 12.4 Flash sequence proposed (each step needs the owner's go-ahead)

1. **P4 proof:** flash `ui_v5_draft.bin` (pack rev ≥ 5) with the **current** app v1324. The old app
   never reads the appended bytes, so the watch should look exactly as now. Proves the bootloader
   accepts a larger image 0xFFFE.
   **Result 2026-10-30: transfer OK on the first attempt (4,233,200 B, `ValidateFW 100301`), watch
   rebooted and reconnected on app 1324 (`ffd4 = 00 c0 52 00`). Installed UI pack is rev 5 → next ≥ 6.**
   Owner confirmed the watch looked unchanged.
2. **Navigation + list:** flash `c1_layout` (v1325). Risk: medium-low — data-only changes in
   rodata/immediates on non-boot screens (the face template is read only on touch/key, not at boot).
   Check on the watch: every swipe in §12.3, button, list scrolling incl. the last item, and that
   the notification list still scrolls with messages present.
   **Result 2026-10-30: v1325 installed first try (`ValidateFW 100301`, `ffd4 = 00 d0 52 00`), watch
   back up. Next app image ≥ 1326. Rollback ready: `research/mods/b5b_worldclock_v1326.bin`
   (v1324 content). **Owner confirmed every navigation and list check on the watch.**
3. **Dot numerals:** flash `c1_full` (v1326) only after steps 1 and 2 passed, and only with the
   matching pack installed.
   **Result 2026-10-30: all 247 pointers re-checked against the installed pack (valid frames, right
   size); v1326 installed first try (`ValidateFW 100301`, `ffd4 = 00 e0 52 00`), watch back up.
   Next app image ≥ 1327. Rollback (navigation kept, no dots): `research/mods/c1_layout_v1327.bin`.**
4. Then: face digit sets (boot path, last), settings pickers (raw strips, in place), quick-panel
   layout, P5 code features.

### 12.5 Settings pickers (built 2026-10-30, not flashed)

`tools/ui_pickers.py` redraws the 19 uncompressed picker strips in place (no growth, no app change):
selected row in CMF orange (was cyan), others grey/white, numbers as 5×7 dots, words in Bahnschrift,
screen-timeout "15" shown as ∞ (always on since b2_timeout), breathing "Sooth" → "Calm".
Pack `research/ui/build/ui_v6.bin` (rev 6) = rev 5 + these strips; append map identical to rev 5, so
the installed app v1326 keeps pointing at valid dot frames. Changed bytes only in the raw tail.
**Result 2026-10-30:** `ui_v6.bin` installed (`ValidateFW 100301`) on the third attempt; attempts 1–2
were BLE connect timeouts before any data was sent. Watch back up on app 1326. Next UI pack ≥ 7.
Quick panel: coordinates are single-byte immediates in builder `0x8587E2` (tiles at x 0x11/0x58/0xA0,
y 0x69 and x 0x34/0x7C, y 0xBF; touch areas next to each), but with fixed 64×64 tiles a data-only
re-layout gains little; the useful changes (inline brightness, more toggles) are code → moved to P5.

### 12.6 Dot numerals dropped (2026-10-30)

The owner did not like the dot numerals. Removed in two flashes: app `c1_layout_v1327.bin`
(navigation + 3-row list, no dot pointers; `ffd4 = 00 f0 52 00`), then UI pack `ui_v7.bin` (rev 7:
pickers keep the orange highlight and ∞ but use Bahnschrift numbers; no appended images, stock size).
Both installed first try. Next app ≥ 1328, next UI pack ≥ 8. `tools/ui_dots.py` stays for reference;
`tools/ui_pickers.py` now draws font numbers (`DOTS = False`).
Owner's next choice: car navigation screen, desk clock / always-on, watch settings page, quick panel
upgrades (all four) → phase P5/P6, built in C (`firmware/s100_ext/`).

### 12.7 Feature release c2 (built 2026-10-30, not flashed)

Owner's choice: car navigation screen, desk clock / always-on, watch-settings page, quick-panel
upgrades. Source `firmware/s100_ext/ext.c` (C, arm-none-eabi-gcc 14.2, `-Os`), built by
`tools/s100_ext.py` into mod `c2_features` (app **v1328** = c1_layout + 69 patches, 4.3 KB). Pairs with
UI pack **`ui_v8.bin`** (rev 8 = rev 7 + 13 appended images: 5 quick-panel tiles, 8 navigation arrows).

| Part | How | Where |
|---|---|---|
| Desk clock | new screen in the FactoryAgingTest slot (`0x20DA1C`, id 0x36 = exempt from wrist-down screen-off): date, 37×44 digit time (+AM/PM), weather now/low/high, battery/charging, BT. Refresh 1 s, never blanks; button or L→R swipe → face | quick-panel tile |
| Navigation | new screen in the FactoryBatteryTest slot (`0x20DA54`, id 0x37 → 0x36): arrow, distance, street, speed, ETA. Opened by a notification whose text starts `NAV|dir|dist|street|speed|eta` (hook at `0x836D44` after the ack: such texts skip the popup and the notification-history flash writes). Back to the face after 90 s without updates | `tools/s100.py nav` / `cardemo` |
| Watch settings | new screen in the FactoryTpTest slot (`0x20E35C`): 12/24 h (`+0x66`), always-on (`+0xFA` 10 s ↔ 65520 s, timer restarted), tap vibration (`+0x2BF`, ours); saved by `save_settings` on exit | quick-panel tile |
| Quick panel | 3×3 grid (stock tiles moved by immediates; 4 new tiles added by wrapping the build tail call at `0x859012`); brightness tile cycles 25/50/75/100 % in place (`0x858634`); always-on tile; Find phone, Watch settings, Desk clock tiles; date moved into the top bar | — |
| Tap tick | hook in the hit test tap path (`0x84341E`): `motor_vibrate(1,2)` (keeps DND / low-battery rules) then shortened to 40 ms; off via Watch settings | — |
| Charger | `gui_switch` charger gate (`0x844B7A`) also allows the clock and navigation screens; the plug/unplug UI handler (`0x83DDBC`) does not switch away from them | — |
| Safety | UTE factory commands redirected to the echo path (no factory code reachable); HeartCheck descriptor functions → `ext_nop`; no `.data/.bss` (state at RAM `0x21B000`) | — |

Verified offline with `tools/s100_screens.py` running the patched image: all four screens render;
taps on all 9 tiles and the 3 settings rows do the right thing (switch targets, settings values,
backlight call, tick); swipe/button on the new screens; charger gate (clock/nav allowed, HeartRate
still refused, charging screen still shown). `nav_check` accepts `NAV|…` and passes other texts.
Not testable offline: the tick's feel (40 ms), real-time refresh, the C5 path end to end.
Code that can run at boot: only the charger gate and plug trampolines (two compares each).
Install order: `ui_v8.bin` first, then `c2_features_v1328.bin`. Rollback: `c1_layout_v1329.bin`
(UI pack v8 is harmless with it).
**Result 2026-10-30:** `ui_v8.bin` installed (rev 8), then `c2_features_v1328.bin` installed on the second
attempt (`ValidateFW 100301`, `ffd4 = 00 00 53 00`); the watch booted and reconnected. A test frame
(`tools/s100.py nav right 200 "MG Road" …`) was accepted by the watch. Next app ≥ 1329 (rollback
`c1_layout_v1329.bin` is that version), next UI pack ≥ 9. On-watch checks pending from the owner.

### 12.8 Release c3: charging dock + mockup restyle (built 2026-10-30, not flashed)

Owner's mockup (CMF-like widget screens). App **v1330** (`c3_dock`, 68 patches, 5.3 KB code) + UI pack
**rev 9** (`ui_v9.bin`, +292 KB appended: 74 images). Preview: `research/screens/v9_preview.png`.

| Mockup window | Result | How |
|---|---|---|
| Dock Mode / AOD Digital / Charging Face | new dock screen (the former desk clock), 3 styles; opens by itself on the charger (`charger_change` replaces the stock charger UI call at `0x83DDBC`, only on state change; boot-from-charger left to stock); untouchable (touches ignored, never blanks); button on the charger cycles styles; style set from the app (`CFG|dock=N` saved in settings `+0x2BE`, 3 = stock charging screen; `CFG|show=N` opens it now) | C + appended digit/ring/icon art |
| Navigation | blue arrows, 56×84 bold distance digits, street, speed + ETA line | C + art |
| Quick Controls | rounded-square tiles (stock 888-894 in place + our 5) | art |
| Music Control | dark disc, orange accent arc (decorative: stock has no song position), orange play circle | art (725/723/724) |
| Weather Glance | 16 flat weather icons (523-538) | art |
| Find Phone | phone + animated blue waves (657-664) | art |
| Charging (stock, when dock = off) / low battery | green / red rings (989-993, 1023) | art |
| Heart Rate / Sleep / Notification / Incoming Call | red heart (crisp, 478-B slot), purple moon background, green bubble, red decline | art |
| Not possible on stock data | AOD analog (needs the rotated-image widget), sleep-stage bars (no stage data), call answer button (no answer action), focus-timer ring (no ring images in CountDown) | — |

Verified in the emulator: 3 dock styles render; `CFG|show/dock` work; plug-in auto-docks for settings 0-2,
setting 3 hands over to stock; unplug from an auto-dock hands over to stock (face); plain notifications pass;
all 74 appended images referenced by the app decode in the pack. Companion app 0.2 adds the
"Charging & always-on" settings. Install order: `ui_v9.bin`, then `c3_dock_v1330.bin`.
**Result 2026-10-30:** the first `ui_v9.bin` (body length 4,366,998 = 2 mod 4) was rejected at its last
buffer on every attempt (status 0x07, reply offset 0x42A000); all earlier packs had a body length that
was a multiple of 4. `s100_ui.py --append` now pads the body to 16 bytes; the padded rev 9 (4,367,008)
installed (`ValidateFW 100301`), then `c3_dock_v1330.bin` installed first try (`ffd4 = 00 20 53 00`), watch
back up. Next app ≥ 1331, next UI pack ≥ 10. Note: stopping a background flash job left its
`openwearota` process running and holding the BLE link — kill it explicitly before a new attempt.

### 12.9 Quick panel rebuilt (c4, built 2026-10-30, not flashed)

On the watch (owner's photo, v1330) the stock date was split: `0x84383C` draws the day digits (which
c2 moved into the status bar) *and* the month / weekday as text at fixed positions behind the first tile
row; two gear icons looked alike; brightness had no level. App **v1331** (`c4_panel`) + UI pack
**rev 10** (`ui_v10.bin`, adds 16 images: 12 tiles + 4 level bars, `tools/ui_qp_art.py`):
`qp_build` runs the stock builder (keeps all its logic and on/off images), then moves its 5 tiles and
their touch areas into the 3×3 grid by matching image / callback addresses, swaps in the new tiles,
drops the stock date widgets (type 3 texts and the 12×17 digits) and adds one status-bar date line,
the always-on / find phone / watch settings / desk clock tiles and a brightness level bar. Grid:
DND · Brightness · Always-on / Raise · Flashlight · Find phone / Watch settings · Desk clock · Settings.
Emulator: both date branches clean; all 9 taps do the right thing.
**Result 2026-10-30:** `ui_v10.bin` and `c4_panel_v1331.bin` both installed first try (`ValidateFW 100301`),
watch back up on app 1331. Next app ≥ 1332, next UI pack ≥ 11.
**c5 (2026-10-30):** on the watch the month / weekday items of the stock date still showed over the
first tile row (they come from a language-dependent path the emulator cannot reproduce, and were not
type-3 text). `qp_build` now keeps only the stock tiles and the status bar's BT / battery items and
drops everything else; tiles are 68 px on a 12/86/160 × 48/122/196 grid (widget w/h set to 68). App
**v1332** (`c5_panel`) + UI pack **rev 11** (`ui_v11.bin`).
**Result 2026-10-30:** `ui_v11.bin` + `c5_panel_v1332.bin` installed first try, watch back up. Next app ≥ 1333, next UI pack ≥ 12.

### 12.10 Release c6 (built 2026-10-30; shipped inside c7, see 12.11)

App **v1333** (`c6_text`) + UI pack **rev 12** (`ui_v12.bin`, 122 appended images, +398 KB):
- **Text fix:** every text widget our code adds now sets widget `+0x20 = 1` (use font tables), like
  stock builders (0x851FA8). Without it the watch drew none of our text (quick-panel date, dock battery
  %, watch-settings labels, navigation street/speed).
- **Quick panel:** squarer watch / phone glyphs (always-on, raise, find phone tiles).
- **Always-on display** (owner's reference): dock style 1 redrawn — dot-matrix 4×6 time (white hours,
  orange minutes, grey colon), "F R I" / "OCT 30", weather outline icon + temperature, battery │ steps
  (steps = settings `+0x14`). Shown at minimum backlight (`backlight_apply` with 25, setting untouched,
  restored on exit); redrawn once a minute. New setting `S_AOD` (`+0x2BD`): the screen-off timer path
  (`0x84236C`, was `b.w 0x8464FA`) shows this screen instead of turning off (not for popups, navigation,
  battery ≤ 10 %); button returns to the face. Switched from the quick-panel tile, Watch settings, and
  the app (`CFG|aod=0/1`; companion app 0.3).
- **Code size:** stock functions are now linker symbols (direct BL; all 46 calls verified to land on
  the stock entry points, no BLX), name tables packed; code in three caves (0x84D600, 0x85F460,
  0x84FCC4), 6.7 KB.
Emulator: AOD hook on/off, popups unaffected, dimming restores, dock styles, charger, CFG/NAV, all
9 quick-panel taps.

### 12.11 Release c7: usable while charging, wake options, settings sync (INSTALLED 2026-10-30)

Flashed 2026-10-30: UI pack rev 13 (`ui_v13.bin`, 2nd attempt; 1st dropped the BLE link at 77%) then app
`c7_wake_v1334.bin` (ValidateFW 100301, first attempt). Readback ffd4 `00 60 53 00` = r1334, battery 100%.
The grown app image (+2.5 KB tail at 0x8974D0) was accepted by the bootloader. c6 (12.10) is included in it.
On-watch checks of each behaviour are still owed by the owner.

App **v1334** (`c7_wake`) + UI pack **rev 13** (`ui_v13.bin`, adds the watch-settings row). The app image
**grows** for the first time: 2.5 KB of code (`t_*` functions + all constants) is linked after the stock end
at 0x8974D0 (`TAIL` in `tools/s100_ext.py`); `tools/s100_mods.py grow_image` fixes the MP-header TLVs,
the control-header payload length and pads the body to 16 bytes, then the SHA-256 is recomputed. The app
bank size is unknown (OEM header 0x801000 not in our files); the running firmware's DFU code checks the
size against the bank, so an image that does not fit is refused, not written.

| Owner's point | Implementation |
|---|---|
| AOD switchable from watch, Android, Windows | quick-panel tile, Watch settings row, `CFG|aod=0/1`; Android 0.4 "Display & wake", Windows app "Display & wake" panel; listed under **Favourites** in custom-firmware-plan.md |
| Usable while charging | gui_switch charger gate allows every screen once booted (d154+0xDB ≠ 0; powered-off charge-only state keeps the stock rule); idle wake goes to the face, not BatteryCharging (0x851548 → nop); stock charging screen: button → face, long → power-off (its +0x28 init word → `t_charge_key`); dock is a normal screen (tap / swipe / button → face) |
| Timeout → AOD or off, also on the charger | screen-off hook (all screens) + dock timer 1 → `t_dock_timeout` (AOD if enabled, else screen off) |
| Touch / Raise / Button to wake | `S_WAKE` (+0x2BC: bit0 tap on, bit1 press off) and stock raise (+0x1BA with its mirrors +0x32, +0x1A6 b1). Button: `b.w 0x843160` at 0x83D486 → `t_button_wake`. Tap: touch-IC sleep method (init word 0x895ABC) → `t_tp_sleep` (no deep sleep when tap-to-wake is on) + dark-screen touch message (0x83D4CE) → `t_touch_wake`. Raise while AOD (display on) → face via 0x83226A; wrist-down on an exempt screen now resets the gesture state (0x835C46 → beq 0x835C1C). Safeguard: if all three are off, press-to-wake turns back on |
| Settings sync | the watch is the source of truth: `CFG|get` / `CFG|aod|tw|rw|bw|h12|vib|dock|show=…` (notification hook); the watch answers every CFG and reports after local changes with `7E 01 aod tap raise press dock h12 vib battery` on 0x33F2 (`ble_notify` 0x8364A4; 0x7E unused by stock and realme Fit 1.2.9). Apps no longer push settings on connect |

Emulator suite (`scratchpad c7test.py`): 30/30 — CFG get/set/report, safeguard, watch-settings rows, button / tap
wake on/off, touch-IC sleep choice, raise on AOD → face, charging gate booted vs powered-off, charging-screen
button, dock tap → face, dock timeout → AOD / off, all 9 quick-panel tiles, navigation.
Not testable offline: real power cost of tap-to-wake (touch IC kept out of deep sleep), feel of wake on the watch.

### 12.12 Release c8: layout audit, AOD after the reference, own AOD brightness (INSTALLED 2026-10-30)

Flashed 2026-10-30: UI pack rev 14 (2nd attempt; the 1st failed to connect) then app v1335 (first attempt),
both ValidateFW 100301. Readback ffd4 `00 70 53 00` = r1335, battery 100 %. On-watch checks owed by the owner.

App **v1335** (`c8_aod`, `research/mods/c8_aod_v1335.bin`) + UI pack **rev 14** (`ui_v14.bin`; adds 61
`o_aod_*` images after every earlier one, so no address used by v1334 moves and v1334 keeps working on
rev 14). Companion apps: `dist/S100-Companion-0.5.apk`, Windows `tools/s100_app.py`.

Root causes found (owner's report: date cut off, battery % missing, AOD bright and "like a normal screen",
menu not reachable from every page):

| Symptom | Root cause | Fix |
|---|---|---|
| Text partly cut / missing on our screens | `add_text` stores `y + 12` and height `box / 2`; the band renderer `0x841938` skips a widget in every band that starts below `y + height`. Our box 28 gave height 14 for a 24 px font-0 line, so the lower part vanished wherever a band boundary fell inside it. The +12 also put every label 12 px lower than intended | `text()` takes the top of the 24 px cell and passes box 56 (as stock, height 28); all call sites re-laid out (row text centred, dock date centred off the round corners, nav lines 212/240) |
| AOD too bright | `backlight_apply` `0x83C2CC` drives a one-wire LED driver with `16 − S_BRIGHT·13/100` pulses (15 = dimmest) and resets `S_BRIGHT < 25` to 50, so the AOD's "25" was the stock minimum (13 pulses) | clamp relaxed to `< 1` (`0x83C2D6`); AOD level 0–3 → `S_BRIGHT` 5/20/28/36 → 15/14/13/12 pulses, set on entry and again on the first tick (a wake still in flight can re-apply the normal level) |
| AOD looks like a normal screen | font-0 text (24 px) and content near the round corners | dedicated layout measured from the owner's reference: word images (letter-spaced weekday, grey month), 8×14 sprite digits via `add_digits` + frame tables, outline icons at reference size, ~30 px from the corners |
| Lowering the wrist turned the screen off even with AOD on | wrist-down path calls `screen_off` directly (`bl 0x8464FA` at `0x835C6C`) | → `t_wrist_down` (AOD when enabled; stays when already AOD) |
| Unplugging while the AOD shows left it | `charger_change` handed the unplug to the stock handler | stays in AOD |
| Quick panel only from the face | swipe-down word (5) of the side pages' navigation templates was 0 | set to the quick panel for activity / sleep / weather / music; heart rate handles vertical swipes itself → trampoline at `0x850BCC` |

New settings: AOD level in `S_WAKE` bits 4–5 (`CFG|ab=0..3`; report byte 10, 11-byte report). Watch
settings has two pages (swipe up / down): **Display** = Always-on, *Show always-on* (only while enabled),
AOD brightness (Min/Low/Mid/High), 12-hour time, Tap vibration; **Wake** = Tap / Raise / Press to wake.

Previewer fixes: text drawn at its stored position with font-0 advances and clipped to its height (so a
too-small box shows up offline); only the instance's `+0x33` widgets are drawn (slots past it hold the
previous screen's widgets, which the watch does not draw).

Emulator suite (`scratchpad c8test.py`): 38/38 — render checks (no text widget under 24 px, all widgets on
screen) for AOD, dock styles 0/1/2, quick panel, navigation, both watch-settings pages; timeout → AOD at
level 0 with the saved brightness restored; `CFG|ab` live; 11-byte report; first-tick re-dim; wrist down
×3; charger plug / dock timeout / unplug; watch-settings actions; swipe down → quick panel from the face and
five side pages; button → menu; CFG set-all, safeguard, navigation.
Not testable offline: perceived AOD brightness per level, exact font-0 glyph look, band boundaries.

### 12.13 Release c9: launcher after the reference, quick-panel battery %, SpO2 (INSTALLED 2026-10-30)

Flashed 2026-10-30: UI pack rev 15 then app v1336, both first attempt, ValidateFW 100301. Readback ffd4
`00 80 53 00` = r1336, battery 91 %. On-watch checks owed by the owner.

App **v1336** (`c9_apps`) + UI pack **rev 15** (`ui_v15.bin`). Pack space: rev 15 drops unused appended
art (rev-12 light digits `h_lw`/`i_lo`, `m_aod_c..g`, ~74 KB) to stay under the bank-5 limit, so image
addresses after them **move**: v1335 must not run on rev 15 for long — flash v1336 right after the pack.

- **Quick panel battery %** missing at 100 %: the stock builder starts the 14 px battery digits further
  left the more digits there are (x 133 at 100 %, 147 at 9 %); the keep-list required x ≥ 140. Battery
  digits are now kept by frame width (14 px; the stock date uses 12 px).
- **App list** (stock 4 × 70 px rows again; c1's 93 px row patches are left out of c9): every row is one
  220 × 55 pill made of two images the stock builder already places: icon part 55 × 55 at x 8 (colour disc,
  white glyph; size `0x851F5A/5E`, x `0x851F7C`) and label part 165 × 55 at x 63 (name + chevron; width
  `0x852014`, x `0x85202E`, the special 145 px case `0x85200E` bypassed). Tables `0x88B718` / `0x88B7A8`
  repointed to `p_apps_*` (tools/ui_apps_art.py). Scrolling, snapping and hit-testing are stock.
- **App grid**: table `0x88CE3C` → 64 × 64 rounded dark tiles with the glyph in the app colour (Workout on
  orange); stock 3 × 92 px geometry (row height is tied to the grid's scroll / touch math).
- **SpO2**: thin ring + drop (`IMG1539`), white-on-black value digits and % (`IMG1522–1535`, `1537`; were
  white-on-red themed orange), "Measure" pill (`IMG1536`, two-level text to fit its 2488 B slot). No
  progress arc: a static arc would suggest a reading that was not taken.
- **Heart rate**: unchanged layout (its bar chart is a type-7 array at absolute positions computed by stock
  code); a smoother heart does not fit IMG1476's 478 B slot.

Emulator suite (`scratchpad c9test.py`): all 38 c8 checks + quick-panel battery digits kept at 100 / 64 / 9 %,
list rows / icons geometry, list taps open Temperature / Workout / Heart rate, list scrolled by 4 rows, grid
9 tiles, grid taps open Temperature / Workout / Heart rate. (The "widget on screen" warnings for the list,
grid and heart-rate screens are the stock off-screen scroll rows and the chart container.)
Not testable offline: the look of the RLE-encoded art on the panel, scroll feel.

Later in c9 (same file names): quick-panel status bar on one centre line with two groups on the tile
grid's edges (link + date at x 20 / 54, battery right-aligned to x 220), date and battery % drawn with one
image set (`q_qs_*`, Bahnschrift 20, 11 px digits; `t_qp_status`). Firmware preview tab in
`tools/s100_app.py` (`tools/s100_preview.py`): runs a built app + pack in the emulator with taps, swipes,
button, screen timeout and simulated battery / time / AOD / charging. Clean-up: unused state fields, the
old `.text3` section and rev-12 art helpers removed; old builds and flash logs moved to
`research/archive/` (git-ignored). Final files: `c9_apps_v1336.bin` (SHA-256 field valid, rev 1336,
567,468 B) + `ui_v15.bin` (image 0x45F2DC of 0x464C00). Rollback pair kept: `c8_aod_v1335.bin` + `ui_v14.bin`.

### 12.14 Release c10: settings survive a power-off (INSTALLED 2026-10-30)

Flashed 2026-10-30 (app only, 3rd attempt; the first two did not connect), ValidateFW 100301, readback
ffd4 `00 90 53 00` = r1337, battery 89 %. Power-cycle check owed by the owner.

App **v1337** (`c10_prefs`), same UI pack rev 15 (only the app changes). Owner's report: Grid chosen as menu
style, after power-off / on the menu is a list again.

Root causes:
1. **Watch-side changes were never saved.** `save_settings` (`0x830654`, block `0x20BE84` → flash
   `0x97A000`) has 8 callers: phone commands, a periodic save at hh:10 when hh % 10 == 0, factory /
   reset paths. Neither the settings screens (menu style `+0x220`, brightness `+0x188`, vibration
   `+0x1F5`, timeout `+0xFA`, DND, raise) nor the quick-panel tiles nor power off (`0x831660`) save.
2. **The button always opened the list.** Key action 14 (`0x8433A4`) switches straight to
   MainMenuList; the menu style is applied only inside the slide code (`0x844D74`, `0x844F6E`), so the
   c1 button mapping ignored it.

Fixes: preference fields (found by driving every settings screen in the emulator and diffing the block:
`+0x32, 0x64–0x66, 0xEE–0xFB, 0x11C, 0x188, 0x1A4–0x1A6, 0x1BA–0x1BB, 0x1F5, 0x220, 0x2BC–0x2BF,
0x2CC–0x2CD`; `+0x1A0/0x1A1` are counters and excluded) are hashed (`t_prefs_sum`); at every screen-off
timeout (`aod_screen_off`, dock timeout) and on power off (`bl 0x83162C` at `0x831664` → `t_power_off`)
the block is saved when the hash differs from the last save. No write below 3 % battery. Our own saves
(CFG from the apps, watch settings, quick-panel AOD tile) go through `t_save` and move the baseline. Key
action 14 → trampoline: grid when `+0x220 == 1`, else list. Nothing is written at boot; stock defaults
apply only when the stored block is used as is.

Emulator (`scratchpad c10test.py`): 18/18 — button → list / grid by style; first screen-off saves once,
no write without change; a write after each of menu style, brightness, vibration, raise, timeout, DND,
AOD; none for steps / counters / battery; power off saves after a change, not at 2 %; CFG saves once and
the next screen-off does not; AOD on timeout unchanged. c9 suite on c10: unchanged.
Not testable offline: the flash write itself and a real power cycle (verify on the watch).

### 12.15 Release c11: uniform app-grid spacing (installed as part of c12 / r1339)

App **v1338** (`c11_grid`), UI pack rev 15 unchanged. The grid's columns step 76 px (64 px tiles, 12 px
gaps) but rows stepped 92 px (28 px gaps). The row height lives in three places that must agree: the
builder (`0x865404` r7), the touch handler's snap step `(0x114 − m) / 3` (`0x865940`, `0x865966`) and the
scroller's height (`0x8659EC`, 3 rows per screen). All now use 76 (height 228 = 3 × 76). Rows start 26 px
lower (trampoline for `subs r0,r6,#1; mul fp,r0,r7` at `0x865458`) so three rows sit centred (32 px
margins) and the touch cells (same y) move with the tiles; tile offset in the row 20 → 6 (`0x865486`);
rows drawn per frame 5 → 6 (`0x86555A`) so no strip is missing at the bottom while scrolling.
Emulator (`scratchpad c11test.py`): 24/24 — full rows at y 32/108/184 and x 12/88/164 (12 px gaps both
ways) at scroll 0 and at the last page (−228); all 18 tiles open their app. c9 / c10 suites unchanged.

### 12.16 Release c12: Settings list icon inset (INSTALLED 2026-10-30)

Flashed 2026-10-30 (app only, first attempt), ValidateFW 100301, readback ffd4 `00 b0 53 00` = r1339, battery
87 %. Includes c11 (grid spacing), which was never flashed on its own.

App **v1339** (`c12_inset`) = c11 + Settings (FunctionList) row icons at x 20 (`movs r2,#0xE` at
`0x84F3CE` → `#0x14`), 10 px inside the 220 px row background at x 10 like the Workout list; labels stay
at x 70. Audit of the list screens: app list (disc 9 px inside its pill), Workout list (10 px), DND,
heart-rate info, weather list, workout summary already have ≥ 9 px; only Settings had 4 px.
Suites on c12: grid 24/24, preferences 18/18, c8/c9 checks unchanged.

### 12.17 Release c13: grid scrolling glitch (INSTALLED 2026-10-30)

Flashed 2026-10-30 (app only, first attempt), ValidateFW 100301, readback ffd4 `00 c0 53 00` = r1340, battery
87 %. Owner confirmed scrolling is smooth (2026-10-30).

App **v1340** (`c13_gridscroll`). Owner: the 76 px grid (c11) glitches while scrolling. Cause: c11 changed
the row step in the builder, the release snap and the scroller call, but the grid code computes
`(0x114 − m) / 3` (= 92) in five more places: finger drag (`0x865A82`), momentum timer (id 4, handler
`0x8655AC`: frame offset `0x86571E`, end-of-fling snap `0x865626`) and two release cases (`0x865BEC`,
`0x865C12`). Mixed 92 / 76 made rows jump during a drag / fling and a fling end on a multiple of 92
(up to 38 px off). All now use 228 / 3 = 76; a scan of the grid code (`0x8653F0–0x865E00`) finds no
other row step (`0x865C5C` is the tap zone 0..276 and stays). The momentum animation could not be driven
faithfully in the emulator; grid layout / taps (24/24), preferences (18/18) and c8/c9 suites pass.
