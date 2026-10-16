"""Informasi statis/umum tentang host."""
from __future__ import annotations

import platform
import socket
import time
from pathlib import Path
from typing import Any, Dict

import psutil


def _os_release() -> Dict[str, str]:
    data: Dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"')
    return data


def host_info() -> Dict[str, Any]:
    osr = _os_release()
    boot = psutil.boot_time()
    return {
        "hostname": socket.gethostname(),
        "os": osr.get("PRETTY_NAME", platform.platform()),
        "os_id": osr.get("ID", ""),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "boot_time": boot,
        "uptime": max(0.0, time.time() - boot),
    }
