package app.circleguard.shared

import kotlin.test.*

class GeofenceEngineTest {
    private val engine = GeofenceEngine()
    @Test fun knownDistance() {
        assertEquals(111_194.9, engine.distanceMeters(0.0, 0.0, 0.0, 1.0), 1.0)
        assertEquals(0.0, engine.distanceMeters(45.0, 10.0, 45.0, 10.0), 0.001)
    }
    @Test fun jitterAndAccuracyDoNotCauseExits() {
        assertEquals("inside", engine.classify(510.0, 500.0, 5.0, "inside"))
        assertEquals("inside", engine.classify(550.0, 500.0, 100.0, "inside"))
        assertEquals("outside", engine.classify(650.0, 500.0, 10.0, "inside"))
        assertEquals("outside", engine.classify(495.0, 500.0, 10.0, "outside"))
        assertEquals("inside", engine.classify(480.0, 500.0, 10.0, "outside"))
    }
    @Test fun onlyInsideToOutsideAlerts() {
        assertTrue(engine.isExit("inside", "outside"))
        assertFalse(engine.isExit("unknown", "outside"))
        assertFalse(engine.isExit("outside", "outside"))
    }
    @Test fun simulationWorksAcrossDateLineAndNearPoles() {
        for ((lat, lon) in listOf(37.3349 to -122.009, 89.999 to 179.999, -89.999 to -179.999)) {
            val point = engine.simulationPoint(lat, lon, 500.0, true)
            assertTrue(engine.validCoordinate(point.latitude, point.longitude))
            assertEquals(750.0, engine.distanceMeters(lat, lon, point.latitude, point.longitude), 0.1)
        }
    }
    @Test fun rejectsInvalidInput() {
        assertFalse(engine.validFence(Double.NaN, 0.0, 500.0))
        assertFalse(engine.validFence(91.0, 0.0, 500.0))
        assertFalse(engine.validFence(0.0, 0.0, 10.0))
    }
}
