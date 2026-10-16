"""Daftar service systemd."""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict

from .. import config, service_control

# Urutan tampil: yang jalan dulu, lalu keluar normal, lalu gagal, lalu sisanya.
_SUB_ORDER = {"running": 0, "exited": 1, "failed": 2}


def list_services() -> Dict[str, Any]:
    if not shutil.which("systemctl"):
        return {"available": False, "error": "systemctl tidak tersedia", "services": []}

    try:
        proc = subprocess.run(
            [
                "systemctl", "list-units", "--type=service", "--all",
                "--no-pager", "--no-legend", "--output=json",
            ],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(proc.stdout or "[]")
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"available": False, "error": str(exc), "services": []}

    services = [
        {
            "unit": unit.get("unit"),
            "load": unit.get("load"),
            "active": unit.get("active"),
            "sub": unit.get("sub"),
            "description": unit.get("description"),
        }
        for unit in data
    ]
    services.sort(
        key=lambda s: (
            _SUB_ORDER.get(s["sub"], 3),
            s["active"] != "active",
            s["unit"] or "",
        )
    )

    return {
        "available": True,
        "control_enabled": config.ENABLE_SERVICE_CONTROL,
        "control_backend": service_control.active_backend(),
        "total": len(services),
        "running": sum(1 for s in services if s["sub"] == "running"),
        "failed": sum(1 for s in services if s["sub"] == "failed"),
        "services": services,
    }
