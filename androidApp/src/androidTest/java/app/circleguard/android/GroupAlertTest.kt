package app.circleguard.android

import android.Manifest
import android.os.Build
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/** Exercises native UI -> shared KMP simulation -> relay -> another member's alert feed. */
class GroupAlertTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun request(path: String, body: JSONObject? = null, token: String = ""): JSONObject {
        val connection = URL("http://10.0.2.2:8787$path").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 10000
            connection.readTimeout = 10000
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            assertEquals(200, connection.responseCode)
            return JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally { connection.disconnect() }
    }

    @Test fun simulatedExitReachesOtherMemberExactlyOnce() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        if (Build.VERSION.SDK_INT >= 33) {
            InstrumentationRegistry.getInstrumentation().uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.POST_NOTIFICATIONS)
        }
        compose.onNodeWithText("Your name").performTextInput("Android Walker")
        compose.onNodeWithText("Connect & continue").performClick()
        val repository = Repository.get(context)
        compose.waitUntil(20000) { repository.state.value.userId.isNotEmpty() }
        compose.onNodeWithText("Create group").performClick()
        compose.onNodeWithText("Create circle").performClick()
        compose.waitUntil(20000) { repository.state.value.groups.isNotEmpty() }
        val group = repository.state.value.groups.first()
        val observer = request("/users", JSONObject().put("name", "Android Observer"))
        val token = observer.getString("token")
        request("/join", JSONObject().put("code", group.code), token)
        compose.onNodeWithText("Move inside").performScrollTo().performClick()
        compose.waitUntil(20000) { repository.state.value.selected?.members?.firstOrNull { it.id == repository.state.value.userId }?.state == "inside" }
        compose.onNodeWithText("Move outside").performScrollTo().performClick()
        compose.waitUntil(20000) { repository.state.value.selected?.members?.firstOrNull { it.id == repository.state.value.userId }?.state == "outside" }
        compose.onNodeWithText("Move outside").performClick()
        compose.waitUntil(20000) { !repository.state.value.busy && repository.state.value.pending == 0 }
        val events = request("/events", token = token).getJSONArray("events")
        assertEquals(1, events.length())
        assertTrue(events.getJSONObject(0).getString("title").startsWith("[TEST]"))

        // Reverse direction verifies native polling and the persistent Activity feed too.
        for (lon in listOf(group.longitude, group.longitude + 0.02)) {
            request("/locations", JSONObject().put("latitude", group.latitude).put("longitude", lon).put("accuracy", 5)
                .put("simulated", true).put("groupId", group.id).put("observedAt", System.currentTimeMillis()/1000.0)
                .put("requestId", UUID.randomUUID().toString()), token)
        }
        compose.waitUntil(20000) { repository.state.value.events.any { it.body.contains("Android Observer") } }
        compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText("Android Observer left My circle’s safe area."))
        compose.onNodeWithText("Android Observer left My circle’s safe area.").assertIsDisplayed()
        val notifications = context.getSystemService(android.app.NotificationManager::class.java).activeNotifications
        assertTrue(notifications.any { it.notification.extras.getString("android.text") == "Android Observer left My circle’s safe area." })
    }
}
