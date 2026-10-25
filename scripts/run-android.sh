#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$ROOT"
./gradlew :androidApp:assembleDebug
adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk
adb shell am start -n app.circleguard.android/.MainActivity
