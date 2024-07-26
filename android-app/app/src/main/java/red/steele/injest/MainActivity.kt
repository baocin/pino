package red.steele.injest

import OverlayManager
import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.EditText
import android.widget.ImageView
import android.widget.Switch
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.github.mikephil.charting.charts.LineChart
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException


class MainActivity : AppCompatActivity() {

    private val REQUEST_RECORD_AUDIO_PERMISSION = 200
    private var permissionToRecordAccepted = false
    private val permissions = arrayOf(Manifest.permission.RECORD_AUDIO)

    private lateinit var projectionManager: MediaProjectionManager
    private lateinit var imageViewLastScreenshot: ImageView
    private lateinit var chartAudio: LineChart
    private lateinit var chartGPS: LineChart
    private lateinit var chartScreenshot: LineChart
    private lateinit var chartSensor: LineChart
    private lateinit var chartPhoto : LineChart
    private lateinit var editServerIp: EditText

    private val client = OkHttpClient()
    private lateinit var statusTextView: TextView

    private val updateHandler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {

            // Update charts
            val audioEntries = AppState.audioResponseTimes.takeLast(100).mapIndexed { _, data -> Entry(data.timestamp.toFloat(), data.duration.toFloat()) }
            val audioDataSet = LineDataSet(audioEntries, "Audio Response Times").apply {
                color = ContextCompat.getColor(this@MainActivity, R.color.colorPrimary)
                valueTextColor = ContextCompat.getColor(this@MainActivity, R.color.colorAccent)
            }
            chartAudio.data = LineData(audioDataSet)
            chartAudio.invalidate()

            val gpsEntries = AppState.gpsResponseTimes.takeLast(100).mapIndexed { _, data -> Entry(data.timestamp.toFloat(), data.duration.toFloat()) }
            val gpsDataSet = LineDataSet(gpsEntries, "GPS Response Times").apply {
                color = ContextCompat.getColor(this@MainActivity, R.color.colorPrimary)
                valueTextColor = ContextCompat.getColor(this@MainActivity, R.color.colorAccent)
            }
            chartGPS.data = LineData(gpsDataSet)
            chartGPS.invalidate()

            val sensorEntries = AppState.sensorResponseTimes.takeLast(100).mapIndexed { _, data -> Entry(data.timestamp.toFloat(), data.duration.toFloat()) }
            val sensorDataSet = LineDataSet(sensorEntries, "Sensor Response Times").apply {
                color = ContextCompat.getColor(this@MainActivity, R.color.colorPrimary)
                valueTextColor = ContextCompat.getColor(this@MainActivity, R.color.colorAccent)
            }
            chartSensor.data = LineData(sensorDataSet)
            chartSensor.invalidate()

            val photoEntries = AppState.photoResponseTimes.takeLast(100).mapIndexed { _, data -> Entry(data.timestamp.toFloat(), data.duration.toFloat()) }
            val photoDataSet = LineDataSet(photoEntries, "Photo Response Times").apply {
                color = ContextCompat.getColor(this@MainActivity, R.color.colorPrimary)
                valueTextColor = ContextCompat.getColor(this@MainActivity, R.color.colorAccent)
            }
            chartPhoto.data = LineData(photoDataSet)
            chartPhoto.invalidate()

            val elapsedTimeInSeconds = (System.currentTimeMillis() - AppState.startTime) / 1000.0
            val audioKBPerSecond = String.format("%.2f", (AppState.totalAudioBytesTransferred / 1024.0) / elapsedTimeInSeconds).toDouble()
            val gpsKBPerSecond = String.format("%.2f", (AppState.totalGpsBytesTransferred / 1024.0) / elapsedTimeInSeconds).toDouble()
            val screenshotKBPerSecond = String.format("%.2f", (AppState.totalScreenshotBytesTransferred / 1024.0) / elapsedTimeInSeconds).toDouble()
            val photoKBPerSecond = String.format("%.2f", (AppState.totalPhotoBytesTransferred / 1024.0) / elapsedTimeInSeconds).toDouble()
            val sensorKBPerSecond = String.format("%.2f", (AppState.totalSensorBytesTransferred / 1024.0) / elapsedTimeInSeconds).toDouble()

            findViewById<TextView>(R.id.text_audio_packets).text = "Audio Packets: $audioKBPerSecond KB/s (Sent: ${AppState.audioResponseTimes.size})"
            findViewById<TextView>(R.id.text_gps_packets).text = "GPS Packets: $gpsKBPerSecond KB/s (Sent: ${AppState.gpsResponseTimes.size})"
            findViewById<TextView>(R.id.text_screenshot_packets).text = "Screenshot Packets: $screenshotKBPerSecond KB/s (Sent: ${AppState.screenshotResponseTimes.size})"
            findViewById<TextView>(R.id.text_sensor_packets).text = "Sensor Packets: $sensorKBPerSecond KB/s (Sent: ${AppState.sensorResponseTimes.size})"
            findViewById<TextView>(R.id.text_photo_packets).text = "Photo Packets: $photoKBPerSecond KB/s (Sent: ${AppState.photoResponseTimes.size})"


            // Check heartbeat
            val request = Request.Builder()
                .url("http://${AppState.serverIp}/heartbeat")
                .build()

            client.newCall(request).enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    runOnUiThread {
                        statusTextView.text = e.message
                        AppState.isConnected = false
                    }
                }

                override fun onResponse(call: Call, response: Response) {
                    runOnUiThread {
                        val jsonResponse = JSONObject(response.body?.string())
                        statusTextView.text = jsonResponse.getString("status")
                        if (response.isSuccessful) {
                            AppState.isConnected = true
                        } else {
                            AppState.isConnected = false
                        }
                        response.close()
                    }
                }
            })

            updateHandler.postDelayed(this, 1000) // Update every second
        }
    }

    private val screenCaptureLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val intent = Intent(this, ScreenshotService::class.java).apply {
                putExtra("mediaProjectionIntent", result.data)
            }
            startService(intent)
        }
    }

    private lateinit var overlayManager: OverlayManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        projectionManager =
            getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager

        imageViewLastScreenshot = findViewById(R.id.image_view_last_screenshot)

        chartPhoto = findViewById(R.id.chart_photo)
        chartAudio = findViewById(R.id.chart_audio)
        chartGPS = findViewById(R.id.chart_gps)
        chartSensor = findViewById(R.id.chart_sensor)
//        chartScreenshot = findViewById(R.id.chart_screenshot)

        statusTextView = findViewById(R.id.text_status)


        updateHandler.post(updateRunnable) // Start updating packet counts every second

        requestPermissions()

        // Ensure permissions are granted before calling requestScreenCapture()
        if (permissionToRecordAccepted && AppState.isScreenshotServiceEnabled) {
            requestScreenCapture()
        }

        // Update isAudioServiceEnabled based on the switch state
        val switchAudioService = findViewById<Switch>(R.id.switch_audio_service)
        switchAudioService.isChecked = AppState.isAudioServiceEnabled
        switchAudioService.setOnCheckedChangeListener { _, isChecked ->
            AppState.isAudioServiceEnabled = isChecked
        }

        // Update isGpsServiceEnabled based on the switch state
        val switchGpsService = findViewById<Switch>(R.id.switch_gps_service)
        switchGpsService.isChecked = AppState.isGpsServiceEnabled
        switchGpsService.setOnCheckedChangeListener { _, isChecked ->
            AppState.isGpsServiceEnabled = isChecked
        }

        // Update isScreenshotServiceEnabled based on the switch state
        val switchScreenshotService = findViewById<Switch>(R.id.switch_screenshot_service)
        switchScreenshotService.isChecked = AppState.isScreenshotServiceEnabled
        switchScreenshotService.setOnCheckedChangeListener { _, isChecked ->
            AppState.isScreenshotServiceEnabled = isChecked
        }

        // Update isSensorServiceEnabled based on the switch state
        val switchSensorService = findViewById<Switch>(R.id.switch_sensor_service)
        switchSensorService.isChecked = AppState.isSensorServiceEnabled
        switchSensorService.setOnCheckedChangeListener { _, isChecked ->
            AppState.isSensorServiceEnabled = isChecked
        }

        // Add a photo service switch
        val switchPhotoService = findViewById<Switch>(R.id.switch_photo_service)
        switchPhotoService.isChecked = AppState.isPhotoServiceEnabled
        switchPhotoService.setOnCheckedChangeListener { _, isChecked ->
            AppState.isPhotoServiceEnabled = isChecked
        }


        editServerIp = findViewById(R.id.editServerIp)
        editServerIp.setText(AppState.serverIp)
//        editServerIp.setOnEditorActionListener { v, actionId, _ ->
//            if (actionId == EditorInfo.IME_ACTION_DONE) {
//                val newServerIp = v.text.toString()
//                AppState.setServerIpToSharedPreferences(newServerIp)
//                Log.d("MainActivity", newServerIp)
//                Log.d("MainActivity", "New server IP set: ${AppState.serverIp}")
//                true
//            } else {
//                false
//            }
//        }
//        editServerIp.setOnFocusChangeListener { _, hasFocus ->
//            if (!hasFocus) {
//                val newServerIp = editServerIp.text.toString()
//                AppState.setServerIpToSharedPreferences(newServerIp)
//                Log.d("MainActivity", "New server IP set: ${AppState.serverIp}")
//            }
//        }
    }

//    private fun updatePacketCounts() {
//        val currentTime = System.currentTimeMillis()
//        val elapsedTimeInSeconds = (currentTime - AppState.startTime) / 1000.0
//
//    }

    private fun requestPermissions() {
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, permissions, REQUEST_RECORD_AUDIO_PERMISSION)
        } else {
            permissionToRecordAccepted = true
            setupServices()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        permissionToRecordAccepted = requestCode == REQUEST_RECORD_AUDIO_PERMISSION &&
                grantResults[0] == PackageManager.PERMISSION_GRANTED

        if (permissionToRecordAccepted) {
            setupServices()
            if (AppState.isScreenshotServiceEnabled) {
                requestScreenCapture()
            }
        } else {
            finish() // Close the app if permission is not granted
        }
    }

    private fun setupServices() {
        if (permissionToRecordAccepted) {
            // Services are now handled by ForegroundService
            val serviceIntent = Intent(this, ForegroundService::class.java)
            ContextCompat.startForegroundService(this, serviceIntent)
        }
    }

    private fun requestScreenCapture() {
        val captureIntent = projectionManager.createScreenCaptureIntent()
        screenCaptureLauncher.launch(captureIntent)
    }

    override fun onDestroy() {
        updateHandler.removeCallbacks(updateRunnable) // Stop updating packet counts
        super.onDestroy()
    }
}