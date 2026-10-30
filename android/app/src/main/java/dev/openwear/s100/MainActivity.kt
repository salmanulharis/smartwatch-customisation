package dev.openwear.s100

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.clickable
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.NotificationManagerCompat
import dev.openwear.s100.service.Hub
import dev.openwear.s100.service.LinkService
import dev.openwear.s100.service.NotifyListener
import dev.openwear.s100.ui.C
import dev.openwear.s100.ui.FacesScreen
import dev.openwear.s100.ui.HomeScreen
import dev.openwear.s100.ui.S100Theme
import dev.openwear.s100.ui.SettingsScreen

class MainActivity : ComponentActivity() {
    private val perms = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { startLink() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Hub.init(this)
        enableEdgeToEdge()
        setContent { S100Theme { App() } }
        perms.launch(buildList {
            if (Build.VERSION.SDK_INT >= 31) { add(Manifest.permission.BLUETOOTH_CONNECT); add(Manifest.permission.BLUETOOTH_SCAN) }
            else add(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.ACCESS_COARSE_LOCATION)
        }.distinct().toTypedArray())
    }

    private fun startLink() = LinkService.start(this)

    fun hasNotificationAccess() = NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)

    fun openNotificationAccess() {
        val i = if (Build.VERSION.SDK_INT >= 30)
            Intent(Settings.ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS)
                .putExtra(Settings.EXTRA_NOTIFICATION_LISTENER_COMPONENT_NAME, ComponentName(this, NotifyListener::class.java).flattenToString())
        else Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        startActivity(i)
    }

    @Composable
    private fun App() {
        var tab by remember { mutableIntStateOf(0) }
        Column(Modifier.fillMaxSize().background(C.Black).systemBarsPadding()) {
            Box(Modifier.weight(1f)) {
                when (tab) {
                    0 -> HomeScreen(this@MainActivity)
                    1 -> FacesScreen(this@MainActivity)
                    else -> SettingsScreen(this@MainActivity)
                }
            }
            Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                listOf("Watch", "Faces", "Settings").forEachIndexed { i, label ->
                    Box(Modifier.weight(1f).clickable { tab = i }.padding(vertical = 8.dp), contentAlignment = Alignment.Center) {
                        Text(label, color = if (tab == i) C.Orange else C.Dim, fontSize = 15.sp,
                            fontWeight = if (tab == i) FontWeight.SemiBold else FontWeight.Normal)
                    }
                }
            }
        }
    }
}
