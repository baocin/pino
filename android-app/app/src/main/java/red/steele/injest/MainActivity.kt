package red.steele.injest

import OverlayManager
import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
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
    // Core Services
    private lateinit var cameraService: CameraService


    private val REQUEST_PERMISSIONS = 100
    private val permissions = arrayOf(
        Manifest.permission.RECORD_AUDIO,
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.CAMERA,
        Manifest.permission.READ_EXTERNAL_STORAGE,
        Manifest.permission.WRITE_EXTERNAL_STORAGE
    )

    private lateinit var projectionManager: MediaProjectionManager
    private var mediaProjection: MediaProjection? = null
    private lateinit var imageViewLastScreenshot: ImageView
    private lateinit var chartAudio: LineChart
    private lateinit var chartGPS: LineChart
    private lateinit var chartScreenshot: LineChart
    private lateinit var chartSensor: LineChart
    private lateinit var chartPhoto: LineChart
    private lateinit var editServerIp: EditText

    private val client = OkHttpClient()
    private lateinit var statusTextView: TextView

    private val updateHandler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {
            // updateCharts()
            // updatePacketInfo()
            // checkHeartbeat()
            updateHandler.postDelayed(this, 1000) // Update every second
        }
    }

    private fun updateCharts() {
        updateChart(chartAudio, AppState.audioResponseTimes, "Audio Response Times")
        updateChart(chartGPS, AppState.gpsResponseTimes, "GPS Response Times")
        updateChart(chartSensor, AppState.sensorResponseTimes, "Sensor Response Times")
        updateChart(chartPhoto, AppState.photoResponseTimes, "Photo Response Times")
    }

    private fun updateChart(chart: LineChart, responseTimes: List<ResponseTime>, label: String) {
        val entries = responseTimes.takeLast(100).mapIndexed { _, data -> Entry(data.timestamp.toFloat(), data.duration.toFloat()) }
        val dataSet = LineDataSet(entries, label).apply {
            color = ContextCompat.getColor(this@MainActivity, R.color.colorPrimary)
            valueTextColor = ContextCompat.getColor(this@MainActivity, R.color.colorAccent)
        }
        chart.data = LineData(dataSet)
        chart.invalidate()
    }

    private fun updatePacketInfo() {
        val elapsedTimeInSeconds = (System.currentTimeMillis() - AppState.startTime) / 1000.0
        updatePacketText(R.id.text_audio_packets, AppState.totalAudioBytesTransferred, AppState.audioResponseTimes.size, "Audio", elapsedTimeInSeconds)
        updatePacketText(R.id.text_gps_packets, AppState.totalGpsBytesTransferred, AppState.gpsResponseTimes.size, "GPS", elapsedTimeInSeconds)
        updatePacketText(R.id.text_screenshot_packets, AppState.totalScreenshotBytesTransferred, AppState.screenshotResponseTimes.size, "AutoScreenshot", elapsedTimeInSeconds)
        updatePacketText(R.id.text_sensor_packets, AppState.totalSensorBytesTransferred, AppState.sensorResponseTimes.size, "Sensor", elapsedTimeInSeconds)
        updatePacketText(R.id.text_photo_packets, AppState.totalPhotoBytesTransferred, AppState.photoResponseTimes.size, "Photo", elapsedTimeInSeconds)
    }

    private fun updatePacketText(viewId: Int, totalBytes: Long, packetCount: Int, packetType: String, elapsedTimeInSeconds: Double) {
        val kbPerSecond = String.format("%.2f", (totalBytes / 1024.0) / elapsedTimeInSeconds).toDouble()
        findViewById<TextView>(viewId).text = "$packetType Packets: $kbPerSecond KB/s (Sent: $packetCount)"
    }

    private fun checkHeartbeat() {
        val request = Request.Builder()
            .url("http://${AppState.serverIp}:${AppState.serverPort}/heartbeat")
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
                    val jsonResponse = response.body?.string()?.let { JSONObject(it) }
                    if (jsonResponse != null) {
                        statusTextView.text = jsonResponse.getString("status")
                    }
                    AppState.isConnected = response.isSuccessful
                    response.close()
                }
            }
        })
    }

    private val screenCaptureLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            mediaProjection = projectionManager.getMediaProjection(result.resultCode, result.data!!)
            val intent = Intent(this, ImageSyncService::class.java).apply {
                putExtra("mediaProjectionIntent", result.data)
            }
            startService(intent)

            // Start AutoScreenshotService
            if (AppState.isAutoScreenshotServiceEnabled) {
                val autoScreenshotIntent = Intent(this, AutoScreenshotService::class.java).apply {
                    putExtra("mediaProjectionIntent", result.data)
                }
                startService(autoScreenshotIntent)
            }
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

        val switchAutoScreenshotService = findViewById<Switch>(R.id.switch_auto_screenshot_service)
        switchAutoScreenshotService.isChecked = AppState.isAutoScreenshotServiceEnabled
        switchAutoScreenshotService.setOnCheckedChangeListener { _, isChecked ->
            AppState.isAutoScreenshotServiceEnabled = isChecked
        }

        editServerIp = findViewById(R.id.editServerIp)
        editServerIp.setText(AppState.serverUrl)
        editServerIp.isEnabled = false

        // Add a button to take a screenshot
        val button = findViewById<Button>(R.id.btn_take_screenshot)
        button.setOnClickListener {
            val b: Bitmap = Screenshot.takeScreenshotOfRootView(imageViewLastScreenshot)
            imageViewLastScreenshot.setImageBitmap(b)
            findViewById<View>(R.id.imageView).setBackgroundColor(Color.parseColor("#999999"))
        }



        // Initialize CameraService
        cameraService = CameraService(this, this)
        requestPermissions()
        cameraService.initializeCamera(isFront = true) // or false for back camera
        cameraService.takePhotoAndGetBase64 {
            Log.d("CameraService", "Photo taken: $it")
            
            // imageViewLastScreenshot.setImageBitmap(b)
            // findViewById<View>(R.id.imageView).setBackgroundColor(Color.parseColor("#999999"))
        }
    }

    private fun requestPermissions() {
        val permissionsToRequest = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }.toTypedArray()

        if (permissionsToRequest.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, permissionsToRequest, REQUEST_PERMISSIONS)
        } else {
            setupServices()
            requestScreenCapture()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PERMISSIONS) {
            if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
                setupServices()
                requestScreenCapture()
            } else {
                // Handle the case where permissions are not granted
                finish() // Close the app if permissions are not granted
            }
        }
    }

    private fun setupServices() {
        // Services are now handled by ForegroundService
        val serviceIntent = Intent(this, ForegroundService::class.java)
        ContextCompat.startForegroundService(this, serviceIntent)
    }

    private fun requestScreenCapture() {
        val captureIntent = projectionManager.createScreenCaptureIntent()
        screenCaptureLauncher.launch(captureIntent)
    }

    override fun onDestroy() {
        updateHandler.removeCallbacks(updateRunnable) // Stop updating packet counts
        super.onDestroy()
    }

    // companion object Screenshot {
    //     private fun takeScreenshot(view: View): Bitmap {
    //         view.isDrawingCacheEnabled = true
    //         view.buildDrawingCache(true)
    //         val b = Bitmap.createBitmap(view.drawingCache)
    //         view.isDrawingCacheEnabled = false
    //         return b
    //     }

    //     fun takeScreenshotOfRootView(v: View): Bitmap {
    //         return takeScreenshot(v.rootView)
    //     }
    // }
}