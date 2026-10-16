#!/usr/bin/env bash
# Jalankan server dasbor.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/aplikasimonitor ]; then
  echo "Paket belum terpasang. Jalankan ./setup.sh dulu." >&2
  exit 1
fi

exec .venv/bin/aplikasimonitor \
  --host "${MONITOR_HOST:-127.0.0.1}" \
  --port "${MONITOR_PORT:-8787}" \
  "$@"
