#!/usr/bin/env bash
# Siapkan lingkungan pengembangan: paket sistem + virtualenv + instal paket (editable).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Memasang paket sistem (butuh sudo)..."
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip lm-sensors iproute2

echo "==> Membuat virtualenv .venv ..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

echo "==> Memasang aplikasimonitor (editable) ..."
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -e .

echo
echo "Selesai. Jalankan dasbor dengan:"
echo "  ./run.sh          # atau: ./.venv/bin/aplikasimonitor"
echo
echo "Dasbor tersedia di http://127.0.0.1:8787"
