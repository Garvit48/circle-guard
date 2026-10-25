#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m unittest discover -s server -v
./gradlew :shared:jvmTest :shared:linkDebugFrameworkIosSimulatorArm64 :androidApp:assembleDebug :androidApp:lintDebug
xcodebuild -quiet -project iosApp/CircleGuard.xcodeproj -scheme CircleGuard -configuration Debug -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath .tools/xcode-derived build
