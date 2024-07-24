package red.steele.injest

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log


class NotificationInterceptorService : NotificationListenerService() {

    private lateinit var webSocketManager: WebSocketManager

    companion object {
        private const val TAG = "NotificationInterceptorService"
    }

    override fun onCreate() {
        super.onCreate()
        webSocketManager = WebSocketManager(AppState.serverIp)
        Log.d(TAG, "NotificationInterceptorService created")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        sbn?.let {
            val notificationText = it.notification.extras.getString("android.text").toString()
            Log.d(TAG, "Notification received: $notificationText")
            webSocketManager.sendNotificationEvent(notificationText) { responseCode ->
//                AppState.notificationResponseCodes.add(
//                    responseCode
//                )
            }
            Log.d(TAG, "Notification event sent to WebSocket: $notificationText")
        }
    }

    override fun onDestroy() {
        webSocketManager.close()
        super.onDestroy()
        Log.d(TAG, "NotificationInterceptorService destroyed")
    }
}

