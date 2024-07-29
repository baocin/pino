package red.steele.injest

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.Environment
import android.util.Base64
import android.util.Size
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer

class CameraService(private val context: Context, private val activity: Activity) {

    private lateinit var cameraManager: CameraManager
    private lateinit var cameraDevice: CameraDevice
    private lateinit var captureSession: CameraCaptureSession
    private lateinit var imageReader: ImageReader
    private var cameraId: String = ""
    private var isFrontCamera: Boolean = false

    fun initializeCamera(isFront: Boolean) {
        isFrontCamera = isFront
        cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        cameraId = getCameraId(isFrontCamera)
        imageReader = ImageReader.newInstance(1080, 1920, ImageFormat.JPEG, 1)
        imageReader.setOnImageAvailableListener({ reader ->
            val image = reader.acquireLatestImage()
            val buffer: ByteBuffer = image.planes[0].buffer
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            saveImage(bytes)
            image.close()
        }, null)

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(activity, arrayOf(Manifest.permission.CAMERA), 101)
            return
        }
        openCamera()
    }

    private fun getCameraId(isFront: Boolean): String {
        for (id in cameraManager.cameraIdList) {
            val characteristics = cameraManager.getCameraCharacteristics(id)
            val facing = characteristics.get(CameraCharacteristics.LENS_FACING)
            if (isFront && facing == CameraCharacteristics.LENS_FACING_FRONT) {
                return id
            } else if (!isFront && facing == CameraCharacteristics.LENS_FACING_BACK) {
                return id
            }
        }
        throw IllegalArgumentException("No suitable camera found")
    }

    private fun openCamera() {
        cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
            override fun onOpened(camera: CameraDevice) {
                cameraDevice = camera
                createCameraPreviewSession()
            }

            override fun onDisconnected(camera: CameraDevice) {
                camera.close()
            }

            override fun onError(camera: CameraDevice, error: Int) {
                camera.close()
            }
        }, null)
    }

    private fun createCameraPreviewSession() {
        val surface = imageReader.surface
        cameraDevice.createCaptureSession(listOf(surface), object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(session: CameraCaptureSession) {
                captureSession = session
                val captureRequestBuilder = cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                captureRequestBuilder.addTarget(surface)
                captureSession.setRepeatingRequest(captureRequestBuilder.build(), null, null)
            }

            override fun onConfigureFailed(session: CameraCaptureSession) {
                // Handle configuration failure
            }
        }, null)
    }

    fun takePhoto() {
        val captureRequestBuilder = cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
        captureRequestBuilder.addTarget(imageReader.surface)
        captureSession.capture(captureRequestBuilder.build(), object : CameraCaptureSession.CaptureCallback() {
            override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
                super.onCaptureCompleted(session, request, result)
                // Photo capture completed
            }
        }, null)
    }

    private fun saveImage(bytes: ByteArray) {
        val file = File(context.getExternalFilesDir(Environment.DIRECTORY_PICTURES), "photo.jpg")
        FileOutputStream(file).use {
            it.write(bytes)
        }
    }

    private fun imageToBase64(image: ByteArray): String {
        return Base64.encodeToString(image, Base64.DEFAULT)
    }

    fun takePhotoAndGetBase64(callback: (String) -> Unit) {
        val captureRequestBuilder = cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
        captureRequestBuilder.addTarget(imageReader.surface)
        captureSession.capture(captureRequestBuilder.build(), object : CameraCaptureSession.CaptureCallback() {
            override fun onCaptureCompleted(session: CameraCaptureSession, request: CaptureRequest, result: TotalCaptureResult) {
                super.onCaptureCompleted(session, request, result)
                val image = imageReader.acquireLatestImage()
                val buffer = image.planes[0].buffer
                val bytes = ByteArray(buffer.capacity())
                buffer.get(bytes)
                image.close()
                val base64Image = imageToBase64(bytes)
                callback(base64Image)
            }
        }, null)
    }
}
