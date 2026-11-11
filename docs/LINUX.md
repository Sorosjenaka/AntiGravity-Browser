# Panduan Lengkap Linux Desktop & Linux VPS (Ubuntu / Debian / Arch)

Panduan ini khusus untuk pengguna **Linux Desktop (GUI)** maupun **Linux VPS / Server Headless (SSH tanpa monitor/X11)**.  
Pada Linux, engine menjalankan browser terisolasi dalam mode headless native (`-headless` untuk Firefox, `--headless=new --disable-dev-shm-usage` untuk Chromium) dengan origin loopback ketat (`http://127.0.0.1:<port>`) serta membuat launcher `.sh` dan `.desktop`.

> **Saran Terbaik:** Gunakan **Antigravity CLI** (`agy`) dengan model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`), atau agent CLI lain seperti Gemini CLI, Codex CLI, Claude Code, dan Hermes di terminal Linux/VPS kamu.

---

## 1. Install Kebutuhan Dasar (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y git build-essential pkg-config rustc cargo python3 python3-pip python3-venv
```

*(Jika distro Linux kamu memiliki versi Rust yang lebih tua dari edisi 2024 di `apt`, install installer resmi Rust dari situs resmi `https://rustup.rs` sesuai dokumentasi distro kamu.)*

### Install Salah Satu Browser Resmi Distro
Pilih satu browser yang kamu inginkan (Firefox sangat ringan dan praktis di Linux/VPS):

```bash
# Pilihan A: Firefox (Ubuntu/Debian)
sudo apt install -y firefox || sudo apt install -y firefox-esr

# Pilihan B: Chromium
sudo apt install -y chromium || sudo apt install -y chromium-browser
```

*(Untuk Google Chrome atau Brave resmi di Ubuntu/Debian, ikuti halaman unduhan resmi `.deb` dari Google Chrome / Brave, lalu install dengan `sudo apt install -y ./nama-paket.deb` agar semua library sistem ikut terpasang.)*

---

## 2. Clone & Setup Otomatis (`setup.sh`)

```bash
git clone https://github.com/Sorosjenaka/AntiGravity-Browser.git
cd AntiGravity-Browser
chmod +x setup.sh run-plan.sh

# Deteksi otomatis browser terpasang:
./setup.sh --browser auto
```

Atau pilih browser secara eksplisit:

```bash
./setup.sh --browser firefox --profile Raid
./setup.sh --browser brave --profile Agent
./setup.sh --browser chrome --profile Agent
./setup.sh --browser edge --profile Agent
```

> **Aman dari Error PEP 668 (`externally-managed-environment`):**  
> Di Ubuntu 23/24+ dan Debian 12+, `pip` sistem sering dibatasi. `setup.sh` otomatis membuat `.venv/` lokal jika `pip` global ditolak, dan CLI Rust `x-social-draft-workflow` otomatis memprioritaskan `.venv/bin/python3`.

---

## 3. Cara Login X Pertama Kali (Pilih Sesuai Kondisi Linux Kamu)

### Skenario A — Kamu Memakai **Linux Desktop (Ada Layar / GUI)**

1. `setup.sh` otomatis membuat:
   - Launcher menu aplikasi: `~/.local/share/applications/antigravity-x-<browser>-<profile>.desktop`
   - Shortcut Desktop (jika `~/Desktop` ada): `~/Desktop/AntiGravity X (<Browser> - <Profile>).desktop`
   - Script launcher di `shortcuts/antigravity-x-<browser>-<profile>.sh`
2. Klik shortcut Desktop (atau jalankan `./shortcuts/antigravity-x-<browser>-<profile>.sh`), lalu **login X sekali**.
3. Tutup jendela browser tersebut.
4. Jalankan deteksi akun X di mode headless:
   ```bash
   ./target/release/x-social-draft-workflow auto-detect-account
   ```

### Skenario B — Kamu Memakai **Linux VPS Headless (SSH-Only Tanpa Layar)**

Karena VPS cloud tidak memiliki monitor/desktop untuk login awal interaktif, login dilakukan sekali dari PC lokal kamu lalu direktori profil terisolasi dikirim ke VPS:

#### Metode 1 (Paling Cepat & Stabil): Salin Profil Terisolasi dari PC Lokal ke VPS

1. **Di PC lokal kamu (Windows / macOS / Linux Desktop):**  
   Jalankan repo ini di PC lokal dengan browser yang sama (`brave`, `chrome`, atau `firefox`), buka launcher `AntiGravity X`, **login X sekali**, lalu **tutup jendela browser tersebut**.
2. **Lokasi folder profil terisolasi workspace di PC lokal:**
   - **Windows (Chromium Brave/Chrome/Edge):** `~\AppData\Local\AntiGravity-Browser\profiles\<browser>-Agent`
   - **macOS (Chromium):** `~/Library/Application Support/AntiGravity-Browser/profiles/<browser>-Agent`
   - **Linux Desktop (Chromium):** `~/.local/share/AntiGravity-Browser/profiles/<browser>-Agent`
   - **Firefox (semua OS):** folder profil `Raid` di direktori profil Firefox (`~/.mozilla/firefox/<id>.Raid` di Linux atau `~\AppData\Roaming\Mozilla\Firefox\Profiles\<id>.Raid` di Windows)
3. **Salin folder profil terisolasi itu ke VPS via `scp` atau `rsync`:**
   - Contoh untuk **Brave / Chrome / Edge** ke VPS Linux:
     ```bash
     ssh user@IP_VPS "mkdir -p ~/.local/share/AntiGravity-Browser/profiles"
     scp -r ~/.local/share/AntiGravity-Browser/profiles/brave-Agent user@IP_VPS:~/.local/share/AntiGravity-Browser/profiles/brave-Agent
     ```
   - Contoh untuk **Firefox (`Raid`)** ke VPS Linux:
     1. Jalankan di VPS sekali: `firefox -headless -CreateProfile Raid`
     2. Cek nama folder `*.Raid` di `~/.mozilla/firefox/` pada VPS, lalu `scp -r` isi folder profil `Raid` dari PC lokal ke folder `*.Raid` di VPS.
4. **Verifikasi di VPS (Headless Penuh):**
   ```bash
   ./target/release/x-social-draft-workflow connect-browser --browser brave --profile Agent
   ./target/release/x-social-draft-workflow status
   ```
   VPS akan langsung mendeteksi `@handle` X kamu secara headless tanpa layar.

#### Metode 2: SSH X11 Forwarding (Jika PC Lokal Punya X Server)

```bash
ssh -X user@IP_VPS
cd AntiGravity-Browser
./shortcuts/antigravity-x-firefox-raid.sh
```

Jendela browser dari VPS tampil di layar PC lokalmu; login X sekali lalu tutup jendelanya, setelah itu jalankan `auto-detect-account` di VPS.

---

## 4. Pakai Lewat AI Agent di Linux / VPS

1. Buka folder `AntiGravity-Browser` di terminal agent pilihan kamu (`agy`, Gemini CLI, Codex, Claude Code, atau Hermes).
2. Kirim prompt:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Kirim berapa pun jumlah link X yang kamu punya (1, 5, 10, 25, 50+). Agent bekerja di mode headless dengan **jeda acak 5–60 detik** antar link.

---

## 5. Eksekutor Lokal Fallback di Linux / VPS (`run-plan.sh`)

Jika memakai agent sandbox atau assistant yang hanya menyiapkan draf, suruh agent membuat `data/action_plan.json`, lalu jalankan di VPS/Linux:

```bash
./run-plan.sh
```

Jika ingin tetap berjalan saat sesi SSH ditutup, jalankan di dalam `tmux` atau `screen`.

---

## 6. Troubleshooting Khusus Linux & VPS

- **Tab Chromium crash di container/VPS kecil:**  
  Flag `--disable-dev-shm-usage` sudah otomatis diaktifkan pada Linux di `browser_hub.py`.
- **Error shared library (`libnss3.so` / `libgbm.so.1`) di VPS minimal:**  
  Install browser via `apt install` resmi distro (bukan arsip zip mentah) agar library sistem ikut terpasang.
- **Snap / Flatpak Firefox di Ubuntu 22.04/24.04:**  
  `browser_hub.py` otomatis membaca `profiles.ini` di `~/.mozilla/firefox/`, `~/snap/firefox/common/.mozilla/firefox/`, maupun Flatpak `~/.var/app/org.mozilla.firefox/...`.
