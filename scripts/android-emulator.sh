#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$ROOT"
mkdir -p "$ANDROID_AVD_HOME"
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" emulator 'system-images;android-35;google_apis;arm64-v8a'
if [ ! -f "$ANDROID_AVD_HOME/CircleGuard.ini" ]; then
  echo no | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" create avd --name CircleGuard \
    --package 'system-images;android-35;google_apis;arm64-v8a' --device pixel_7
fi
exec "$ANDROID_HOME/emulator/emulator" -avd CircleGuard -no-snapshot -no-boot-anim "$@"
