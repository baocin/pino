package red.steele.injest

import android.util.JsonReader
import android.util.JsonToken
import android.util.Log
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.accessibility.AccessibilityEvent
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.io.StringReader
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class WebSocketManager(private val serverUrl: String) {

    private val client = OkHttpClient()
    private var webSocket: WebSocket? = null
    private val listeners = mutableListOf<WebSocketListener>()
    private var messageId = "" // Unique message ID for each payload
    private val messageSendTimes = mutableMapOf<String, Long>() // Dictionary to store message_id and send_time
    private val messageCache = mutableMapOf<String, String>()

    init {
        connect()
    }

    private fun connect() {
        val serverIp = AppState.serverIp
        val request = Request.Builder().url("ws://$serverIp/ws").build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                listeners.forEach { it.onOpen(webSocket, response) }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                listeners.forEach { it.onMessage(webSocket, text) }

                // Handle server response
                val responseJson = JsonReader(StringReader(text)).use { reader ->
                    val map = mutableMapOf<String, Any>()
                    reader.beginObject()
                    while (reader.hasNext()) {
                        val name = reader.nextName()
                        val value = when (reader.peek()) {
                            JsonToken.STRING -> reader.nextString()
                            JsonToken.NUMBER -> reader.nextInt()
                            JsonToken.BOOLEAN -> reader.nextBoolean()
                            else -> reader.skipValue()
                        }
                        map[name] = value
                    }
                    reader.endObject()
                    map
                }

                if (responseJson.containsKey("message_id") && responseJson.containsKey("status") && responseJson.containsKey("message_type")) {
                    val messageId = responseJson["message_id"]?.toString() ?: ""
                    val status = responseJson["status"] as? Int ?: -1
                    val messageType = responseJson["message_type"]?.toString() ?: ""
                    if (messageId.isNotEmpty() && status != -1 && messageType.isNotEmpty()) {
                        handleServerResponse(messageId, status, messageType)
                    }
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                listeners.forEach { it.onMessage(webSocket, bytes) }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                listeners.forEach { it.onClosing(webSocket, code, reason) }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                listeners.forEach { it.onClosed(webSocket, code, reason) }
                reconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                listeners.forEach { it.onFailure(webSocket, t, response) }
                reconnect()
            }
        })
    }

    private fun reconnect() {
        Executors.newSingleThreadScheduledExecutor().schedule({
            connect()
        }, 5, TimeUnit.SECONDS)
    }

    fun addListener(listener: WebSocketListener) {
        listeners.add(listener)
    }

    fun removeListener(listener: WebSocketListener) {
        listeners.remove(listener)
    }

    fun sendAudioData(audioData: ByteArray, callback: (Int) -> Unit) {
        if (AppState.shouldSendData() && AppState.isAudioServiceEnabled) {
            updateMessageId()
            val message = """{ "message_id": "$messageId", "type": "audio", "data": "${audioData.toBase64()}", "device_id": 1}"""
            sendMessage(message, callback)
            AppState.totalAudioBytesTransferred += message.toByteArray().size
        }
    }

    fun sendGpsData(latitude: Double, longitude: Double, altitude: Double, time: Long, callback: (Int) -> Unit) {
        if (AppState.shouldSendData() && AppState.isGpsServiceEnabled) {
            updateMessageId()
            val message = """{"message_id": "$messageId", "type": "gps", "data": {"latitude": $latitude, "longitude": $longitude, "altitude": $altitude, "time": $time}, "device_id": 1}"""
            sendMessage(message, callback)
            AppState.totalGpsBytesTransferred += message.toByteArray().size
        }
    }

    fun sendScreenshotData(screenshotData: ByteArray, callback: (Int) -> Unit) {
        if (AppState.shouldSendData() && AppState.isScreenshotServiceEnabled) {
            updateMessageId()
            val message = """{"message_id": "$messageId","type": "screenshot", "data": "${screenshotData.toBase64()}", "device_id": 1}"""
            sendMessage(message, callback)
            AppState.totalScreenshotBytesTransferred += message.toByteArray().size
        }
    }

    fun sendSensorData(sensorType: String, values: FloatArray, callback: (Int) -> Unit) {
        if (AppState.shouldSendData() && AppState.isSensorServiceEnabled) {
            val time = System.currentTimeMillis()
            val x = values.getOrNull(0)?.toString() ?: "null"
            val y = values.getOrNull(1)?.toString() ?: "null"
            val z = values.getOrNull(2)?.toString() ?: "null"
            updateMessageId()
            val message = """{ "message_id": "$messageId","type": "sensor", "data": {"time": $time, "sensorType": "$sensorType", "x": $x, "y": $y, "z": $z}, "device_id": 1}"""
            sendMessage(message, callback)
            AppState.totalSensorBytesTransferred += message.toByteArray().size
        }
    }

    fun sendSensorDataList(sensorDataList: List<Pair<String, FloatArray>>, callback: (Int) -> Unit) {
        if (AppState.shouldSendData() && AppState.isSensorServiceEnabled) {
            val time = System.currentTimeMillis()
            val dataList = sensorDataList.map { (sensorType, values) ->
                val x = values.getOrNull(0)?.toString() ?: "null"
                val y = values.getOrNull(1)?.toString() ?: "null"
                val z = values.getOrNull(2)?.toString() ?: "null"
                updateMessageId()
                val message = """{"time": $time, "sensorType": "$sensorType", "x": $x, "y": $y, "z": $z}"""
                """{"type": "sensor", "data": $message, "device_id": 1, "message_id": "$messageId"}"""
            }
            val jsonDataList = dataList.joinToString(separator = ",", prefix = "[", postfix = "]")
            sendMessage(jsonDataList, callback)
            AppState.totalSensorBytesTransferred += dataList.sumOf { it.toByteArray().size }
        }
    }

    fun sendKeyEvent(event: KeyEvent, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "key", "keyCode": ${event.keyCode}, "action": ${event.action}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
        }
    }

    fun sendMotionEvent(event: MotionEvent, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "motion", "x": ${event.x}, "y": ${event.y}, "action": ${event.action}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
        }
    }

    fun sendNotificationEvent(notification: String, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "notification", "data": "$notification", "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
            AppState.totalNotificationBytesTransferred += message.toByteArray().size
        }
    }

    fun sendManualPhotoData(photo: ByteArray, isScreenshot : Boolean, callback: (Int) -> Unit) {
        if (AppState.shouldSendData() && AppState.isPhotoServiceEnabled) {
            updateMessageId()
            val message = """{"type": "manual_photo", "source": "phone", "data": {"isScreenshot": $isScreenshot, "photo": "${photo.toBase64()}"}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
            AppState.totalPhotoBytesTransferred += message.toByteArray().size
        }
    }

    fun sendSystemStats(systemStats: String, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "system_stats", "data": $systemStats, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
        }
    }

    fun sendSMSData(smsData: String, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "sms", "data": $smsData, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
        }
    }

    fun updateMessageId(){
        messageId = java.util.UUID.randomUUID().toString()
    }

    private fun sendMessage(message: String, callback: (Int) -> Unit) {
        
        try {
            webSocket?.send(message)
            messageSendTimes[messageId] = System.currentTimeMillis() // Store the send time
            messageCache[messageId] = message
            
            // messageId += 1 // ensure it is unique
            val responseCode = 200 // Assuming 200 as success status code
            callback(responseCode)
        } catch (e: Exception) {
            Log.e("WebSocketManager", "Error sending message", e)
            e.printStackTrace()
            val responseCode = 500 // Assuming 500 as failure status code
            callback(responseCode)
        }
    }

    fun sendPowerConnectionStatus(isPlugged: Boolean, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            val message = """{"type": "power_connection", "data": {"isPlugged": $isPlugged}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
            AppState.totalPowerBytesTransferred += message.toByteArray().size
        }
    }

    private fun ByteArray.toBase64(): String {
        return ByteString.of(*this).base64()
    }

    fun close() {
        webSocket?.close(NORMAL_CLOSURE_STATUS, "Closing WebSocket connection")
    }

    fun sendAccessibilityEvent(event: AccessibilityEvent, callback: (Int) -> Unit) {
        if (AppState.shouldSendData()) {
            val message = """{"type": "accessibility", "data": {"event": $event}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message, callback)
        }
    }

    private fun handleServerResponse(messageId: String, status: Int, messageType: String) {
        messageCache.remove(messageId)
        // Handle server response based on messageId, status, and messageType
        // Update AppState response times and durations accordingly
        val sendTime = messageSendTimes[messageId]
        val duration = if (sendTime != null) System.currentTimeMillis() - sendTime else -1L
        Log.d("WebSocketManager", "handleServerResponse called with messageId: $messageId, status: $status, messageType: $messageType")

        when (messageType) {
            "audio" -> AppState.audioResponseTimes.add(ResponseTime(AppState.audioResponseTimes.size.toLong(), status.toLong(), duration))
            "gps" -> AppState.gpsResponseTimes.add(ResponseTime(AppState.gpsResponseTimes.size.toLong(), status.toLong(), duration))
            "screenshot" -> AppState.screenshotResponseTimes.add(ResponseTime(AppState.screenshotResponseTimes.size.toLong(), status.toLong(), duration))
            "sensor" -> AppState.sensorResponseTimes.add(ResponseTime(AppState.sensorResponseTimes.size.toLong(), status.toLong(), duration))
            "power_connection" -> AppState.powerResponseTimes.add(ResponseTime(AppState.powerResponseTimes.size.toLong(), status.toLong(), duration))
            "notification" -> AppState.notificationResponseTimes.add(ResponseTime(AppState.notificationResponseTimes.size.toLong(), status.toLong(), duration))
            "manual_photo" -> AppState.photoResponseTimes.add(ResponseTime(AppState.photoResponseTimes.size.toLong(), status.toLong(), duration))
            else -> Log.w("WebSocketManager", "Unknown messageType: $messageType")
        }

        messageSendTimes.remove(messageId)
    }

    companion object {
        private const val NORMAL_CLOSURE_STATUS = 1000
    }
}
