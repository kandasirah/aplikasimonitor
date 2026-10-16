"""Konfigurasi terpusat, semua bisa dioverride lewat environment variable."""
from __future__ import annotations

import os
from pathlib import Path

# Berkas statis ikut terpasang sebagai package data di aplikasimonitor/static/.
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "static"

HOST = os.getenv("MONITOR_HOST", "127.0.0.1")
PORT = int(os.getenv("MONITOR_PORT", "8787"))

# Interval push snapshot resource lewat SSE (detik).
STREAM_INTERVAL = float(os.getenv("MONITOR_STREAM_INTERVAL", "2"))

# Kontrol service (start/stop/restart).
ENABLE_SERVICE_CONTROL = os.getenv("MONITOR_SERVICE_CONTROL", "1") == "1"
# Jalur kontrol: "auto" (dbus bila tersedia, jika tidak systemctl), "dbus", atau "systemctl".
SERVICE_BACKEND = os.getenv("MONITOR_SERVICE_BACKEND", "auto")
# Hanya untuk jalur systemctl: awali perintah dengan `sudo -n`.
USE_SUDO = os.getenv("MONITOR_SUDO", "0") == "1"
