#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/scripts/env.sh"
cd "$ROOT"
if [ ! -x "$ROOT/.tools/gradle-8.11.1/bin/gradle" ]; then
  echo 'Run python3 scripts/bootstrap.py first.' >&2
  exit 1
fi
exec "$ROOT/.tools/gradle-8.11.1/bin/gradle" "$@"
