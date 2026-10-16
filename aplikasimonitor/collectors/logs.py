"""Stream log journald sebagai async generator (untuk SSE)."""
from __future__ import annotations

import asyncio
import json
import shutil
from typing import AsyncIterator, Optional

PRIORITY_NAMES = {
    "0": "emerg",
    "1": "alert",
    "2": "crit",
    "3": "err",
    "4": "warning",
    "5": "notice",
    "6": "info",
    "7": "debug",
}


async def journal_stream(
    unit: Optional[str] = None,
    lines: int = 50,
    priority: Optional[str] = None,
) -> AsyncIterator[dict]:
    if not shutil.which("journalctl"):
        yield {"error": "journalctl tidak tersedia"}
        return

    args = [
        "journalctl", "-f", "-o", "json", "--no-pager",
        "-n", str(max(0, min(lines, 1000))),
    ]
    if unit:
        args += ["-u", unit]
    if priority:
        args += ["-p", priority]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        assert proc.stdout is not None
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = event.get("MESSAGE")
            if not isinstance(message, str):
                message = str(message)

            prio = str(event.get("PRIORITY", "6"))
            yield {
                "ts": event.get("__REALTIME_TIMESTAMP"),
                "unit": event.get("_SYSTEMD_UNIT")
                or event.get("SYSLOG_IDENTIFIER")
                or event.get("_COMM"),
                "pid": event.get("_PID"),
                "priority": prio,
                "level": PRIORITY_NAMES.get(prio, "info"),
                "message": message,
            }
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
