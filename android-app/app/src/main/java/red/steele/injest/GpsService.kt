package red.steele.injest

import android.app.Service
import android.content.Context
import android.content.Intent
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.IBinder
import java.util.concurrent.Executors

class GpsService : Service(), LocationListener {

    private lateinit var locationManager: LocationManager
    private lateinit var webSocketManager: WebSocketManager

    companion object {
        private const val TAG = "GpsService"
        private const val MIN_UPDATE_TIME = 1000L  // 1 second
        private const val MIN_UPDATE_DISTANCE = 0.0f  // 0 meters
    }

    override fun onCreate() {
        super.onCreate()
        locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        webSocketManager = WebSocketManager(AppState.serverUrl)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startLocationUpdates()
        return START_STICKY
    }

    private fun startLocationUpdates() {
        try {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                MIN_UPDATE_TIME,
                MIN_UPDATE_DISTANCE,
                this
            )
        } catch (e: SecurityException) {
            // Handle exception (e.g., log or notify the user)
        }
    }

    override fun onLocationChanged(location: Location) {
        Executors.newSingleThreadExecutor().execute {
            if (AppState.shouldSendData()) {
                AppState.gpsPacketsSent++
                sendLocationDataToWebSocket(location)
            }
        }
    }

    private fun sendLocationDataToWebSocket(location: Location) {
        webSocketManager.sendGpsData(
            latitude = location.latitude,
            longitude = location.longitude,
            altitude = location.altitude,
            time = location.time
        )
    }

    override fun onStatusChanged(provider: String, status: Int, extras: Bundle) {}
    override fun onProviderEnabled(provider: String) {}
    override fun onProviderDisabled(provider: String) {}

    override fun onDestroy() {
        locationManager.removeUpdates(this)
        webSocketManager.close()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}