package dev.openwear.s100.feature

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.core.app.NotificationCompat
import dev.openwear.s100.R

/** "Find phone" on the watch: ring loudly (alarm stream) and vibrate until stopped or 30 s pass. */
object FindPhone {
    private var ringtone: Ringtone? = null
    private var savedVolume = -1

    fun ring(context: Context) {
        if (ringtone?.isPlaying == true) return
        val am = context.getSystemService(AudioManager::class.java)
        savedVolume = am.getStreamVolume(AudioManager.STREAM_ALARM)
        am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)
        val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM) ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        ringtone = RingtoneManager.getRingtone(context, uri)?.apply {
            audioAttributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build()
            play()
        }
        context.getSystemService(Vibrator::class.java)?.vibrate(
            VibrationEffect.createWaveform(longArrayOf(0, 600, 400), 0))
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("find", "Find phone", NotificationManager.IMPORTANCE_HIGH))
        val stop = PendingIntent.getBroadcast(context, 1, Intent(context, StopReceiver::class.java), PendingIntent.FLAG_IMMUTABLE)
        nm.notify(7, NotificationCompat.Builder(context, "find")
            .setSmallIcon(R.drawable.ic_watch).setContentTitle("Your watch is looking for this phone")
            .setContentText("Tap to stop").setContentIntent(stop).setDeleteIntent(stop).setAutoCancel(true)
            .addAction(0, "Stop", stop).setPriority(NotificationCompat.PRIORITY_MAX).build())
        android.os.Handler(context.mainLooper).postDelayed({ stop(context) }, 30_000)
    }

    fun stop(context: Context) {
        ringtone?.stop(); ringtone = null
        context.getSystemService(Vibrator::class.java)?.cancel()
        if (savedVolume >= 0) {
            context.getSystemService(AudioManager::class.java).setStreamVolume(AudioManager.STREAM_ALARM, savedVolume, 0)
            savedVolume = -1
        }
        context.getSystemService(NotificationManager::class.java).cancel(7)
    }

    class StopReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) = stop(context)
    }
}
