package red.steele.injest

import android.Manifest
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.IBinder
import android.util.Log
import androidx.core.app.ActivityCompat
import com.github.luben.zstd.Zstd
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.Executors

class AudioService : Service() {

    private lateinit var audioRecord: AudioRecord
    private lateinit var webSocketManager: WebSocketManager
    private val sampleRate = 8000
    private val bufferSize = 512
//     AudioRecord.getMinBufferSize(
//        sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
//    )

    companion object {
        private const val TAG = "AudioService"
    }

    override fun onCreate() {
        super.onCreate()

        Log.d(TAG, "Buffer size: $bufferSize")
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Log.e(TAG, "Audio recording permission not granted")
            stopSelf()
            return
        }
        initializeAudioRecord()
        webSocketManager = WebSocketManager(AppState.serverIp)
    }

    private fun initializeAudioRecord() {
        if (ActivityCompat.checkSelfPermission(
                this,
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            // TODO: Consider calling
            //    ActivityCompat#requestPermissions
            // here to request the missing permissions, and then overriding
            //   public void onRequestPermissionsResult(int requestCode, String[] permissions,
            //                                          int[] grantResults)
            // to handle the case where the user grants the permission. See the documentation
            // for ActivityCompat#requestPermissions for more details.
            return
        }
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize
        )
        if (audioRecord.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord not initialized")
            stopSelf()
            return
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (::audioRecord.isInitialized) {
            startRecording()
        } else {
            Log.e(TAG, "AudioRecord is not initialized")
            stopSelf()
        }
        return START_STICKY
    }

    private fun startRecording() {
        Executors.newSingleThreadExecutor().execute {
            audioRecord.startRecording()
            val buffer = ShortArray(bufferSize / 2)
            while (audioRecord.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                val readSize = audioRecord.read(buffer, 0, buffer.size)
                if (readSize > 0) {
                    if (AppState.shouldSendData()) {
                        AppState.audioPacketsSent++ // Increment the count of audio packets sent
                        sendAudioDataToWebSocket(buffer, readSize)
                    }
                }
            }
        }
    }

    private fun sendAudioDataToWebSocket(data: ShortArray, size: Int) {
        val byteBuffer = ByteBuffer.allocate(size * 2).order(ByteOrder.LITTLE_ENDIAN)
        data.forEach { byteBuffer.putShort(it) }
        val toSend = byteBuffer.array()
        val compressedData = Zstd.compress(toSend)
        //zstd: Audio size: 640 bytes -> Compressed audio size: 475 byte
        // not going lossless  because I want all granular detail for environment classification
        webSocketManager.sendAudioData(compressedData) { statusCode ->
//            AppState.audioHttpStatusCodes.add(statusCode)
        }
    }

    override fun onDestroy() {
        if (::audioRecord.isInitialized) {
            audioRecord.stop()
            audioRecord.release()
        }
        webSocketManager.close()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}