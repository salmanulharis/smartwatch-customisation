# TechLife S100 — UI resource pack format

Decoded 2026-10-29 from `RH288A_V000957_U0006_ui_1641738154_5635.bin` (4,075,524 bytes, UTE S3)
with `tools/s100_ui.py export` (read-only; output in git-ignored `research/ui/`).

## File layout

| File offset | Content |
|---|---|
| `0x000` | Realtek MP header TLVs: IC `RTL8762D`, image id field `0x0012` = `0xFFFE`, size `0x3E2E04` |
| `0x200` | Realtek image header (ic_type 9, ROM UUID `1d6a69f1…`, SHA-256 at `0x374`, same scheme as the app image) |
| `0x600` | **Payload** (flash address `0xACB400`) |

Payload header (0x40 bytes): ASCII `RH288AV000957_U0006` (+0x00), `0x01` (+0x1B),
u32 length of payload after the header (+0x1C), **CRC-32 (zlib) of payload[0x40:]** (+0x20),
rest `0xFF`. Both checked by the tool.

## Images

From payload `0x40` to `0x38C4FC`: **2,163 row-compressed RGB565 images stored back to back**
(no gaps, no per-image header):

```
u32 row_offset[h]          ; relative to image start; row_offset[0] = 4*h (gives h)
row  := group*             ; until the next row offset (last row: until w pixels)
group:= u8 n, u8 rep, n × be16 RGB565 colour ; each colour repeated rep times
```

Width = pixel count of a row (all rows equal). Seen widths 4–240, heights up to 280.
Black (`0x0000`) is the background in every image.

`0x38C4FC`–end (~350 KB): **uncompressed** RGB565 images; 33 firmware pointers land here
(e.g. full-width 240-px strips). Their sizes come from the code that draws them — not decoded yet.

## How the firmware finds them

The app image addresses payload offset `o` as flash `0xACB400 + o`. 1,804 of the 2,163 images
are pointed at directly (2,176 pointers; most in tables at firmware file `0x7C45C`–`0x7F2A8`, the
rest as literals near code). The other 359 are reached some other way (index arithmetic,
`movw/movt` pairs) or are unused — **open question**.

Screen positions, scrolling, list spacing and hit areas are in the **app code**, not the pack.

## Contents (by index, approx.)

Text labels are pre-rendered images in **English and Thai** (pairs). Groups seen: digit sprite
sets in many sizes/colours (`- . / 0–9 :`), app icons (menu, ~1258–1274), app titles, workout
icons + names, breathe animation frames, find-phone radar frames, HR/SpO2/temperature screens,
progress arcs (step/kcal rings in 11–12 steps), alarm/timer buttons, toggles, sleep art, status texts.
See `research/ui/sheet_*.png` after running the export.

## Reskin rules (derived)

1. **Keep every image's w × h.** Positions are fixed in code; a different size misaligns or
   overlaps, and lists/scrolling assume the stock sizes.
2. **Same compressed size or smaller** lets an image be replaced in place (pad the tail with an
   unused-but-valid encoding) — no firmware pointer changes. Larger images need a repacked pack
   *and* every pointer (incl. the 359 unexplained ones) updated in a new app image → much riskier.
3. Recompute payload CRC-32 and the image-header SHA-256 (`tools/rehash_rtl_image.py` scheme).
4. **Delivery: transfer proven 2026-10-29** (gear test pack, revision 1: `StartDfu` OK, full
   4,075,000-byte buffer-check stream, `ValidateFW 100301`, watch rebooted and reconnected on app
   1323; on-screen result: pending user check). Still a risky step: The pack is DFU image id `0xFFFE` = `IMAGE_USER_DATA`, which the
   RTL8762D SDK marks "only support unsafe single bank ota" (`patch_header_check.h`): it is
   written **over the live pack** (no second bank), sector by sector, and activated with
   `dfu_set_image_ready` after `VALID_FW` (`dfu_service.c`). An interrupted transfer leaves a
   half-written pack; the stock app drawing a broken image may fault before BLE comes up.
   Our driver already takes the image id from the file header, and resume (device-reported
   offset) is implemented. The vendor app delivers UI packs the same way in the field.
5. **Interrupted transfers (seen 2026-10-29):** the watch erases and writes 4 KB sectors in order,
   so a drop leaves new data before the cut, old data after it and one partly erased sector.
   With the same layout on both sides only the images in that sector are broken. The app kept
   running and advertising after two drops; once it stopped advertising until restarted. The
   driver cannot resume (it always restarts at 0), so retry the full transfer straight away:
   scan until the watch is seen, then flash, and repeat on a drop.
6. The firmware's 2,176 pointers match this pack's image offsets exactly, so app V001319 and
   UI V000957_U0006 are a pair; only rebuild packs from this file.

## Tooling

- `tools/s100_ui.py export` — decode to PNGs + `index.json`.
- `tools/s100_ui.py build <dir>` — replace `NNNN.png` images in place (same w×h; encoding padded
  to the stock length; refuses if larger), fix CRC-32 + SHA-256, self-check. The encoder
  reproduces all 2,163 stock images byte for byte; a no-op build equals the stock file.
- `tools/ui_cmf.py` — CMF-style replacement art (own drawings), reduced to the fewest colours
  that fit each stock slot. First item: Settings gear `1273` (48×48, 2,698 bytes).
