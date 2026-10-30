package dev.openwear.s100.service

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import dev.openwear.s100.ble.Protocol
import dev.openwear.s100.feature.MusicBridge
import dev.openwear.s100.feature.NavMirror
import kotlinx.coroutines.launch

/**
 * Notification access: forwards notifications to the watch, mirrors Google Maps turn-by-turn
 * notifications to the watch's navigation screen, and (through the same permission) lets
 * MusicBridge read media sessions.
 */
class NotifyListener : NotificationListenerService() {
    private val recent = LinkedHashMap<String, Long>()

    override fun onListenerConnected() {
        Hub.init(this)
        MusicBridge.attach(this)
    }

    override fun onListenerDisconnected() { MusicBridge.detach() }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        Hub.init(this)
        val n = sbn.notification
        if (sbn.packageName == NavMirror.MAPS) { NavMirror.onMapsNotification(this, n); return }
        if (sbn.packageName == packageName) return
        if (!Hub.prefs.forwardNotifications) return
        if (n.flags and (Notification.FLAG_ONGOING_EVENT or Notification.FLAG_GROUP_SUMMARY) != 0 &&
            n.category != Notification.CATEGORY_CALL) return
        if (n.category == Notification.CATEGORY_TRANSPORT || n.category == Notification.CATEGORY_PROGRESS) return
        Hub.prefs.seenApps = Hub.prefs.seenApps + sbn.packageName
        if (sbn.packageName in Hub.prefs.blockedApps) return

        val ex = n.extras
        val title = ex.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val body = (ex.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: ex.getCharSequence(Notification.EXTRA_TEXT))
            ?.toString().orEmpty()
        if (title.isBlank() && body.isBlank()) return
        val isCall = n.category == Notification.CATEGORY_CALL
        val text = if (isCall) title.ifBlank { "Incoming call" } else listOf(title, body).filter { it.isNotBlank() }.joinToString(": ")

        // drop exact repeats (apps re-post the same notification when it updates)
        val key = sbn.packageName + text
        val now = System.currentTimeMillis()
        if ((recent[key] ?: 0L) > now - 15_000) return
        recent[key] = now
        if (recent.size > 50) recent.remove(recent.keys.first())

        val type = if (isCall) Protocol.TYPE_CALL else Protocol.APP_TYPES[sbn.packageName] ?: Protocol.TYPE_OTHER
        Hub.scope.launch { Hub.notify(text, type) }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        if (sbn.packageName == NavMirror.MAPS) NavMirror.onMapsEnded()
    }
}
