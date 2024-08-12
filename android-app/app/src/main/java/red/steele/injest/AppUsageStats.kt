package red.steele.injest

import android.app.Service
import android.app.usage.UsageStats
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class AppUsageStats : Service() {

    private lateinit var webSocketManager: WebSocketManager
    private var lastScheduledTime: Long = System.currentTimeMillis()

    override fun onCreate() {
        super.onCreate()
        try {
            webSocketManager = WebSocketManager(AppState.serverUrl)
        } catch (e: Exception) {
            Log.e("AppUsageStats", "Error in onCreate: ${e.message}", e)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        scheduleAppUsageStats()
        return START_STICKY
    }

    fun getAppUsageStatsJson(): String {
        val usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val endTime = System.currentTimeMillis()
        val startTime = lastScheduledTime

        val usageStatsList: List<UsageStats> = usageStatsManager.queryUsageStats(
            UsageStatsManager.INTERVAL_DAILY, startTime, endTime
        )

        val jsonArray = JSONArray()

        for (usageStats in usageStatsList) {
            val jsonObject = JSONObject()
            jsonObject.put("packageName", usageStats.packageName)
            jsonObject.put("totalTimeInForeground", usageStats.totalTimeInForeground)
            jsonObject.put("firstTimeStamp", usageStats.firstTimeStamp)
            jsonObject.put("lastTimeStamp", usageStats.lastTimeStamp)
            jsonObject.put("lastTimeUsed", usageStats.lastTimeUsed)
            jsonObject.put("lastTimeVisible", usageStats.lastTimeVisible)
            jsonObject.put("lastTimeForegroundServiceUsed", usageStats.lastTimeForegroundServiceUsed)
            jsonObject.put("totalTimeVisible", usageStats.totalTimeVisible)
            jsonObject.put("totalTimeForegroundServiceUsed", usageStats.totalTimeForegroundServiceUsed)
            jsonArray.put(jsonObject)
        }

        Log.e("AppUsageStats", "App usage stats JSON: $jsonArray")
        return jsonArray.toString()
    }

    private fun scheduleAppUsageStats() {
        Log.d("AppUsageStats", "Scheduling app usage stats collection")
        val scheduler = Executors.newSingleThreadScheduledExecutor()
        scheduler.scheduleWithFixedDelay({
            val appUsageStatsJson = getAppUsageStatsJson()
            webSocketManager.sendAppUsageStats(appUsageStatsJson)
            lastScheduledTime = System.currentTimeMillis()
        }, 0, 5, TimeUnit.SECONDS)
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d("AppUsageStats", "Service destroyed")
    }
}