"""Penyimpanan: pemakaian partisi (termasuk inode) dan aktivitas I/O per disk.

Memakai psutil + os.statvfs saja; tanpa dependensi maupun hak istimewa tambahan.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import psutil

# Filesystem virtual/pseudo yang tidak relevan bagi pengguna.
_PSEUDO_FS = {
    "", "autofs", "binfmt_misc", "bpf", "cgroup", "cgroup2", "configfs",
    "debugfs", "devpts", "devtmpfs", "fusectl", "mqueue", "nsfs", "overlay",
    "proc", "pstore", "ramfs", "rpc_pipefs", "securityfs", "squashfs",
    "sysfs", "tmpfs", "tracefs",
}

# Snapshot I/O sebelumnya untuk menghitung laju.
_prev_io: Optional[Dict[str, Any]] = None
_prev_io_ts: Optional[float] = None

# Perangkat yang bukan disk fisik (loop, RAM disk, optical, LVM mapper).
_SKIP_PREFIX = ("loop", "ram", "zram", "sr", "dm-", "fd", "md")


def _whole_disks() -> Optional[Set[str]]:
    """Nama disk utuh dari /sys/block (tanpa partisi). None bila tidak tersedia."""
    try:
        return {entry.name for entry in Path("/sys/block").iterdir()}
    except OSError:
        return None


def _inodes(mount: str) -> Optional[Dict[str, Any]]:
    """Pemakaian inode; None bila filesystem tidak melaporkannya (mis. btrfs)."""
    try:
        st = os.statvfs(mount)
    except OSError:
        return None
    total = st.f_files
    if not total:
        return None
    used = total - st.f_ffree
    return {
        "total": total,
        "used": used,
        "free": st.f_ffree,
        "percent": round(used / total * 100, 1),
    }


def read_partitions() -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype in _PSEUDO_FS:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        parts.append(
            {
                "device": part.device,
                "mount": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
                "inodes": _inodes(part.mountpoint),
            }
        )
    # Root dulu, lalu urut nama mount.
    parts.sort(key=lambda d: (d["mount"] != "/", d["mount"]))
    return parts


def read_disk_io() -> Dict[str, Any]:
    """Laju baca/tulis per disk fisik, dihitung dari selisih dua sampel."""
    global _prev_io, _prev_io_ts
    now = time.time()
    counters = psutil.disk_io_counters(perdisk=True) or {}
    whole = _whole_disks()

    disks: List[Dict[str, Any]] = []
    for name, cur in counters.items():
        if name.startswith(_SKIP_PREFIX):
            continue
        if whole is not None and name not in whole:
            continue  # hanya disk utuh, bukan partisi (mis. sda1)
        entry = {
            "name": name,
            "read_bytes": cur.read_bytes,
            "write_bytes": cur.write_bytes,
            "read_bps": 0.0,
            "write_bps": 0.0,
            "read_iops": 0.0,
            "write_iops": 0.0,
            "busy_percent": None,
        }
        prev = _prev_io.get(name) if _prev_io else None
        if prev is not None and _prev_io_ts is not None:
            dt = max(now - _prev_io_ts, 1e-6)
            entry["read_bps"] = max(0.0, (cur.read_bytes - prev.read_bytes) / dt)
            entry["write_bps"] = max(0.0, (cur.write_bytes - prev.write_bytes) / dt)
            entry["read_iops"] = max(0.0, (cur.read_count - prev.read_count) / dt)
            entry["write_iops"] = max(0.0, (cur.write_count - prev.write_count) / dt)
            busy = getattr(cur, "busy_time", None)
            busy_prev = getattr(prev, "busy_time", None)
            if busy is not None and busy_prev is not None:
                entry["busy_percent"] = min(100.0, max(0.0, (busy - busy_prev) / (dt * 1000) * 100))
        disks.append(entry)

    _prev_io, _prev_io_ts = counters, now

    disks.sort(key=lambda d: -(d["read_bps"] + d["write_bps"]))
    return {
        "disks": disks,
        "total_read_bps": sum(d["read_bps"] for d in disks),
        "total_write_bps": sum(d["write_bps"] for d in disks),
    }


def read_storage() -> Dict[str, Any]:
    return {"partitions": read_partitions(), **read_disk_io()}
