package app.circleguard.android

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import app.circleguard.shared.GeofenceEngine
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.util.UUID

data class Member(val id: String, val name: String, val state: String, val mode: String, val updatedAt: Double)
data class Group(val id: String, val name: String, val code: String, val ownerId: String,
                 val latitude: Double, val longitude: Double, val radius: Double, val members: List<Member>)
data class ExitEvent(val id: Int, val title: String, val body: String, val createdAt: Double)
data class ScreenState(
    val name: String = "", val userId: String = "", val baseUrl: String = "http://10.0.2.2:8787",
    val groups: List<Group> = emptyList(), val selectedId: String = "", val events: List<ExitEvent> = emptyList(),
    val simulation: Boolean = true, val tracking: Boolean = false, val pending: Int = 0,
    val busy: Boolean = false, val status: String = "Connect to your local relay", val error: String? = null,
) { val selected: Group? get() = groups.firstOrNull { it.id == selectedId } ?: groups.firstOrNull() }

class RelayException(val code: Int, override val message: String) : Exception(message)

class Repository private constructor(private val context: Context) {
    private val preferences = context.getSharedPreferences("circle-guard", Context.MODE_PRIVATE)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val pollMutex = Mutex()
    private val queueMutex = Mutex()
    private var token = preferences.getString("token", "")!!
    private var cursor = preferences.getInt("cursor", 0)
    private val queue = mutableListOf<JSONObject>()
    private val mutable = MutableStateFlow(ScreenState(
        name = preferences.getString("name", "")!!, userId = preferences.getString("userId", "")!!,
        baseUrl = preferences.getString("url", "http://10.0.2.2:8787")!!,
        simulation = preferences.getBoolean("simulation", true),
    ))
    val state = mutable.asStateFlow()
    val engine = GeofenceEngine()

    init {
        val pending = JSONArray(preferences.getString("outbox", "[]"))
        for (i in 0 until pending.length()) queue.add(pending.getJSONObject(i))
        val saved = JSONArray(preferences.getString("events", "[]"))
        mutable.update { it.copy(events = parseEvents(saved), pending = queue.size) }
        channels(context)
        scope.launch {
            while (isActive) {
                if (token.isNotEmpty()) refresh()
                delay(3000)
            }
        }
    }

    private suspend fun request(path: String, method: String = "GET", body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        val url = URI(state.value.baseUrl + path).toURL()
        if (url.protocol !in listOf("http", "https")) throw RelayException(0, "Use an http:// or https:// relay URL")
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 10000
            connection.readTimeout = 10000
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("Content-Type", "application/json")
            if (body != null) {
                connection.doOutput = true
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val response = JSONObject(stream?.bufferedReader()?.use { it.readText() } ?: "{}")
            if (code !in 200..299) throw RelayException(code, response.optString("error", "Relay returned HTTP $code"))
            response
        } finally { connection.disconnect() }
    }

    fun connect(name: String, url: String) = action {
        require(name.isNotBlank()) { "Enter your name" }
        val normalized = url.trim().trimEnd('/')
        val uri = URI(normalized)
        require(uri.scheme in listOf("http", "https") && uri.host != null) { "Enter a valid relay URL" }
        mutable.update { it.copy(baseUrl = normalized) }
        request("/health")
        val user = request("/users", "POST", JSONObject().put("name", name.trim()))
        token = user.getString("token")
        preferences.edit().putString("token", token).putString("name", user.getString("name"))
            .putString("userId", user.getString("id")).putString("url", normalized).apply()
        mutable.update { it.copy(name = user.getString("name"), userId = user.getString("id")) }
        refresh()
    }

    fun create(name: String, lat: Double, lon: Double, radius: Double) = action {
        require(engine.validFence(lat, lon, radius)) { "Use valid coordinates and a radius of 100–10,000 metres" }
        applyGroups(request("/groups", "POST", JSONObject().put("name", name).put("latitude", lat).put("longitude", lon).put("radius", radius)))
        mutable.update { it.copy(selectedId = it.groups.lastOrNull()?.id ?: "") }
    }

    fun join(code: String) = action { applyGroups(request("/join", "POST", JSONObject().put("code", code.trim()))) }
    fun leave(group: Group) = action { applyGroups(request("/groups/${group.id}/leave", "POST", JSONObject())) }
    fun select(id: String) { mutable.update { it.copy(selectedId = id) } }
    fun dismissError() { mutable.update { it.copy(error = null) } }
    fun showError(message: String) { mutable.update { it.copy(error = message) } }
    fun setTracking(enabled: Boolean) { mutable.update { it.copy(tracking = enabled) } }
    fun setSimulation(enabled: Boolean) {
        context.stopService(Intent(context, TrackingService::class.java))
        preferences.edit().putBoolean("simulation", enabled).apply()
        mutable.update { it.copy(simulation = enabled, tracking = false) }
    }

    fun simulate(outside: Boolean) = action {
        val group = state.value.selected ?: return@action
        if (!state.value.simulation) return@action
        val point = engine.simulationPoint(group.latitude, group.longitude, group.radius, outside)
        enqueue(point.latitude, point.longitude, 5.0, System.currentTimeMillis()/1000.0, true, group.id)
        refresh()
    }

    fun reportLocation(latitude: Double, longitude: Double, accuracy: Double, observed: Double) {
        if (state.value.simulation) return
        scope.launch { enqueue(latitude, longitude, accuracy, observed, false, null) }
    }

    private suspend fun enqueue(lat: Double, lon: Double, accuracy: Double, observed: Double, simulated: Boolean, groupId: String?) {
        queueMutex.withLock {
            if (queue.size >= 500) { showError("Location queue is full. Reconnect to the relay."); return }
            queue.add(JSONObject().put("latitude", lat).put("longitude", lon).put("accuracy", accuracy)
                .put("observedAt", observed).put("simulated", simulated).put("requestId", UUID.randomUUID().toString())
                .also { if (groupId != null) it.put("groupId", groupId) })
            persistQueue()
        }
        flush()
    }

    private fun persistQueue() {
        preferences.edit().putString("outbox", JSONArray(queue).toString()).commit()
        mutable.update { it.copy(pending = queue.size) }
    }

    private suspend fun flush() = queueMutex.withLock {
        while (queue.isNotEmpty()) {
            try {
                request("/locations", "POST", queue.first())
                queue.removeAt(0)
                persistQueue()
            } catch (error: Exception) {
                if (error is RelayException && error.code in listOf(400, 403)) {
                    queue.removeAt(0)
                    persistQueue()
                    showError("Discarded an expired or unauthorized location: ${error.message}")
                } else {
                    mutable.update { it.copy(status = "Location queued — waiting for relay") }
                    break
                }
            }
        }
    }

    private fun action(block: suspend () -> Unit) {
        scope.launch {
            mutable.update { it.copy(busy = true, error = null) }
            try { block() }
            catch (error: Exception) { showError(error.message ?: "Request failed") }
            finally { mutable.update { it.copy(busy = false) } }
        }
    }

    private suspend fun refresh() {
        if (!pollMutex.tryLock()) return
        try {
            applyGroups(request("/groups"))
            val response = request("/events?after=$cursor")
            val incoming = parseEvents(response.getJSONArray("events"))
            incoming.filter { event -> state.value.events.none { it.id == event.id } }.forEach { notifyExit(it) }
            val events = (incoming.reversed() + state.value.events).distinctBy { it.id }.take(100)
            cursor = response.getInt("cursor")
            preferences.edit().putInt("cursor", cursor).putString("events", JSONArray(events.map {
                JSONObject().put("id", it.id).put("title", it.title).put("body", it.body).put("created_at", it.createdAt)
            }).toString()).apply()
            mutable.update { it.copy(events = events, status = if (it.tracking) "Connected · background sharing active" else "Connected · live alerts while app is open") }
            flush()
        } catch (error: Exception) {
            mutable.update { it.copy(status = "Relay offline · ${it.pending} location(s) queued") }
            if (error is RelayException && error.code == 401) showError(error.message)
        } finally { pollMutex.unlock() }
    }

    private fun applyGroups(response: JSONObject) {
        val array = response.getJSONArray("groups")
        val groups = (0 until array.length()).map { index ->
            val g = array.getJSONObject(index)
            val members = g.getJSONArray("members")
            Group(g.getString("id"), g.getString("name"), g.getString("code"), g.getString("owner_id"),
                g.getDouble("latitude"), g.getDouble("longitude"), g.getDouble("radius"),
                (0 until members.length()).map {
                    val m = members.getJSONObject(it)
                    Member(m.getString("id"), m.getString("name"), m.getString("state"), m.getString("mode"), m.getDouble("updated_at"))
                })
        }
        mutable.update { it.copy(groups = groups) }
    }

    private fun parseEvents(array: JSONArray): List<ExitEvent> = (0 until array.length()).map {
        val e = array.getJSONObject(it)
        ExitEvent(e.getInt("id"), e.getString("title"), e.getString("body"), e.getDouble("created_at"))
    }

    private fun notifyExit(event: ExitEvent) {
        val intent = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = NotificationCompat.Builder(context, "exits").setSmallIcon(android.R.drawable.ic_dialog_map)
            .setContentTitle(event.title).setContentText(event.body).setStyle(NotificationCompat.BigTextStyle().bigText(event.body))
            .setContentIntent(intent).setAutoCancel(true).setPriority(NotificationCompat.PRIORITY_HIGH).build()
        try { context.getSystemService(NotificationManager::class.java).notify(event.id + 1000, notification) }
        catch (_: SecurityException) { /* The persistent Activity feed still receives the event. */ }
    }

    companion object {
        @Volatile private var instance: Repository? = null
        fun get(context: Context): Repository = instance ?: synchronized(this) {
            instance ?: Repository(context.applicationContext).also { instance = it }
        }
        fun channels(context: Context) {
            context.getSystemService(NotificationManager::class.java).apply {
                createNotificationChannel(NotificationChannel("exits", "Group exit alerts", NotificationManager.IMPORTANCE_HIGH))
                createNotificationChannel(NotificationChannel("tracking", "Location sharing", NotificationManager.IMPORTANCE_LOW))
            }
        }
    }
}
