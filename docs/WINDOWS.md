# Panduan Lengkap Windows (Desktop & PowerShell)

Panduan ini khusus untuk pengguna **Windows 10 / Windows 11**. Semua script berjalan 100% tersembunyi di background (`headless` + `CREATE_NO_WINDOW` + `SW_HIDE`) agar jendela browser dan pekerjaan utama kamu di Desktop tidak pernah terganggu.

> **Saran Terbaik:** Gunakan **Antigravity Desktop** atau **Antigravity CLI** (`agy`) dengan model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`).

---

## 1. Kebutuhan Awal di Windows

Pastikan sudah terpasang:
1. **Git for Windows**
2. **Rust (`cargo`)** — install via `winget install Rustlang.Rustup` atau dari `https://rustup.rs`
3. **Python 3.10+** — pastikan `python --version` berjalan di PowerShell
4. Minimal **1 browser** pilihan kamu: **Brave**, **Google Chrome**, **Microsoft Edge**, atau **Mozilla Firefox**

---

## 2. Install & Setup Otomatis (1 Menit)

Buka **PowerShell** di folder kerja kamu, lalu jalankan:

```powershell
git clone https://github.com/Sorosjenaka/AntiGravity-Browser.git
cd AntiGravity-Browser

# Pilih browser otomatis, atau tentukan langsung:
.\setup.ps1 -Browser auto
```

Jika ingin langsung memilih browser favorit kamu:

```powershell
.\setup.ps1 -Browser brave -Profile Agent
.\setup.ps1 -Browser chrome -Profile Agent
.\setup.ps1 -Browser edge -Profile Agent
.\setup.ps1 -Browser firefox -Profile Raid

# Atau browser Chromium custom lain:
.\setup.ps1 -Browser custom -ExePath "C:\Path\ke\browser.exe" -Profile Agent
```

> **Jika PowerShell memblokir `.ps1` (*ExecutionPolicy*):** jalankan sekali:
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Browser auto
> ```

Yang otomatis dikerjakan `setup.ps1`:
- Mengetes & compile CLI Rust ke `.\target\release\x-social-draft-workflow.exe`
- Memastikan modul Python `websockets` tersedia
- Membuat database lokal `history.sqlite3`
- Menghubungkan browser pilihan ke profil terisolasi (`%LOCALAPPDATA%\AntiGravity-Browser\profiles\...` untuk Chromium, atau profil `-P` untuk Firefox)
- Membuat **Shortcut Desktop Windows (`.lnk`)** di Desktop kamu & di folder `shortcuts/`
- Menjalankan **auto-deteksi akun X** di hidden background

---

## 3. Login X Pertama Kali Lewat Shortcut Desktop

Jika pada tahap setup akun X belum terdeteksi (`"logged_in": false`):

1. Cari shortcut baru di **Desktop Windows** kamu bernama **`AntiGravity X (<Browser> - <Profile>).lnk`**.
2. **Klik ganda (double-click)** shortcut itu — jendela browser profil terpisah akan terbuka ke `https://x.com/home` tanpa menyentuh browser kerja utama kamu.
3. **Login akun X** kamu sekali di jendela itu.
4. **Tutup jendela browser tersebut** (close total agar port debug & kunci profil siap diambil alih headless mode).
5. Jalankan ulang auto-deteksi:
   ```powershell
   .\target\release\x-social-draft-workflow.exe auto-detect-account
   ```

Sekarang `@handle` dan `display_name` kamu otomatis tercatat, dan selanjutnya agent selalu bekerja 100% di background tanpa memunculkan jendela apa pun.

---

## 4. Pakai Lewat AI Agent

1. Buka folder `AntiGravity-Browser` sebagai workspace di **Antigravity Desktop / CLI** (atau Gemini CLI, Codex, Claude, Hermes, Cursor, Windsurf).
2. Ketik:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Saat agent menjawab siap kerja, **tinggal kirim daftar link X kamu** dalam jumlah berapa pun (1, 3, 10, 25, 50+).
4. Agent otomatis membaca post, menulis 3 draft Bahasa Inggris tanpa tanda tanya (`7–9` kata), memilih draft bebas duplikat, melakukan Like + Reply dengan **jeda acak 5–60 detik** antar post, dan menampilkan tabel laporan.

---

## 5. Eksekutor Lokal Fallback (Jika Agent Dibatasi Sandbox)

Jika kamu memakai agent yang tidak diizinkan mengakses browser lokal, suruh agent membuat `data/action_plan.json`, lalu jalankan 1 perintah di PowerShell Windows:

```powershell
.\run-plan.ps1
```

---

## 6. Troubleshooting Singkat Windows

- **Browser utama masih terbuka saat agent jalan, apakah aman?**  
  Aman. Profil terpisah memakai `--user-data-dir` khusus atau `-no-remote -P <Profile>` di port debug otomatis (`9222–9235` atau port acak bebas). Browser kerja utama kamu tidak tersentuh.
- **Error `browser headless exited early`:**  
  Biasanya jendela login dari shortcut `.lnk` masih terbuka (mengunci folder profil tanpa port headless). Tutup dulu jendela login shortcut tersebut, lalu ulangi perintahnya.
- **Port bentrok:**  
  `browser_hub.py` otomatis mendeteksi port aktif lewat `DevToolsActivePort` / scan `9222–9235` atau mencari port TCP localhost baru yang kosong.
