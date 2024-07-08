// package red.steele.injest

// import android.Manifest
// import android.content.Context
// import android.content.pm.PackageManager
// import android.graphics.Bitmap
// import android.hardware.camera2.CameraAccessException
// import android.hardware.camera2.CameraCharacteristics
// import android.hardware.camera2.CameraManager
// import android.hardware.camera2.CameraCaptureSession
// import android.hardware.camera2.CameraDevice
// import android.hardware.camera2.CaptureRequest
// import android.hardware.camera2.TotalCaptureResult
// import android.media.ImageReader
// import android.os.Build
// import android.util.Log
// import android.util.Size
// import android.view.Surface
// import androidx.annotation.RequiresApi
// import androidx.core.app.ActivityCompat
// import java.util.concurrent.Executors
// import java.util.concurrent.ScheduledExecutorService
// import java.util.concurrent.TimeUnit

// class CameraService(private val context: Context) {

//     private val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
//     private val executor = Executors.newSingleThreadExecutor()
//     private val scheduler: ScheduledExecutorService = Executors.newScheduledThreadPool(1)

//     init {
//         scheduler.scheduleAtFixedRate({
//             takePhotosFromAllCameras()
//         }, 0, 10, TimeUnit.SECONDS)
//     }

//     @RequiresApi(Build.VERSION_CODES.LOLLIPOP)
//     fun takePhoto(cameraId: String, callback: (Bitmap?) -> Unit) {
//         if (ActivityCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
//             Log.e("CameraService", "Camera permission not granted")
//             callback(null)
//             return
//         }

//         try {
//             val characteristics = cameraManager.getCameraCharacteristics(cameraId)
//             val map = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
//             val largestSize = map?.getOutputSizes(ImageReader::class.java)?.maxByOrNull { it.height * it.width } ?: Size(640, 480)
//             val imageReader = ImageReader.newInstance(largestSize.width, largestSize.height, android.graphics.ImageFormat.JPEG, 1)

//             cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
//                 override fun onOpened(camera: CameraDevice) {
//                     val captureRequestBuilder = camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
//                     captureRequestBuilder.addTarget(imageReader.surface)

//                     camera.createCaptureSession(listOf(imageReader.surface), object : CameraCaptureSession.StateCallback() {
//                         override fun onConfigured(session: CameraCaptureSession) {
//                             session.capture(captureRequestBuilder.build(), object : CameraCaptureSession.CaptureCallback() {
//                                 override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
//                                     val image = imageReader.acquireLatestImage()
//                                     val buffer = image.planes[0].buffer
//                                     val bytes = ByteArray(buffer.remaining())
//                                     buffer.get(bytes)
//                                     val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
//                                     callback(bitmap)
//                                     image.close()
//                                     camera.close()
//                                 }
//                             }, executor)
//                         }

//                         override fun onConfigureFailed(session: CameraCaptureSession) {
//                             Log.e("CameraService", "Failed to configure camera")
//                             callback(null)
//                             camera.close()
//                         }
//                     }, executor)
//                 }

//                 override fun onDisconnected(camera: CameraDevice) {
//                     Log.e("CameraService", "Camera disconnected")
//                     callback(null)
//                 }

//                 override fun onError(camera: CameraDevice, error: Int) {
//                     Log.e("CameraService", "Camera error: $error")
//                     callback(null)
//                 }
//             }, executor)
//         } catch (e: CameraAccessException) {
//             Log.e("CameraService", "Camera access exception: ${e.message}")
//             callback(null)
//         }
//     }

//     @RequiresApi(Build.VERSION_CODES.LOLLIPOP)
//     fun takePhotosFromAllCameras(): Map<String, Bitmap?> {
//         val cameraIds = cameraManager.cameraIdList
//         val results = mutableMapOf<String, Bitmap?>()
//         val remaining = cameraIds.size
//         val latch = CountDownLatch(remaining)

//         cameraIds.forEach { cameraId ->
//             takePhoto(cameraId) { bitmap ->
//                 results[cameraId] = bitmap
//                 latch.countDown()
//             }
//         }

//         results.forEach { (cameraId, bitmap) ->
//             bitmap?.let {
//                 val byteCount = it.byteCount
//                 val sizeInMB = byteCount / (1024.0 * 1024.0)
//                 Log.d("CameraService", "Camera ID: $cameraId, Bitmap size: ${"%.2f".format(sizeInMB)} MB")
//             }
//         }

//         latch.await()
//         return results
//     }
// }
