package dev.openwear.s100.ui

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color as AColor
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.openwear.s100.MainActivity
import dev.openwear.s100.feature.Faces
import dev.openwear.s100.feature.WeatherSync
import dev.openwear.s100.service.Hub
import kotlinx.coroutines.launch

@Composable
private fun Pill(text: String, accent: Boolean = false, onClick: () -> Unit) {
    Box(Modifier.clip(RoundedCornerShape(50)).background(if (accent) C.Orange else C.Line)
        .clickable(onClick = onClick).padding(horizontal = 18.dp, vertical = 12.dp)) {
        Text(text, color = if (accent) C.Black else C.Text, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

// ================================================================== Watch
@Composable
fun HomeScreen(act: MainActivity) {
    val status by Hub.status.collectAsState()
    val link by Hub.link.collectAsState()
    val battery by (link?.battery ?: remember { kotlinx.coroutines.flow.MutableStateFlow(-1) }).collectAsState()
    val fw by (link?.firmware ?: remember { kotlinx.coroutines.flow.MutableStateFlow("") }).collectAsState()
    val nav by Hub.lastNav.collectAsState()
    val wx by WeatherSync.latest.collectAsState()
    val scope = rememberCoroutineScope()
    var toast by remember { mutableStateOf("") }
    var notifyOn by remember { mutableStateOf(Hub.prefs.forwardNotifications) }
    var navOn by remember { mutableStateOf(Hub.prefs.navMirror) }
    var musicOn by remember { mutableStateOf(Hub.prefs.musicSync) }

    LazyColumn(Modifier.padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Column(Modifier.padding(start = 6.dp, top = 28.dp, bottom = 8.dp)) {
                Text("S100", style = Big)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(if (status == "Connected") C.Orange else C.Line))
                    Spacer(Modifier.width(8.dp))
                    Text(status, color = C.Dim, fontSize = 14.sp)
                }
            }
        }
        item {
            Card {
                Row {
                    Column(Modifier.weight(1f)) {
                        Text("BATTERY", style = Label)
                        Text(if (battery >= 0) "$battery%" else "—", color = C.Text, fontSize = 30.sp, fontWeight = FontWeight.Light)
                    }
                    Column(Modifier.weight(1f)) {
                        Text("WEATHER", style = Label)
                        Text(wx?.let { "${it.current}°" } ?: "—", color = C.Text, fontSize = 30.sp, fontWeight = FontWeight.Light)
                        Text(wx?.city.orEmpty(), color = C.Dim, fontSize = 12.sp)
                    }
                }
                if (fw.isNotEmpty()) Text("Firmware $fw", color = C.Dim, fontSize = 12.sp)
            }
        }
        if (nav.isNotEmpty()) item {
            Card { Text("NAVIGATING", style = Label); Text(nav, color = C.Orange, fontSize = 16.sp) }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Pill("Find watch", accent = true) { scope.launch { Hub.vibrateWatch(3) } }
                Pill("Sync") { scope.launch { toast = WeatherSync.refresh(act); Hub.link.value?.let { l -> l.request(dev.openwear.s100.ble.Protocol.time(), byteArrayOf(0xA3.toByte())) } } }
                Pill("Test alert") { scope.launch { toast = if (Hub.notify("Hello from your phone", 4)) "Sent" else "Not connected" } }
            }
        }
        if (toast.isNotEmpty()) item { Text(toast, color = C.Dim, fontSize = 13.sp, modifier = Modifier.padding(start = 6.dp)) }
        item { SectionLabel("Features") }
        item {
            Card {
                ToggleRow("Notifications", "Forward phone notifications and calls", notifyOn) { notifyOn = it; Hub.prefs.forwardNotifications = it }
                ToggleRow("Navigation", "Mirror Google Maps directions to the watch", navOn) { navOn = it; Hub.prefs.navMirror = it }
                ToggleRow("Music", "Song title on the watch, watch buttons control playback", musicOn) { musicOn = it; Hub.prefs.musicSync = it }
            }
        }
        if (!act.hasNotificationAccess()) item {
            Card {
                Text("Notification access needed", color = C.Text, fontSize = 16.sp)
                Text("Required for notifications, Google Maps navigation and music.", color = C.Dim, fontSize = 13.sp)
                Pill("Grant access", accent = true) { act.openNotificationAccess() }
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

// ================================================================== Faces
@Composable
fun FacesScreen(act: MainActivity) {
    val scope = rememberCoroutineScope()
    val progress by Hub.dialProgress.collectAsState()
    var log by remember { mutableStateOf("") }
    val faces = remember { Faces.gallery(act) }
    var photo by remember { mutableStateOf<Bitmap?>(null) }
    var color by remember { mutableStateOf(AColor.WHITE) }
    var layout by remember { mutableStateOf(Faces.Layout.CENTER) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let { photo = act.contentResolver.openInputStream(it)?.use(BitmapFactory::decodeStream) }
    }
    val built = remember(photo, color, layout) { photo?.let { Faces.photoFace(it, color, layout, Hub.prefs.twelveHour) } }

    LazyVerticalGrid(GridCells.Fixed(2), Modifier.padding(horizontal = 18.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(2) }) {
            Column(Modifier.padding(start = 6.dp, top = 28.dp)) {
                Text("Faces", style = Big)
                if (progress >= 0f) LinearProgressIndicator(progress = { progress }, color = C.Orange, trackColor = C.Line,
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp))
                if (log.isNotEmpty()) Text(log, color = C.Dim, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
            }
        }
        item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(2) }) {
            Card {
                Text("PHOTO FACE", style = Label)
                if (built == null) {
                    Text("Your picture with the time, date and battery on top.", color = C.Dim, fontSize = 13.sp)
                    Pill("Choose photo", accent = true) { pick.launch("image/*") }
                } else {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Image(built.second.asImageBitmap(), null, Modifier.width(120.dp).aspectRatio(240f / 280f).clip(RoundedCornerShape(18.dp)))
                        Spacer(Modifier.width(16.dp))
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                listOf(AColor.WHITE, 0xFFFF5A1E.toInt(), 0xFF5AE6B4.toInt(), 0xFF1E1E1E.toInt()).forEach { c ->
                                    Box(Modifier.size(28.dp).clip(CircleShape).background(Color(c))
                                        .border(2.dp, if (c == color) C.Orange else C.Line, CircleShape).clickable { color = c })
                                }
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Faces.Layout.entries.forEach { l -> Pill(l.name.lowercase(), accent = l == layout) { layout = l } }
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Pill("Install", accent = true) {
                                    scope.launch { log = "Uploading…"; Faces.upload(built.first) { log = it } }
                                }
                                Pill("Other photo") { pick.launch("image/*") }
                            }
                        }
                    }
                }
            }
        }
        items(faces) { f ->
            val bmp = remember(f) { Faces.preview(act, f) }
            Column(Modifier.clip(RoundedCornerShape(24.dp)).background(C.Card).clickable {
                scope.launch {
                    log = "Uploading ${f.name}…"
                    val blob = act.assets.open(f.asset).use { it.readBytes() }
                    Faces.upload(blob) { log = it }
                }
            }.padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                if (bmp != null) Image(bmp.asImageBitmap(), null, Modifier.fillMaxWidth().aspectRatio(240f / 280f).clip(RoundedCornerShape(18.dp)))
                Text(f.name, color = C.Text, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
            }
        }
        item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(2) }) { Spacer(Modifier.height(24.dp)) }
    }
}

// ================================================================== Settings
@SuppressLint("MissingPermission")
@Composable
fun SettingsScreen(act: MainActivity) {
    val scope = rememberCoroutineScope()
    var address by remember { mutableStateOf(Hub.prefs.address) }
    var metric by remember { mutableStateOf(Hub.prefs.metric) }
    var city by remember { mutableStateOf(Hub.prefs.weatherCity) }
    var scanning by remember { mutableStateOf(false) }
    val found = remember { mutableStateListOf<Pair<String, String>>() }
    var blocked by remember { mutableStateOf(Hub.prefs.blockedApps) }

    DisposableEffect(scanning) {
        val scanner = act.getSystemService(BluetoothManager::class.java).adapter?.bluetoothLeScanner
        val cb = object : ScanCallback() {
            override fun onScanResult(type: Int, r: ScanResult) {
                val name = r.scanRecord?.deviceName ?: r.device.name ?: return
                if (found.none { it.second == r.device.address }) found += name to r.device.address
            }
        }
        if (scanning) try { scanner?.startScan(cb) } catch (_: SecurityException) { scanning = false }
        onDispose { if (scanning) try { scanner?.stopScan(cb) } catch (_: SecurityException) { } }
    }

    LazyColumn(Modifier.padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Settings", style = Big, modifier = Modifier.padding(start = 6.dp, top = 28.dp)) }
        item { SectionLabel("Watch") }
        item {
            Card {
                Text(if (address.isBlank()) "No watch selected" else address, color = C.Text, fontSize = 16.sp)
                Text("Unpair it in realme Fit first: only one app can be connected.", color = C.Dim, fontSize = 13.sp)
                Pill(if (scanning) "Stop scan" else "Scan for watch", accent = !scanning) { found.clear(); scanning = !scanning }
                found.forEach { (name, mac) ->
                    Row(Modifier.fillMaxWidth().clickable {
                        address = mac; Hub.prefs.address = mac; scanning = false; Hub.stop(); Hub.start()
                    }.padding(vertical = 6.dp)) {
                        Text(name, color = C.Text, modifier = Modifier.weight(1f)); Text(mac, color = C.Dim, fontSize = 12.sp)
                    }
                }
            }
        }
        item { SectionLabel("Display & wake") }
        item {
            val ws by Hub.watchSettings.collectAsState()
            var msg by remember { mutableStateOf("") }
            fun set(key: String, on: Boolean) = scope.launch {
                msg = if (Hub.setWatch(key, on)) "" else "Watch not connected"
            }
            Card {
                val w = ws
                if (w == null) {
                    Text("Connect the watch to see its settings. They are stored on the watch; " +
                        "changes made on the watch show up here.", color = C.Dim, fontSize = 13.sp)
                    Pill("Read from watch") { scope.launch { msg = if (Hub.notify("CFG|get", 4)) "" else "Watch not connected" } }
                } else {
                    ToggleRow("Always-on display", "Dims to a minimal screen instead of turning off (more battery)", w.aod) { set("aod", it) }
                    val level = w.aodLevel
                    if (w.aod && level != null) {
                        Text("Always-on brightness", color = C.Text, fontSize = 15.sp)
                        Text("Its own level; the normal brightness is not changed", color = C.Dim, fontSize = 12.sp)
                        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("Min", "Low", "Mid", "High").forEachIndexed { i, name ->
                                Box(Modifier.weight(1f).clip(RoundedCornerShape(14.dp))
                                    .background(if (level == i) C.Orange else C.Line)
                                    .clickable { scope.launch { msg = if (Hub.setAodLevel(i)) "" else "Watch not connected" } }
                                    .padding(vertical = 10.dp), contentAlignment = Alignment.Center) {
                                    Text(name, color = C.Text, fontSize = 14.sp)
                                }
                            }
                        }
                        Pill("Show always-on now") { scope.launch { msg = if (Hub.showDock(1)) "Shown" else "Watch not connected" } }
                    }
                    ToggleRow("Tap to wake", "Touch the dark screen to wake (keeps the touch chip awake: a little more battery)", w.tapWake) { set("tw", it) }
                    ToggleRow("Raise to wake", "Lift your wrist", w.raiseWake) { set("rw", it) }
                    ToggleRow("Press to wake", "Side button wakes the screen", w.pressWake) { set("bw", it) }
                    ToggleRow("12-hour time", "", w.twelveHour) { set("h12", it) }
                    ToggleRow("Tap vibration", "Short tick on every tap", w.tapVibration) { set("vib", it) }
                    Text("At least one wake option always stays on.", color = C.Dim, fontSize = 12.sp)
                }
                if (msg.isNotEmpty()) Text(msg, color = C.Dim, fontSize = 13.sp)
            }
        }
        item { SectionLabel("On the charger") }
        item {
            val ws by Hub.watchSettings.collectAsState()
            var msg by remember { mutableStateOf("") }
            Card {
                Text("When you plug the charger in, the watch shows this screen. It is a normal screen: " +
                    "tap or press to use the watch; on timeout it dims to always-on or turns off.",
                    color = C.Dim, fontSize = 13.sp)
                val dock = ws?.dock ?: -1
                listOf("Dock" to "Big time, weather, battery", "Always-on" to "Dot-matrix time, dimmed",
                       "Charging" to "Battery ring and percentage", "Nothing" to "Keep the current screen")
                    .forEachIndexed { i, (title, sub) ->
                        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
                            .background(if (dock == i) C.Line else Color.Transparent)
                            .clickable { scope.launch { msg = if (Hub.setDock(i)) "" else "Watch not connected" } }
                            .padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(10.dp).clip(CircleShape).background(if (dock == i) C.Orange else C.Line))
                            Spacer(Modifier.width(12.dp))
                            Column { Text(title, color = C.Text, fontSize = 16.sp); Text(sub, color = C.Dim, fontSize = 13.sp) }
                        }
                    }
                if (dock in 0..2) Pill("Show on watch now") { scope.launch { msg = if (Hub.showDock(dock)) "Shown" else "Watch not connected" } }
                if (msg.isNotEmpty()) Text(msg, color = C.Dim, fontSize = 13.sp)
            }
        }
        item { SectionLabel("Units") }
        item {
            Card {
                ToggleRow("Metric units", "km, °C", metric) { metric = it; Hub.prefs.metric = it; scope.launch { Hub.applyUnits() } }
            }
        }
        item { SectionLabel("Weather") }
        item {
            Card {
                OutlinedTextField(city, { city = it; Hub.prefs.weatherCity = it }, singleLine = true,
                    label = { Text("City (empty = your location)") }, modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = C.Orange, unfocusedBorderColor = C.Line,
                        focusedLabelColor = C.Orange, cursorColor = C.Orange))
            }
        }
        item { SectionLabel("Notification apps") }
        item {
            Card {
                val pm = act.packageManager
                val apps = Hub.prefs.seenApps.sorted()
                if (apps.isEmpty()) Text("Apps appear here after they post a notification.", color = C.Dim, fontSize = 13.sp)
                apps.forEach { pkg ->
                    val label = try { pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString() }
                        catch (_: PackageManager.NameNotFoundException) { pkg }
                    ToggleRow(label, "", pkg !in blocked) { on ->
                        blocked = if (on) blocked - pkg else blocked + pkg; Hub.prefs.blockedApps = blocked
                    }
                }
            }
        }
        item {
            Text("S100 Companion 0.1 · OpenWearOTA", color = C.Dim, fontSize = 12.sp,
                modifier = Modifier.padding(start = 6.dp, top = 12.dp, bottom = 32.dp))
        }
    }
}
