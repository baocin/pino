package red.steele.injest

import android.annotation.SuppressLint
import android.content.Context
import android.content.res.Resources
import android.graphics.Bitmap
import io.github.cdimascio.dotenv.dotenv
import java.util.concurrent.CopyOnWriteArrayList

@SuppressLint("StaticFieldLeak")
object AppState {
    private val dotenv = dotenv {
        directory = "/assets"
        filename = "env"
    }
    private val defaultServerIp = dotenv.get("REALTIME_SERVER_IP") ?: "REPLACE_WITH_SERVER_IP"
    private val defaultServerPort = dotenv.get("REALTIME_SERVER_PORT") ?: "80"

    private lateinit var _context: Context
    val context: Context
        get() = _context

    var serverIp: String = defaultServerIp
    var serverPort: String = defaultServerPort
    var serverUrl: String = "$serverIp:$serverPort"

    var totalAudioBytesTransferred: Float = 0f
    var totalGpsBytesTransferred: Float = 0f
    var totalScreenshotBytesTransferred: Float = 0f
    var totalSensorBytesTransferred: Float = 0f
    var totalNotificationBytesTransferred: Float = 0f
    var totalPowerBytesTransferred: Float = 0f
    var totalPhotoBytesTransferred: Float = 0f

    var onlySendWhenPlugged: Boolean = false
    var sendDataEver: Boolean = true

    val startTime = System.currentTimeMillis()

    var audioPacketsSent: Int = 0
    var gpsPacketsSent: Int = 0
    var screenshotPacketsSent: Int = 0
    var sensorPacketsSent: Int = 0

    var isGpsServiceEnabled: Boolean = true
    var isSensorServiceEnabled: Boolean = true
    var isAudioServiceEnabled: Boolean = true
    var isScreenshotServiceEnabled: Boolean = false
    var isForegroundServiceEnabled: Boolean = true
    var isNotificationInterceptorServiceEnabled: Boolean = true
    var isPhotoServiceEnabled : Boolean = true

    var isConnected : Boolean = true

    //    Audio size: 640 bytes -> Compressed audio size: 475 bytes
    //    Screenshot size: 87537 bytes -> Compressed screenshot size: 74264 bytes
    //
    var audioResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()
    var gpsResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()
    var screenshotResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()
    var sensorResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()
    var powerResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()
    var notificationResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()
    var photoResponseTimes: CopyOnWriteArrayList<ResponseTime> = CopyOnWriteArrayList()

    var screenshotHeight: Int = Resources.getSystem().displayMetrics.heightPixels
    var screenshotWidth: Int = Resources.getSystem().displayMetrics.widthPixels

    var powerConnectionReceiver: PowerConnectionReceiver = PowerConnectionReceiver()

    var lastScreenshot: Bitmap? = null

    fun initialize(appContext: Context) {
        _context = appContext.applicationContext
        serverIp = loadServerIp()
    }

    fun shouldSendData(): Boolean {
        if (!sendDataEver) {
            return false
        }
        if (!isConnected){
            return false
        }
        if (onlySendWhenPlugged) {
            return powerConnectionReceiver.isPlugged
        }
        return true
    }

    private fun loadServerIp(): String {
        val sharedPreferences = context.getSharedPreferences("AppPreferences", Context.MODE_PRIVATE)
        return sharedPreferences.getString("REALTIME_SERVER_IP", defaultServerIp) ?: defaultServerIp
    }

//    fun setServerIpToSharedPreferences(newIp: String) {
//        Log.d("AppState", "New ip: ${AppState.defaultServerIp}")
//
//        val sharedPreferences =
//            context.getSharedPreferences("AppPreferences", Context.MODE_PRIVATE)
//        with(sharedPreferences.edit()) {
//            putString("SERVER_IP", newIp)
//            apply()
//        }
//        serverIp = newIp
//    }
}

data class ResponseTime(val timestamp: Long, val status : Long, val duration: Long)
