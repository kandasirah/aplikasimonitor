"""Daftar proses via psutil."""
from __future__ import annotations

import time
from typing import Any, Dict

import psutil

_ATTRS = [
    "pid", "name", "username", "status", "cpu_percent",
    "memory_percent", "memory_info", "cmdline", "create_time", "num_threads",
]

_SORTS = {
    "cpu": (lambda p: p["cpu"], True),
    "mem": (lambda p: p["mem"], True),
    "pid": (lambda p: p["pid"], False),
    "name": (lambda p: (p["name"] or "").lower(), False),
}


def _prime() -> None:
    """Panggilan pertama cpu_percent selalu 0; panaskan cache psutil sekali."""
    psutil.cpu_percent(interval=None)
    for _ in psutil.process_iter(["cpu_percent"]):
        pass


_prime()


def list_processes(sort: str = "cpu", limit: int = 50) -> Dict[str, Any]:
    now = time.time()
    limit = max(1, min(limit, 500))
    procs = []

    for proc in psutil.process_iter(_ATTRS):
        try:
            info = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

        memory = info.get("memory_info")
        cmdline = info.get("cmdline") or []
        created = info.get("create_time") or now

        procs.append(
            {
                "pid": info.get("pid"),
                "name": info.get("name") or "?",
                "user": info.get("username") or "?",
                "status": info.get("status") or "?",
                "cpu": round(info.get("cpu_percent") or 0.0, 1),
                "mem": round(info.get("memory_percent") or 0.0, 1),
                "mem_mb": round((memory.rss / 1048576.0) if memory else 0.0, 1),
                "threads": info.get("num_threads") or 0,
                "cmd": " ".join(cmdline) if cmdline else (info.get("name") or ""),
                "age": round(now - created, 1),
            }
        )

    key, reverse = _SORTS.get(sort, _SORTS["cpu"])
    procs.sort(key=key, reverse=reverse)

    return {"total": len(procs), "sort": sort, "processes": procs[:limit]}
