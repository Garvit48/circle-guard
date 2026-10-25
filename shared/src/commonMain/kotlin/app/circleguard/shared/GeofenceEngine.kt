package app.circleguard.shared

import kotlin.math.*

/** Metres on a spherical Earth. Used by both native UIs and their simulation controls. */
class GeofenceEngine {
    fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        require(validCoordinate(lat1, lon1) && validCoordinate(lat2, lon2))
        val p1 = lat1 * PI / 180
        val p2 = lat2 * PI / 180
        val dp = (lat2 - lat1) * PI / 180
        val dl = (lon2 - lon1) * PI / 180
        val a = (sin(dp / 2).pow(2) + cos(p1) * cos(p2) * sin(dl / 2).pow(2)).coerceIn(0.0, 1.0)
        return 6_371_000.0 * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    fun validCoordinate(latitude: Double, longitude: Double): Boolean =
        latitude.isFinite() && longitude.isFinite() && latitude in -90.0..90.0 && longitude in -180.0..180.0

    fun validFence(latitude: Double, longitude: Double, radius: Double): Boolean =
        validCoordinate(latitude, longitude) && radius.isFinite() && radius in 100.0..10_000.0

    /** Accuracy-aware Schmitt trigger: boundary jitter cannot repeatedly trigger exits. */
    fun classify(distance: Double, radius: Double, accuracy: Double, previous: String): String {
        require(distance.isFinite() && distance >= 0 && radius.isFinite() && radius > 0)
        require(accuracy.isFinite() && accuracy >= 0)
        val margin = max(15.0, accuracy)
        return when {
            distance > radius + margin -> "outside"
            distance < max(0.0, radius - margin) -> "inside"
            else -> previous
        }
    }

    fun isExit(previous: String, current: String): Boolean = previous == "inside" && current == "outside"

    /** Destination on the sphere; handles fences near the poles and antimeridian. */
    fun simulationPoint(latitude: Double, longitude: Double, radius: Double, outside: Boolean): GeoPoint {
        require(validFence(latitude, longitude, radius))
        if (!outside) return GeoPoint(latitude, longitude)
        val delta = (radius + max(100.0, radius * 0.5)) / 6_371_000.0
        val phi = latitude * PI / 180
        val lambda = longitude * PI / 180
        val lat = asin(sin(phi) * cos(delta))
        val lon = lambda + atan2(sin(delta) * cos(phi), cos(delta) - sin(phi) * sin(lat))
        return GeoPoint(lat * 180 / PI, ((lon * 180 / PI + 540) % 360) - 180)
    }
}

data class GeoPoint(val latitude: Double, val longitude: Double)
