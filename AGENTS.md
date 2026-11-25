# AntiGravity-Browser Workspace Instructions

Compatible with **Antigravity Desktop/CLI**, **Gemini CLI**, **OpenAI Codex CLI**, **Claude Code**, **Hermes**, **Cursor**, **Windsurf**, and local developer assistants across **Windows**, **Linux Desktop / VPS**, and **macOS**.

This repository pairs a local Rust SQLite validation & strict audit CLI (`x-social-draft-workflow`) with an isolated, anti-throttled headless WebDriver BiDi / Chrome DevTools Protocol (CDP) engine supporting **Google Chrome**, **Microsoft Edge**, **Brave Browser**, **Mozilla Firefox**, or custom executables.

## Communication & Safety Boundaries

- **Chat Language:** Always communicate with the user in clear, natural **Indonesian (Bahasa Indonesia)**.
- **Draft Language:** When using the repo default prompt (`reply_prompt.md`), all generated X reply options (`drafts_*.json`) must be written in **English (`en`)** per `reply_prompt.md`. If the user supplies a custom prompt and policy via `set-prompt`, follow the user's configured prompt & policy.
- **Workspace Isolation:** All automation runs strictly inside a dedicated isolated browser profile (`AntiGravity-Browser/profiles/` for Chromium, or `-no-remote -P <Profile>` for Firefox) over `127.0.0.1` loopback with strict `--remote-allow-origins=http://127.0.0.1:<port>`. It never reads or alters the user's personal desktop browser profile, personal passwords, or external system directories.
- **Draft-Only / Sandbox Fallback:** If the active agent runtime lacks local browser access or restricts direct social-media actions by policy, still complete setup/reading/drafting cleanly (`add-post`, `save-drafts`, `data/action_plan.json`), present the 3 validated draft options, and instruct the user in Indonesian to execute `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS) directly on their machine.

## Mandatory Interactive Setup & Pre-Work Confirmation Gates

When the user asks to install, load, set up, or check workspace readiness:

1. Ensure the release binary exists (`cargo build --release` if absent) and Python `websockets` is available.
2. Ensure `history.sqlite3` is initialized (`<CLI> init`).
3. **Browser Choice Gate (DO NOT force Brave silently):**
   - Run `<CLI> list-browsers` and display installed browsers (`Google Chrome`, `Microsoft Edge`, `Brave Browser`, `Mozilla Firefox`, or custom path).
   - If `dedicated_browser_designated` is `false` (or the user hasn't chosen a browser yet), **ask the user in Indonesian which browser they want to use** before running `<CLI> connect-browser --browser <chosen>`.
   - If `dedicated_browser_designated` is `true` and `account_confirmed` is `false`, run `<CLI> auto-detect-account`.
4. **Prompt Selection + Sample Output & Logic Clarification Gate:**
   - Run `<CLI> show-prompt --json` and **ask the user in Indonesian**:
     - Apakah mau memakai **prompt milik user sendiri** (tampung teks/file lalu simpan via `<CLI> set-prompt --file ...` atau `--text ...`) atau **prompt bawaan repo** (`reply_prompt.md`, via `<CLI> set-prompt --default`)?
   - Generate and display **3 concrete sample draft outputs** (dalam format tabel Markdown, termasuk panjang kata, probabilitas, skor bintang, dan opsi rekomendasi) sesuai prompt aktif, lalu tanyakan ke user:
     - *"Apakah output sampel dari prompt ini sudah cocok dan sesuai?"*
     - *"Apakah ada yang ingin ditambahkan atau diperbaiki?"*
     - *"Apakah ingin menambahkan penegasan untuk memperjelas logika?"*
   - If the user adds clarifications or rule adjustments, persist them immediately via `<CLI> set-prompt --append-rule "<penegasan>"` (or update prompt/policy flags), re-display the updated sample/rules, and lock it once confirmed.
5. Once browser, account, and prompt are confirmed, confirm in Indonesian:
   `Sudah ter-install, terkonfigurasi sesuai pilihan browser & prompt kamu, dan siap kerja 100%. Tinggal kirim daftar link X-nya aja sekarang.`
6. If `logged_in` is `false`, guide the user in Indonesian to log in once using their clean generated OS launcher (`.lnk` / `.desktop` / `.command` / `.sh`, which launches without debug flags so X login succeeds cleanly) or via Firefox `about:profiles` (or `scp`/X11 on headless VPS as documented in `docs/LINUX.md`), close that window (and ensure no tray background lock remains), and run `auto-detect-account`.

## X Workflow, Strict Auto-Check & Parallel Post-Completion Verification

1. Follow `.agents/skills/x-social-browser-workflow/SKILL.md`.
2. **Flexible link count:** Accept any number of X links supplied by the user (1, 3, 10, 25, 50, or more). Read them cleanly in parallel (`read_posts.py --concurrency 3 --urls-file data/urls.txt --strict`).
3. **Humanized randomized pacing (5–60s):** `engage_posts.py` defaults to `--min-delay 5 --max-delay 60` (`compute_random_delay`) between posts with per-item watchdog timeouts, automatic retries, session health recovery, and periodic tab recycling (optimized for Chrome, Edge, Brave, and Firefox).
4. **Mandatory Parallel Verification & Table Report After Completion:**
   - Every `engage_posts.py` run (and `run-plan.ps1` / `run-plan.sh`) automatically runs **parallel post-completion verification** (`verify_work.py` / `--verify-parallel --verify-concurrency 3 --auto-repair`) across concurrent headless browser tabs AND SQLite `audit`, repairing any missed item automatically if detected.
   - After confirming verified items (`confirm-posted` / `confirm-liked`), ALWAYS run `<CLI> audit --plan data/action_plan.json` (or `--urls-file data/urls.txt`) AND `<CLI> report`, and present the **complete Markdown tables** (`Parallel Audit Table` + `SQLite Report Table`) in Indonesian so the user can see 100% proof nothing was missed or delayed!
5. Keep personal credentials and runtime outputs out of git (`history.sqlite3`, `browser_config.json`, `custom_prompt.md`, `shortcuts/`, `*.lnk`, `*.desktop`, `*.command`, `.venv/`, `target/`, `data/*.txt`, non-example `data/*.json`).
