package dev.openwear.s100.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Reconnect to the watch after a phone restart (if a watch was set up). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        Hub.init(context)
        if (Hub.prefs.address.isNotBlank()) LinkService.start(context)
    }
}
