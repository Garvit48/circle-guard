import SwiftUI
import CoreLocation
import UserNotifications
import Shared

@MainActor
final class AppStore: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published var serverURL = UserDefaults.standard.string(forKey: "relayURL") ?? "http://127.0.0.1:8787"
    @Published var profile: Profile?
    @Published var groups: [TrackingGroup] = []
    @Published var events: [ExitEvent] = []
    @Published var selectedID = ""
    @Published var error: String?
    @Published var status = "Connect to your local relay"
    @Published var busy = false
    @Published var simulation = true
    @Published var tracking = false
    @Published var pendingCount = 0
    @Published var locationPermission = "Not requested"
    let engine = GeofenceEngine()
    let location = CLLocationManager()
    private var refreshTask: Task<Void, Never>?
    private var refreshing = false
    private var flushing = false
    private var lastFix: TimeInterval = 0
    private var outbox: [LocationReport] = []
    private var apnsAvailable = false
    private var pushRegistered = false
    private var registeredPushToken = ""
    private var cursor = 0
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var monitorSignature = ""
    var selected: TrackingGroup? { groups.first { $0.id == selectedID } ?? groups.first }
    private var storageKey: String { "\(serverURL).\(profile?.id ?? "none")" }

    override init() {
        super.init()
        location.delegate = self
        location.desiredAccuracy = kCLLocationAccuracyBest
        location.distanceFilter = 20
        location.pausesLocationUpdatesAutomatically = false
        profile = ProcessInfo.processInfo.arguments.contains("--uitest") ? nil : ProfileVault.load(server: serverURL)
        simulation = UserDefaults.standard.object(forKey: "simulation") as? Bool ?? true
        loadState()
        updatePermission()
        tracking = !simulation && UserDefaults.standard.bool(forKey: "trackingEnabled")
        if tracking { startTracking() }
        startPolling()
    }

    func connect(name: String) async {
        busy = true
        defer { busy = false }
        do {
            serverURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            _ = try await Relay.request(HealthResponse.self, base: serverURL, path: "/health")
            let saved = ProcessInfo.processInfo.arguments.contains("--uitest") ? nil : ProfileVault.load(server: serverURL)
            let newProfile: Profile
            if let saved { newProfile = saved }
            else {
                newProfile = try await Relay.request(Profile.self, base: serverURL, path: "/users", method: "POST", body: Relay.json(["name": name]))
                try ProfileVault.save(newProfile, server: serverURL)
            }
            profile = newProfile
            UserDefaults.standard.set(serverURL, forKey: "relayURL")
            loadState()
            error = nil
            await enableNotifications()
            await refresh()
        } catch { self.error = error.localizedDescription }
    }

    func enableNotifications() async {
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            if granted { UIApplication.shared.registerForRemoteNotifications() }
            else { status = "Notifications denied — alerts still appear in Activity" }
        } catch { self.error = error.localizedDescription }
    }

    private func loadState() {
        outbox = []
        events = []
        groups = []
        cursor = UserDefaults.standard.integer(forKey: storageKey + ".cursor")
        if let data = UserDefaults.standard.data(forKey: storageKey + ".groups") {
            groups = (try? JSONDecoder().decode([TrackingGroup].self, from: data)) ?? []
        }
        if let data = UserDefaults.standard.data(forKey: storageKey + ".outbox") {
            outbox = (try? JSONDecoder().decode([LocationReport].self, from: data)) ?? []
        }
        if let data = UserDefaults.standard.data(forKey: storageKey + ".events") {
            events = (try? JSONDecoder().decode([ExitEvent].self, from: data)) ?? []
        }
        pendingCount = outbox.count
    }

    private func startPolling() {
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }

    func refresh() async {
        guard let profile, !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        do {
            let health = try await Relay.request(HealthResponse.self, base: serverURL, path: "/health")
            apnsAvailable = health.apns
            let response = try await Relay.request(GroupsResponse.self, base: serverURL, path: "/groups", token: profile.token)
            groups = response.groups
            UserDefaults.standard.set(try? JSONEncoder().encode(groups), forKey: storageKey + ".groups")
            if selected == nil || !groups.contains(where: { $0.id == selectedID }) { selectedID = groups.first?.id ?? "" }
            configureRegions()
            await registerPushIfNeeded()
            let updates = try await Relay.request(EventsResponse.self, base: serverURL, path: "/events?after=\(cursor)", token: profile.token)
            for event in updates.events {
                if !events.contains(where: { $0.id == event.id }) {
                    events.insert(event, at: 0)
                    if !(apnsAvailable && pushRegistered) {
                        let content = UNMutableNotificationContent()
                        content.title = event.title
                        content.body = event.body
                        content.sound = .default
                        content.userInfo = ["eventId": event.id]
                        try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: "exit-\(event.id)", content: content, trigger: nil))
                    }
                }
            }
            events = Array(events.prefix(100))
            cursor = updates.cursor
            UserDefaults.standard.set(cursor, forKey: storageKey + ".cursor")
            UserDefaults.standard.set(try? JSONEncoder().encode(events), forKey: storageKey + ".events")
            status = apnsAvailable && pushRegistered ? "Connected · Apple push enabled" : "Connected · live alerts while app is open"
            await flush()
        } catch { status = "Relay offline · \(outbox.count) location(s) queued" }
    }

    private func registerPushIfNeeded() async {
        guard let profile, let token = UserDefaults.standard.string(forKey: "apnsToken"), token != registeredPushToken else { return }
        do {
            #if DEBUG
            let environment = "sandbox"
            #else
            let environment = "production"
            #endif
            _ = try await Relay.request(OKResponse.self, base: serverURL, path: "/devices", method: "POST", token: profile.token,
                                        body: Relay.json(["token": token, "environment": environment]))
            registeredPushToken = token
            pushRegistered = true
        } catch { pushRegistered = false }
    }

    func createGroup(name: String, latitude: Double, longitude: Double, radius: Double) async {
        guard engine.validFence(latitude: latitude, longitude: longitude, radius: radius) else { error = "Use valid coordinates and a radius of 100–10,000 metres."; return }
        await change(path: "/groups", data: ["name": name, "latitude": latitude, "longitude": longitude, "radius": radius])
        selectedID = groups.last?.id ?? ""
    }

    func join(code: String) async { await change(path: "/join", data: ["code": code]) }
    func leave(_ group: TrackingGroup) async { await change(path: "/groups/\(group.id)/leave", data: [:]) }

    private func change(path: String, data: [String: Any]) async {
        guard let profile else { return }
        busy = true
        defer { busy = false }
        do {
            let response = try await Relay.request(GroupsResponse.self, base: serverURL, path: path, method: "POST", token: profile.token, body: Relay.json(data))
            groups = response.groups
            error = nil
            configureRegions()
        } catch { self.error = error.localizedDescription }
    }

    func setSimulation(_ enabled: Bool) {
        simulation = enabled
        UserDefaults.standard.set(enabled, forKey: "simulation")
        stopTracking()
        status = enabled ? "Test mode · send an inside fix before an outside fix" : "GPS mode · tap Start location sharing"
    }

    func simulate(outside: Bool) async {
        guard simulation, let group = selected else { return }
        let point = engine.simulationPoint(latitude: group.latitude, longitude: group.longitude, radius: group.radius, outside: outside)
        enqueue(LocationReport(latitude: point.latitude, longitude: point.longitude, accuracy: 5, observedAt: Date().timeIntervalSince1970,
                               requestId: UUID().uuidString, simulated: true, groupId: group.id))
        await flush()
        await refresh()
    }

    private func enqueue(_ report: LocationReport) {
        guard outbox.count < 500 else { error = "Location queue is full. Reconnect to the relay."; return }
        outbox.append(report)
        persistQueue()
    }

    private func persistQueue() {
        pendingCount = outbox.count
        UserDefaults.standard.set(try? JSONEncoder().encode(outbox), forKey: storageKey + ".outbox")
    }

    private func flush() async {
        guard !flushing, let profile else { return }
        flushing = true
        defer { flushing = false }
        while let report = outbox.first {
            do {
                _ = try await Relay.request(LocationResponse.self, base: serverURL, path: "/locations", method: "POST", token: profile.token, body: JSONEncoder().encode(report))
                outbox.removeFirst()
                persistQueue()
            } catch let issue as RelayError where [400, 403].contains(issue.status) {
                error = "Discarded an expired or unauthorized location: \(issue.message)"
                outbox.removeFirst()
                persistQueue()
            } catch { status = "Location queued — waiting for relay"; break }
        }
    }

    func startTracking() {
        guard !simulation else { return }
        tracking = true
        UserDefaults.standard.set(true, forKey: "trackingEnabled")
        switch location.authorizationStatus {
        case .notDetermined: location.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            location.allowsBackgroundLocationUpdates = true
            location.showsBackgroundLocationIndicator = true
            location.startUpdatingLocation()
            configureRegions()
        default:
            error = "Allow location access in Settings to share your location."
            stopTracking()
        }
    }

    func requestAlways() { location.requestAlwaysAuthorization() }

    func stopTracking() {
        tracking = false
        UserDefaults.standard.set(false, forKey: "trackingEnabled")
        location.stopUpdatingLocation()
        for region in location.monitoredRegions { location.stopMonitoring(for: region) }
        monitorSignature = ""
    }

    private func configureRegions() {
        guard tracking, !simulation, CLLocationManager.isMonitoringAvailable(for: CLCircularRegion.self) else { return }
        let signature = groups.map { "\($0.id):\($0.version)" }.joined(separator: ",")
        guard signature != monitorSignature else { return }
        for region in location.monitoredRegions { location.stopMonitoring(for: region) }
        for group in groups.prefix(20) {
            let region = CLCircularRegion(center: CLLocationCoordinate2D(latitude: group.latitude, longitude: group.longitude),
                                          radius: min(group.radius, location.maximumRegionMonitoringDistance), identifier: group.id)
            region.notifyOnEntry = true
            region.notifyOnExit = true
            location.startMonitoring(for: region)
        }
        monitorSignature = signature
    }

    private func updatePermission() {
        switch location.authorizationStatus {
        case .authorizedAlways: locationPermission = "Always allowed"
        case .authorizedWhenInUse: locationPermission = "While using app"
        case .denied, .restricted: locationPermission = "Denied — enable in Settings"
        default: locationPermission = "Not requested"
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        updatePermission()
        if tracking { startTracking() }
    }
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard tracking, !simulation, let fix = locations.last, fix.horizontalAccuracy >= 0,
              abs(fix.timestamp.timeIntervalSinceNow) < 120, Date().timeIntervalSince1970-lastFix > 3 else { return }
        lastFix = Date().timeIntervalSince1970
        enqueue(LocationReport(latitude: fix.coordinate.latitude, longitude: fix.coordinate.longitude, accuracy: fix.horizontalAccuracy,
                               observedAt: fix.timestamp.timeIntervalSince1970, requestId: UUID().uuidString, simulated: false, groupId: nil))
        Task {
            await flush()
            if backgroundTask != .invalid { UIApplication.shared.endBackgroundTask(backgroundTask); backgroundTask = .invalid }
        }
    }
    func locationManager(_ manager: CLLocationManager, didExitRegion region: CLRegion) { requestRegionFix() }
    func locationManager(_ manager: CLLocationManager, didEnterRegion region: CLRegion) { requestRegionFix() }
    private func requestRegionFix() {
        guard tracking, !simulation else { return }
        lastFix = 0
        if backgroundTask == .invalid {
            backgroundTask = UIApplication.shared.beginBackgroundTask { [weak self] in
                guard let self, self.backgroundTask != .invalid else { return }
                UIApplication.shared.endBackgroundTask(self.backgroundTask)
                self.backgroundTask = .invalid
            }
        }
        location.requestLocation()
    }
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        self.error = error.localizedDescription
        if backgroundTask != .invalid { UIApplication.shared.endBackgroundTask(backgroundTask); backgroundTask = .invalid }
    }
}
