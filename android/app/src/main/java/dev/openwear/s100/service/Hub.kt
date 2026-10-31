package dev.openwear.s100.service

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import dev.openwear.s100.ble.Protocol
import dev.openwear.s100.ble.WatchLink
import dev.openwear.s100.feature.FindPhone
import dev.openwear.s100.feature.MusicBridge
import dev.openwear.s100.feature.WeatherSync
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** App-wide state and the single connection to the watch (lives as long as the process). */
@SuppressLint("StaticFieldLeak")   // application context only
object Hub {
    private const val TAG = "Hub"
    lateinit var app: Context
        private set
    lateinit var prefs: Prefs
        private set
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val link = MutableStateFlow<WatchLink?>(null)
    val status = MutableStateFlow("Not set up")
    val lastNav = MutableStateFlow("")
    val dialProgress = MutableStateFlow(-1f)          // -1 idle, 0..1 uploading

    /** Display and wake settings as last reported by the watch (0x7E report); null = not known yet.
     *  The watch is the source of truth: the app never pushes these on connect. */
    data class WatchSettings(val aod: Boolean, val tapWake: Boolean, val raiseWake: Boolean, val pressWake: Boolean,
                             val dock: Int, val twelveHour: Boolean, val tapVibration: Boolean, val battery: Int,
                             val aodLevel: Int? = null,   // always-on backlight 0 (dimmest) - 3; firmware r1335+
                             val turnAlerts: Boolean? = null) // navigation turn alerts; firmware r1341+
    val watchSettings = MutableStateFlow<WatchSettings?>(null)
    private var loop: Job? = null
    private val notifyLock = Mutex()

    fun init(context: Context) {
        if (::app.isInitialized) return
        app = context.applicationContext
        prefs = Prefs(app)
    }

    /** Keep connected while the service runs: connect, bind, sync, then wait for a drop. */
    fun start() {
        if (loop?.isActive == true) return
        loop = scope.launch {
            var backoff = 2_000L
            while (isActive) {
                val mac = prefs.address
                if (mac.isBlank()) { status.value = "Pick your watch in Settings"; delay(3_000); continue }
                val l = WatchLink(app, mac)
                link.value = l
                status.value = "Connecting…"
                val ok = try { l.connect() } catch (e: SecurityException) { status.value = "Bluetooth permission missing"; false }
                if (ok) {
                    backoff = 2_000L
                    status.value = "Connected"
                    onConnected(l)
                    l.state.first { it == WatchLink.State.DISCONNECTED }
                    status.value = "Disconnected — reconnecting"
                } else {
                    status.value = "Watch not reachable — retrying"
                }
                l.close()
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(30_000L)
            }
        }
    }

    fun stop() { loop?.cancel(); link.value?.close(); link.value = null; status.value = "Stopped" }

    private fun onConnected(l: WatchLink) {
        scope.launch {
            l.request(Protocol.time(), byteArrayOf(0xA3.toByte()))
            notify("CFG|get", Protocol.TYPE_OTHER)            // watch answers with its settings (0x7E)
            WeatherSync.pushCached(l)
            MusicBridge.pushCurrent()
        }
        scope.launch {                                     // watch -> phone events
            l.incoming.collect { m ->
                Protocol.parseSettings(m)?.let { watchSettings.value = it; prefs.twelveHour = it.twelveHour }
                if (m.size >= 2 && m[0] == 0xD1.toByte()) {
                    val ev = m[1].toInt() and 0xFF
                    Log.i(TAG, "watch event $ev")
                    if (ev == Protocol.EV_FIND_PHONE) FindPhone.ring(app) else MusicBridge.onWatchButton(ev)
                }
            }
        }
        scope.launch {                                     // hourly time + weather refresh
            while (l.state.value == WatchLink.State.READY) {
                delay(60 * 60 * 1000L)
                l.request(Protocol.time(), byteArrayOf(0xA3.toByte()))
                WeatherSync.refresh(app)
            }
        }
    }

    val ready get() = link.value?.state?.value == WatchLink.State.READY

    /** Send a notification (C5 chunks + C5 FD). Returns false if not connected or not acked. */
    suspend fun notify(text: String, appType: Int): Boolean {
        val l = link.value?.takeIf { ready } ?: return false
        return notifyLock.withLock {
            l.session {
                for (chunk in Protocol.notification(text, appType)) {
                    val ack = request(chunk, byteArrayOf(0xC5.toByte())) ?: return@session false
                    if (ack.size > 1 && ack[1] == 0xFF.toByte()) return@session false
                }
                request(byteArrayOf(0xC5.toByte(), 0xFD.toByte()), byteArrayOf(0xC5.toByte(), 0xFD.toByte()), 3000)
                true
            }
        }
    }

    suspend fun vibrateWatch(times: Int = 2) { link.value?.takeIf { ready }?.write(Protocol.vibrate(times)) }

    /** Charging screen style on the watch (0 dock, 1 always-on look, 2 charging ring, 3 off). */
    suspend fun setDock(style: Int): Boolean = notify("CFG|dock=$style", Protocol.TYPE_OTHER)

    /** One watch setting: aod, tw (tap to wake), rw (raise), bw (press), h12, vib, na (turn alerts). The watch replies
     *  with its full settings report, which updates [watchSettings]. */
    suspend fun setWatch(key: String, on: Boolean): Boolean = notify("CFG|$key=${if (on) 1 else 0}", Protocol.TYPE_OTHER)

    /** Always-on backlight level 0 (dimmest) - 3, separate from the normal brightness. */
    suspend fun setAodLevel(level: Int): Boolean = notify("CFG|ab=${level.coerceIn(0, 3)}", Protocol.TYPE_OTHER)

    /** Open the dock / always-on screen on the watch now (style 0-2). */
    suspend fun showDock(style: Int) = notify("CFG|show=$style", Protocol.TYPE_OTHER)

    suspend fun applyUnits() {      // units only; 12/24 h comes from the watch report
        val h12 = watchSettings.value?.twelveHour ?: prefs.twelveHour
        link.value?.takeIf { ready }?.request(Protocol.units(h12, prefs.metric), byteArrayOf(0xA0.toByte()))
    }
}

class Prefs(context: Context) {
    private val p: SharedPreferences = context.getSharedPreferences("s100", Context.MODE_PRIVATE)
    var address: String
        get() = p.getString("address", "") ?: ""
        set(v) = p.edit().putString("address", v).apply()
    var twelveHour: Boolean
        get() = p.getBoolean("twelve", false)
        set(v) = p.edit().putBoolean("twelve", v).apply()
    var metric: Boolean
        get() = p.getBoolean("metric", true)
        set(v) = p.edit().putBoolean("metric", v).apply()
    var forwardNotifications: Boolean
        get() = p.getBoolean("notify", true)
        set(v) = p.edit().putBoolean("notify", v).apply()
    var navMirror: Boolean
        get() = p.getBoolean("nav", true)
        set(v) = p.edit().putBoolean("nav", v).apply()
    var musicSync: Boolean
        get() = p.getBoolean("music", true)
        set(v) = p.edit().putBoolean("music", v).apply()
    var aod: Boolean
        get() = p.getBoolean("aod", false)
        set(v) = p.edit().putBoolean("aod", v).apply()
    var dockStyle: Int
        get() = p.getInt("dock", 0)
        set(v) = p.edit().putInt("dock", v).apply()
    var weatherCity: String
        get() = p.getString("city", "") ?: ""
        set(v) = p.edit().putString("city", v).apply()
    var weatherCache: String
        get() = p.getString("wx", "") ?: ""
        set(v) = p.edit().putString("wx", v).apply()
    var blockedApps: Set<String>
        get() = p.getStringSet("blocked", emptySet()) ?: emptySet()
        set(v) = p.edit().putStringSet("blocked", v).apply()
    var seenApps: Set<String>
        get() = p.getStringSet("seen", emptySet()) ?: emptySet()
        set(v) = p.edit().putStringSet("seen", v).apply()
}
