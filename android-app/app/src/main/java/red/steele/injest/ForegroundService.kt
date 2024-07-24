package red.steele.injest

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ForegroundService : Service() {

    companion object {
        const val CHANNEL_ID = "InjestServiceChannel"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Stomach")
            .setContentText("Injesting...")
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        startForeground(1, notification)

//        notifyService.startService()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Start and manage the sensor, GPS, audio, and screenshot services
        startService(Intent(this, ScreenshotService::class.java)) // started in mainactivity because dependes on permissions
        startService(Intent(this, GpsService::class.java))
        startService(Intent(this, SensorService::class.java))
        startService(Intent(this, AudioService::class.java))
        startService(Intent(this, SMSService::class.java))


        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    private fun createNotificationChannel() {
        val serviceChannel = NotificationChannel(
            CHANNEL_ID,
            "Injest Service",
            NotificationManager.IMPORTANCE_DEFAULT
        )
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(serviceChannel)
    }
}