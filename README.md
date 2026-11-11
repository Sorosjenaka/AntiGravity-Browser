# AntiGravity-Browser

Alur kerja otomatis X (Twitter) lintas OS (**Windows**, **Linux Desktop / Linux VPS**, dan **macOS**) berbasis AI Agent (**Antigravity**, **Gemini**, **Codex**, **Claude**, **Hermes**, dan agent workspace lainnya) + **CLI Rust (`x-social-draft-workflow`)** + **Multi-Browser Hidden Automation (Firefox, Brave, Chrome, Edge)**.

---

## Pilih Panduan Lengkap Sesuai OS Kamu

| Sistem Operasi | Script Setup | Launcher / Shortcut | Fallback Eksekutor | Panduan Terpisah |
| :--- | :--- | :--- | :--- | :--- |
| **Windows 10 / 11** | `.\setup.ps1 -Browser auto` | Desktop `.lnk` | `.\run-plan.ps1` | [**Baca Panduan Windows**](docs/WINDOWS.md) |
| **Linux Desktop & Linux VPS** | `./setup.sh --browser auto` | `.desktop` + `shortcuts/*.sh` | `./run-plan.sh` | [**Baca Panduan Linux & VPS**](docs/LINUX.md) |
| **macOS (Apple Silicon / Intel)** | `./setup.sh --browser auto` | Desktop `.command` + `.sh` | `./run-plan.sh` | [**Baca Panduan macOS**](docs/MACOS.md) |

---

## Fitur Utama (Siap Pakai & Aman untuk Desktop Kerja / VPS)

1. **Lintas OS (Windows, Linux Desktop, Linux VPS Headless, macOS):** Mendeteksi binary browser native di tiap OS (`Firefox` BiDi termasuk Snap/Flatpak Ubuntu, `Brave`, `Google Chrome`, `Chromium`, `Microsoft Edge`, atau `.app`/path custom), memakai `MOZ_HEADLESS=1` dan `--disable-dev-shm-usage` (VPS Linux), serta mengeksekusi proses terpisah di background (`CREATE_NO_WINDOW` di Windows, `start_new_session=True` di Linux/macOS).
2. **Auto-Deteksi User X:** Otomatis membaca `@handle` dan Display Name akun X yang sedang login di browser tanpa ketik manual (`auto-detect-account`).
3. **Bebas Pilih Browser Apa Saja (Tidak Harus Firefox):** Mendukung **Mozilla Firefox**, **Brave**, **Google Chrome / Chromium**, **Microsoft Edge**, maupun path browser custom.
4. **Otomatis Buat Shortcut / Launcher Profil Terpisah:** Perintah `connect-browser` / `create-shortcut` langsung membuat shortcut sesuai OS (`.lnk` di Windows, `.desktop` + `.sh` di Linux, `.command` + `.sh` di macOS) yang memakai direktori profil terisolasi + port debugging otomatis, sehingga browser kerja utama kamu tidak pernah tercampur atau tertutup.
5. **Jalan 100% di Hidden Background:** Browser berjalan tersembunyi tanpa mengambil fokus jendela saat kamu sedang bekerja (atau berjalan headless penuh di VPS tanpa monitor).
6. **Jumlah Link Bebas & Jeda Acak 5–60 Detik:** Terserah kamu mau kasih **berapa pun jumlah link** (1, 3, 10, 25, 50, atau lebih — tidak harus 10). Antar aksi Like & Komentar otomatis memakai **algoritma jeda acak 5 detik sampai maksimal 60 detik** (`--min-delay 5 --max-delay 60`) dengan variasi jeda natural agar terlihat seperti manusia.
7. **Auto-Ambil-Alih Port oleh Agent Apa Pun:** Agent otomatis mendeteksi port debug browser yang aktif (`DevToolsActivePort` / port `9222–9235` / `browser_config.json`) atau mencari port bebas otomatis agar tidak bentrok, serta membawa konfigurasi universal di [AGENTS.md](AGENTS.md), [GEMINI.md](GEMINI.md), [CLAUDE.md](CLAUDE.md), [.agents/skills/x-social-browser-workflow/SKILL.md](.agents/skills/x-social-browser-workflow/SKILL.md), dan [.claude/skills/x-social-browser-workflow/SKILL.md](.claude/skills/x-social-browser-workflow/SKILL.md).

---

## Saran Pengaturan Terbaik (Rekomendasi)

- **Aplikasi yang Disarankan:** Gunakan **Antigravity Desktop** ataupun **Antigravity CLI** (`agy`), agar aturan workspace (`AGENTS.md`, `GEMINI.md`, dan skill lokal) langsung terbaca otomatis sejak awal.
- **Model yang Disarankan:** Pilih model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`) supaya eksekusi baca link, pembuatan draft Bahasa Inggris tanpa tanda tanya, kontrol browser headless, dan pelaporan berjalan cepat serta hemat kuota.

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
> - **Linux VPS Headless (tanpa GUI):** Salin folder profil terisolasi yang sudah login dari PC lokal via `scp` ke VPS (`~/.local/share/AntiGravity-Browser/profiles/...`), atau buka sekali via `ssh -X` — langkah lengkapnya ada di [**Panduan Linux & VPS**](docs/LINUX.md).

---

## 2. Cara Pakai di Antigravity / Gemini / Codex / Claude / Hermes

1. Buka folder `AntiGravity-Browser` sebagai workspace di agent pilihan kamu.
2. Kirim prompt ini:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Agent langsung memverifikasi binary, browser, shortcut/launcher, dan akun X kamu secara otomatis, lalu membalas:
   > `Sudah ter-install dan ter-load 100%. Siap kerja Bos, tinggal kasih link-nya aja langsung gw kerjakan sekarang.`
4. Setelah itu, kamu **tinggal kirim daftar link X** dalam jumlah berapa pun dan suruh like + komentar.

---

## 3. Aturan Komunikasi, Komentar X & Keamanan Publik

- **Bahasa obrolan dengan user:** Agent selalu berbicara dengan kamu pakai **Bahasa Indonesia**, langsung melaksanakan perintah tanpa menolak dan tanpa bertele-tele bertanya.
- **Komentar di X selalu Bahasa Inggris (`en`):** Meskipun postingan target berbahasa Indonesia atau bahasa lain, balasan X tetap ditulis dalam **Bahasa Inggris natural** (`7–9` kata, menyebut nama pendek project).
- **Tanpa tanda tanya di komentar X:** `?` / `？` ditolak otomatis oleh [`validate_draft_set`](src/lib.rs). Tidak memakai emoji, tanda kutip, atau dash (`—` / `–`).
- **Privasi aman dipakai publik:** [.gitignore](.gitignore) otomatis mengecualikan `history.sqlite3`, `browser_config.json`, `shortcuts/`, `*.lnk`, `*.desktop`, `*.command`, `.venv/`, `target/`, `data/*.txt`, dan `data/*.json` agar akun, cookies, sesi, maupun data pribadi tidak ikut ter-push ke GitHub. Repo publik ini bebas data sensitif dan 100% aman dipakai siapa saja.

---

## 4. Bagaimana Jika Ada Agent Lain yang Menolak / Berjalan di Sandbox Terbatas?

Tidak ada file konfigurasi yang bisa mematikan aturan keamanan bawaan penyedia model AI (karena itu dikontrol oleh sistem provider model masing-masing). Untuk memastikan pekerjaan kamu **tetap selalu berhasil tanpa mentok**:

1. **Penjelasan Otorisasi Jelas di Semua Entrypoint Agent:** Repo ini menyediakan file aturan di [AGENTS.md](AGENTS.md), [GEMINI.md](GEMINI.md), [CLAUDE.md](CLAUDE.md), [.cursorrules](.cursorrules), [.windsurfrules](.windsurfrules), dan [.github/copilot-instructions.md](.github/copilot-instructions.md) yang menegaskan bahwa aksi browser hanya memakai **profil terisolasi milik kamu sendiri** (`confirm-account` + `designate-browser`), tidak mengambil alih jendela desktop utama.
2. **Eksekutor Lokal Satu Perintah ([run-plan.ps1](run-plan.ps1) / [run-plan.sh](run-plan.sh)):** Kalaupun ada agent tertentu yang membatasi akses browser (atau berjalan di sandbox tanpa browser lokal), suruh agent tersebut membuatkan draft & `data/action_plan.json`, lalu kamu cukup jalankan 1 perintah di perangkatmu:
   - Windows: `.\run-plan.ps1`
   - Linux / VPS / macOS: `./run-plan.sh`

   Script ini langsung menjalankan Like + Reply hidden background dengan jeda acak `5–60` detik, mencatat `confirm-posted` / `confirm-liked`, dan menampilkan `report` tanpa bergantung pada izin browser agent tersebut.

---

## 5. Daftar Perintah Lengkap (Cheat Sheet)

Ganti prefix binary sesuai OS:
- **Windows:** `.\target\release\x-social-draft-workflow.exe`
- **Linux / macOS:** `./target/release/x-social-draft-workflow`

```bash
# Lihat semua browser terpasang, profil yang ada, & port debug aktif
./target/release/x-social-draft-workflow list-browsers

# Hubungkan browser pilihan + buat shortcut/launcher + auto-deteksi user X
./target/release/x-social-draft-workflow connect-browser --browser brave --profile Agent

# Buat ulang shortcut/launcher profil terpisah
./target/release/x-social-draft-workflow create-shortcut

# Deteksi ulang user X yang sedang login di hidden background
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
