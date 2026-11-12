# AntiGravity-Browser Workspace Instructions

Compatible with **Antigravity Desktop/CLI**, **Gemini CLI**, **OpenAI Codex CLI**, **Claude Code**, **Hermes**, **Cursor**, **Windsurf**, and local developer assistants across **Windows**, **Linux Desktop / VPS**, and **macOS**.

This repository pairs a local Rust SQLite validation CLI (`x-social-draft-workflow`) with an isolated, headless WebDriver BiDi / Chrome DevTools Protocol (CDP) helper supporting **Mozilla Firefox**, **Brave**, **Google Chrome**, **Microsoft Edge**, or custom executables.

## Communication & Safety Boundaries

- **Chat Language:** Always communicate with the user in clear, natural **Indonesian (Bahasa Indonesia)**. Keep replies concise without unnecessary questions.
- **Draft Language:** All generated X reply options (`drafts_*.json`) must ALWAYS be written in **English (`en`)** per `reply_prompt.md`.
- **Workspace Isolation:** All automation runs strictly inside a dedicated isolated browser profile (`AntiGravity-Browser/profiles/` for Chromium, or `-no-remote -P <Profile>` for Firefox) over `127.0.0.1` loopback with strict `--remote-allow-origins=http://127.0.0.1:<port>`. It never reads or alters the user's personal desktop browser profile, personal passwords, or external system directories.
- **Draft-Only / Sandbox Fallback:** If the active agent runtime lacks local browser access or restricts direct social-media actions by policy, still complete setup/reading/drafting cleanly (`add-post`, `save-drafts`, `data/action_plan.json`), present the 3 validated English draft options, and instruct the user in Indonesian to execute `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS) directly on their machine.

## Initialization Check (Windows / Linux / VPS / macOS)

Detect OS first:
- **CLI Binary:** `.\target\release\x-social-draft-workflow.exe` (Windows) or `./target/release/x-social-draft-workflow` (Linux/macOS).
- **Python Binary:** `.venv\Scripts\python.exe` / `python` (Windows) or `.venv/bin/python3` / `python3` (Linux/macOS; `./setup.sh` handles PEP 668 via `.venv` automatically).

When the user asks to set up, load, or check workspace readiness:

1. Ensure the release binary exists (build via `cargo build --release` if absent).
2. Ensure Python `websockets` is available (via `./setup.sh` or `.\setup.ps1`).
3. Ensure `history.sqlite3` is initialized (`<CLI> init`).
4. Run `<CLI> status`:
   - If `dedicated_browser_designated` is `false` (or `browser_config.json` is absent), run `<CLI> connect-browser --browser auto` to configure the isolated profile, create the OS launcher (`.lnk`, `.desktop`+`.sh`, or `.command`+`.sh`), and check the X login session in headless mode.
   - If `dedicated_browser_designated` is `true` and `account_confirmed` is `false`, run `<CLI> auto-detect-account`.
5. Once ready, confirm in Indonesian:
   `Sudah ter-install dan ter-load 100%. Siap kerja Bos, tinggal kasih link-nya aja langsung gw kerjakan sekarang.`
6. If `logged_in` is `false`, guide the user in Indonesian to log in once using their clean generated OS launcher (`.lnk` / `.desktop` / `.command` / `.sh`, which launches without debug flags so X login succeeds cleanly) or via Firefox `about:profiles` (or `scp`/X11 on headless VPS as documented in `docs/LINUX.md`), close that window, and run `auto-detect-account`.

## X Workflow & Pacing Rules

1. Follow the workflow in `.agents/skills/x-social-browser-workflow/SKILL.md`.
2. **Flexible link count:** Accept any number of X links supplied by the user (1, 3, 10, 25, 50, or more — never require a fixed count of 10). Use `--urls` or `--urls-file data/urls.txt` in `read_posts.py`.
3. **Humanized randomized pacing (5–60s):** `engage_posts.py` defaults to `--min-delay 5 --max-delay 60` (`compute_random_delay`) between posts unless the user explicitly specifies another delay.
4. Read posts in headless mode, record them via `add-post`, save 3 distinct non-question English drafts (`7–9` words, `project_short`, no `?`/`？`/emojis/quotes/dashes) via `save-drafts`, verify execution (`engage_posts.py` or user running `run-plan`), confirm via `confirm-posted` / `confirm-liked`, and show the `report` table in Indonesian.
5. Keep personal credentials and runtime outputs out of git (`history.sqlite3`, `browser_config.json`, `shortcuts/`, `*.lnk`, `*.desktop`, `*.command`, `.venv/`, `target/`, `data/*.txt`, non-example `data/*.json`).
