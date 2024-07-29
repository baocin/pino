package red.steele.injest

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent


class PowerConnectionReceiver : BroadcastReceiver() {
    private lateinit var webSocketManager: WebSocketManager

    var isPlugged: Boolean = false
        private set

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        if (action == Intent.ACTION_POWER_CONNECTED) {
            isPlugged = true
            webSocketManager.sendPowerConnectionStatus(true)
        } else if (action == Intent.ACTION_POWER_DISCONNECTED) {
            isPlugged = false
            webSocketManager.sendPowerConnectionStatus(false)
        }
    }
}