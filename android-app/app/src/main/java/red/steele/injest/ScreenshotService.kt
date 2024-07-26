package red.steele.injest

import android.app.Service
import android.content.Intent
import android.database.ContentObserver
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.MediaStore
import android.util.Log
import com.github.luben.zstd.Zstd
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.Executors

class ScreenshotService : Service() {

    private lateinit var webSocketManager: WebSocketManager
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var contentObserver: ContentObserver

    companion object {
        private const val TAG = "ScreenshotService"
    }

    override fun onCreate() {
        webSocketManager = WebSocketManager(AppState.serverUrl)

        // Register content observer to listen for new images added to the camera roll
        contentObserver = object : ContentObserver(handler) {
            override fun onChange(selfChange: Boolean, uri: Uri?) {
                super.onChange(selfChange, uri)
                uri?.let {
                    handleNewImage(uri)
                }
            }
        }
        contentResolver.registerContentObserver(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            true,
            contentObserver
        )
    }

    private fun handleNewImage(uri: Uri) {
        Executors.newSingleThreadExecutor().execute {
            try {
                var isPending = true
                while (isPending) {
                    val cursor = contentResolver.query(uri, arrayOf(MediaStore.Images.Media.IS_PENDING), null, null, null)
                    cursor?.use {
                        if (it.moveToFirst()) {
                            isPending = it.getInt(it.getColumnIndexOrThrow(MediaStore.Images.Media.IS_PENDING)) != 0
                        }
                    }
                    if (isPending) {
                        Log.e(TAG, "Image is still pending and cannot be accessed yet. Retrying...")
                        Thread.sleep(500) // Wait for 500ms before retrying
                    }
                }
                Log.e(TAG, "Image is NOT pending and cannot be accessed yet. Retrying...")

                // Get the image from the URI
                val bitmap = MediaStore.Images.Media.getBitmap(contentResolver, uri)
                val isScreenshot = try {
                    val cursor = contentResolver.query(uri, arrayOf(MediaStore.Images.Media.DISPLAY_NAME), null, null, null)
                    cursor?.use {
                        if (it.moveToFirst()) {
                            val displayName = it.getString(it.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME))
                            displayName.contains("screenshot", ignoreCase = true)
                        } else {
                            false
                        }
                    } ?: false
                } catch (e: Exception) {
                    Log.e(TAG, "Error checking if image is a screenshot", e)
                    false
                }
                Log.d("uri", uri.toString())
                Log.d("isScreenshot", isScreenshot.toString())
                val byteArrayOutputStream = ByteArrayOutputStream()
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    bitmap.compress(Bitmap.CompressFormat.WEBP_LOSSY, 75, byteArrayOutputStream)
                }else{
                    bitmap.compress(Bitmap.CompressFormat.PNG, 75, byteArrayOutputStream)
                }
                val byteArray = byteArrayOutputStream.toByteArray()
                val compressedData = Zstd.compress(byteArray)
                webSocketManager.sendManualPhotoData(compressedData, isScreenshot) { statusCode ->
//                    AppState.photoHttpStatusCodes.add(statusCode)
                }
            } catch (e: IOException) {
                Log.e(TAG, "Error loading image thumbnail", e)
            } catch (e: SecurityException) {
                Log.e(TAG, "Security exception: ${e.message}", e)
            } catch (e: InterruptedException) {
                Log.e(TAG, "Thread was interrupted while waiting for image to be accessible", e)
            }
        }
    }
//
//    private fun takeScreenshotAndSend() {
//        try {
//            // Create a bitmap of the current screen
//            val rootView = (getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay
//            val screenshot = Bitmap.createBitmap(rootView.width, rootView.height, Bitmap.Config.ARGB_8888)
//            val canvas = Canvas(screenshot)
//            rootView.draw(canvas)
//
//            // Compress the bitmap to a byte array
//            val byteArrayOutputStream = ByteArrayOutputStream()
//            screenshot.compress(Bitmap.CompressFormat.WEBP_LOSSY, 75, byteArrayOutputStream)
//            val byteArray = byteArrayOutputStream.toByteArray()
//            val compressedData = Zstd.compress(byteArray)
//
//            // Check if the image is a screenshot
//            val isScreenshot = true // Since we are taking a screenshot, this is always true
//
//            // Send the screenshot data via WebSocket
//            webSocketManager.sendManualPhotoData(compressedData, isScreenshot) { statusCode ->
//                AppState.photoHttpStatusCodes.add(statusCode)
//            }
//
//            Log.d(TAG, "Screenshot taken and sent successfully")
//        } catch (e: Exception) {
//            Log.e(TAG, "Error taking and sending screenshot", e)
//        }
//    }

    override fun onDestroy() {
        webSocketManager.close()
        contentResolver.unregisterContentObserver(contentObserver) // Unregister content observer
        super.onDestroy()
    }

    override fun onBind(p0: Intent?): IBinder? {
      return null
    }
}
