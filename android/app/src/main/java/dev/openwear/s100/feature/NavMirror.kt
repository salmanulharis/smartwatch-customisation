package dev.openwear.s100.feature

import android.annotation.SuppressLint
import android.app.Notification
import android.content.Context
import android.graphics.Bitmap
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Icon
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Looper
import dev.openwear.s100.ble.Protocol
import dev.openwear.s100.service.Hub
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/**
 * Google Maps turn-by-turn -> the watch's navigation screen (firmware c2_features, app >= 1328).
 * Maps shows the next manoeuvre in an ongoing notification: title = distance (or the instruction),
 * text = street / instruction, sub-text = "12 min · 4.5 km · 14:45 ETA", large icon = arrow.
 * The direction comes from the instruction words; if there are none, from the arrow bitmap.
 */
object NavMirror {
    const val MAPS = "com.google.android.apps.maps"
    private var last = ""
    private var lastSent = 0L
    private var keepAlive: Job? = null
    private var speedKmh = -1
    private var gps: LocationListener? = null

    fun onMapsNotification(context: Context, n: Notification) {
        if (!Hub.prefs.navMirror) return
        if (n.flags and Notification.FLAG_ONGOING_EVENT == 0) return       // only the navigation card
        val ex = n.extras
        val title = clean(ex.getCharSequence(Notification.EXTRA_TITLE))
        val text = clean(ex.getCharSequence(Notification.EXTRA_TEXT))
        val sub = clean(ex.getCharSequence(Notification.EXTRA_SUB_TEXT))
        if (title.isBlank() && text.isBlank()) return
        startGps(context)

        val all = "$title $text"
        val dist = DIST.find(all)?.value?.replace(Regex("\\s+"), " ")?.trim() ?: ""
        var instr = (if (DIST.matches(title.trim())) text else title).trim()
        val street = STREET.find(instr)?.groupValues?.get(2)?.trim() ?: if (DIST.matches(title.trim())) text.trim() else instr
        val dir = direction(all) ?: arrowDirection(context, n) ?: 'S'
        val eta = sub.split("·", "•").map { it.trim() }.lastOrNull { it.isNotEmpty() }?.removeSuffix(" ETA") ?: ""
        val speed = if (speedKmh >= 0) "$speedKmh km/h" else ""
        val msg = Protocol.navText(dir, dist, street, speed, eta)
        Hub.lastNav.value = "$dir  $dist  $street  $eta"
        send(msg)
        if (keepAlive?.isActive != true) keepAlive = Hub.scope.launch {
            while (true) { delay(20_000); if (System.currentTimeMillis() - lastSent > 18_000) send(last, force = true) }
        }
    }

    fun onMapsEnded() {
        keepAlive?.cancel(); keepAlive = null
        stopGps()
        Hub.lastNav.value = ""
    }

    private fun send(msg: String, force: Boolean = false) {
        if (msg.isBlank() || (!force && msg == last && System.currentTimeMillis() - lastSent < 5_000)) return
        last = msg; lastSent = System.currentTimeMillis()
        Hub.scope.launch { Hub.notify(msg, Protocol.TYPE_OTHER) }
    }

    /** Maps puts a no-break space between number and unit ("2.5\u00A0km") and typographic dashes in
     *  street names; plain ASCII spaces / dashes make the distance parse and survive the watch's
     *  ASCII-only text. */
    private fun clean(cs: CharSequence?): String = cs?.toString().orEmpty()
        .replace(Regex("[\u00A0\u2007\u2009\u202F\u2000-\u200A]"), " ")
        .replace(Regex("[\u2010-\u2015\u2212]"), "-")
        .trim()

    private val DIST = Regex("""\d+(?:[.,]\d+)?\s?(?:km|m|mi|ft|yd)\b""", RegexOption.IGNORE_CASE)
    private val STREET = Regex("""\b(onto|on|towards|toward|into|to)\s+(.+)$""", RegexOption.IGNORE_CASE)

    /** Direction letters of the watch's arrow set (ext.c NAV_DIRS): S straight, L / R turn,
     *  l / r slight, U U-turn (right-hand traffic) / u U-turn to the right (left-hand traffic),
     *  A arrive, O roundabout, < / > sharp, k / K keep (fork), M merge, e / E exit (ramp).
     *  More specific phrases are checked first ("sharp left" before "left"). */
    fun direction(s: String): Char? {
        val t = s.lowercase()
        fun side(l: Char, r: Char) = if ("left" in t) l else if ("right" in t) r else null
        return when {
            "roundabout" in t || "rotary" in t -> 'O'
            "u-turn" in t || "make a u" in t -> if (leftHandTraffic()) 'u' else 'U'
            "destination" in t || "arrive" in t || "you have arrived" in t -> 'A'
            "sharp left" in t -> '<'
            "sharp right" in t -> '>'
            ("exit" in t || "ramp" in t || "slip road" in t) && side('e', 'E') != null -> side('e', 'E')
            "merge" in t -> 'M'
            "keep left" in t || "fork left" in t || "stay left" in t -> 'k'
            "keep right" in t || "fork right" in t || "stay right" in t -> 'K'
            "slight left" in t || "bear left" in t -> 'l'
            "slight right" in t || "bear right" in t -> 'r'
            "left" in t -> 'L'
            "right" in t -> 'R'
            "straight" in t || "continue" in t || "head " in t -> 'S'
            else -> null
        }
    }

    /** Countries that drive on the left: U-turns go to the right there (Maps draws them so). */
    private val LHT = setOf("IN", "GB", "IE", "AU", "NZ", "JP", "ZA", "MY", "SG", "TH", "ID", "PK", "BD", "LK",
        "NP", "BT", "HK", "MO", "KE", "UG", "TZ", "ZM", "ZW", "BW", "NA", "MZ", "MW", "MU", "CY", "MT", "JM", "TT",
        "BS", "BB", "GY", "SR", "FJ", "PG", "BN", "TL", "MV", "SC", "LS", "SZ")

    private fun leftHandTraffic(): Boolean {
        val tm = ctx?.getSystemService(android.telephony.TelephonyManager::class.java)
        val cc = (tm?.networkCountryIso?.takeIf { it.isNotBlank() } ?: java.util.Locale.getDefault().country).uppercase()
        return cc in LHT
    }

    /** Fallback: where the arrow's ink is in the upper half of Maps' large icon. */
    private fun arrowDirection(context: Context, n: Notification): Char? {
        val icon: Icon = n.getLargeIcon() ?: return null
        val bmp: Bitmap = (icon.loadDrawable(context) as? BitmapDrawable)?.bitmap ?: return null
        val w = bmp.width; val h = bmp.height
        var sx = 0.0; var cnt = 0
        for (y in 0 until h / 2 step 2) for (x in 0 until w step 2) {
            if ((bmp.getPixel(x, y) ushr 24) > 128) { sx += x; cnt++ }
        }
        if (cnt < 10) return null
        val c = sx / cnt / w
        return when { c < 0.38 -> 'L'; c > 0.62 -> 'R'; c < 0.46 -> 'l'; c > 0.54 -> 'r'; else -> 'S' }
    }

    @SuppressLint("MissingPermission")
    private fun startGps(context: Context) {
        if (gps != null) return
        val lm = context.getSystemService(LocationManager::class.java)
        val l = LocationListener { loc: Location -> speedKmh = if (loc.hasSpeed()) (loc.speed * 3.6f).roundToInt() else -1 }
        try {
            lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 2000L, 0f, l, Looper.getMainLooper())
            gps = l
        } catch (_: Exception) { }
        this.ctx = context.applicationContext
    }

    private var ctx: Context? = null
    private fun stopGps() {
        gps?.let { ctx?.getSystemService(LocationManager::class.java)?.removeUpdates(it) }
        gps = null; speedKmh = -1
    }
}
