package app.circleguard.android

import android.Manifest
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.IBinder
import androidx.core.app.NotificationCompat

/** Explicit, user-started foreground sharing; no Play Services or cloud geofence SDK. */
class TrackingService : Service(), LocationListener {
    private lateinit var manager: LocationManager
    private lateinit var repository: Repository
    private var lastFix = 0L

    override fun onCreate() {
        super.onCreate()
        repository = Repository.get(this)
        manager = getSystemService(LocationManager::class.java)
        Repository.channels(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "STOP") { stopSelf(); return START_NOT_STICKY }
        if (repository.state.value.simulation || checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            stopSelf()
            return START_NOT_STICKY
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop = PendingIntent.getService(this, 1, Intent(this, TrackingService::class.java).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE)
        startForeground(1, NotificationCompat.Builder(this, "tracking").setSmallIcon(android.R.drawable.ic_dialog_map)
            .setContentTitle("CircleGuard location sharing").setContentText("Your circles receive alerts when you leave their safe area.")
            .setContentIntent(open).setOngoing(true).addAction(0, "Stop sharing", stop).build())
        repository.setTracking(true)
        try {
            var available = false
            for (provider in listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)) {
                if (manager.isProviderEnabled(provider)) {
                    manager.requestLocationUpdates(provider, 5000, 10f, this)
                    available = true
                }
            }
            if (!available) repository.showError("Turn on device Location services to share GPS fixes.")
        } catch (error: SecurityException) {
            repository.showError(error.message ?: "Location permission required")
            stopSelf()
        }
        return START_NOT_STICKY
    }

    override fun onLocationChanged(location: Location) {
        if (!location.hasAccuracy() || location.accuracy < 0 || System.currentTimeMillis() - location.time > 120000) return
        if (location.time - lastFix < 3000) return
        lastFix = location.time
        repository.reportLocation(location.latitude, location.longitude, location.accuracy.toDouble(), location.time / 1000.0)
    }
    override fun onDestroy() {
        manager.removeUpdates(this)
        repository.setTracking(false)
        super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
