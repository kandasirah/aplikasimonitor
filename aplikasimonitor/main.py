"""Aplikasi Monitor — API FastAPI + penyaji frontend.

Jalankan: ./run.sh   (atau uvicorn backend.main:app)
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, service_control
from .collectors import logs, ports, processes, resources, sensors, services, system

app = FastAPI(title="Aplikasi Monitor", version="1.0.0")

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


# --------------------------------------------------------------------------- #
# REST
# --------------------------------------------------------------------------- #
@app.get("/api/host")
def api_host():
    return system.host_info()


@app.get("/api/resources")
def api_resources():
    return resources.read_resources()


@app.get("/api/sensors")
def api_sensors():
    return sensors.read_sensors()


@app.get("/api/ports")
def api_ports():
    return ports.read_ports()


@app.get("/api/services")
def api_services():
    return services.list_services()


@app.post("/api/services/{unit}/{action}")
async def api_service_action(unit: str, action: str):
    if not config.ENABLE_SERVICE_CONTROL:
        raise HTTPException(403, "Kontrol service dinonaktifkan (MONITOR_SERVICE_CONTROL=0).")
    try:
        return await service_control.perform(unit, action)
    except service_control.ServiceControlError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@app.get("/api/processes")
def api_processes(
    sort: str = Query("cpu", pattern="^(cpu|mem|pid|name)$"),
    limit: int = Query(50, ge=1, le=500),
):
    return processes.list_processes(sort=sort, limit=limit)


# --------------------------------------------------------------------------- #
# SSE
# --------------------------------------------------------------------------- #
@app.get("/api/stream")
async def api_stream(request: Request):
    """Snapshot resource realtime. Ringan: hanya penghitung psutil, tanpa iterasi
    proses (tabel proses punya endpoint sendiri yang di-poll terpisah)."""
    async def generate():
        while True:
            if await request.is_disconnected():
                break
            payload = {"ts": time.time(), "resources": resources.read_resources()}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(config.STREAM_INTERVAL)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.get("/api/logs/stream")
async def api_logs_stream(
    request: Request,
    unit: str | None = Query(None),
    lines: int = Query(50, ge=0, le=1000),
    priority: str | None = Query(None, pattern="^[0-7]$"),
):
    async def generate():
        async for entry in logs.journal_stream(unit=unit, lines=lines, priority=priority):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(entry)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# --------------------------------------------------------------------------- #
# Frontend statis (harus paling akhir agar tidak menutupi /api/*)
# --------------------------------------------------------------------------- #
app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="static")
