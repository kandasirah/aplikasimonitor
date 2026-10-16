"""Kontrol service systemd.

Jalur utama memakai API D-Bus systemd, di mana otorisasi ditangani **polkit**
(bukan sudo). Dengan begitu aplikasi tidak perlu berjalan sebagai root maupun
memasang aturan `NOPASSWD` di sudoers — syarat penting agar layak didistribusikan.

Bila `dbus-next` tidak tersedia, tersedia jalur cadangan lewat perintah `systemctl`.
Pilihan jalur diatur `MONITOR_SERVICE_BACKEND` (`auto` | `dbus` | `systemctl`).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Dict

from . import config

ALLOWED_ACTIONS = {"start", "stop", "restart", "reload"}
_UNIT_RE = re.compile(r"^[A-Za-z0-9@._:+-]+$")

# nama aksi -> nama metode pada antarmuka org.freedesktop.systemd1.Manager
_DBUS_METHODS = {
    "start": "call_start_unit",
    "stop": "call_stop_unit",
    "restart": "call_restart_unit",
    "reload": "call_reload_or_restart_unit",
}


class ServiceControlError(Exception):
    """Kesalahan yang sudah dipetakan ke kode HTTP."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


def validate(unit: str, action: str) -> None:
    if action not in ALLOWED_ACTIONS:
        raise ServiceControlError(f"aksi tidak dikenal: {action}", 400)
    if not unit or not _UNIT_RE.match(unit):
        raise ServiceControlError("nama unit tidak valid", 400)


def dbus_available() -> bool:
    try:
        import dbus_next  # noqa: F401
    except ImportError:
        return False
    return True


def active_backend() -> str:
    """Jalur yang benar-benar dipakai sekarang."""
    backend = config.SERVICE_BACKEND
    if backend == "auto":
        return "dbus" if dbus_available() else "systemctl"
    return backend


async def _perform_dbus(unit: str, action: str) -> Dict[str, Any]:
    from dbus_next import BusType
    from dbus_next.aio import MessageBus
    from dbus_next.errors import DBusError

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        introspection = await bus.introspect(
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1"
        )
        proxy = bus.get_proxy_object(
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1", introspection
        )
        manager = proxy.get_interface("org.freedesktop.systemd1.Manager")
        method = getattr(manager, _DBUS_METHODS[action])
        job = await method(unit, "replace")
        return {"method": "dbus", "job": job}
    except DBusError as exc:
        text = str(exc)
        low = text.lower()
        if "notauthorized" in low.replace(" ", "") or "not authorized" in low or "accessdenied" in low.replace(" ", ""):
            raise ServiceControlError(
                "Ditolak oleh polkit. Jalankan aplikasi dari sesi desktop agar dialog izin "
                "muncul, atau setel MONITOR_SERVICE_BACKEND=systemctl.",
                403,
            ) from exc
        if "nosuchunit" in low.replace(" ", "") or "not found" in low:
            raise ServiceControlError(f"unit tidak ditemukan: {unit}", 404) from exc
        raise ServiceControlError(text, 500) from exc
    finally:
        bus.disconnect()


def _perform_systemctl(unit: str, action: str) -> Dict[str, Any]:
    if not shutil.which("systemctl"):
        raise ServiceControlError("systemctl tidak tersedia", 500)

    cmd = ["systemctl", action, unit]
    if config.USE_SUDO:
        cmd = ["sudo", "-n"] + cmd

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.SubprocessError as exc:
        raise ServiceControlError(str(exc), 500) from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        low = err.lower()
        if "not found" in low or "could not be found" in low:
            raise ServiceControlError(f"unit tidak ditemukan: {unit}", 404)
        if "password is required" in low or "a password is required" in low:
            raise ServiceControlError(
                "sudo meminta password. Pakai jalur D-Bus/polkit "
                "(MONITOR_SERVICE_BACKEND=dbus) agar tidak perlu sudo.",
                403,
            )
        if "not authorized" in low or "access denied" in low or "authentication" in low:
            raise ServiceControlError(err, 403)
        raise ServiceControlError(err or f"systemctl keluar dengan kode {proc.returncode}", 500)

    return {"method": "systemctl", "output": proc.stdout.strip() or "ok"}


async def perform(unit: str, action: str) -> Dict[str, Any]:
    validate(unit, action)

    backend = active_backend()
    if backend == "dbus":
        if not dbus_available():
            raise ServiceControlError(
                "MONITOR_SERVICE_BACKEND=dbus tapi dbus-next tidak terpasang "
                "(pip install 'aplikasimonitor[dbus]')",
                500,
            )
        result = await _perform_dbus(unit, action)
    else:
        result = _perform_systemctl(unit, action)

    return {"unit": unit, "action": action, **result}
