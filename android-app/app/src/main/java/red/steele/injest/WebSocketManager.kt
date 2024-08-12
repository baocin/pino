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
        val request = Request.Builder().url("ws://$serverUrl/ws").build()
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

    fun sendAudioData(audioData: ByteArray
) {
        if (AppState.shouldSendData() && AppState.isAudioServiceEnabled) {
            updateMessageId()
            val message = """{ "message_id": "$messageId", "type": "audio", "data": "${audioData.toBase64()}", "device_id": 1}"""
            sendMessage(message)

            AppState.totalAudioBytesTransferred += message.toByteArray().size
        }
    }

    fun sendGpsData(latitude: Double, longitude: Double, altitude: Double, time: Long
) {
        if (AppState.shouldSendData() && AppState.isGpsServiceEnabled) {
            updateMessageId()
            val message = """{"message_id": "$messageId", "type": "gps", "data": {"latitude": $latitude, "longitude": $longitude, "altitude": $altitude, "time": $time}, "device_id": 1}"""
            sendMessage(message)

            AppState.totalGpsBytesTransferred += message.toByteArray().size
        }
    }
    fun sendImageData(imageData: ByteArray, isScreenshot: Boolean?, isGenerated: Boolean?, isManual: Boolean?, isFrontCamera: Boolean?, isRearCamera: Boolean?, imageHash: String?, imageId: String?) {
        Log.d("WebSocketManager", "sendImageData captured and sent. Size: ${imageData.size} bytes")

        if (AppState.shouldSendData()) {
            updateMessageId()
            val base64ImageData = imageData.toBase64()
            
            val dataJson = buildString {
                append("""{"data": "$base64ImageData"""")
                if (isGenerated == true) append(""", "is_generated": $isGenerated""")
                if (isManual == true) append(""", "is_manual": $isManual""")
                if (isFrontCamera == true) append(""", "is_front_camera": $isFrontCamera""")
                if (isRearCamera == true) append(""", "is_rear_camera": $isRearCamera""")
                if (imageHash != null) append(""", "image_hash": "$imageHash"""")
                if (imageId != null) append(""", "image_id": $imageId"""")
                append("}")
            }

            val message = """
            {
                "message_id": "$messageId",
                "type": "image",
                "data": $dataJson,
                "device_id": 1
            }
            """.trimIndent()
            sendMessage(message)
        }
    }

    fun sendAppUsageStats(appUsageStats: String) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"message_id": "$messageId", "type": "app_usage", "data": $appUsageStats, "device_id": 1}"""
            Log.d("WebSocketManager", "sendAppUsageStats captured and sent. Size: ${message} bytes")
            sendMessage(message)

            AppState.totalNotificationBytesTransferred += message.toByteArray().size
        }
    }

    fun sendScreenshotData(screenshotData: ByteArray, isAutoGenerated: Boolean
) {
        Log.d("WebSocketManager", "sendScreenshotData captured and sent. Size: ${screenshotData.size} bytes")

        if (AppState.shouldSendData() && AppState.isImageSyncServiceEnabled) {
            updateMessageId()
            val metadata = if (isAutoGenerated) "auto" else "manual"
            val message = """{"message_id": "$messageId","type": "screenshot", "data": {"metadata": "$metadata", "screenshot": "${screenshotData.toBase64()}"}, "device_id": 1}"""
            sendMessage(message)

            AppState.totalScreenshotBytesTransferred += message.toByteArray().size
        }
    }

    fun sendSensorData(sensorType: String, values: FloatArray
) {
        if (AppState.shouldSendData() && AppState.isSensorServiceEnabled) {
            val time = System.currentTimeMillis()
            val x = values.getOrNull(0)?.toString() ?: "null"
            val y = values.getOrNull(1)?.toString() ?: "null"
            val z = values.getOrNull(2)?.toString() ?: "null"
            updateMessageId()
            val message = """{ "message_id": "$messageId","type": "sensor", "data": {"time": $time, "sensorType": "$sensorType", "x": $x, "y": $y, "z": $z}, "device_id": 1}"""
            sendMessage(message)

            AppState.totalSensorBytesTransferred += message.toByteArray().size
        }
    }

    fun sendSensorDataList(sensorDataList: List<Pair<String, FloatArray>>
) {
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
            sendMessage(jsonDataList)

            AppState.totalSensorBytesTransferred += dataList.sumOf { it.toByteArray().size }
        }
    }

    fun sendKeyEvent(event: KeyEvent
) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "key", "keyCode": ${event.keyCode}, "action": ${event.action}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)

        }
    }

    fun sendMotionEvent(event: MotionEvent
) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "motion", "x": ${event.x}, "y": ${event.y}, "action": ${event.action}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)

        }
    }

    fun sendNotificationEvent(notification: String
) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "notification", "data": "$notification", "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)

            AppState.totalNotificationBytesTransferred += message.toByteArray().size
        }
    }

    fun sendManualPhotoData(photo: ByteArray, isScreenshot : Boolean
) {
        Log.d("WebSocketManager", "sendManualPhotoData captured and sent. Size: ${photo.size} bytes")

        if (AppState.shouldSendData() && AppState.isPhotoServiceEnabled) {
            updateMessageId()
            val message = """{"type": "manual_photo", "source": "phone", "data": {"isScreenshot": $isScreenshot, "photo": "${photo.toBase64()}"}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)
            AppState.totalPhotoBytesTransferred += message.toByteArray().size
        }
    }

    fun sendSystemStats(systemStats: String
) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "system_stats", "data": $systemStats, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)

        }
    }

    fun sendSMSData(smsData: String
) {
        if (AppState.shouldSendData()) {
            updateMessageId()
            val message = """{"type": "sms", "data": $smsData, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)
        }
    }

    fun updateMessageId(){
        messageId = java.util.UUID.randomUUID().toString()
    }

    private fun sendMessage(message: String
) {
        
        try {
            webSocket?.send(message)
            messageSendTimes[messageId] = System.currentTimeMillis() // Store the send time
            messageCache[messageId] = message
            
        } catch (e: Exception) {
            Log.e("WebSocketManager", "Error sending message", e)
            e.printStackTrace()
        }
    }

    fun sendPowerConnectionStatus(isPlugged: Boolean) {
        if (AppState.shouldSendData()) {
            val message = """{"type": "power_connection", "data": {"isPlugged": $isPlugged}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)
            AppState.totalPowerBytesTransferred += message.toByteArray().size
        }
    }

    private fun ByteArray.toBase64(): String {
        return ByteString.of(*this).base64()
    }

    fun close() {
        webSocket?.close(NORMAL_CLOSURE_STATUS, "Closing WebSocket connection")
    }

    fun sendAccessibilityEvent(event: AccessibilityEvent
) {
        if (AppState.shouldSendData()) {
            val message = """{"type": "accessibility", "data": {"event": $event}, "device_id": 1, "message_id": "$messageId"}"""
            sendMessage(message)

        }
    }

    fun handleAppUsageReponse(){
        return true
    }

    private fun handleServerResponse(messageId: String, status: Int, messageType: String) {
        messageCache.remove(messageId)
        // Handle server response based on messageId, status, and messageType
        // Update AppState response times and durations accordingly
        val sendTime = messageSendTimes[messageId]
        val duration = if (sendTime != null) System.currentTimeMillis() - sendTime else -1L
//        Log.d("WebSocketManager", "handleServerResponse called with messageId: $messageId, status: $status, messageType: $messageType")

        when (messageType) {
            "audio" -> AppState.audioResponseTimes.add(ResponseTime(AppState.audioResponseTimes.size.toLong(), status.toLong(), duration))
            "gps" -> AppState.gpsResponseTimes.add(ResponseTime(AppState.gpsResponseTimes.size.toLong(), status.toLong(), duration))
            "screenshot" -> AppState.screenshotResponseTimes.add(ResponseTime(AppState.screenshotResponseTimes.size.toLong(), status.toLong(), duration))
            "sensor" -> AppState.sensorResponseTimes.add(ResponseTime(AppState.sensorResponseTimes.size.toLong(), status.toLong(), duration))
            "power_connection" -> AppState.powerResponseTimes.add(ResponseTime(AppState.powerResponseTimes.size.toLong(), status.toLong(), duration))
            "notification" -> AppState.notificationResponseTimes.add(ResponseTime(AppState.notificationResponseTimes.size.toLong(), status.toLong(), duration))
            "manual_photo" -> AppState.photoResponseTimes.add(ResponseTime(AppState.photoResponseTimes.size.toLong(), status.toLong(), duration))
            "app_usage" -> handleAppUsageReponse()
            else -> Log.w("WebSocketManager", "Unknown messageType: $messageType")
        }

        messageSendTimes.remove(messageId)
    }

    companion object {
        private const val NORMAL_CLOSURE_STATUS = 1000
    }
}