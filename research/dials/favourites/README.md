# Favourite watch faces

| Name | File | Notes |
|---|---|---|
| Dot-matrix (Nothing style) | `dotmatrix-nothing.bin` | 12-hour time, AM/PM, weekday + date, phone dot, 11-step battery, weather icon + temp. Saved 2026-10-29. |
| Widgets (dot-matrix time + cards) | `widgets-dotmatrix.bin` | Weekday, BT, battery pill, 12-h time, weather card (icon + condition + temp), date card, heart-rate card, battery ring with exact % (type 33), connection ring. Saved 2026-10-29. |
| Widgets + mini analog clock | `widgets-analog.bin` | Same as widgets, but the battery ring is replaced by a mini analog clock (hour/minute hands rotated by the watch). Saved 2026-10-29. |
| Duo (light theme) | `duo.bin` | Cream background, hour on a dark pill + minutes on a coral circle (chunky dot digits), AM/PM bubble, weekday + date, Bluetooth + battery pill, weather, dot-matrix heart rate. Saved 2026-10-29. |
| Duo 2 (light theme) | `duo2.bin` | Hour on a black circle, minutes on a coral pill (thin digits), AM/PM, dot-matrix weekday + date, Bluetooth + battery pill, step-goal dot column + step count, weather, dot-matrix heart rate. Saved 2026-10-29. |
| Duo 3 (light theme) | `duo3.bin` | Stacked thin time + AM/PM, weather bubble in a grey capsule, coral halftone circle over a black steps capsule, bottom circles: heart rate, step-goal grid, today's date. Saved 2026-10-29. |
| Duo 4 (light theme) | `duo4.bin` | Twin time capsules (hour on black, minutes on coral, dot digits) + AM/PM, weekday + date, weather card, black steps card, heart-rate card, battery dot pill, decorative circles. Saved 2026-10-29. |
| Duo 5 (light analog) | `duo5.bin` | Big analog dial (black hour / coral minute hands, coral gradient quadrant), weekday + date, Bluetooth + battery dots, weather bubble, steps capsule, step-goal dot capsule, heart-rate card. Saved 2026-10-29. |
| Duo 6 (light minimal analog) | `duo6.bin` | Dot ring dial with smooth black hour / coral minute hands, weekday + date, weather (icon + temp + condition), steps, battery pill, grey/coral decor circles. Saved 2026-10-29. |
| Blob (light) | `blob.bin` | Stacked metaball-dot time with coral accent dots, weekday + date, weather / steps / battery bubbles on an arc (battery: icon fill + LOW/MID/GOOD/FULL), decor circles. Saved 2026-10-29. |
| Dusk (dark analog landscape) | `dusk.bin` | White hour / coral minute hands, tick dots, weather bubble, vertical battery bar, step-goal dots, moon, sun and layered landscape with a wavy line. Saved 2026-10-29. |
| Dashboard | `dashboard.bin` | Weekday + date, Bluetooth pill, battery pill + exact % (type 33), dot-matrix 12-h time, weather tile, analog clock + heart-rate card, steps + goal bar card. Saved 2026-10-29. |
| World (dark, world clocks) | `world.bin` | Dotted world map, big coral dot-matrix time, weekday + date, live 2×2 world clocks (Mumbai / New York / Dubai / London), steps ring + odometer count, weather, heart rate. **Needs firmware mod `b5_worldclock` (v1323+).** City offsets fixed at build time (DST included): rebuild after a DST change (New York 2026-11-01). Saved 2026-10-29. |
| Grid (dark dot clock) | `grid.bin` | Dot clock (grey disc, 30-dot ring, coral minute dot, coral hour hand + white centre cap), sun / weather + temperature, mono 12-h time, 12×3 step-goal dot grid, bolt + 5 battery dots. Saved 2026-10-29. |

Re-install any of them (venv active, phone Bluetooth off):

```
python tools\s100_dial.py upload research\dials\favourites\<file>.bin
```
