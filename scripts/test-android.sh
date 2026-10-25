#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$ROOT"
curl -fsS http://127.0.0.1:8787/health >/dev/null
adb wait-for-device
# Run on the dedicated CircleGuard emulator: instrumentation expects a fresh profile.
adb shell pm clear app.circleguard.android || true
./gradlew :androidApp:connectedDebugAndroidTest
