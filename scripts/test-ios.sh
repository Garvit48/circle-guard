#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
curl -fsS http://127.0.0.1:8787/health >/dev/null
DEVICE="${1:-$(xcrun simctl list devices available -j | python3 -c 'import json,sys; print(next(d["udid"] for ds in json.load(sys.stdin)["devices"].values() for d in ds if "iPhone" in d["name"]))')}"
xcodebuild -project iosApp/CircleGuard.xcodeproj -scheme CircleGuard -configuration Debug \
  -destination "platform=iOS Simulator,id=$DEVICE" -derivedDataPath .tools/xcode-derived \
  -resultBundlePath ".tools/ios-ui-$(date +%Y%m%d-%H%M%S).xcresult" -parallel-testing-enabled NO test
