#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$ROOT"
DEVICE="${1:-$(xcrun simctl list devices available -j | python3 -c 'import json,sys; print(next(d["udid"] for ds in json.load(sys.stdin)["devices"].values() for d in ds if "iPhone" in d["name"]))')}"
xcodebuild -quiet -project iosApp/CircleGuard.xcodeproj -scheme CircleGuard -configuration Debug -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath .tools/xcode-derived build
xcrun simctl boot "$DEVICE" 2>/dev/null || true
xcrun simctl bootstatus "$DEVICE" -b
xcrun simctl install "$DEVICE" .tools/xcode-derived/Build/Products/Debug-iphonesimulator/CircleGuard.app
xcrun simctl launch "$DEVICE" app.circleguard.ios
DEVELOPER="$(xcode-select -p)"
if [ -d "$DEVELOPER/Applications/Simulator.app" ]; then
  open -a "$DEVELOPER/Applications/Simulator.app"
else
  open -a "$DEVELOPER/../Applications/DeviceHub.app"
fi
