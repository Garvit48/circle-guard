import SwiftUI
import MapKit

struct ContentView: View {
    @EnvironmentObject var store: AppStore
    @State private var displayName = ""
    @State private var showingCreate = false
    @State private var showingJoin = false
    @State private var invite = ""
    @State private var leaving: TrackingGroup?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack {
                        Image(systemName: "location.circle.fill").font(.system(size: 44)).foregroundStyle(.teal)
                        VStack(alignment: .leading) {
                            Text("Stay in the circle.").font(.title2.bold())
                            Text("A little space. A little peace of mind.").font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    if store.profile == nil { connection }
                    else { dashboard }
                }.padding(20)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("CircleGuard")
            .toolbar {
                if store.profile != nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button("Create a group", systemImage: "plus.circle") { showingCreate = true }
                            Button("Join with a code", systemImage: "person.badge.plus") { showingJoin = true }
                            Button("Enable notifications", systemImage: "bell") { Task { await store.enableNotifications() } }
                        } label: { Image(systemName: "plus.circle.fill").font(.title2) }
                    }
                }
            }
            .sheet(isPresented: $showingCreate) { CreateGroupView().environmentObject(store) }
            .alert("Join a circle", isPresented: $showingJoin) {
                TextField("10-character invite code", text: $invite).textInputAutocapitalization(.characters)
                Button("Join") { Task { await store.join(code: invite) } }
                Button("Cancel", role: .cancel) {}
            } message: { Text("Ask a group member for their invite code.") }
            .alert("Something needs attention", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) {
                Button("OK") { store.error = nil }
            } message: { Text(store.error ?? "") }
            .confirmationDialog("Leave \(leaving?.name ?? "group")?", isPresented: Binding(get: { leaving != nil }, set: { if !$0 { leaving = nil } }), titleVisibility: .visible) {
                Button("Leave group", role: .destructive) { if let group = leaving { Task { await store.leave(group) } }; leaving = nil }
            }
        }
    }

    private var connection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Your circle starts here").font(.title3.bold())
            Text("Connect everyone to the same relay. Your profile is saved securely on this device.").foregroundStyle(.secondary)
            TextField("Your name", text: $displayName).textFieldStyle(.roundedBorder).accessibilityIdentifier("profileName")
            TextField("Relay URL", text: $store.serverURL).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(.roundedBorder).accessibilityIdentifier("relayURL")
            Text("Simulator: http://127.0.0.1:8787\nPhysical phone: use your Mac’s LAN IP.").font(.caption).foregroundStyle(.secondary)
            Button { Task { await store.connect(name: displayName) } } label: {
                HStack { Spacer(); if store.busy { ProgressView() }; Text("Connect & continue"); Spacer() }
            }.buttonStyle(.borderedProminent).disabled(store.busy || displayName.trimmingCharacters(in: .whitespaces).isEmpty).accessibilityIdentifier("connect")
        }.padding(20).background(.background, in: RoundedRectangle(cornerRadius: 20))
    }

    private var dashboard: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Hello, \(store.profile?.name ?? "")").font(.headline)
                    Text(store.status).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if store.pendingCount > 0 { Text("\(store.pendingCount) queued").font(.caption).foregroundStyle(.orange) }
            }
            if store.groups.isEmpty {
                VStack(spacing: 14) {
                    Image(systemName: "person.3.sequence.fill").font(.system(size: 40)).foregroundStyle(.teal)
                    Text("Good company. Shared boundaries.").font(.headline)
                    Text("Create a circle, set a safe area, and invite someone to try an exit alert.").multilineTextAlignment(.center).foregroundStyle(.secondary)
                    Button("Create a group") { showingCreate = true }.buttonStyle(.borderedProminent).accessibilityIdentifier("createGroup")
                    Button("Join an existing group") { showingJoin = true }
                }.frame(maxWidth: .infinity).padding(24).background(.background, in: RoundedRectangle(cornerRadius: 20))
            }
            if let group = store.selected {
                if store.groups.count > 1 {
                    Picker("Circle", selection: $store.selectedID) {
                        ForEach(store.groups) { Text($0.name).tag($0.id) }
                    }.pickerStyle(.menu)
                }
                groupCard(group)
                simulationCard
                membersCard(group)
            }
            activityCard
            Text("Only inside → outside transitions alert other members. An initial outside fix does not send an alert. Boundary accuracy is accounted for.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private func groupCard(_ group: TrackingGroup) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(group.name).font(.title2.bold())
                    Text("\(Int(group.radius)) m safe area · \(group.members.count) members").font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    ShareLink(item: group.code) { Label("Share invite code", systemImage: "square.and.arrow.up") }
                    Button("Leave group", role: .destructive) { leaving = group }
                } label: { Image(systemName: "ellipsis.circle").font(.title2) }
            }
            Map(initialPosition: .region(MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: group.latitude, longitude: group.longitude),
                latitudinalMeters: group.radius * 3.5, longitudinalMeters: group.radius * 3.5)), interactionModes: []) {
                MapCircle(center: CLLocationCoordinate2D(latitude: group.latitude, longitude: group.longitude), radius: group.radius)
                    .foregroundStyle(.teal.opacity(0.17)).stroke(.teal, lineWidth: 2)
                Annotation("Safe area", coordinate: CLLocationCoordinate2D(latitude: group.latitude, longitude: group.longitude)) {
                    Image(systemName: "house.fill").padding(10).foregroundStyle(.white).background(.teal, in: Circle())
                }
            }.id("\(group.id):\(group.version)").frame(height: 210).clipShape(RoundedRectangle(cornerRadius: 14))
            HStack {
                Text("INVITE").font(.caption2.bold()).foregroundStyle(.secondary)
                Text(group.code).font(.system(.body, design: .monospaced).bold()).textSelection(.enabled).accessibilityIdentifier("inviteCode")
                Spacer()
                Button { UIPasteboard.general.string = group.code } label: { Image(systemName: "doc.on.doc") }.accessibilityLabel("Copy invite code")
            }
        }.padding(18).background(.background, in: RoundedRectangle(cornerRadius: 20))
    }

    private var simulationCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Toggle(isOn: Binding(get: { store.simulation }, set: { store.setSimulation($0) })) {
                Label("Location test lab", systemImage: "testtube.2").font(.headline)
            }.accessibilityIdentifier("simulationToggle")
            if store.simulation {
                Text("GPS is paused. Send an inside fix, then an outside fix. Other members receive a [TEST] exit alert.").font(.subheadline).foregroundStyle(.secondary)
                HStack {
                    Button { Task { await store.simulate(outside: false) } } label: { Label("Move inside", systemImage: "arrow.down.right.circle") }
                        .buttonStyle(.bordered).accessibilityIdentifier("moveInside")
                    Button { Task { await store.simulate(outside: true) } } label: { Label("Move outside", systemImage: "arrow.up.right.circle") }
                        .buttonStyle(.borderedProminent).accessibilityIdentifier("moveOutside")
                }
                Text("Re-enter to re-arm. Staying outside sends no extra alerts.").font(.caption).foregroundStyle(.secondary)
            } else {
                Text("Location: \(store.locationPermission)").font(.subheadline)
                Button(store.tracking ? "Stop location sharing" : "Start location sharing") { store.tracking ? store.stopTracking() : store.startTracking() }
                    .buttonStyle(.borderedProminent)
                Button("Allow Always location access") { store.requestAlways() }.font(.subheadline)
                Text("Background sharing uses iOS location services. Keep the relay reachable. Apple push is needed to alert other suspended iPhones.").font(.caption).foregroundStyle(.secondary)
            }
        }.padding(18).background(Color.teal.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
    }

    private func membersCard(_ group: TrackingGroup) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("In your circle").font(.headline)
            ForEach(group.members) { member in
                HStack(spacing: 12) {
                    Text(String(member.name.prefix(1)).uppercased()).font(.headline).frame(width: 38, height: 38).background(.teal.opacity(0.1), in: Circle())
                    VStack(alignment: .leading, spacing: 3) {
                        Text(member.name + (member.id == store.profile?.id ? " (you)" : "")).font(.subheadline.bold())
                        if member.updatedAt > 0 {
                            Text(Date(timeIntervalSince1970: member.updatedAt), style: .relative).font(.caption).foregroundStyle(.secondary)
                        } else { Text("Waiting for first location").font(.caption).foregroundStyle(.secondary) }
                    }
                    Spacer()
                    VStack(alignment: .trailing) {
                        Text(member.state.capitalized).font(.caption.bold()).foregroundStyle(member.state == "outside" ? .orange : .secondary)
                        if member.mode == "simulation" { Text("TEST").font(.caption2).foregroundStyle(.teal) }
                    }
                }
            }
        }.padding(18).background(.background, in: RoundedRectangle(cornerRadius: 20))
    }

    private var activityCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Activity", systemImage: "bell.badge").font(.headline)
            if store.events.isEmpty {
                Text("All quiet. Exits by other members will appear here.").font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(store.events.prefix(20)) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.title).font(.subheadline.bold()).foregroundStyle(.orange)
                    Text(event.body).font(.subheadline)
                    Text(Date(timeIntervalSince1970: event.createdAt), style: .time).font(.caption).foregroundStyle(.secondary)
                }
                Divider()
            }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(18).background(.background, in: RoundedRectangle(cornerRadius: 20))
    }
}

struct CreateGroupView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var name = "My circle"
    @State private var latitude = "37.3349"
    @State private var longitude = "-122.0090"
    @State private var radius = 500.0
    var body: some View {
        NavigationStack {
            Form {
                Section("Your group") { TextField("Group name", text: $name).accessibilityIdentifier("groupName") }
                Section("Geofence center") {
                    TextField("Latitude", text: $latitude).keyboardType(.numbersAndPunctuation)
                    TextField("Longitude", text: $longitude).keyboardType(.numbersAndPunctuation)
                    Text("Default: Apple Park. Coordinates make testing anywhere easy.").font(.caption)
                }
                Section("Radius: \(Int(radius)) metres") { Slider(value: $radius, in: 100...10000, step: 100) }
                Section {
                    Button("Create circle") {
                        Task {
                            guard let lat = Double(latitude), let lon = Double(longitude) else { store.error = "Enter numeric coordinates."; return }
                            await store.createGroup(name: name, latitude: lat, longitude: lon, radius: radius)
                            if store.error == nil { dismiss() }
                        }
                    }.disabled(store.busy || name.trimmingCharacters(in: .whitespaces).isEmpty).accessibilityIdentifier("saveGroup")
                }
            }.navigationTitle("New circle").toolbar { Button("Cancel") { dismiss() } }
        }
    }
}
