# AntiGravity-Browser

Alur kerja X (Twitter) lintas OS (**Windows**, **Linux Desktop / Linux VPS**, dan **macOS**) berbasis AI Agent (**Antigravity**, **Gemini**, **Codex**, **Claude**, **Hermes**, dan assistant workspace lainnya) + **CLI Rust (`x-social-draft-workflow`)** + **Multi-Browser Headless Terisolasi (Firefox, Brave, Chrome, Edge)**.

---

## Pilih Panduan Lengkap Sesuai OS Kamu

| Sistem Operasi | Script Setup | Launcher / Shortcut | Fallback Eksekutor | Panduan Terpisah |
| :--- | :--- | :--- | :--- | :--- |
| **Windows 10 / 11** | `.\setup.ps1 -Browser auto` | Desktop `.lnk` (`MS-SHLLINK`) | `.\run-plan.ps1` | [**Baca Panduan Windows**](docs/WINDOWS.md) |
| **Linux Desktop & Linux VPS** | `./setup.sh --browser auto` | `.desktop` + `shortcuts/*.sh` | `./run-plan.sh` | [**Baca Panduan Linux & VPS**](docs/LINUX.md) |
| **macOS (Apple Silicon / Intel)** | `./setup.sh --browser auto` | Desktop `.command` + `.sh` | `./run-plan.sh` | [**Baca Panduan macOS**](docs/MACOS.md) |

---

## Arsitektur Aman & Fitur Utama

1. **Lintas OS (Windows, Linux Desktop, Linux VPS Headless, macOS):** Mendeteksi executable browser native tiap OS (`Firefox` WebDriver BiDi termasuk Snap/Flatpak Ubuntu, `Brave`, `Google Chrome`, `Chromium`, `Microsoft Edge`, atau bundle `.app`/path custom), serta memakai mode headless standar (`-headless` dan `--headless=new` + `--disable-dev-shm-usage` di Linux).
2. **Isolasi Profil Ketat & Aman Security-Scanner:**
   - **Tidak mengakses profil browser pribadi kamu** dan **tidak melakukan port-scanning** ke aplikasi lain.
   - Seluruh sesi berjalan pada direktori profil terisolasi milik workspace (`AntiGravity-Browser/profiles/` untuk Chromium atau profil `-P` khusus untuk Firefox), hanya lewat loopback `127.0.0.1` dengan origin debug ketat (`--remote-allow-origins=http://127.0.0.1:<port>`).
   - Shortcut Desktop Windows (`.lnk`) ditulis langsung dengan format biner standar `[MS-SHLLINK]` murni secara native di Python.
3. **Auto-Deteksi User X:** Otomatis membaca `@handle` dan Display Name akun X yang sedang login di profil terisolasi tersebut (`auto-detect-account`).
4. **Bebas Pilih Browser Apa Saja:** Mendukung **Mozilla Firefox**, **Brave**, **Google Chrome / Chromium**, **Microsoft Edge**, maupun path browser custom.
5. **Jumlah Link Bebas & Jeda Acak 5–60 Detik:** Mendukung **berapa pun jumlah link** (1, 3, 10, 25, 50, atau lebih — tidak dibatasi 10). Antar aksi Like & Reply otomatis memakai **algoritma jeda acak 5 detik sampai maksimal 60 detik** (`--min-delay 5 --max-delay 60`) dengan distribusi multi-band natural.
6. **Berjalan Tanpa Mengganggu Pekerjaan Desktop:** Eksekusi menggunakan mode headless standar agar jendela kerja utama di Desktop tetap fokus.

---

## Saran Pengaturan Terbaik (Rekomendasi)

- **Aplikasi yang Disarankan:** Gunakan **Antigravity Desktop** ataupun **Antigravity CLI** (`agy`), supaya aturan workspace dan skill lokal langsung terbaca sejak awal.
- **Model yang Disarankan:** Pilih model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`) agar pembacaan link, penulisan draft Bahasa Inggris tanpa tanda tanya, eksekusi headless, dan laporan berjalan cepat serta efisien.

---

## 1. Cara Install Cepat (1 Menit)

### Lewat Windows (PowerShell)
Detail lengkap baca [**Panduan Windows**](docs/WINDOWS.md):
```powershell
git clone https://github.com/Sorosjenaka/AntiGravity-Browser.git
cd AntiGravity-Browser
.\setup.ps1 -Browser auto
```

### Lewat Linux / VPS / macOS (Bash)
Detail lengkap baca [**Panduan Linux & VPS**](docs/LINUX.md) atau [**Panduan macOS**](docs/MACOS.md):
```bash
git clone https://github.com/Sorosjenaka/AntiGravity-Browser.git
cd AntiGravity-Browser
chmod +x setup.sh run-plan.sh
./setup.sh --browser auto
```

Opsi memilih browser spesifik (`-Browser` di Windows atau `--browser` di Linux/macOS):
- `auto` (otomatis pilih browser terpasang)
- `brave` | `chrome` | `edge` | `firefox`
- `custom` dengan `-ExePath` / `--exe-path` (termasuk bundle `.app` di macOS atau `/usr/bin/chromium` di Linux)

> **Catatan Login X Pertama Kali:**
> - **Windows / Linux Desktop / macOS:** Klik ganda shortcut (`AntiGravity X (...).lnk` / `.desktop` / `.command`), login akun X sekali di browser terisolasi itu, lalu tutup jendelanya. Setelah itu jalankan `auto-detect-account`.
> - **Linux VPS Headless (tanpa GUI):** Salin folder profil terisolasi yang sudah login dari PC lokal via `scp` ke VPS (`~/.local/share/AntiGravity-Browser/profiles/...`), atau login via `ssh -X` — langkah lengkapnya ada di [**Panduan Linux & VPS**](docs/LINUX.md).

---

## 2. Cara Pakai di Antigravity / Gemini / Codex / Claude / Hermes

1. Buka folder `AntiGravity-Browser` sebagai workspace di agent pilihan kamu.
2. Kirim prompt ini:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Agent memverifikasi binary, profil browser terisolasi, launcher, dan akun X kamu secara otomatis.
4. Setelah itu, kamu **tinggal kirim daftar link X** dalam jumlah berapa pun.

---

## 3. Aturan Komunikasi, Draf X & Keamanan Publik

- **Bahasa obrolan dengan user:** Agent berbicara pakai **Bahasa Indonesia** yang jelas dan langsung ke inti.
- **Komentar di X selalu Bahasa Inggris (`en`):** Meskipun postingan target berbahasa Indonesia atau bahasa lain, draf balasan X ditulis dalam **Bahasa Inggris natural** (`7–9` kata, menyebut nama pendek project).
- **Tanpa tanda tanya di komentar X:** `?` / `？` ditolak otomatis oleh [`validate_draft_set`](src/lib.rs). Tidak memakai emoji, tanda kutip, atau dash (`—` / `–`).
- **Privasi aman dipakai publik:** [.gitignore](.gitignore) otomatis mengecualikan `history.sqlite3`, `browser_config.json`, `shortcuts/`, `*.lnk`, `*.desktop`, `*.command`, `.venv/`, `target/`, `data/*.txt`, dan `data/*.json` agar akun, sesi, maupun data pribadi tidak pernah ikut ter-push ke GitHub.

---

## 4. Mode Fallback Lokal Jika Agent Hanya Membuat Draf / Sandbox

Sebagian AI assistant memiliki kebijakan internal yang hanya mengizinkan pembuatan teks/draf secara manual atau berjalan di sandbox tanpa akses browser lokal. Jika hal ini terjadi:

1. Minta agent tersebut membuatkan draf balasan tervalidasi (`data/action_plan.json`).
2. Jalankan 1 perintah eksekutor lokal di perangkat kamu sendiri:
   - **Windows:** `.\run-plan.ps1`
   - **Linux / VPS / macOS:** `./run-plan.sh`

   Script ini mengeksekusi `data/action_plan.json` secara lokal dengan **jeda acak 5–60 detik** pada profil terisolasi kamu, menyimpan status ke SQLite, dan menampilkan tabel `report` akhir.

---

## 5. Daftar Perintah Lengkap (Cheat Sheet)

Ganti prefix binary sesuai OS:
- **Windows:** `.\target\release\x-social-draft-workflow.exe`
- **Linux / macOS:** `./target/release/x-social-draft-workflow`

```bash
# Lihat semua browser terpasang, profil terisolasi workspace, & port terkonfigurasi
./target/release/x-social-draft-workflow list-browsers

# Hubungkan browser pilihan + buat shortcut/launcher + deteksi user X
./target/release/x-social-draft-workflow connect-browser --browser brave --profile Agent

# Buat ulang shortcut/launcher profil terpisah
./target/release/x-social-draft-workflow create-shortcut

# Deteksi ulang user X yang sedang login di profil terisolasi
./target/release/x-social-draft-workflow auto-detect-account

# Cek status sistem, database, browser, & akun aktif
./target/release/x-social-draft-workflow status
```

Sub-perintah workflow post & laporan:
```text
init
status
list-browsers
connect-browser --browser <auto|brave|chrome|edge|firefox|custom> [--profile NAME] [--exe-path PATH]
create-shortcut
auto-detect-account
confirm-account --handle @name --display-name Name
designate-browser --label LABEL
add-post --url URL --text-file PATH --language LANG
save-drafts --post-id ID --file PATH
check-duplicate --text-file PATH
import-reply --text-file PATH
confirm-posted --draft-id ID
confirm-liked --post-id ID
report
show-prompt
```
