package dev.openwear.s100.ble

import java.io.ByteArrayOutputStream
import java.time.LocalDateTime
import java.util.UUID
import java.util.zip.CRC32

/**
 * UTE protocol of the realme TechLife Watch S100 (stock firmware + our mods).
 * Byte-for-byte the same as tools/s100.py and tools/s100_dial.py, which were verified on the watch.
 * Reference: docs/bluetooth-protocol.md, docs/custom-dial-format.md.
 */
object Protocol {
    val CMD_SERVICE: UUID = UUID.fromString("000055ff-0000-1000-8000-00805f9b34fb")
    val CMD_CHAR: UUID = UUID.fromString("000033f1-0000-1000-8000-00805f9b34fb")
    val CMD_NOTIFY: UUID = UUID.fromString("000033f2-0000-1000-8000-00805f9b34fb")
    val BIG_SERVICE: UUID = UUID.fromString("000056ff-0000-1000-8000-00805f9b34fb")
    val BIG_CHAR: UUID = UUID.fromString("000034f1-0000-1000-8000-00805f9b34fb")
    val BIG_NOTIFY: UUID = UUID.fromString("000034f2-0000-1000-8000-00805f9b34fb")
    val BATTERY_SERVICE: UUID = UUID.fromString("0000180f-0000-1000-8000-00805f9b34fb")
    val BATTERY_LEVEL: UUID = UUID.fromString("00002a19-0000-1000-8000-00805f9b34fb")
    val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    const val ACCOUNT_ID = 0x00511000          // bind id used by our tools (watch already bound to it)
    const val MAX_TEXT_BYTES = 160

    // notification app types (WriteCommandToBLE.getAppType). Type 3 (SMS) is dropped by the
    // firmware, so SMS go out as 4.
    const val TYPE_CALL = 0
    const val TYPE_OTHER = 4
    val APP_TYPES = mapOf(
        "com.tencent.mobileqq" to 1, "com.tencent.mm" to 2, "com.facebook.katana" to 5,
        "com.twitter.android" to 6, "com.whatsapp" to 7, "com.whatsapp.w4b" to 7,
        "com.facebook.orca" to 8, "com.instagram.android" to 9, "com.linkedin.android" to 11,
        "jp.naver.line.android" to 13, "com.skype.raider" to 15, "com.viber.voip" to 16,
        "com.kakao.talk" to 17, "org.telegram.messenger" to 24,
    )

    fun bind() = byteArrayOf(0x33, 0x02) + int32be(ACCOUNT_ID)

    fun time(t: LocalDateTime = LocalDateTime.now()) = bytes(
        0xA3, t.year shr 8, t.year and 0xFF, t.monthValue, t.dayOfMonth, t.hour, t.minute, t.second)

    /** A0 <unit 1 metric / 2 imperial> <hours 1 = 24 h / 2 = 12 h> */
    fun units(twelveHour: Boolean, metric: Boolean) = bytes(0xA0, if (metric) 1 else 2, if (twelveHour) 2 else 1)

    fun version() = bytes(0xA1)

    fun vibrate(times: Int) = bytes(0xAB, 0, 0, 0, 1, times and 0xFF, 7, 1)

    /** UTF-16BE, BMP only, control and C1 characters dropped (GBUtils.string2unicode). */
    fun encodeText(text: String): ByteArray {
        val out = ByteArrayOutputStream()
        text.forEachIndexed { i, ch ->
            val cp = ch.code
            if (Character.isSurrogate(ch) || cp < 32 || cp in 127..159 || cp == 8197 || cp == 9924 || cp == 9748) return@forEachIndexed
            if (i == text.lastIndex && cp <= 32) return@forEachIndexed
            out.write(cp shr 8); out.write(cp and 0xFF)
        }
        val b = out.toByteArray()
        return if (b.size <= MAX_TEXT_BYTES) b else b.copyOf(MAX_TEXT_BYTES)
    }

    /** C5 notification as 18-byte chunks: C5 <seq> <chunk>, then C5 FD. */
    fun notification(text: String, appType: Int): List<ByteArray> {
        val body = encodeText(text).let { if (it.isEmpty()) encodeText("-") else it }
        val payload = byteArrayOf(appType.toByte(), body.size.toByte()) + body
        return payload.toList().chunked(18).mapIndexed { seq, c -> byteArrayOf(0xC5.toByte(), seq.toByte()) + c.toByteArray() }
    }

    /** Navigation frame for the watch's navigation screen (firmware/s100_ext/ext.c nav_check).
     *  The watch keeps 80 characters of a notification (160 bytes UTF-16), so the street gets what is
     *  left after the other fields (at most 47, the watch's field size). */
    fun navText(dir: Char, distance: String, street: String, speed: String, eta: String): String {
        val d = distance.take(11); val sp = speed.take(15); val e = eta.take(23)
        val room = (80 - "NAV|$dir|$d|||$sp|$e".length).coerceIn(0, 47)
        return "NAV|$dir|$d|${street.take(room).trimEnd()}|$sp|$e"
    }

    /** CB weather: 7 days of (condition, max, min) plus current temperature; city on 34f1. */
    fun weather(days: List<Triple<Int, Int, Int>>, current: Int): List<ByteArray> {
        fun t(v: Int) = if (v < 0) (-v or 0x80) else v
        val d = (days + List(7) { days.last() }).take(7)
        val p1 = bytes(0xCB, 1, d[0].first, 0, t(current), t(d[0].second), t(d[0].third), 0, 0, 0, 0) + ByteArray(8)
        val p2 = bytes(0xCB, 2) + d.subList(1, 5).flatMap { listOf(it.first, 0, t(it.second), t(it.third)) }.map { it.toByte() }
        val p3 = bytes(0xCB, 3) + d.subList(5, 7).flatMap { listOf(it.first, 0, t(it.second), t(it.third)) }.map { it.toByte() }
        return listOf(p1, p2, p3)
    }

    fun weatherCity(name: String): ByteArray {
        val n = name.toByteArray().let { if (it.size > 100) it.copyOf(100) else it }
        return bytes(0xCB, 0xFF, n.size) + n
    }

    /** 3A music packets on 34f1: state (1 playing, 2 paused), title, commit. */
    fun music(title: String, playing: Boolean): List<ByteArray> {
        val t = title.toByteArray().let { if (it.size > 52) it.copyOf(52) else it }
        return listOf(
            bytes(0x3A, 1, if (playing) 1 else 2) + ByteArray(10) { 0xFF.toByte() },
            bytes(0x3A, 6, t.size) + t,
            bytes(0x3A, 0xFA),
        )
    }

    // watch -> phone events (D1 xx on 33f2)
    const val EV_PLAY_PAUSE = 0x07
    const val EV_NEXT = 0x08
    const val EV_PREV = 0x09
    const val EV_FIND_PHONE = 0x0A
    const val EV_VOL_UP = 0x0D
    const val EV_VOL_DOWN = 0x0E

    /** WMO weather code (Open-Meteo) -> watch condition 1..12. */
    fun conditionFromWmo(code: Int) = when (code) {
        0, 1 -> 1; 2 -> 2; 3 -> 3; 45, 48 -> 11
        51, 53, 55, 56, 57, 61, 66 -> 7
        63, 65, 67 -> 8; 80, 81, 82 -> 4; 95, 96, 99 -> 5
        71, 73, 75, 77, 85, 86 -> 9
        else -> 2
    }

    /** Watch settings report (firmware c7): 7E 01 aod tap raise press dock h12 vib battery [aod level, c8+] */
    fun parseSettings(m: ByteArray): dev.openwear.s100.service.Hub.WatchSettings? {
        if (m.size < 10 || m[0] != 0x7E.toByte() || m[1] != 1.toByte()) return null
        fun on(i: Int) = m[i].toInt() != 0
        return dev.openwear.s100.service.Hub.WatchSettings(on(2), on(3), on(4), on(5), m[6].toInt(), on(7), on(8),
            m[9].toInt() and 0xFF, if (m.size > 10) m[10].toInt() and 3 else null,
            if (m.size > 11) on(11) else null)
    }

    fun bytes(vararg v: Int) = ByteArray(v.size) { v[it].toByte() }
    fun int32be(v: Int) = bytes(v ushr 24, (v ushr 16) and 0xFF, (v ushr 8) and 0xFF, v and 0xFF)
}

/** Custom watch-face ("online dial") file, compatibility level 1 (docs/custom-dial-format.md). */
object DialFile {
    const val W = 240
    const val H = 280

    class Element(val type: Int, val x: Int, val y: Int, val w: Int, val h: Int, val frames: List<ByteArray>)

    fun build(elements: List<Element>): ByteArray {
        val els = elements.sortedBy { it.type }
        val dataOff = (els.size + 1) * 24 + 2
        val blocks = ArrayList<ByteArray>()
        val seen = HashMap<String, Int>()
        val records = ByteArrayOutputStream()
        var next = dataOff
        for (e in els) {
            val blob = e.frames.fold(ByteArray(0)) { a, b -> a + b }
            val key = blob.contentHashCode().toString() + ":" + blob.size
            val off = seen.getOrPut(key) { blocks.add(blob); next.also { next += blob.size } }
            records.write(le16(e.type)); records.write(le16(e.w)); records.write(le32(off))
            records.write(le16(e.h)); records.write(le16(e.x)); records.write(le16(e.y))
            records.write(le16(0)); records.write(e.frames.size); records.write(ByteArray(7))
        }
        var body = records.toByteArray() + ByteArray(2) + blocks.fold(ByteArray(0)) { a, b -> a + b }
        // the watch rejects files whose last 4 KB sector is within one packet of full (tools/s100_dial.py)
        val rem = (24 + body.size) % 4096
        if (rem == 0 || rem > 4096 - 256) body += ByteArray(4096 - rem + 128)
        val crc = CRC32().apply { update(body) }.value.toInt()
        val header = ByteArray(24) { 0xFF.toByte() }
        le32(body.size).copyInto(header, 4); le32(crc).copyInto(header, 8)
        le16(W).copyInto(header, 12); le16(H).copyInto(header, 14)
        header[16] = 0; header[17] = if (els.any { it.type == 17 }) 1 else 0; header[18] = 0xFF.toByte()
        return header + body
    }

    private fun le16(v: Int) = byteArrayOf((v and 0xFF).toByte(), (v shr 8 and 0xFF).toByte())
    private fun le32(v: Int) = byteArrayOf((v and 0xFF).toByte(), (v shr 8 and 0xFF).toByte(),
        (v shr 16 and 0xFF).toByte(), (v ushr 24).toByte())
}
