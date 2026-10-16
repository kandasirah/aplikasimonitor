"""Daftar port yang mendengarkan, dari `ss -tulpnH`."""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Dict, List

_PROTO = {"tcp": "TCP", "udp": "UDP", "tcp6": "TCP6", "udp6": "UDP6"}
_PROC_RE = re.compile(r'\("([^"]+)",pid=(\d+)')


def read_ports() -> Dict[str, Any]:
    if not shutil.which("ss"):
        return {"available": False, "error": "ss tidak tersedia", "ports": []}

    try:
        proc = subprocess.run(
            ["ss", "-tulpnH"], capture_output=True, text=True, timeout=5
        )
    except subprocess.SubprocessError as exc:
        return {"available": False, "error": str(exc), "ports": []}

    ports: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 5:
            continue
        netid, state, _recv, _send, local = parts[:5]
        process_field = parts[6] if len(parts) > 6 else ""

        address, _, port = local.rpartition(":")
        if not address:
            address = local

        # ss menempelkan scope interface (mis. `127.0.0.53%lo`); buang sebelum cek.
        bare = address.split("%", 1)[0]
        is_loopback = bare.startswith("127.") or bare in ("::1", "[::1]", "localhost")

        processes = [
            {"name": name, "pid": int(pid)}
            for name, pid in _PROC_RE.findall(process_field)
        ]

        ports.append(
            {
                "proto": _PROTO.get(netid, netid.upper()),
                "state": state,
                "address": address,
                "port": int(port) if port.isdigit() else 0,
                "raw_port": port,
                "processes": processes,
                "exposed": not is_loopback,
            }
        )

    ports.sort(key=lambda p: (p["port"], p["proto"]))
    return {"available": True, "ports": ports}
