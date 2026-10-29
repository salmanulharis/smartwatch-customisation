# Always-On Display Analysis — realme TechLife Watch S100

Last updated: 2026-10-28.

---

## 1. Display hardware

| Property | Value | Confidence |
|----------|-------|------------|
| Panel | 1.69" IPS LCD, 240×280 px | **[confirmed]** |
| Brightness | 530 nits peak (GSMArena spec) | **[likely]** |
| Controller | Unknown; probably ST7789-class SPI/QSPI | **[unverified]** |
| Backlight | LED, required for visibility (LCD, not OLED) | **[confirmed]** (LCD = no self-emission) |
| Resolution for dial | 240×280, max dial size 1 MB, compat level 1 | **[confirmed]** (`26 01` reply) |

**LCD vs OLED implication:** An LCD panel requires the backlight to be on for any content to
be visible. "Always-on" means "backlight always on" — this draws continuous power and
produces heat. True low-power always-on (like OLED where only lit pixels consume power) is
not physically possible with this display.

---

## 2. Four display modes evaluated

### Mode A: Native always-on display (hardware-supported)

**Status: Not available.**

The stock firmware has no always-on display option. The settings menu offers only 5, 10, or
15 seconds of screen-on time. There is no BLE command to change this (the `A9` byte 5 is
confirmed ignored by firmware disassembly). There is no "always-on" setting in the watch's
own menus.

The RTL8762C hardware *could* drive the display continuously, but the stock firmware does not
expose this capability.

### Mode B: Low-power clock with periodic refresh

**Status: Requires custom firmware.**

A custom firmware could render a clock face and keep the backlight on, refreshing only the
time digits every minute. This would be the ideal always-on implementation:

- Estimated power: backlight + SPI refresh ~20–40 mA (varies by brightness)
- Battery life on 260 mAh: ~6–13 hours continuously
- Suitable for docked/charging use; not for wrist wear

This mode requires custom firmware and is therefore blocked until a recovery path is verified.

### Mode C: Screen stays awake while connected (notification keep-alive)

**Status: Working on stock firmware. This is the current best option.**

Verified 2026-10-28: sending a UTE notification (`C5` packet) every 2 seconds keeps the
screen continuously lit with no dark gaps. At 4-second intervals, brief dark gaps appear.

**How it works:**
- Each notification wakes the screen and resets the screen-off timer
- At 2-second intervals, the timer never expires → screen stays on
- No vibration (type 4 = "other" with no vibrate command)
- Content can be time, date, weather, navigation, or any text

**Limitations:**
- Requires a connected BLE central (PC or phone) sending notifications continuously
- Watch displays the notification popup, not a custom clock face
- Notification text is limited to 160 bytes (UTF-16BE)
- Notifications may accumulate in the watch's notification list
- Power draw: backlight on + BLE active = higher than native always-on would be

**This is the implemented `deskclock` and `cardemo` mode in `tools/s100.py`.**

### Mode D: Screen wakes on user interaction only

**Status: Default stock behavior.**

The screen turns on when:
- The side button is pressed
- Raise-to-wake triggers (if enabled)
- A notification arrives

This is the standard smartwatch behavior and requires no modifications.

---

## 3. Recommended implementation by use case

### Desktop buddy (docked, on charger)

**Use Mode C now.** The watch is on a dock with power — battery life doesn't matter. The
companion app sends a clock + weather + status notification every 2 seconds. Screen stays
on continuously.

Content format (fits in 160 bytes):
```
14:32  Tue 28 Oct
29° Cloudy  Kochi
♫ Kesariya - Arijit
🔋 92%  📶 BLE
```

(Font limitations: no emoji rendering on this watch. Use ASCII: `92% BLE` etc.)

### Car/bike navigation (docked, charging via car USB)

**Use Mode C now.** The companion sends navigation frames every 2 seconds:

```
52 km/h  RIGHT 200m  MG Road
12.4km left  ETA 14:45
```

Verified working with `tools/s100.py cardemo`. Buzzes only at the turn point.

### Wrist wear (untethered)

**Use Mode D (default stock behavior).** Continuous screen-on drains the battery in hours.
For wrist wear, rely on raise-to-wake and button press.

### True always-on clock (custom firmware, future)

**Requires Mode B.** Design a minimal clock face that:
- Updates time digits every 60 seconds
- Updates date, weather, battery every 5 minutes
- Keeps backlight at minimum brightness
- Targets ~20 mA idle draw → ~13 hours on 260 mAh
- Shows BLE connection status

Blocked until custom firmware is possible (recovery path verified).

---

## 4. Power estimates

| Mode | Estimated draw | Battery life (260 mAh) | Needs charger? |
|------|---------------|----------------------|----------------|
| D: Screen off (idle) | ~2–5 mA | 2–5 days | No |
| C: Notification keep-alive (2s) | ~30–50 mA (backlight + BLE) | 5–9 hours | Yes for continuous use |
| B: Custom FW always-on (min backlight) | ~20–40 mA | 6–13 hours | Yes for continuous use |
| B: Custom FW always-on (max backlight) | ~50–80 mA | 3–5 hours | Yes |

These are rough estimates. Actual measurements require a current meter on the battery leads.

---

## 5. Heat considerations

The watch is intended for docked use (desk or car mount). Continuous backlight + BLE +
charging generates heat. Recommendations:

- Do not charge in direct sunlight or inside a hot parked car
- Use a ventilated dock
- If the watch feels hot, reduce screen brightness or increase notification interval
- Li-ion cells degrade faster above 45°C — monitor if the watch is in continuous use
