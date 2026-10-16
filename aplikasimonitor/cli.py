"""Entry point CLI: perintah `aplikasimonitor`."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aplikasimonitor",
        description="Dasbor monitoring Linux: service systemd, proses, port, sensor, dan log.",
    )
    parser.add_argument(
        "--host", default=os.getenv("MONITOR_HOST", "127.0.0.1"),
        help="alamat bind (default: 127.0.0.1, pakai 0.0.0.0 untuk LAN)",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("MONITOR_PORT", "8787")),
        help="port (default: 8787)",
    )
    parser.add_argument(
        "--interval", type=float,
        default=float(os.getenv("MONITOR_STREAM_INTERVAL", "2")),
        help="interval push SSE dalam detik (default: 2)",
    )
    parser.add_argument(
        "--no-service-control", action="store_true",
        help="matikan tombol start/stop/restart service",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="mode pengembangan: muat ulang otomatis saat berkas berubah",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # config.py membaca environment saat impor, jadi set dulu sebelum mengimpor app.
    os.environ["MONITOR_STREAM_INTERVAL"] = str(args.interval)
    if args.no_service_control:
        os.environ["MONITOR_SERVICE_CONTROL"] = "0"

    import uvicorn

    if args.reload:
        # reload butuh target berupa string agar worker bisa mengimpor ulang.
        uvicorn.run(
            "aplikasimonitor.main:app",
            host=args.host, port=args.port, reload=True,
        )
    else:
        from .main import app

        uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
