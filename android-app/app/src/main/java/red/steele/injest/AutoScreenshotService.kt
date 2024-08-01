package red.steele.injest

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.annotation.RequiresApi
import com.github.luben.zstd.Zstd
import java.io.ByteArrayOutputStream
import java.security.MessageDigest

class AutoScreenshotService : Service() {

    private lateinit var webSocketManager: WebSocketManager
    private val handler = Handler(Looper.getMainLooper())
    private val screenshotInterval = 1000L // 1 second
    private var mediaProjection: MediaProjection? = null
    private var mediaProjectionManager: MediaProjectionManager? = null
    private var mediaProjectionIntent: Intent? = null

    override fun onCreate() {
        super.onCreate()
        webSocketManager = WebSocketManager(AppState.serverUrl)
        mediaProjectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        Log.d("AutoScreenshotService", "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d("AutoScreenshotService", "onStartCommand called")
        mediaProjectionIntent = intent?.getParcelableExtra("mediaProjectionIntent")
        if (mediaProjectionIntent != null) {
            Log.d("AutoScreenshotService", "MediaProjectionIntent received")
            startTakingScreenshots()
        } else {
            Log.e("AutoScreenshotService", "MediaProjectionIntent is null, stopping service")
            stopSelf()
        }
        return START_NOT_STICKY
    }

    private fun startTakingScreenshots() {
        Log.d("AutoScreenshotService", "Starting to take screenshots")
        handler.post(object : Runnable {
            @RequiresApi(Build.VERSION_CODES.R)
            override fun run() {
                mediaProjection = mediaProjectionManager?.getMediaProjection(RESULT_OK, mediaProjectionIntent!!)
                mediaProjection?.registerCallback(object : MediaProjection.Callback() {
                    override fun onStop() {
                        Log.d("AutoScreenshotService", "MediaProjection stopped")
                        handler.removeCallbacksAndMessages(null)
                        stopSelf()
                    }
                }, handler)
                takeScreenshot(mediaProjection!!)
                handler.postDelayed(this, screenshotInterval)
            }
        })
    }

    @RequiresApi(Build.VERSION_CODES.R)
    private fun takeScreenshot(mediaProjection: MediaProjection) {
        Log.d("AutoScreenshotService", "Taking screenshot")
        // Get the current display metrics
        val metrics = resources.displayMetrics
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val density = metrics.densityDpi

        // Create an image reader to capture the screen content
        val imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        val virtualDisplay = mediaProjection.createVirtualDisplay(
            "ScreenCapture",
            width, height, density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader.surface, null, null
        )

        // Capture the screen content
        val image = imageReader.acquireLatestImage()
        if (image != null) {
            Log.d("AutoScreenshotService", "Image captured successfully")
            // Convert the image to a bitmap
            val planes = image.planes
            val buffer = planes[0].buffer
            val pixelStride = planes[0].pixelStride
            val rowStride = planes[0].rowStride
            val rowPadding = rowStride - pixelStride * width

            val bitmap = Bitmap.createBitmap(
                width + rowPadding / pixelStride, height,
                Bitmap.Config.ARGB_8888
            )
            bitmap.copyPixelsFromBuffer(buffer)
            // Compress and send the bitmap
            val byteArrayOutputStream = ByteArrayOutputStream()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                bitmap.compress(Bitmap.CompressFormat.WEBP_LOSSY, 75, byteArrayOutputStream)
            } else {
                bitmap.compress(Bitmap.CompressFormat.PNG, 75, byteArrayOutputStream)
            }
            val byteArray = byteArrayOutputStream.toByteArray()
            val compressedData = Zstd.compress(byteArray)

            // Generate SHA256 hash
            val messageDigest = MessageDigest.getInstance("SHA-256")
            val hashBytes = messageDigest.digest(compressedData)
            val imageHash = hashBytes.joinToString("") { "%02x".format(it) }

            // Send the screenshot data with metadata
            Log.d("AutoScreenshotService", "Screenshot processed. Size: ${compressedData.size} bytes, Hash: $imageHash")
//            webSocketManager.sendImageData(
//                imageData = compressedData,
//                isScreenshot = true,
//                isGenerated = true,
//                isManual = false,
//                isFrontCamera = false,
//                isRearCamera = false,
//                imageHash = imageHash,
//                imageId = imageHash
//            )

            // Clean up resources
            image.close()
            imageReader.close()
            virtualDisplay.release()

            Log.d("AutoScreenshotService", "Screenshot captured and processed successfully")
        } else {
            Log.e("AutoScreenshotService", "Failed to capture screenshot: Image is null")
        }
    }

    override fun onBind(intent: Intent?): IBinder? {
        Log.d("AutoScreenshotService", "onBind called")
        return null
    }

    override fun onDestroy() {
        Log.d("AutoScreenshotService", "Service being destroyed")
        handler.removeCallbacksAndMessages(null)
        mediaProjection?.stop()
        super.onDestroy()
    }

    companion object {
        private const val RESULT_OK = -1
    }
}