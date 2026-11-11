# Panduan Lengkap Linux Desktop & Linux VPS (Ubuntu / Debian / Arch)

Panduan ini khusus untuk pengguna **Linux Desktop (GUI)** maupun **Linux VPS / Server Headless (SSH tanpa monitor/X11)**.  
Pada Linux, engine otomatis memakai mode headless native (`MOZ_HEADLESS=1` untuk Firefox, `--headless=new --disable-dev-shm-usage` untuk Chromium, dan `start_new_session=True`) serta membuat launcher `.sh` dan `.desktop`.

> **Saran Terbaik:** Gunakan **Antigravity CLI** (`agy`) dengan model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`), atau agent CLI lain seperti Gemini CLI, Codex CLI, Claude Code, dan Hermes di terminal VPS/Linux kamu.

---

## 1. Install Kebutuhan Dasar (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y git curl build-essential pkg-config python3 python3-pip python3-venv

# Install Rust (cargo)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/bin/env"
```

### Install Salah Satu Browser
Pilih browser yang kamu inginkan (Firefox sangat ringan dan mudah untuk VPS):

```bash
# Pilihan A: Firefox (Ubuntu/Debian)
sudo apt install -y firefox || sudo apt install -y firefox-esr

# Pilihan B: Google Chrome (.deb resmi)
curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/chrome.deb
sudo apt install -y /tmp/chrome.deb

# Pilihan C: Brave Browser
sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main" | sudo tee /etc/apt/sources.list.d/brave-browser-release.list
sudo apt update && sudo apt install -y brave-browser
```

> **Catatan Arch Linux / Fedora:** cukup install `rust python base-devel` (`pacman`) atau `rust cargo python3 gcc` (`dnf`) ditambah `firefox` / `chromium` / `brave-bin`.

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
> Di Ubuntu 23/24+ dan Debian 12+, `pip` sistem sering diblokir. `setup.sh` otomatis membuat `.venv/` lokal jika `pip` global ditolak, dan CLI Rust `x-social-draft-workflow` otomatis memprioritaskan `.venv/bin/python3`.

---

## 3. Cara Login X Pertama Kali (Pilih Sesuai Kondisi Linux Kamu)

### Skenario A — Kamu Memakai **Linux Desktop (Ada Layar / GUI)**

1. `setup.sh` otomatis membuat:
   - Launcher menu aplikasi: `~/.local/share/applications/antigravity-x-<browser>-<profile>.desktop`
   - Shortcut Desktop (jika `~/Desktop` ada): `~/Desktop/AntiGravity X (<Browser> - <Profile>).desktop`
   - Script terminal di `shortcuts/antigravity-x-<browser>-<profile>.sh`
2. Klik shortcut Desktop (atau jalankan `./shortcuts/antigravity-x-<browser>-<profile>.sh`), lalu **login X sekali**.
3. Tutup jendela browser tersebut.
4. Jalankan auto-deteksi akun X secara headless:
   ```bash
   ./target/release/x-social-draft-workflow auto-detect-account
   ```

### Skenario B — Kamu Memakai **Linux VPS Headless (SSH-Only Tanpa Layar)**

Karena VPS cloud tidak memiliki layar Desktop, login akun X dilakukan sekali dari PC lokal kamu lalu profil terisolasinya dikirim ke VPS (**tidak perlu login ulang setiap hari**):

#### Metode 1 (Paling Cepat & Stabil): Salin Profil Terisolasi dari PC Lokal ke VPS

1. **Di PC lokal kamu (Windows / macOS / Linux Desktop):**  
   Jalankan repo ini di PC lokal dengan browser yang sama (misal `brave` atau `chrome` atau `firefox`), buka shortcut `AntiGravity X`, **login X sekali**, lalu **tutup browser tersebut**.
2. **Lokasi folder profil terisolasi agent di PC lokal:**
   - **Windows (Chromium Brave/Chrome/Edge):** `%LOCALAPPDATA%\AntiGravity-Browser\profiles\<browser>-Agent`
   - **macOS (Chromium):** `~/Library/Application Support/AntiGravity-Browser/profiles/<browser>-Agent`
   - **Linux Desktop (Chromium):** `~/.local/share/AntiGravity-Browser/profiles/<browser>-Agent`
   - **Firefox (semua OS):** folder profil `Raid` di direktori profil Firefox (`~/.mozilla/firefox/<id>.Raid` di Linux atau `%APPDATA%\Mozilla\Firefox\Profiles\<id>.Raid` di Windows)
3. **Kirim folder profil itu ke VPS via `scp` atau `rsync`:**
   - Contoh untuk **Brave / Chrome / Edge** dari PC ke VPS Linux:
     ```bash
     ssh user@IP_VPS "mkdir -p ~/.local/share/AntiGravity-Browser/profiles"
     scp -r "C:/Users/NAMA_KAMU/AppData/Local/AntiGravity-Browser/profiles/brave-Agent" user@IP_VPS:~/.local/share/AntiGravity-Browser/profiles/brave-Agent
     ```
   - Contoh untuk **Firefox (`Raid`)** ke VPS Linux:
     1. Jalankan di VPS sekali: `firefox -headless -CreateProfile Raid`
     2. Cek nama folder `*.Raid` di `~/.mozilla/firefox/` pada VPS, lalu `scp -r` isi folder profil `Raid` dari PC lokal ke folder `*.Raid` di VPS.
4. **Verifikasi di VPS (100% Headless):**
   ```bash
   ./target/release/x-social-draft-workflow connect-browser --browser brave --profile Agent
   ./target/release/x-social-draft-workflow status
   ```
   VPS akan langsung mendeteksi `@handle` X kamu secara headless tanpa layar!

#### Metode 2: SSH X11 Forwarding (Jika SSH Client Lokal Punya X Server)

Jika PC lokal kamu punya X Server (Linux Desktop, macOS XQuartz, atau Windows VcXsrv):

```bash
ssh -X user@IP_VPS
cd AntiGravity-Browser
./shortcuts/antigravity-x-firefox-raid.sh
```

Jendela browser dari VPS akan muncul di layar PC lokalmu; login X sekali lalu tutup jendelanya, setelah itu jalankan `auto-detect-account` di VPS.

---

## 4. Pakai Lewat AI Agent di Linux / VPS

1. Jalankan agent di folder `AntiGravity-Browser` (misal `agy`, `gemini`, `codex`, `claude`, atau `hermes`).
2. Kirim prompt:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Berikan berapa pun jumlah link X yang kamu punya (1, 5, 10, 25, 50+). Agent berjalan penuh di hidden background headless dengan **jeda acak 5–60 detik** antar link.

---

## 5. Eksekutor Lokal Fallback di Linux / VPS (`run-plan.sh`)

Jika memakai agent sandbox yang tidak bisa menjalankan browser lokal, suruh agent menulis `data/action_plan.json`, lalu jalankan:

```bash
./run-plan.sh
```

Atau jalankan di background VPS bahkan saat SSH ditutup (`nohup` / `tmux` / `screen`):

```bash
nohup ./run-plan.sh > run.log 2>&1 &
```

---

## 6. Troubleshooting Khusus Linux & VPS

- **Tab Chromium crash di VPS Docker / container kecil:**  
  Sudah otomatis dicegah oleh flag `--disable-dev-shm-usage` di `browser_hub.py`.
- **Error `libnss3.so` / `libgbm.so.1` missing saat Chromium headless di VPS minimal:**  
  Install browser via `.deb` memakai `sudo apt install -y ./chrome.deb` (bukan ekstrak zip manual) agar `apt` memasang seluruh library sistem yang dibutuhkan.
- **Snap Firefox di Ubuntu 22.04/24.04:**  
  `browser_hub.py` otomatis membaca `profiles.ini` di `~/.mozilla/firefox/`, `~/snap/firefox/common/.mozilla/firefox/`, maupun Flatpak `~/.var/app/org.mozilla.firefox/...`.
