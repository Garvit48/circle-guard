# CircleGuard

A local-first group geofencing app: **Kotlin Multiplatform shared logic, SwiftUI iOS, Kotlin/Compose Android**, and a small local Python/SQLite relay.

Create a group, choose a circular geofence, share its invite code, and receive an alert when another member goes from inside to outside. Both apps include a **Location test lab** with fake-location buttons that exercise the real relay and notification flow.

## Quick start on this Mac

```bash
cd ~/projects/CircleGuard
python3 scripts/bootstrap.py     # Already completed on this machine
./scripts/run-relay.sh
```

In a second terminal:

```bash
cd ~/projects/CircleGuard
./scripts/run-ios.sh
```

Or open `iosApp/CircleGuard.xcodeproj` in Xcode, choose **CircleGuard**, select an iPhone simulator, and Run. Xcode builds the shared Kotlin framework automatically. The launcher supports both Simulator.app and Xcode 27’s DeviceHub.

For Android:

```bash
./scripts/android-emulator.sh    # Separate terminal; first run downloads the local emulator image
./scripts/run-android.sh         # Another terminal, after the emulator boots
```

The Android APK is at `androidApp/build/outputs/apk/debug/androidApp-debug.apk`.

### Relay addresses

| Client | URL |
| --- | --- |
| iOS simulator | `http://127.0.0.1:8787` |
| Android emulator | `http://10.0.2.2:8787` |
| Physical phone on the same Wi-Fi | `http://YOUR_MAC_LAN_IP:8787` |

For physical devices, start the relay with `./scripts/run-relay.sh --host 0.0.0.0`, allow incoming connections if macOS asks, and use the same LAN address on both phones. The relay’s default bind is loopback. Xcode device builds also need your signing team.

## Test the alerts without moving

1. Open two app instances (iOS + Android, or two different iOS simulators). Give each a different name.
2. On the first device, **Create group**. The default is a 500 m circle at Apple Park; coordinates and radius are editable before creation.
3. Copy its 10-character invite code. On the second device, **Join group** with that code.
4. Allow notifications. Keep the receiving app open for a fully local test.
5. On the first device, leave **Location test lab** enabled. Tap **Move inside**, then **Move outside**.
6. The second device receives **[TEST] Geofence exit**, and its Activity feed names the member who left. The sender does not receive their own alert.
7. Tap **Move outside** again: no duplicate alert. Tap **Move inside**, then **Move outside** to trigger another.

The buttons use the shared Kotlin spherical-coordinate calculation and send simulated fixes through the same authenticated `/locations` endpoint as GPS. Simulation pauses GPS, is labeled in member status and alerts, and is available on physical phones without mock-location permissions. Switching between GPS and simulation resets that member’s baseline on the next fix.

### One phone + a command-line walker

```bash
.venv/bin/python scripts/demo.py
```

Join the displayed invite code in the app, then press Enter in the terminal. The script creates two independent users, sends an inside/outside/outside sequence, and verifies exactly one recipient event.

### Test the actual OS location path

Disable the test lab, tap **Start location sharing**, and grant precise location access. For the default Apple Park fence:

```bash
# iOS simulator: use a specific simulator UUID instead of booted if several are running
xcrun simctl location booted set 37.3349,-122.0090
# Wait for the app to show Inside, then:
xcrun simctl location booted set 37.3349,-121.9900

# Android emulator (longitude first)
source scripts/env.sh
adb emu geo fix -122.0090 37.3349
# Wait for Inside, then:
adb emu geo fix -121.9900 37.3349
```

Xcode can also use `iosApp/Locations/Inside.gpx` and `Outside.gpx` via Debug → Simulate Location. OS region callbacks are asynchronous; the built-in test lab is the deterministic test path.

## Notifications and background behavior

**All local:** the relay stores recipient events, and open apps poll every 3 seconds, showing an OS local notification plus a persistent Activity entry. Android also polls while its explicitly started location foreground service is running; the ongoing notification has a Stop action. Android battery/Doze policies can delay background delivery.

**iOS background:** Core Location handles GPS and up to 20 monitored regions. Enable Always access for background region monitoring; the app provides an access request button. Sharing can be stopped explicitly. iOS may delay location callbacks, and force-quitting can prevent background relaunch. An unreachable relay queues up to 500 fixes on-device for retry; fixes older than 24 hours are discarded with an error.

**Alerting a suspended receiving iPhone requires APNs.** A local relay cannot wake an arbitrary suspended app by polling. The optional APNs worker sends visible alerts using your own Apple credentials; no Firebase account is required. Without APNs, received events are shown when the app resumes.

### Optional Apple push setup

1. Use an Apple Developer account and enable Push Notifications for `app.circleguard.ios` (or your own bundle ID).
2. In Xcode’s Signing & Capabilities, choose your team and add Push Notifications. `iosApp/CircleGuard/Push.entitlements` is provided as a development template; it is deliberately not attached to local simulator builds. Set the app target’s Code Signing Entitlements to this file for a signed development device build. Distribution signing needs the production APNs entitlement. Local simulator builds use automatic ad-hoc signing so Keychain storage works.
3. Install optional packages only in the existing project venv:

   ```bash
   .venv/bin/pip install -r server/requirements-push.txt
   ```

4. Set these in the relay terminal (keep the `.p8` key private):

   ```bash
   export APNS_KEY_PATH="$PWD/.data/AuthKey_YOUR_KEY_ID.p8"
   export APNS_KEY_ID="YOUR_KEY_ID"
   export APNS_TEAM_ID="YOUR_TEAM_ID"
   export APNS_TOPIC="app.circleguard.ios"
   ./scripts/run-relay.sh --host 0.0.0.0
   ```

5. Install the signed app, allow notifications, and connect it to the relay. Status reads **Apple push enabled** after device registration. Debug builds register sandbox tokens; Release builds register production tokens. The relay needs outbound HTTPS to Apple.

APNs uses HTTP/2, ES256 authentication, retry backoff, invalid-token cleanup, and a 24-hour event expiry. Physical-device background delivery and Apple credential provisioning need validation with your account; they are not covered by local simulator tests.

## Verification

```bash
./scripts/check.sh             # Python integration tests, KMP tests, Android APK/lint, iOS build

# With the local relay running:
./scripts/test-ios.sh          # XCUITest: native profile/group UI + another member’s simulated exit
./scripts/test-android.sh      # Dedicated emulator only: clears app data, then two-way alert test
```

Tests cover:
- Five shared Kotlin tests: known distances, invalid coordinates, boundary jitter/accuracy, transitions, and simulation near poles/date line.
- Eight real HTTP/SQLite integration tests: membership/auth, recipient-only events, duplicates, re-entry, stale fixes, source changes, fence updates, and leaving.
- iOS UI automation creating a group and showing another member’s simulated exit in Activity.
- Android UI automation sending fake locations to another user, asserting one alert, then receiving a reverse-direction alert in the native Activity feed.

Reports live under `shared/build/test-results`, `androidApp/build/reports`, and `.tools/*.xcresult`.

## Project structure

```text
shared/       Kotlin Multiplatform distance, validation, hysteresis, simulation + tests
iosApp/       SwiftUI, MapKit, Core Location, Keychain, local/APNs notifications
androidApp/   Compose, Android LocationManager, foreground service, local notifications
server/       Authenticated local HTTP relay, SQLite, optional APNs worker + tests
scripts/      Local bootstrap, build/run/test helpers, two-user demo
.tools/       Project-local JDK, Gradle, Android SDK/AVD, Kotlin/Native, Xcode build output
.venv/        Project-local Python environment
.gradle/      Project-local Gradle caches
.data/        Runtime SQLite database and logs (ignored)
```

The server mirrors the shared geofence mathematics and is authoritative for transitions, so retrying a location cannot send duplicate alerts. It does not store a trail of precise coordinates: group centers, member distance/status/source/last-update, request IDs, and recipient events are persisted. Names and session credentials are saved on-device (iOS Keychain; Android app-private storage with backup disabled). Each installation has an independent profile; account recovery and multi-device sign-in are outside this local prototype.

The relay is a **local development service**, with cleartext HTTP enabled in both apps to reach it. For internet deployment, use HTTPS, restrict transport exceptions, add account lifecycle/abuse controls, and deploy the relay somewhere all phones can reach. Real-time sharing across separate devices requires that shared network service even though the geofence math runs locally.

### Tool isolation

Bootstrap uses the already-installed Python, curl, and Xcode. Java 17, Gradle 8.11.1, Android tools, Kotlin/Native dependencies, build caches, and the Python venv stay inside this checkout. No Homebrew installs, global pip packages, or shell-profile edits are needed. Android SDK licenses are accepted by bootstrap. Apple’s already-installed simulator service manages its runtime data in its standard system location. The Android emulator helper targets Apple Silicon Macs.
# circle-guard
