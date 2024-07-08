package red.steele.injest

import android.content.res.Resources
import android.graphics.Bitmap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.Properties
import java.io.FileInputStream

object AppState {
    var totalAudioBytesTransferred: Float = 0f
    var totalGpsBytesTransferred: Float = 0f
    var totalScreenshotBytesTransferred: Float = 0f
    var totalSensorBytesTransferred: Float = 0f
    var totalNotificationBytesTransferred: Float = 0f
    var totalPowerBytesTransferred: Float = 0f
    var totalPhotoBytesTransferred: Float = 0f

    var onlySendWhenPlugged: Boolean = false
    var sendDataEver: Boolean = true

    var serverIp: String = loadServerIp()
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

    public fun shouldSendData(): Boolean {
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
        val properties = Properties()
        val inputStream = FileInputStream(".env")
        properties.load(inputStream)
        return properties.getProperty("SERVER_IP", "REPLACE_WITH_SERVER_IP")
    }
}

data class ResponseTime(val timestamp: Long, val status : Long, val duration: Long)
