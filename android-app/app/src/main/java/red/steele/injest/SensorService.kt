package red.steele.injest

import android.app.Service
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.TriggerEvent
import android.hardware.TriggerEventListener
import android.os.IBinder

class SensorService : Service(), SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private var magnetometer: Sensor? = null
    private var gyroscope: Sensor? = null
    private var lightSensor: Sensor? = null
    private var proximitySensor: Sensor? = null
    private var gravitySensor: Sensor? = null
    private var linearAccelerationSensor: Sensor? = null
    private var rotationVectorSensor: Sensor? = null
    private var ambientTemperatureSensor: Sensor? = null
    private var pressureSensor: Sensor? = null
    private var humiditySensor: Sensor? = null
    private var significantMotionSensor: Sensor? = null
    private var stepCounterSensor: Sensor? = null
    private lateinit var webSocketManager: WebSocketManager

    private val sensorDataBatch = mutableListOf<Pair<String, FloatArray>>()
    private val batchSize = 100

    companion object {
        private const val TAG = "SensorService"
    }

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        magnetometer = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
        gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
        lightSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT)
        proximitySensor = sensorManager.getDefaultSensor(Sensor.TYPE_PROXIMITY)
        gravitySensor = sensorManager.getDefaultSensor(Sensor.TYPE_GRAVITY)
        linearAccelerationSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LINEAR_ACCELERATION)
        rotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        ambientTemperatureSensor = sensorManager.getDefaultSensor(Sensor.TYPE_AMBIENT_TEMPERATURE)
        pressureSensor = sensorManager.getDefaultSensor(Sensor.TYPE_PRESSURE)
        humiditySensor = sensorManager.getDefaultSensor(Sensor.TYPE_RELATIVE_HUMIDITY)
        significantMotionSensor = sensorManager.getDefaultSensor(Sensor.TYPE_SIGNIFICANT_MOTION)
        stepCounterSensor = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)

        webSocketManager = WebSocketManager(AppState.serverUrl)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        registerSensorListener(accelerometer)
        registerSensorListener(magnetometer)
        registerSensorListener(gyroscope)
        registerSensorListener(lightSensor)
        registerSensorListener(proximitySensor)
        registerSensorListener(gravitySensor)
        registerSensorListener(linearAccelerationSensor)
        registerSensorListener(rotationVectorSensor)
        registerSensorListener(ambientTemperatureSensor)
        registerSensorListener(pressureSensor)
        registerSensorListener(humiditySensor)
        registerTriggerSensor(significantMotionSensor)
        registerSensorListener(stepCounterSensor)
        return START_STICKY
    }

    private fun registerSensorListener(sensor: Sensor?) {
        sensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
    }

    private fun registerTriggerSensor(sensor: Sensor?) {
        sensor?.let {
            sensorManager.requestTriggerSensor(triggerEventListener, it)
        }
    }

    private val triggerEventListener = object : TriggerEventListener() {
        override fun onTrigger(event: TriggerEvent) {
            val sensorType = when (event.sensor.type) {
                Sensor.TYPE_SIGNIFICANT_MOTION -> "significant_motion"
                else -> return
            }

            if (AppState.shouldSendData()) {
                AppState.sensorPacketsSent++
                addSensorDataToBatch(sensorType, event.values)
            }

            // Re-register the trigger sensor if needed
            registerTriggerSensor(event.sensor)
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        val sensorType = when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> "accelerometer"
            Sensor.TYPE_MAGNETIC_FIELD -> "magnetometer"
            Sensor.TYPE_GYROSCOPE -> "gyroscope"
            Sensor.TYPE_LIGHT -> "light"
            Sensor.TYPE_PROXIMITY -> "proximity"
            Sensor.TYPE_GRAVITY -> "gravity"
            Sensor.TYPE_LINEAR_ACCELERATION -> "linear_acceleration"
            Sensor.TYPE_ROTATION_VECTOR -> "rotation_vector"
            Sensor.TYPE_AMBIENT_TEMPERATURE -> "ambient_temperature"
            Sensor.TYPE_PRESSURE -> "pressure"
            Sensor.TYPE_RELATIVE_HUMIDITY -> "humidity"
            Sensor.TYPE_SIGNIFICANT_MOTION -> "significant_motion"
            Sensor.TYPE_STEP_COUNTER -> "step_counter"
            else -> return
        }

        if (AppState.shouldSendData()) {
            AppState.sensorPacketsSent++
            addSensorDataToBatch(sensorType, event.values)
        }
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {}

    private fun addSensorDataToBatch(sensorType: String, values: FloatArray) {
        sensorDataBatch.add(Pair(sensorType, values))
        if (sensorDataBatch.size >= batchSize) {
            sendSensorDataBatchToServer()
        }
    }

    private fun sendSensorDataBatchToServer() {
        webSocketManager.sendSensorDataList(sensorDataBatch) { statusCode ->
//            AppState.sensorHttpStatusCodes.add(statusCode)
        }
        sensorDataBatch.clear()
    }

    override fun onDestroy() {
        sensorManager.unregisterListener(this)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}
