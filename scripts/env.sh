#!/bin/bash
if [ -n "${BASH_VERSION:-}" ]; then
  ENV_SCRIPT="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  ENV_SCRIPT="${(%):-%x}"
else
  echo 'Source scripts/env.sh from bash or zsh.' >&2
  return 1
fi
ROOT="$(cd "$(dirname "$ENV_SCRIPT")/.." && pwd)"
export JAVA_HOME="$ROOT/.tools/jdk/Contents/Home"
export ANDROID_HOME="$ROOT/.tools/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export ANDROID_USER_HOME="$ROOT/.tools/android-user"
export ANDROID_AVD_HOME="$ROOT/.tools/android-avd"
export GRADLE_USER_HOME="$ROOT/.gradle"
export KONAN_DATA_DIR="$ROOT/.tools/konan"
export PIP_CACHE_DIR="$ROOT/.tools/pip-cache"
export PATH="$JAVA_HOME/bin:$ROOT/.tools/gradle-8.11.1/bin:$ANDROID_HOME/platform-tools:$PATH"
