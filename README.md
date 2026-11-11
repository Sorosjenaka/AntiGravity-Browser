# AntiGravity-Browser

Alur kerja otomatis X (Twitter) berbasis AI Agent (**Antigravity**, **Gemini**, **Codex**, **Claude**, **Hermes**, dan agent workspace lainnya) + **CLI Rust (`x-social-draft-workflow`)** + **Multi-Browser Hidden Automation (Firefox, Brave, Chrome, Edge)**.

---

## Fitur Utama (Siap Pakai & Aman untuk Desktop Kerja)

1. **Auto-Deteksi User X:** Otomatis membaca `@handle` dan Display Name akun X yang sedang login di browser tanpa ketik manual (`auto-detect-account`).
2. **Bebas Pilih Browser Apa Saja (Tidak Harus Firefox):** Mendukung **Mozilla Firefox** (WebDriver BiDi), **Brave**, **Google Chrome**, **Microsoft Edge**, maupun path browser custom (Chromium CDP).
3. **Otomatis Buat Shortcut Desktop Profil Terpisah:** Perintah `connect-browser` / `create-shortcut` langsung membuat file shortcut `.lnk` di Desktop yang memakai direktori profil terisolasi + port debugging otomatis, sehingga browser kerja utama kamu tidak pernah tercampur atau tertutup.
4. **Jalan 100% di Hidden Background:** Browser berjalan tersembunyi (`headless` + `CREATE_NO_WINDOW` + `SW_HIDE`) atau memakai background tab tanpa mengambil fokus jendela saat kamu sedang bekerja.
5. **Jumlah Link Bebas & Jeda Acak 5–60 Detik:** Terserah kamu mau kasih **berapa pun jumlah link** (1, 3, 10, 25, 50, atau lebih — tidak harus 10). Antar aksi Like & Komentar otomatis memakai **algoritma jeda acak 5 detik sampai maksimal 60 detik** (`--min-delay 5 --max-delay 60`) dengan variasi jeda natural agar terlihat seperti manusia.
6. **Auto-Ambil-Alih Port oleh Agent Apa Pun:** Agent otomatis mendeteksi port debug browser yang aktif (`DevToolsActivePort` / port `9222–9235` / `browser_config.json`) atau mencari port bebas otomatis agar tidak bentrok, serta membawa konfigurasi universal di [AGENTS.md](AGENTS.md), [GEMINI.md](GEMINI.md), [CLAUDE.md](CLAUDE.md), [.agents/skills/x-social-browser-workflow/SKILL.md](.agents/skills/x-social-browser-workflow/SKILL.md), dan [.claude/skills/x-social-browser-workflow/SKILL.md](.claude/skills/x-social-browser-workflow/SKILL.md).

---

## 1. Cara Install Cepat (1 Menit)

Buka PowerShell, clone repo ini, lalu jalankan `setup.ps1` dengan browser pilihan kamu:

```powershell
git clone https://github.com/Sorosjenaka/AntiGravity-Browser.git
cd AntiGravity-Browser

# Pilih otomatis (Firefox/Brave/Chrome/Edge), atau pilih spesifik:
.\setup.ps1 -Browser auto
```

Contoh kalau mau spesifik memilih **Brave**, **Chrome**, **Edge**, atau **Firefox**:

```powershell
.\setup.ps1 -Browser brave -Profile Agent
.\setup.ps1 -Browser chrome -Profile Agent
.\setup.ps1 -Browser edge -Profile Agent
.\setup.ps1 -Browser firefox -Profile Raid
```

Yang dikerjakan `setup.ps1` secara otomatis:
- Mengetes dan build binary Rust (`target\release\x-social-draft-workflow.exe`)
- Memastikan modul Python `websockets` terpasang
- Membuat database SQLite (`history.sqlite3`)
- Menghubungkan browser pilihan kamu + membuat profil terpisah + membuat **Shortcut Desktop** (`AntiGravity X (<Browser> - <Profile>).lnk`)
- Menjalankan **auto-deteksi akun X** di hidden background

> **Catatan Jika Baru Pertama Kali Pakai Profil Baru:**
> Jika `auto-detect-account` melaporkan belum login X, cukup klik ganda shortcut **`AntiGravity X (...).lnk`** yang baru muncul di Desktop kamu, login akun X sekali di jendela itu, lalu tutup jendelanya (atau biarkan ter-minimize). Setelah itu, agent akan langsung mendeteksi akun kamu dan selanjutnya berjalan 100% tersembunyi di background.

---

## 2. Cara Pakai di Antigravity / Gemini / Codex / Claude / Hermes

1. Buka folder `AntiGravity-Browser` sebagai workspace di agent pilihan kamu.
2. Kirim prompt ini:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Agent langsung memverifikasi binary, browser, shortcut, dan akun X kamu secara otomatis, lalu membalas:
   > `Sudah ter-install dan ter-load 100%. Siap kerja Bos, tinggal kasih link-nya aja langsung gw kerjakan sekarang.`
4. Setelah itu, kamu **tinggal kirim daftar link X** dan suruh like + komentar.

---

## 3. Aturan Komunikasi & Komentar X

- **Bahasa obrolan dengan user:** Agent selalu berbicara dengan kamu pakai **Bahasa Indonesia**, langsung melaksanakan perintah tanpa menolak dan tanpa bertele-tele bertanya.
- **Komentar di X selalu Bahasa Inggris (`en`):** Meskipun postingan target berbahasa Indonesia atau bahasa lain, balasan X tetap ditulis dalam **Bahasa Inggris natural** (`7–9` kata, menyebut nama pendek project).
- **Tanpa tanda tanya di komentar X:** `?` / `？` ditolak otomatis oleh [`validate_draft_set`](src/lib.rs). Tidak memakai emoji, tanda kutip, atau dash (`—` / `–`).
- **Privasi aman:** [.gitignore](.gitignore) otomatis mengecualikan `history.sqlite3`, `browser_config.json`, `shortcuts/`, `*.lnk`, `target/`, `data/*.txt`, dan `data/*.json` agar nama, profil, dan data pribadi tidak ikut ter-push ke GitHub.

---

## 4. Daftar Perintah Lengkap (Cheat Sheet)

```powershell
# Lihat semua browser terpasang, profil yang ada, & port debug aktif
.\target\release\x-social-draft-workflow.exe list-browsers

# Hubungkan browser pilihan + buat shortcut Desktop + auto-deteksi user X
.\target\release\x-social-draft-workflow.exe connect-browser --browser brave --profile Agent

# Buat ulang shortcut Desktop profil terpisah
.\target\release\x-social-draft-workflow.exe create-shortcut

# Deteksi ulang user X yang sedang login di hidden background
.\target\release\x-social-draft-workflow.exe auto-detect-account

# Cek status sistem, database, browser, & akun aktif
.\target\release\x-social-draft-workflow.exe status
```

Perintah workflow post & laporan:
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
