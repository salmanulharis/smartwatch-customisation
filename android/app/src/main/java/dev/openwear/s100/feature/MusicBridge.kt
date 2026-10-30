package dev.openwear.s100.feature

import android.content.ComponentName
import android.content.Context
import android.media.AudioManager
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import dev.openwear.s100.ble.Protocol
import dev.openwear.s100.service.Hub
import dev.openwear.s100.service.NotifyListener
import kotlinx.coroutines.launch

/** Phone media session <-> watch music screen (title + play state out, buttons in). */
object MusicBridge {
    private var manager: MediaSessionManager? = null
    private var controller: MediaController? = null
    private var context: Context? = null
    private var lastSent = ""

    private val sessionsListener = MediaSessionManager.OnActiveSessionsChangedListener { list -> pick(list) }

    private val callback = object : MediaController.Callback() {
        override fun onMetadataChanged(metadata: MediaMetadata?) = pushCurrent()
        override fun onPlaybackStateChanged(state: PlaybackState?) = pushCurrent()
    }

    fun attach(ctx: Context) {
        context = ctx.applicationContext
        val m = ctx.getSystemService(MediaSessionManager::class.java)
        manager = m
        val cn = ComponentName(ctx, NotifyListener::class.java)
        try {
            m.addOnActiveSessionsChangedListener(sessionsListener, cn)
            pick(m.getActiveSessions(cn))
        } catch (_: SecurityException) { /* notification access not granted yet */ }
    }

    fun detach() {
        manager?.removeOnActiveSessionsChangedListener(sessionsListener)
        controller?.unregisterCallback(callback)
        controller = null
    }

    private fun pick(list: List<MediaController>?) {
        val c = list?.firstOrNull { it.playbackState?.state == PlaybackState.STATE_PLAYING } ?: list?.firstOrNull()
        if (c?.sessionToken == controller?.sessionToken) return
        controller?.unregisterCallback(callback)
        controller = c
        c?.registerCallback(callback)
        pushCurrent()
    }

    fun pushCurrent() {
        if (!Hub.prefs.musicSync) return
        val c = controller ?: return
        val md = c.metadata ?: return
        val title = listOfNotNull(md.getString(MediaMetadata.METADATA_KEY_TITLE),
            md.getString(MediaMetadata.METADATA_KEY_ARTIST)).filter { it.isNotBlank() }.joinToString(" - ")
        val playing = c.playbackState?.state == PlaybackState.STATE_PLAYING
        val key = "$title|$playing"
        if (key == lastSent || title.isBlank()) return
        val link = Hub.link.value?.takeIf { Hub.ready } ?: return
        lastSent = key
        Hub.scope.launch {
            link.session {
                val pk = Protocol.music(title, playing)
                write(pk[0], big = true); write(pk[1], big = true)
                request(pk[2], byteArrayOf(0x3A, 0xFA.toByte()), 3000, big = true)
            }
        }
    }

    fun onWatchButton(ev: Int) {
        val tc = controller?.transportControls
        val am = context?.getSystemService(AudioManager::class.java)
        when (ev) {
            Protocol.EV_PLAY_PAUSE -> if (controller?.playbackState?.state == PlaybackState.STATE_PLAYING) tc?.pause() else tc?.play()
            Protocol.EV_NEXT -> tc?.skipToNext()
            Protocol.EV_PREV -> tc?.skipToPrevious()
            Protocol.EV_VOL_UP -> am?.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_RAISE, 0)
            Protocol.EV_VOL_DOWN -> am?.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_LOWER, 0)
        }
    }
}
