package app.circleguard.android

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import java.text.DateFormat
import java.util.Date

private val Teal = Color(0xFF087F6C)

class MainActivity : ComponentActivity() {
    private val repository by lazy { Repository.get(this) }
    private val notifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
    private val locationPermission = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if (it[Manifest.permission.ACCESS_FINE_LOCATION] == true) startSharing()
        else repository.showError("Precise location access is needed for small geofences. Enable it in Settings.")
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightStatusBars = true
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Teal, secondary = Teal, background = Color(0xFFF3F6F5))) {
                CircleScreen(repository, onSharing = {
                    if (repository.state.value.tracking) stopService(Intent(this, TrackingService::class.java))
                    else if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) startSharing()
                    else locationPermission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
                }, onNotifications = {
                    if (Build.VERSION.SDK_INT >= 33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                }, onCopy = { code ->
                    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("CircleGuard invite", code))
                })
            }
        }
    }
    private fun startSharing() { startForegroundService(Intent(this, TrackingService::class.java)) }
}

@Composable
private fun CircleScreen(repository: Repository, onSharing: () -> Unit, onNotifications: () -> Unit, onCopy: (String) -> Unit) {
    val state by repository.state.collectAsState()
    var name by remember { mutableStateOf("") }
    var url by remember { mutableStateOf(state.baseUrl) }
    var create by remember { mutableStateOf(false) }
    var join by remember { mutableStateOf(false) }
    var code by remember { mutableStateOf("") }
    var leave by remember { mutableStateOf<Group?>(null) }
    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            item {
                Text("CircleGuard", fontSize = 32.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text("Stay in the circle.", color = Teal, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                Text("A little space. A little peace of mind.", color = Color.Gray)
            }
            if (state.userId.isEmpty()) {
                item { Panel {
                    Text("Your circle starts here", style = MaterialTheme.typography.titleLarge)
                    Text("Connect everyone to the same local relay.")
                    OutlinedTextField(name, { name = it }, label = { Text("Your name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(url, { url = it }, label = { Text("Relay URL") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
                    Text("Emulator: http://10.0.2.2:8787\nPhysical phone: use your Mac’s LAN IP.", style = MaterialTheme.typography.bodySmall)
                    Button(onClick = { onNotifications(); repository.connect(name, url) }, enabled = !state.busy && name.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
                        Text(if (state.busy) "Connecting…" else "Connect & continue")
                    }
                } }
            } else {
                item {
                    Text("Hello, ${state.name}", fontWeight = FontWeight.Bold)
                    Text(state.status, style = MaterialTheme.typography.bodySmall)
                    if (state.pending > 0) Text("${state.pending} locations queued", color = Color(0xFFA65D00))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { create = true }) { Text("Create group") }
                        OutlinedButton(onClick = { join = true }) { Text("Join group") }
                    }
                }
                if (state.groups.isEmpty()) item { Panel {
                    Text("Good company. Shared boundaries.", style = MaterialTheme.typography.titleMedium)
                    Text("Create a circle, set a safe area, and invite someone to try an exit alert.")
                } }
                if (state.groups.size > 1) item {
                    Column { state.groups.forEach { group ->
                        FilterChip(selected = state.selected?.id == group.id, onClick = { repository.select(group.id) }, label = { Text(group.name) })
                    } }
                }
                state.selected?.let { group ->
                    item { Panel {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Text(group.name, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                            TextButton(onClick = { leave = group }) { Text("Leave") }
                        }
                        Text("${group.radius.toInt()} m safe area · ${group.members.size} members", color = Color.Gray)
                        FenceDiagram(group, state.userId)
                        Text("Center: ${group.latitude}, ${group.longitude}", style = MaterialTheme.typography.bodySmall)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("INVITE  ${group.code}", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                            TextButton(onClick = { onCopy(group.code) }) { Text("Copy") }
                        }
                    } }
                    item { Panel(tinted = true) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Location test lab", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            Switch(checked = state.simulation, onCheckedChange = { repository.setSimulation(it) })
                        }
                        if (state.simulation) {
                            Text("GPS is paused. Move inside, then outside. Other members receive a [TEST] exit alert.")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = { repository.simulate(false) }, enabled = !state.busy) { Text("Move inside") }
                                Button(onClick = { repository.simulate(true) }, enabled = !state.busy) { Text("Move outside") }
                            }
                            Text("Re-enter to re-arm. Staying outside sends no extra alerts.", style = MaterialTheme.typography.bodySmall)
                        } else {
                            Button(onClick = onSharing) { Text(if (state.tracking) "Stop location sharing" else "Start location sharing") }
                            Text("Background sharing uses an ongoing notification. Keep Location services on and the relay reachable.", style = MaterialTheme.typography.bodySmall)
                        }
                        TextButton(onClick = onNotifications) { Text("Enable notifications") }
                    } }
                    item { Panel {
                        Text("In your circle", style = MaterialTheme.typography.titleMedium)
                        group.members.forEach { member ->
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(member.name + if (member.id == state.userId) " (you)" else "", fontWeight = FontWeight.SemiBold)
                                    Text(if (member.updatedAt > 0) "Last fix: ${DateFormat.getTimeInstance().format(Date((member.updatedAt * 1000).toLong()))}" else "Waiting for first location", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                                }
                                Text(member.state.uppercase() + if (member.mode == "simulation") " · TEST" else "",
                                    color = if (member.state == "outside") Color(0xFFA65D00) else Teal, style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    } }
                }
                item { Text("Activity", style = MaterialTheme.typography.titleLarge) }
                if (state.events.isEmpty()) item { Text("All quiet. Exits by other members will appear here.", color = Color.Gray) }
                items(state.events.take(20), key = { it.id }) { event -> Panel {
                    Text(event.title, color = Color(0xFFA65D00), fontWeight = FontWeight.Bold)
                    Text(event.body)
                    Text(DateFormat.getTimeInstance().format(Date((event.createdAt * 1000).toLong())), style = MaterialTheme.typography.bodySmall)
                } }
                item { Text("Only inside → outside transitions alert other members. Boundary accuracy is accounted for. An initial outside fix sends no alert.", style = MaterialTheme.typography.bodySmall, color = Color.Gray) }
            }
        }
    }
    if (create) CreateDialog(onDismiss = { create = false }) { groupName, lat, lon, radius ->
        repository.create(groupName, lat, lon, radius)
        create = false
    }
    if (join) AlertDialog(onDismissRequest = { join = false }, title = { Text("Join a circle") },
        text = { OutlinedTextField(code, { code = it.uppercase() }, label = { Text("10-character invite code") }, singleLine = true) },
        confirmButton = { TextButton(onClick = { repository.join(code); join = false }) { Text("Join") } },
        dismissButton = { TextButton(onClick = { join = false }) { Text("Cancel") } })
    leave?.let { group -> AlertDialog(onDismissRequest = { leave = null }, title = { Text("Leave ${group.name}?") },
        text = { Text("You’ll stop sharing your status and receiving new alerts from this group.") },
        confirmButton = { TextButton(onClick = { repository.leave(group); leave = null }) { Text("Leave") } },
        dismissButton = { TextButton(onClick = { leave = null }) { Text("Cancel") } }) }
    state.error?.let { message -> AlertDialog(onDismissRequest = { repository.dismissError() }, title = { Text("Something needs attention") },
        text = { Text(message) }, confirmButton = { TextButton(onClick = { repository.dismissError() }) { Text("OK") } }) }
}

@Composable
private fun Panel(tinted: Boolean = false, content: @Composable ColumnScope.() -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = if (tinted) Color(0xFFE3F1EC) else Color.White), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}

@Composable
private fun FenceDiagram(group: Group, userId: String) {
    val outside = group.members.firstOrNull { it.id == userId }?.state == "outside"
    Box(Modifier.fillMaxWidth().height(165.dp).background(Color(0xFFF0F7F4)), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val radius = size.height * 0.36f
            drawCircle(Teal.copy(alpha = 0.12f), radius)
            drawCircle(Teal.copy(alpha = 0.8f), radius, style = Stroke(width = 3f))
            drawCircle(Teal.copy(alpha = 0.2f), radius * 1.25f, style = Stroke(width = 1f))
            drawCircle(if (outside) Color(0xFFD5821D) else Teal, 10f,
                Offset(size.width/2 + if (outside) radius*1.5f else 0f, size.height/2))
        }
        Text("Geofence overview · not a live map", modifier = Modifier.align(Alignment.BottomCenter).padding(5.dp), style = MaterialTheme.typography.labelSmall, color = Color.Gray)
    }
}

@Composable
private fun CreateDialog(onDismiss: () -> Unit, onCreate: (String, Double, Double, Double) -> Unit) {
    var name by remember { mutableStateOf("My circle") }
    var lat by remember { mutableStateOf("37.3349") }
    var lon by remember { mutableStateOf("-122.0090") }
    var radius by remember { mutableFloatStateOf(500f) }
    val valid = name.isNotBlank() && lat.toDoubleOrNull()?.let { it in -90.0..90.0 } == true && lon.toDoubleOrNull()?.let { it in -180.0..180.0 } == true
    AlertDialog(onDismissRequest = onDismiss, title = { Text("New circle") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(name, { name = it }, label = { Text("Group name") })
            OutlinedTextField(lat, { lat = it }, label = { Text("Latitude") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text))
            OutlinedTextField(lon, { lon = it }, label = { Text("Longitude") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text))
            Text("Radius: ${radius.toInt()} metres")
            Slider(radius, { radius = it }, valueRange = 100f..10000f, steps = 98)
            Text("Default center: Apple Park", style = MaterialTheme.typography.bodySmall)
        }
    }, confirmButton = { TextButton(onClick = { onCreate(name, lat.toDouble(), lon.toDouble(), radius.toDouble()) }, enabled = valid) { Text("Create circle") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}
