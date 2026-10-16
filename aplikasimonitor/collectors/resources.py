"""CPU, memori, disk, jaringan, baterai, suhu, dan fan."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import psutil

_prev_net = None
_prev_net_ts: Optional[float] = None


def _safe(fn: Callable, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - sensor bisa hilang kapan saja
        return default


def read_battery() -> Optional[Dict[str, Any]]:
    battery = _safe(psutil.sensors_battery)
    if battery is None:
        return None
    secs = battery.secsleft
    if secs in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) or secs < 0:
        secs = None
    return {
        "percent": round(battery.percent, 1),
        "plugged": bool(battery.power_plugged),
        "secsleft": secs,
    }


def read_temperatures() -> List[Dict[str, Any]]:
    temps = _safe(psutil.sensors_temperatures)
    if not temps:
        return []
    out = []
    for chip, entries in temps.items():
        for entry in entries:
            out.append(
                {
                    "chip": chip,
                    "label": entry.label or chip,
                    "current": entry.current,
                    "high": entry.high,
                    "critical": entry.critical,
                }
            )
    out.sort(key=lambda t: (t["current"] is None, -(t["current"] or 0)))
    return out


def read_fans() -> List[Dict[str, Any]]:
    fans = _safe(psutil.sensors_fans)
    if not fans:
        return []
    out = []
    for chip, entries in fans.items():
        for entry in entries:
            out.append({"chip": chip, "label": entry.label or chip, "rpm": entry.current})
    return out


def read_disks() -> List[Dict[str, Any]]:
    disks = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype in ("", "squashfs", "tmpfs", "devtmpfs", "overlay", "ramfs"):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append(
            {
                "device": part.device,
                "mount": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        )
    disks.sort(key=lambda d: d["mount"])
    return disks


def read_resources() -> Dict[str, Any]:
    global _prev_net, _prev_net_ts
    now = time.time()

    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    net = psutil.net_io_counters()

    up_bps = down_bps = 0.0
    if _prev_net is not None and _prev_net_ts is not None:
        delta = max(now - _prev_net_ts, 1e-6)
        up_bps = max(0.0, (net.bytes_sent - _prev_net.bytes_sent) / delta)
        down_bps = max(0.0, (net.bytes_recv - _prev_net.bytes_recv) / delta)
    _prev_net, _prev_net_ts = net, now

    freq = _safe(psutil.cpu_freq)
    load = _safe(psutil.getloadavg, (0.0, 0.0, 0.0))

    return {
        "ts": now,
        "cpu": {
            "percent": psutil.cpu_percent(interval=None),
            "per_cpu": psutil.cpu_percent(interval=None, percpu=True),
            "count": psutil.cpu_count(logical=True),
            "freq_mhz": round(freq.current) if freq else None,
            "load": [round(value, 2) for value in load],
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
        },
        "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
        "disk": read_disks(),
        "network": {
            "up_bps": up_bps,
            "down_bps": down_bps,
            "sent": net.bytes_sent,
            "recv": net.bytes_recv,
        },
        "battery": read_battery(),
        "temperatures": read_temperatures(),
        "fans": read_fans(),
        "boot_time": psutil.boot_time(),
    }
