# Panduan Lengkap Windows (Desktop & PowerShell)

Panduan ini khusus untuk pengguna **Windows 10 / Windows 11**. Browser workspace berjalan dalam mode **headless terisolasi** (`-headless` / `--headless=new`) memakai folder profil terpisah sehingga browser kerja utama kamu di Desktop tidak pernah terganggu.

> **Saran Terbaik:** Gunakan **Antigravity Desktop** atau **Antigravity CLI** (`agy`) dengan model **`Gemini 3.8 Flash`** (`Gemini 3.8Flash`).

---

## 1. Kebutuhan Awal di Windows

Pastikan sudah terpasang:
1. **Git for Windows**
2. **Rust (`cargo`)** — install lewat `winget install Rustlang.Rustup` atau dari `https://rustup.rs`
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

> **Jika PowerShell belum mengizinkan script lokal:** aktifkan kebijakan standar Microsoft untuk user saat ini:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

Yang otomatis dikerjakan `setup.ps1`:
- Mengetes & compile CLI Rust ke `.\target\release\x-social-draft-workflow.exe`
- Memastikan modul Python `websockets` tersedia
- Membuat database lokal `history.sqlite3`
- Menghubungkan browser pilihan ke profil terisolasi (`~\AppData\Local\AntiGravity-Browser\profiles\...` untuk Chromium, atau profil `-P` untuk Firefox) dengan origin debug ketat (`http://127.0.0.1:<port>`)
- Membuat **Shortcut Desktop Windows (`.lnk`)** langsung dengan format standar Shell Link (`MS-SHLLINK`) di Desktop & folder `shortcuts/`
- Mendeteksi akun X aktif di mode headless

---

## 3. Login X Pertama Kali Lewat Shortcut Desktop

Jika pada tahap setup akun X belum terdeteksi (`"logged_in": false`):

1. Cari shortcut baru di **Desktop Windows** kamu bernama **`AntiGravity X (<Browser> - <Profile>).lnk`**.
2. **Klik ganda (double-click)** shortcut itu — jendela browser profil terpisah akan terbuka ke `https://x.com` sebagai **jendela browser normal (tanpa port debug aktif)** agar X tidak menolak login saat memasukkan username.
3. Tunggu halaman `x.com` termuat penuh (1–2 detik), klik **Sign in / Masuk**, lalu **login akun X** kamu sekali di jendela itu.
4. **Tutup jendela browser tersebut** secara penuh agar kunci profil dilepas dan siap dipakai mode headless.
5. Jalankan ulang deteksi akun:
   ```powershell
   .\target\release\x-social-draft-workflow.exe auto-detect-account
   ```

Sekarang `@handle` dan `display_name` kamu otomatis tercatat, dan selanjutnya agent berjalan dalam mode headless tanpa memunculkan jendela GUI.

### Alternatif Jika X Gagal Saat Memasukkan Username di Shortcut

Kadang X / Cloudflare menolak login pada profil browser baru yang belum punya riwayat/cookie sama sekali (`Something went wrong` atau gagal sebelum tahap password):

1. **Cara Tercepat untuk Firefox (`about:profiles`):**
   - Buka **Mozilla Firefox biasa** dari Start Menu / Taskbar.
   - Ketik **`about:profiles`** pada address bar lalu tekan **Enter**.
   - Cari profil **`Raid`** -> klik tombol **"Launch profile in new browser"** (*Buka profil di peramban baru*).
   - Login X lewat jendela Firefox biasa tersebut sampai masuk beranda (`x.com/home`).
   - Tutup penuh Firefox yang baru dibuka itu, lalu jalankan `.\target\release\x-social-draft-workflow.exe auto-detect-account`.
   *(Jika sebelumnya kamu sudah login X di profil Firefox default, kamu juga bisa menutup semua Firefox lalu menyalin isi folder profil default ke folder `*.Raid` yang tertera di halaman `about:profiles`.)*
2. **Untuk Brave / Chrome / Edge:**
   - Pastikan shortcut sudah diperbarui memakai versi repo terbaru (`.\target\release\x-social-draft-workflow.exe create-shortcut`) supaya bebas debug flag saat login.
   - Buka `https://x.com` lewat shortcut itu, muat halaman 1–2 detik atau login via tautan **Sign in with Google / Apple** jika akun X kamu tertaut, atau salin manual isi folder profil `Default` yang sudah terlogin X ke `~\AppData\Local\AntiGravity-Browser\profiles\<browser>-Agent\Default` (saat semua jendela browser ditutup).

---

## 4. Pakai Lewat AI Agent

1. Buka folder `AntiGravity-Browser` sebagai workspace di **Antigravity Desktop / CLI** (atau agent lain seperti Gemini CLI, Codex, Claude, Hermes, Cursor, Windsurf).
2. Ketik:
   ```text
   Install, load, dan cek semua setup workspace ini sampai 100% siap kerja.
   ```
3. Saat agent menjawab siap kerja, **tinggal kirim daftar link X kamu** dalam jumlah berapa pun (1, 3, 10, 25, 50+).
4. Agent otomatis membaca post, menulis 3 draft Bahasa Inggris tanpa tanda tanya (`7–9` kata), memilih draft bebas duplikat, melakukan Like + Reply dengan **jeda acak 5–60 detik** antar post, dan menampilkan tabel laporan.

---

## 5. Eksekutor Lokal Fallback (Untuk Agent Mode Draf / Sandbox)

Jika kamu memakai agent yang hanya membuat draf atau tidak memiliki akses browser lokal, suruh agent tersebut membuat `data/action_plan.json`, lalu jalankan 1 perintah di PowerShell Windows:

```powershell
.\run-plan.ps1
```

---

## 6. Troubleshooting Singkat Windows

- **Browser utama masih terbuka saat agent jalan, apakah aman?**  
  Aman. Profil workspace terisolasi menggunakan `--user-data-dir` khusus atau `-no-remote -P <Profile>` di port loopback terkonfigurasi (`127.0.0.1`). Browser pribadi kamu tidak tersentuh.
- **Error `browser headless exited early`:**  
  Biasanya jendela login dari shortcut `.lnk` masih terbuka dan mengunci direktori profil. Tutup dulu jendela login shortcut tersebut, lalu ulangi perintahnya.
- **Port bentrok:**  
  Jika port default terpakai, engine otomatis mencari port TCP loopback `127.0.0.1` yang kosong.
