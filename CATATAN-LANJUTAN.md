# Catatan Lanjutan

Dua bagian: **(A)** cara mendistribusikan aplikasi ini ke laptop Linux lain, dan
**(B)** ide pengembangan berikutnya.

> **Status:** prasyarat di **A.2 sudah dikerjakan** — `pyproject.toml` + entry point
> CLI, restrukturisasi menjadi paket `aplikasimonitor/`, dan kontrol service lewat
> **D-Bus + polkit** (menggantikan `sudoers`). Kerangka `debian/` tersedia di **A.3**.

### Catatan polkit

Sering disangka semua aksi systemd butuh autentikasi. Kenyataannya:

| Aksi | Default policy |
|---|---|
| `org.freedesktop.systemd1.manage-units` | butuh autentikasi (`auth_admin`) |
| `org.freedesktop.login1.reboot` / `power-off` | `allow_active=yes` — sesi desktop aktif boleh tanpa dialog |

Jadi menguji "aksi yang seharusnya ditolak" memakai `Reboot()` itu keliru: aksi
tersebut memang diizinkan secara bawaan. Untuk sekadar mengecek izin, gunakan
`pkcheck` atau `CanReboot()`.

Penting untuk pengemasan: `python3-dbus-next` tersedia di repo Debian/Ubuntu,
sehingga `.deb` bisa bergantung pada paket resmi tanpa mem-bundle pip.

---


## A. Distribusi paket untuk Linux

### A.0 Ringkasan jawaban

Bisa. Tapi penting dipahami dulu: **aplikasi ini bukan aplikasi biasa.** Ia perlu
membaca `/proc`, `/sys`, sensor, socket, dan journal sistem, lalu (opsional) mengontrol
service. Paket yang mengurung aplikasi dalam *sandbox* justru menyulitkannya. Jadi
pilihan kanal sangat ditentukan oleh kebutuhan akses host ini.

### A.1 Perbandingan kanal distribusi

| Kanal | Cara user pasang | Cocok untuk app ini? | Catatan |
|---|---|---|---|
| **pipx / PyPI** | `pipx install aplikasimonitor` | ⭐ **Paling cocok** | Ini aplikasi Python. Paling sedikit gesekan, lintas distro. Bukan "repo Linux" tapi standar de-facto ekosistem Python. |
| **.deb + PPA** | `add-apt-repository ppa:…` lalu `apt install` | ⭐ **Cocok** | Target utama Mint/Ubuntu/Mint. Proses paling matang. |
| **.deb + repo APT sendiri** | `apt install` dari repo Anda | Cocok | Kontrol penuh, tanpa Launchpad. Pakai `aptly`/`reprepro` atau hosting statis + GPG. |
| **.deb lepas** | `sudo apt install ./file.deb` | Cocok | Paling cepat untuk berbagi; tanpa auto-update. |
| **Snap** | `snap install` | Netral | Interface `system-observe`/`hardware-observe`/`network-observe` memang dirancang untuk ini. **Tapi Linux Mint tidak menyertakan snapd secara bawaan.** |
| **AppImage** | unduh & jalankan | Netral | Tanpa sandbox → akses host penuh. Ukuran besar (bundle Python), tanpa integrasi paket manager. |
| **Flatpak / Flathub** | `flatpak install` | ❌ **Kurang cocok** | Butuh `--filesystem=host` + akses bus sistem; kebijakan Flathub biasanya menolak akses host seluas itu. Sandbox=malah menghalangi. |
| **AUR (Arch)** | `yay -S …` | Cocok bila menarget Arch | Cukup `PKGBUILD`. |
| **COPR (Fedora)** | `dnf copr enable` | Cocok bila menarget Fedora | Mirip PPA. |
| **Nixpkgs / Nix** | `nix run` | Cocok | Perlu `default.nix`. |
| **OCI (Docker)** | `docker run …` | Netral | Perlu `--pid=host --privileged`; jelek dan berisiko. |
| **Repo resmi Debian/Ubuntu** | `apt install aplikasimonitor` | Ideal, tapi lama | Lihat A.4 — perlu sponsor, lintian bersih, DEP-5, dst. |

**Rekomendasi urutan:** `pipx/PyPI` dulu (cepat, lintas distro) → lalu `.deb` via PPA
atau repo sendiri untuk pengguna Mint/Ubuntu.

### A.2 Prasyarat: rapikan kode dulu

Sebelum bisa dikemas rapi, ada tiga hal yang harus diubah:

**1. Metadata paket (`pyproject.toml`)**

Tambahkan entry point supaya muncul perintah CLI dan bisa dipasang `pipx`/`pybuild`:

```toml
[project]
name = "aplikasimonitor"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = ["fastapi>=0.110", "uvicorn[standard]>=0.29", "psutil>=5.9"]

[project.scripts]
aplikasimonitor = "backend.cli:main"

[tool.setuptools.package-data]
"backend" = ["static/*", "static/**/*"]
```

Frontend perlu ikut terpasang sebagai *package data* (bukan folder terpisah), dan
dibaca pakai `importlib.resources` alih-alih path relatif ke direktori sumber.

**2. Ganti `sudo`/sudoers dengan D-Bus + polkit** ← ini yang paling penting

Pendekatan `NOPASSWD sudoers` yang dipakai sekarang **tidak layak untuk paket
distribusi** (dianggap celah keamanan). Ganti dengan API resmi systemd:

```
org.freedesktop.systemd1.Manager.StartUnit("nginx.service", "replace")
```

Melalui **bus sistem**, otorisasi ditangani **polkit**, dan pengguna akan diminta
password lewat dialog bawaan desktop-nya (GNOME/KDE sudah punya agen polkit). Ini
cara yang dipakai Cockpit dan GNOME System Monitor.

- Pustaka: `dbus-next` (async, murni Python, tanpa dependensi C) — lebih portabel untuk
  pengemasan daripada `python3-dbus` (butuh binding C).
- Keuntungan: aplikasi berjalan **tanpa hak istimewa**; hanya naik hak per-aksi.
- Buat berkas kebijakan polkit sendiri (`.policy`) untuk aksi kustom bila perlu.

Konsekuensinya: server harus berjalan **di dalam sesi pengguna** agar agen polkit bisa
muncul. Maka jadikan **`systemd --user` service**, bukan service sistem.

**3. Unit systemd (user service)**

`~/.config/systemd/user/aplikasimonitor.service`:

```ini
[Unit]
Description=Aplikasi Monitor
After=default.target

[Service]
ExecStart=%h/.local/bin/aplikasimonitor
Restart=on-failure

[Install]
WantedBy=default.target
```

Lalu `systemctl --user enable --now aplikasimonitor`. Paket `.deb` bisa memakai
`dh_installsystemduser` agar ini otomatis.

### A.3 Membangun `.deb` dengan `dh-python` (jalur yang disarankan)

Debian/Ubuntu punya helper khusus Python, jadi tidak serumit yang dibayangkan:

```bash
sudo apt install dh-python python3-all devscripts debhelper lintian

mkdir -p debian/source
# debian/control, debian/rules, debian/changelog, debian/copyright,
# debian/aplikasimonitor.install, debian/postinst, debian/prerm

# debian/rules cukup sesingkat ini:
#   #!/usr/bin/make -f
#   %:
#   	dh $@ --with python3 --buildsystem=pybuild

dpkg-buildpackage -us -uc -b     # hasilkan .deb di ../ 
lintian ../aplikasimonitor_1.0.0_amd64.deb   # wajib bersih
```

Yang **harus** ada agar lolos standar:
- `debian/copyright` format **DEP-5** (mesin-baca, bukan prosa).
- `debian/changelog` format Debian yang valid.
- **manpage** (`aplikasimonitor.1`).
- `Rules-Requires-Root: no` bila memungkinkan.
- Build **reproducible**.

### A.4 Masuk repo resmi (jalur panjang, tapi nyata)

Untuk bisa `apt install aplikasimonitor` tanpa menambah repo pihak ketiga:

1. **Debian dulu** (Ubuntu menyerap dari Debian):
   - Ajukan bug **ITP** (Intent To Package) di `bugs.debian.org`.
   - Siapkan paket, lalu cari **sponsor** di `debian-mentors`
     (mailing list / Matrix). Hosting di `salsa.debian.org`.
   - Syarat: lintian bersih, DEP-5, autopkgtest, maintainer yang responsif.
2. Setelah masuk Debian, paket otomatis tersinkron ke **Ubuntu universe**.
3. Dari situ baru bisa dipertimbangkan masuk **main** Ubuntu.

Ini hitungan **bulan**, bukan hari — tapi inilah satu-satunya cara masuk repo resmi.
Untuk sebagian besar proyek, PPA atau repo sendiri sudah lebih dari cukup.

### A.5 Membuat repo APT sendiri (alternatif PPA)

Alternatif tanpa Launchpad:
- `aptly` atau `reprepro` untuk mengelola kumpulan `.deb`.
- **Wajib** tanda tangan GPG pada berkas `Release` (`Release.gpg`/`InRelease`).
- Hosting bisa di server biasa, GitHub Pages, atau Cloudflare Pages.

Sisi pengguna (perhatikan `signed-by`, karena `apt-key` sudah usang):

```bash
curl -fsSL https://example.com/aplikasimonitor.gpg \
  | sudo tee /etc/apt/keyrings/aplikasimonitor.gpg >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/aplikasimonitor.gpg] https://example.com/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/aplikasimonitor.list
sudo apt update && sudo apt install aplikasimonitor
```

### A.6 Alat yang perlu disiapkan

| Alat | Untuk |
|---|---|
| `dpkg-buildpackage` | membangun `.deb` (`dpkg-buildpackage -us -uc -b`) |
| `debhelper`, `dh-python`, `pybuild-plugin-pyproject`, `python3-setuptools` | perkakas build Debian |
| `lintian` | memeriksa mutu paket |
| `aptly` / `reprepro` | mengelola repo APT sendiri |
| `pipx` | memasang dari PyPI secara terisolasi |
| `snapcraft`, `appimagetool` | bila memilih kanal Snap / AppImage |

---

## B. Ide pengembangan lanjutan

**Prioritas tinggi (efek besar, usaha sedang)**

1. **Endpoint `/metrics` format Prometheus.** Satu endpoint tambahan membuat dasbor ini
   bisa dikonsumsi Prometheus + Grafana yang mungkin sudah Anda pakai. Sekaligus jadi
   jembatan ke ekosistem monitoring profesional. (Bisa juga `/api/export` JSON.)
2. **Riwayat persisten (SQLite).** Sekarang grafik hanya menyimpan 60 sampel di memori.
   Simpan ke SQLite → bisa lihat tren "minggu lalu CPU sempat 100%". Ringan, tanpa server.
3. **Alerting.** Aturan ambang (suhu > 85°C, service gagal, disk > 90%) → notifikasi
   desktop (`notify-send`), Telegram, atau webhook. Ini yang mengubah "dasbor yang
   dilihat" jadi "sistem yang memberi tahu".

**Prioritas menengah**

4. **Deteksi & auto-restart service gagal.** Aplikasi sudah menandai service yang
   gagal; tinggal ditambah policy opsional.
5. **Kesehatan disk (SMART)** via `smartctl -j` — prediksi kegagalan disk jauh lebih
   berguna daripada sekadar persentase pemakaian.
6. **Grafik per-proses** dan "top talkers" jaringan per proses (butuh `nethogs`/`ss`).
7. **Multi-host.** Pisahkan menjadi *agent* (di tiap laptop) + *hub* terpusat. Cocok
   bila nanti ingin memantau beberapa mesin dari satu halaman.
8. **Mode CLI.** `aplikasimonitor --once` mencetak snapshot ke terminal — berguna untuk
   SSH dan skrip.

**Polesan**

9. **Autentikasi + bind LAN.** Sebelum `MONITOR_HOST=0.0.0.0`, tambahkan token/HTTP auth.
10. **PWA** agar bisa "di-install" dari browser dan dibuka seperti aplikasi desktop.
11. **Dukungan container** (podman/docker) — daftar container yang berjalan.
12. **Kontrol kipas / profil daya** (mis. `dell_smm` pada laptop Dell).

**Urutan yang saya sarankan:** `/metrics` → riwayat SQLite → alerting. Ketiganya
memakai ulang collector yang sudah ada, jadi murah secara kode tapi besar manfaatnya.
