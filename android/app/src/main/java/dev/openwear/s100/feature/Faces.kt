package dev.openwear.s100.feature

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import dev.openwear.s100.ble.DialFile
import dev.openwear.s100.ble.Protocol
import dev.openwear.s100.service.Hub
import kotlinx.coroutines.delay

/** Watch faces: the bundled gallery (assets/dials) and photo faces built on the phone. */
object Faces {
    data class Face(val name: String, val asset: String)

    fun gallery(context: Context): List<Face> =
        context.assets.list("dials").orEmpty().filter { it.endsWith(".bin") }.sorted()
            .map { Face(it.removeSuffix(".bin").replace('-', ' ').replaceFirstChar(Char::uppercase), "dials/$it") }

    fun preview(context: Context, f: Face): Bitmap? = try {
        context.assets.open(f.asset.removeSuffix(".bin") + ".png").use { android.graphics.BitmapFactory.decodeStream(it) }
    } catch (_: Exception) { null }

    /** Upload a dial file (same protocol and pacing as tools/s100_dial.py send_dial). */
    suspend fun upload(blob: ByteArray, log: (String) -> Unit): Boolean {
        val link = Hub.link.value?.takeIf { Hub.ready } ?: run { log("Watch not connected"); return false }
        Hub.dialProgress.value = 0f
        try {
            return link.session {
                val cfg = request(byteArrayOf(0x26, 0x01), byteArrayOf(0x26, 0x01), 5000)
                if (cfg == null || cfg.size < 16) { log("No dial config reply"); return@session false }
                val maxSize = ((cfg[11].toInt() and 0xFF) shl 24) or ((cfg[12].toInt() and 0xFF) shl 16) or
                    ((cfg[13].toInt() and 0xFF) shl 8) or (cfg[14].toInt() and 0xFF)
                if (blob.size > maxSize) { log("Face too large"); return@session false }
                if (request(byteArrayOf(0x26, 0x02), byteArrayOf(0x26, 0x02), 10_000) == null) {
                    log("Watch not ready"); return@session false
                }
                val step = link.maxLen - 3
                val packets = blob.toList().chunked(step).map { it.toByteArray() }
                var start = 0
                repeat(4) {
                    for (seq in start until packets.size) {
                        write(byteArrayOf(0x27, (seq shr 8).toByte(), seq.toByte()) + packets[seq], big = true)
                        if ((seq + 1) * step / 4096 != seq * step / 4096) expect(byteArrayOf(0x26, 0x03, 0x04), 3000)
                        else if (seq % 10 == 9) delay(40)
                        Hub.dialProgress.value = (seq + 1f) / packets.size
                    }
                    delay(3000)
                    write(byteArrayOf(0x26, 0x03, 0x00))
                    var reply: ByteArray?
                    do { reply = expect(byteArrayOf(0x26, 0x03), 15_000) } while (reply != null && reply.size > 2 && reply[2].toInt() == 4)
                    if (reply == null || reply.size < 3) { log("No final reply from the watch"); return@session false }
                    when (reply[2].toInt()) {
                        0 -> { request(Protocol.time(), byteArrayOf(0xA3.toByte())); log("Face installed"); return@session true }
                        3 -> if (reply.size >= 5) {
                            start = ((reply[3].toInt() and 0xFF) shl 8) or (reply[4].toInt() and 0xFF)
                            log("Resending from packet $start")
                        } else return@session false
                        1 -> { log("CRC check failed"); return@session false }
                        2 -> { log("Face too large"); return@session false }
                        else -> { log("Watch error ${reply[2]}"); return@session false }
                    }
                }
                false
            }
        } finally { Hub.dialProgress.value = -1f }
    }

    // ---------------------------------------------------------------- photo face
    enum class Layout { TOP, CENTER, BOTTOM }

    /** Photo (cropped to 240x280) + time, date, weekday and battery in [color]. */
    fun photoFace(photo: Bitmap, color: Int, layout: Layout, twelveHour: Boolean): Pair<ByteArray, Bitmap> {
        val bg = cropTo(photo, DialFile.W, DialFile.H)
        val bold = Typeface.create("sans-serif-condensed", Typeface.BOLD)
        val reg = Typeface.create("sans-serif-condensed", Typeface.NORMAL)
        val dw = 44; val dh = 76                                  // big digit cell
        val timeY = when (layout) { Layout.TOP -> 30; Layout.CENTER -> 96; Layout.BOTTOM -> 170 }
        val x0 = (DialFile.W - (4 * dw + 18)) / 2
        val digits = digitFrames(dw, dh, color, bold, dh * 1.05f)
        val colon = textFrame(":", 18, dh, color, bold, dh * 1.0f)
        val sw = 13; val sh = 22
        val small = digitFrames(sw, sh, color, reg, sh * 1.05f)
        val sep = textFrame("/", 9, sh, color, reg, sh * 1.0f)
        val dateY = timeY + dh + 4
        val week = (listOf("日", "一", "二", "三", "四", "五", "六") + listOf("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"))
            .map { textFrame(it, 48, sh, color, reg, sh * 0.95f) }
        val battery = (0..10).map { batteryFrame(30, 14, it, color) }
        val els = mutableListOf(
            DialFile.Element(17, 0, 0, DialFile.W, DialFile.H, listOf(rgb565(bg, bg, 0, 0, keepBlack = true))),
            DialFile.Element(57, x0, timeY, dw, dh, digits.map { rgb565(it, bg, x0, timeY) }),
            DialFile.Element(58, x0 + dw, timeY, dw, dh, digits.map { rgb565(it, bg, x0 + dw, timeY) }),
            DialFile.Element(7, x0 + 2 * dw, timeY, 18, dh, listOf(rgb565(colon, bg, x0 + 2 * dw, timeY))),
            DialFile.Element(59, x0 + 2 * dw + 18, timeY, dw, dh, digits.map { rgb565(it, bg, x0 + 2 * dw + 18, timeY) }),
            DialFile.Element(60, x0 + 3 * dw + 18, timeY, dw, dh, digits.map { rgb565(it, bg, x0 + 3 * dw + 18, timeY) }),
            DialFile.Element(15, 64, dateY, 48, sh, week.map { rgb565(it, bg, 64, dateY) }),
            DialFile.Element(63, 120, dateY, sw, sh, small.map { rgb565(it, bg, 120, dateY) }),
            DialFile.Element(64, 133, dateY, sw, sh, small.map { rgb565(it, bg, 133, dateY) }),
            DialFile.Element(14, 146, dateY, 9, sh, listOf(rgb565(sep, bg, 146, dateY))),
            DialFile.Element(65, 155, dateY, sw, sh, small.map { rgb565(it, bg, 155, dateY) }),
            DialFile.Element(66, 168, dateY, sw, sh, small.map { rgb565(it, bg, 168, dateY) }),
            DialFile.Element(8, 105, 254, 30, 14, battery.map { rgb565(it, bg, 105, 254) }),
        )
        if (twelveHour) {
            val ampm = listOf("AM", "PM", "AM", "PM").map { textFrame(it, 30, sh, color, reg, sh * 0.9f) }
            els += DialFile.Element(16, x0 + 4 * dw + 18 - 30, timeY - sh - 2, 30, sh,
                ampm.map { rgb565(it, bg, x0 + 4 * dw + 18 - 30, timeY - sh - 2) })
        }
        // preview thumbnail (type 10): the face with sample values, 240x240
        val preview = Bitmap.createBitmap(DialFile.W, DialFile.H, Bitmap.Config.ARGB_8888).also { pv ->
            val c = Canvas(pv); c.drawBitmap(bg, 0f, 0f, null)
            listOf(digits[4], digits[3], colon, digits[6], digits[5]).fold(x0) { x, f -> c.drawBitmap(f, x.toFloat(), timeY.toFloat(), null); x + f.width }
        }
        val thumb = Bitmap.createBitmap(240, 240, Bitmap.Config.ARGB_8888).also {
            Canvas(it).drawBitmap(preview, Rect(0, 0, 240, 280), Rect(17, 0, 223, 240), Paint(Paint.FILTER_BITMAP_FLAG))
        }
        els += DialFile.Element(10, 0, 0, 240, 240, listOf(rgb565(thumb, thumb, 0, 0, keepBlack = true)))
        return DialFile.build(els) to preview
    }

    private fun cropTo(src: Bitmap, w: Int, h: Int): Bitmap {
        val s = maxOf(w.toFloat() / src.width, h.toFloat() / src.height)
        val sw = (w / s).toInt(); val sh = (h / s).toInt()
        val sx = (src.width - sw) / 2; val sy = (src.height - sh) / 2
        val out = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        Canvas(out).apply {
            drawBitmap(src, Rect(sx, sy, sx + sw, sy + sh), Rect(0, 0, w, h), Paint(Paint.FILTER_BITMAP_FLAG))
            drawColor(Color.argb(70, 0, 0, 0))                    // slight dim so text stays readable
        }
        return out
    }

    private fun textFrame(s: String, w: Int, h: Int, color: Int, tf: Typeface, size: Float): Bitmap {
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color; typeface = tf; textSize = size; textAlign = Paint.Align.CENTER }
        var size2 = size
        while (p.measureText(s) > w && size2 > 6) { size2 -= 1f; p.textSize = size2 }
        val fm = p.fontMetrics
        Canvas(b).drawText(s, w / 2f, h / 2f - (fm.ascent + fm.descent) / 2, p)
        return b
    }

    /** 14 frames "- . / 0-9 :" (docs/custom-dial-format.md §3) */
    private fun digitFrames(w: Int, h: Int, color: Int, tf: Typeface, size: Float) =
        "-./0123456789:".map { textFrame(it.toString(), w, h, color, tf, size) }

    private fun batteryFrame(w: Int, h: Int, level: Int, color: Int): Bitmap {
        val b = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(b)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color; style = Paint.Style.STROKE; strokeWidth = 2f }
        c.drawRoundRect(1f, 1f, w - 5f, h - 1f, 3f, 3f, p)
        p.style = Paint.Style.FILL
        c.drawRect(w - 4f, h * 0.3f, w - 1f, h * 0.7f, p)
        c.drawRect(4f, 4f, 4f + (w - 13f) * level / 10f, h - 4f, p)
        return b
    }

    /**
     * RGB565 big-endian, pre-blended onto the background at (x, y) like the vendor app; fully
     * transparent pixels become 0x0000 (the watch's transparency key) unless [keepBlack], and
     * visible black is lifted to (17,9,17) so it is not treated as transparent.
     */
    private fun rgb565(fg: Bitmap, bg: Bitmap, x: Int, y: Int, keepBlack: Boolean = false): ByteArray {
        val out = ByteArray(fg.width * fg.height * 2)
        var i = 0
        for (yy in 0 until fg.height) for (xx in 0 until fg.width) {
            val c = fg.getPixel(xx, yy)
            val a = Color.alpha(c)
            var r: Int; var g: Int; var bl: Int
            if (a == 0 && !keepBlack) { r = 0; g = 0; bl = 0 } else {
                val b0 = if (keepBlack) c else bg.getPixel((x + xx).coerceIn(0, bg.width - 1), (y + yy).coerceIn(0, bg.height - 1))
                r = (Color.red(c) * a + Color.red(b0) * (255 - a)) / 255
                g = (Color.green(c) * a + Color.green(b0) * (255 - a)) / 255
                bl = (Color.blue(c) * a + Color.blue(b0) * (255 - a)) / 255
                if (r < 17 && g < 9 && bl < 17) { r = 17; g = 9; bl = 17 }
            }
            val v = ((r shr 3) shl 11) or ((g shr 2) shl 5) or (bl shr 3)
            out[i++] = (v shr 8).toByte(); out[i++] = v.toByte()
        }
        return out
    }
}
