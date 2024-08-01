package red.steele.injest

import android.app.Service
import android.content.Intent
import android.database.ContentObserver
import android.graphics.Bitmap
import android.media.ExifInterface
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
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

class ImageSyncService : Service() {

    private lateinit var webSocketManager: WebSocketManager
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var contentObserver: ContentObserver
    private lateinit var scheduledExecutor: ScheduledExecutorService

    companion object {
        private const val TAG = "ImageSyncService"
        private const val SYNC_INTERVAL_MINUTES = 15L
    }

    override fun onCreate() {
        Log.d(TAG, "onCreate: Initializing ImageSyncService")
        webSocketManager = WebSocketManager(AppState.serverUrl)
        scheduledExecutor = Executors.newSingleThreadScheduledExecutor()

        contentObserver = object : ContentObserver(handler) {
            override fun onChange(selfChange: Boolean) {
                super.onChange(selfChange)
                Log.d(TAG, "New photo detected")
                if (AppState.isImageSyncServiceEnabled) {
                    Log.d(TAG, "Image sync is enabled, handling new images")
                    handleNewImages()
                } else {
                    Log.d(TAG, "Image sync is disabled, skipping new image handling")
                }
            }
        }
        contentResolver.registerContentObserver(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            true,
            contentObserver
        )
        Log.d(TAG, "Content observer registered")

        if (AppState.isImageSyncServiceEnabled) {
            Log.d(TAG, "Starting periodic image sync")
            startPeriodicImageSync()
        } else {
            Log.d(TAG, "Periodic image sync not started (disabled in AppState)")
        }
    }

    private fun startPeriodicImageSync() {
        Log.d(TAG, "Scheduling periodic image sync every $SYNC_INTERVAL_MINUTES minutes")
        scheduledExecutor.scheduleWithFixedDelay({
            if (AppState.isImageSyncServiceEnabled) {
                Log.d(TAG, "Periodic sync: Handling new images")
                handleNewImages()
            } else {
                Log.d(TAG, "Periodic sync: Image sync is disabled, skipping")
            }
        }, 0, SYNC_INTERVAL_MINUTES, TimeUnit.MINUTES)
    }

    private fun handleNewImages() {
        Log.d(TAG, "handleNewImages: Starting to process new images")
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DISPLAY_NAME,
            MediaStore.Images.Media.DATE_ADDED,
            MediaStore.Images.Media.DATA
        )
        val sortOrder = "${MediaStore.Images.Media.DATE_ADDED} DESC"
        
        contentResolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            projection,
            null,
            null,
            sortOrder
        )?.use { cursor ->
            Log.d(TAG, "Query returned ${cursor.count} results")
            val idColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val nameColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val dataColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATA)

            while (cursor.moveToNext()) {
                val id = cursor.getLong(idColumn)
                val name = cursor.getString(nameColumn)
                val filePath = cursor.getString(dataColumn)
                val contentUri = Uri.withAppendedPath(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    id.toString()
                )

                Log.d(TAG, "Processing new image: $name (ID: $id)")
                
                val exif = ExifInterface(filePath)
                val metadata = mutableMapOf<String, Any?>()
                
                Log.d(TAG, "Compiling EXIF data for $name")
                // Compile all EXIF data
                ExifInterface::class.java.declaredFields
                    .filter { it.name.startsWith("TAG_") }
                    .forEach { field ->
                        val tag = field.get(null) as String
                        val value = exif.getAttribute(tag)
                        if (value != null) {
                            metadata[tag] = value
                            Log.v(TAG, "EXIF data for $name: $tag = $value")
                        }
                    }
                
                // Add GPS coordinates if available
                val latLong = FloatArray(2)
                if (exif.getLatLong(latLong)) {
                    metadata["GPS_LATITUDE"] = latLong[0]
                    metadata["GPS_LONGITUDE"] = latLong[1]
                    Log.d(TAG, "GPS data for $name: Lat ${latLong[0]}, Long ${latLong[1]}")
                } else {
                    Log.d(TAG, "No GPS data available for $name")
                }
                
                // Determine camera type
                val cameraType = when (metadata[ExifInterface.TAG_MAKE]) {
                    "front" -> "front"
                    "back" -> "back"
                    else -> "unknown"
                }
                metadata["CAMERA_TYPE"] = cameraType
                metadata["IMAGE_ID"] = id
                Log.d(TAG, "Camera type for $name: $cameraType")

                processImage(contentUri, name, metadata)
            }
        }
        Log.d(TAG, "handleNewImages: Finished processing new images")
    }

    private fun processImage(uri: Uri, displayName: String, metadata: Map<String, Any?>) {
        Log.d(TAG, "processImage: Starting to process $displayName")
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
                    Log.d(TAG, "$displayName is still pending, waiting...")
                    Thread.sleep(200)
                }
            }
            Log.d(TAG, "$displayName is no longer pending, proceeding with processing")

            val bitmap = MediaStore.Images.Media.getBitmap(contentResolver, uri)
            Log.d(TAG, "Bitmap created for $displayName")
            val byteArrayOutputStream = ByteArrayOutputStream()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                bitmap.compress(Bitmap.CompressFormat.WEBP_LOSSY, 75, byteArrayOutputStream)
                Log.d(TAG, "Compressed $displayName using WEBP_LOSSY format")
            } else {
                bitmap.compress(Bitmap.CompressFormat.PNG, 75, byteArrayOutputStream)
                Log.d(TAG, "Compressed $displayName using PNG format")
            }
            val byteArray = byteArrayOutputStream.toByteArray()
            val compressedData = Zstd.compress(byteArray)
            Log.d(TAG, "Zstd compression applied to $displayName. Compressed size: ${compressedData.size} bytes")
            
            val isScreenshot = displayName.contains("screenshot", ignoreCase = true)
            val isGenerated = false
            val isManual = true
            val isFrontCamera = metadata["CAMERA_TYPE"] == "front"
            val isRearCamera = metadata["CAMERA_TYPE"] == "back"
            val lat = metadata["GPS_LATITUDE"] as? Float
            val lng = metadata["GPS_LONGITUDE"] as? Float

            Log.d(TAG, "Image metadata for $displayName: isScreenshot=$isScreenshot, isGenerated=$isGenerated, " +
                    "isManual=$isManual, isFrontCamera=$isFrontCamera, isRearCamera=$isRearCamera, " +
                    "lat=$lat, lng=$lng")

            // Generate SHA256 hash
            val messageDigest = MessageDigest.getInstance("SHA-256")
            val hashBytes = messageDigest.digest(compressedData)
            val imageHash = hashBytes.joinToString("") { "%02x".format(it) }
            Log.d(TAG, "Generated hash for $displayName: $imageHash")

            val imageId = metadata["IMAGE_ID"].toString()

            Log.d(TAG, "Sending image data for $displayName to WebSocket")
            webSocketManager.sendImageData(compressedData, isScreenshot, isGenerated, isManual, isFrontCamera, isRearCamera, imageHash,
                imageId
            )
            Log.d(TAG, "Image processed and sent: $displayName")
        } catch (e: IOException) {
            Log.e(TAG, "Error loading image: $displayName", e)
        } catch (e: SecurityException) {
            Log.e(TAG, "Security exception for image: $displayName", e)
        } catch (e: InterruptedException) {
            Log.e(TAG, "Thread was interrupted while waiting for image to be accessible: $displayName", e)
        }
    }

    override fun onDestroy() {
        Log.d(TAG, "onDestroy: Cleaning up ImageSyncService")
        webSocketManager.close()
        contentResolver.unregisterContentObserver(contentObserver)
        scheduledExecutor.shutdown()
        Log.d(TAG, "ImageSyncService destroyed")
        super.onDestroy()
    }

    override fun onBind(p0: Intent?): IBinder? {
        Log.d(TAG, "onBind called")
        return null
    }
}