"""Baca sensor lengkap dari lm-sensors (`sensors -j`).

psutil dipakai untuk data suhu/fan ringan di jalur realtime; modul ini untuk
detail lengkap (min/max/crit, label adapter) di halaman sensor.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any, Dict, List

# Prefix nama fitur di lm-sensors -> satuan.
_KIND_UNIT = {
    "temp": "°C",
    "fan": "RPM",
    "in": "V",
    "curr": "A",
    "power": "W",
    "energy": "J",
    "humidity": "%",
}

_KEY_RE = re.compile(r"^([a-z]+)(\d+)_([a-z]+)$")


def read_sensors() -> Dict[str, Any]:
    if not shutil.which("sensors"):
        return {"available": False, "error": "lm-sensors tidak terpasang", "readings": []}

    try:
        proc = subprocess.run(
            ["sensors", "-j"], capture_output=True, text=True, timeout=5
        )
        raw = json.loads(proc.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {"available": False, "error": str(exc), "readings": []}

    readings: List[Dict[str, Any]] = []
    for chip, labels in raw.items():
        if not isinstance(labels, dict):
            continue
        adapter = labels.get("Adapter")
        for label, features in labels.items():
            if label == "Adapter" or not isinstance(features, dict):
                continue
            for key, value in features.items():
                match = _KEY_RE.match(key)
                if not match:
                    continue
                kind, index, attr = match.groups()
                if attr != "input":
                    continue
                readings.append(
                    {
                        "chip": chip,
                        "adapter": adapter,
                        "label": label,
                        "kind": kind,
                        "unit": _KIND_UNIT.get(kind, ""),
                        "value": float(value),
                        "max": features.get(f"{kind}{index}_max"),
                        "crit": features.get(f"{kind}{index}_crit"),
                    }
                )

    readings.sort(key=lambda r: (r["chip"], r["label"], r["kind"]))
    return {"available": True, "readings": readings}
