# Panduan Lengkap macOS (Apple Silicon & Intel)

Panduan ini khusus untuk pengguna **macOS** (MacBook / iMac / Mac Mini). Browser workspace berjalan terisolasi dalam mode headless (`-headless` / `--headless=new`) menggunakan direktori profil terpisah di `~/Library/Application Support/AntiGravity-Browser/profiles/` serta membuat launcher klik-ganda `.command` di Desktop Finder.

> **Saran Terbaik:** Gunakan **Antigravity Desktop** atau **Antigravity CLI** (`agy`) dengan model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`).

---

## 1. Kebutuhan Awal di macOS

Buka **Terminal**, lalu pastikan **Homebrew**, **Rust**, dan **Python 3** sudah terpasang:

```bash
# Jika belum ada Command Line Tools:
xcode-select --install

# Install Rust & Python via Homebrew:
brew install rust python git
```

Pastikan minimal **1 browser** sudah terpasang di `/Applications`:
- `Brave Browser.app`
- `Google Chrome.app`
- `Microsoft Edge.app`
- `Firefox.app`

---

## 2. Clone & Setup Otomatis (`setup.sh`)

```bash
git clone https://github.com/Sorosjenaka/AntiGravity-Browser.git
cd AntiGravity-Browser
chmod +x setup.sh run-plan.sh

# Pilih otomatis browser terpasang, atau pilih langsung:
./setup.sh --browser auto
```

Contoh memilih browser spesifik di macOS:

```bash
./setup.sh --browser brave --profile Agent
./setup.sh --browser chrome --profile Agent
./setup.sh --browser edge --profile Agent
./setup.sh --browser firefox --profile Raid

# Atau menunjuk langsung bundle .app di macOS:
./setup.sh --browser custom --exe-path "/Applications/Brave Browser.app" --profile Agent
```

Yang otomatis dilakukan `setup.sh` di macOS:
- Test & compile binary Rust ke `./target/release/x-social-draft-workflow`
- Memastikan `websockets` terpasang (membuat `.venv/` otomatis jika Homebrew Python membatasi `pip` global karena PEP 668)
- Inisialisasi SQLite (`history.sqlite3`)
- Membuat profil terisolasi di:
  - Chromium: `~/Library/Application Support/AntiGravity-Browser/profiles/<browser>-<profile>`
  - Firefox: `~/Library/Application Support/Firefox/` (`-no-remote -P <profile>`)
- Membuat shortcut Finder **`~/Desktop/AntiGravity X (<Browser> - <Profile>).command`** + script `shortcuts/antigravity-x-*.sh`
- Menjalankan deteksi user X di mode headless

---

## 3. Login X Pertama Kali Lewat Shortcut `.command`

Jika `auto-detect-account` melaporkan belum login:

1. Buka Desktop Finder dan klik ganda **`AntiGravity X (<Browser> - <Profile>).command`** (atau jalankan `./shortcuts/antigravity-x-*.sh` di Terminal).
2. Jika muncul izin Gatekeeper untuk file `.command` yang baru dibuat, jalankan dari Terminal:
   ```bash
   ./shortcuts/antigravity-x-*.sh
   ```
3. Login ke akun X kamu sekali di jendela browser terpisah yang muncul, lalu **tutup total (`Cmd+Q`)** jendela browser profil workspace itu.
4. Jalankan ulang deteksi akun:
   ```bash
   ./target/release/x-social-draft-workflow auto-detect-account
   ```

---

## 4. Pakai Lewat AI Agent

1. Buka folder `AntiGravity-Browser` di **Antigravity Desktop / CLI** (atau Claude Code, Codex, Gemini CLI, Hermes, Cursor, Windsurf).
2. Ketik:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Saat agent menyatakan siap kerja, **tinggal kirim daftar link X** berapa pun jumlahnya (1, 3, 10, 20, 50+). Agent bekerja dalam mode headless dengan **jeda acak 5–60 detik** antar post tanpa mengganggu jendela Mac yang sedang kamu pakai.

---

## 5. Eksekutor Lokal Fallback di macOS (`run-plan.sh`)

Jika memakai agent sandbox atau assistant yang hanya membuat draf, suruh agent menulis `data/action_plan.json`, lalu jalankan 1 perintah di Terminal macOS:

```bash
./run-plan.sh
```

---

## 6. Troubleshooting Singkat macOS

- **Browser tidak terdeteksi walau sudah diunduh:**  
  Pastikan aplikasi sudah dipindahkan ke `/Applications/` (bukan masih berada di `Downloads` atau disk image `.dmg`). Atau gunakan `--exe-path "/Applications/..."`.
- **Error profil terkunci / headless langsung keluar:**  
  Pastikan jendela browser yang dibuka lewat shortcut `.command` sudah ditutup penuh (`Cmd+Q`) sebelum menjalankan mode headless.
