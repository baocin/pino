package red.steele.injest

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

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
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Start and manage the sensor, GPS, audio, and screenshot services
//        if (hasPermissions()) {
            // startService(Intent(this, ImageSyncService::class.java))
              startService(Intent(this, AutoScreenshotService::class.java))
            startService(Intent(this, GpsService::class.java))
            startService(Intent(this, SensorService::class.java))
            startService(Intent(this, AudioService::class.java))
            // startService(Intent(this, SMSService::class.java))
//        }

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
    private fun hasPermissions(): Boolean {
        Log.d("ForegroundService", "Checking permissions")
        val permissions = arrayOf(
            android.Manifest.permission.RECORD_AUDIO,
            android.Manifest.permission.ACCESS_FINE_LOCATION,
            android.Manifest.permission.CAMERA,
            android.Manifest.permission.READ_EXTERNAL_STORAGE,
            android.Manifest.permission.WRITE_EXTERNAL_STORAGE
        )
        val allGranted = permissions.all {
            val isGranted = ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
            Log.d("ForegroundService", "Permission $it: ${if (isGranted) "Granted" else "Denied"}")
            isGranted
        }
        Log.d("ForegroundService", "All permissions granted: $allGranted")
//        return allGranted
        return true
    }
}