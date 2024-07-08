package red.steele.injest

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat

class NotifyService : Service() {

    companion object {
        const val CHANNEL_ID = "NotifyServiceChannel"
        const val CHANNEL_NAME = "Notify Service Channel"
        const val NOTIFICATION_ID = 3

//        fun startService(context: Context) {
//            val startIntent = Intent(context, NotifyService::class.java)
//            context.startService(startIntent)
//        }
//
//        fun showNotification(context: Context, title: String, message: String) {
//            val intent = Intent(context, NotifyService::class.java)
//            intent.putExtra("title", title)
//            intent.putExtra("message", message)
//            context.startService(intent)
//        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
//        val notification = createNotification("Service Started", "NotifyService is running")
//        startForeground(NOTIFICATION_ID, notification)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
//        val title = intent?.getStringExtra("title")
//        val message = intent?.getStringExtra("message")
//        if (title != null && message != null) {
//            val notification = createNotification(title, message)
//            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
//            manager.notify(NOTIFICATION_ID, notification)
//        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    private fun createNotificationChannel() {
        val serviceChannel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_DEFAULT
        )
        val manager = getSystemService(NotificationManager::class.java)
        manager?.createNotificationChannel(serviceChannel)

    }


    fun createNotification(context: Context, title: String, message: String): Notification {
        val notification = NotificationCompat.Builder(
            context,
            CHANNEL_ID
        )
            .setContentTitle(title)
            .setContentText(message)
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .build();

        startForeground(NOTIFICATION_ID, notification);
//        return NotificationCompat.Builder(this, CHANNEL_ID)
//            .setContentTitle(title)
//            .setContentText(message)
//            .setSmallIcon(android.R.drawable.ic_notification_overlay) // Added a default icon to avoid null reference
//            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
//            .build()
        return notification
    }
}
