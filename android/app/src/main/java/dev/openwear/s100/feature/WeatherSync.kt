package dev.openwear.s100.feature

import android.annotation.SuppressLint
import android.content.Context
import android.location.Geocoder
import android.location.LocationManager
import dev.openwear.s100.ble.Protocol
import dev.openwear.s100.ble.WatchLink
import dev.openwear.s100.service.Hub
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.roundToInt

/** 7-day weather from Open-Meteo (free, no API key) for the chosen city or the last known location. */
object WeatherSync {
    data class Wx(val city: String, val current: Int, val days: List<Triple<Int, Int, Int>>, val time: Long)

    val latest = kotlinx.coroutines.flow.MutableStateFlow<Wx?>(null)

    private fun get(url: String): JSONObject {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 10_000; c.readTimeout = 10_000
        return c.inputStream.bufferedReader().use { JSONObject(it.readText()) }
    }

    @SuppressLint("MissingPermission")
    private fun place(context: Context): Triple<Double, Double, String>? {
        val city = Hub.prefs.weatherCity.trim()
        if (city.isNotEmpty()) {
            val r = get("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + URLEncoder.encode(city, "UTF-8"))
                .optJSONArray("results")?.optJSONObject(0) ?: return null
            return Triple(r.getDouble("latitude"), r.getDouble("longitude"), r.optString("name", city))
        }
        val lm = context.getSystemService(LocationManager::class.java)
        val loc = try {
            listOf(LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER, LocationManager.PASSIVE_PROVIDER)
                .mapNotNull { lm.getLastKnownLocation(it) }.maxByOrNull { it.time }
        } catch (_: SecurityException) { null } ?: return null
        val name = try {
            @Suppress("DEPRECATION") Geocoder(context).getFromLocation(loc.latitude, loc.longitude, 1)?.firstOrNull()?.locality
        } catch (_: Exception) { null }
        return Triple(loc.latitude, loc.longitude, name ?: "")
    }

    /** Fetch (network) and push to the watch if connected. Returns a short status line. */
    suspend fun refresh(context: Context): String = withContext(Dispatchers.IO) {
        try {
            val (lat, lon, name) = place(context) ?: return@withContext "No location: set a city or allow location"
            val j = get("https://api.open-meteo.com/v1/forecast?latitude=$lat&longitude=$lon" +
                "&current=temperature_2m,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min" +
                "&timezone=auto&forecast_days=7")
            val cur = j.getJSONObject("current")
            val d = j.getJSONObject("daily")
            val codes = d.getJSONArray("weather_code"); val hi = d.getJSONArray("temperature_2m_max"); val lo = d.getJSONArray("temperature_2m_min")
            val days = (0 until codes.length()).map {
                Triple(Protocol.conditionFromWmo(codes.getInt(it)), hi.getDouble(it).roundToInt(), lo.getDouble(it).roundToInt())
            }
            val wx = Wx(name, cur.getDouble("temperature_2m").roundToInt(), days, System.currentTimeMillis())
            latest.value = wx
            Hub.prefs.weatherCache = JSONObject().put("city", wx.city).put("cur", wx.current)
                .put("days", days.joinToString(";") { "${it.first},${it.second},${it.third}" }).put("t", wx.time).toString()
            Hub.link.value?.takeIf { Hub.ready }?.let { push(it, wx) }
            "${wx.current}° ${wx.city}".trim()
        } catch (e: Exception) {
            "Weather failed: ${e.message}"
        }
    }

    suspend fun pushCached(link: WatchLink) {
        val wx = latest.value ?: Hub.prefs.weatherCache.takeIf { it.isNotBlank() }?.let {
            val j = JSONObject(it)
            Wx(j.optString("city"), j.getInt("cur"), j.getString("days").split(";").map { s ->
                s.split(",").map(String::toInt).let { v -> Triple(v[0], v[1], v[2]) } }, j.getLong("t"))
        }
        if (wx == null || System.currentTimeMillis() - wx.time > 3 * 3600_000L) { refresh(Hub.app); return }
        latest.value = wx
        push(link, wx)
    }

    private suspend fun push(link: WatchLink, wx: Wx) {
        link.session {
            for (p in Protocol.weather(wx.days, wx.current)) request(p, byteArrayOf(0xCB.toByte()), 3000)
            if (wx.city.isNotBlank()) request(Protocol.weatherCity(wx.city), byteArrayOf(0xCB.toByte(), 0xFF.toByte()), 3000, big = true)
        }
    }
}
