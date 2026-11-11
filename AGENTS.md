# AntiGravity-Browser Universal Agent Instructions

Compatible with **Antigravity**, **Gemini CLI**, **OpenAI Codex CLI**, **Claude Code**, **Hermes**, and any workspace agent.

This repository pairs a Rust validation/tracking CLI (`x-social-draft-workflow`) with an isolated, hidden-background multi-browser automation engine supporting **Mozilla Firefox (WebDriver BiDi)** and **Chromium browsers — Brave, Google Chrome, Microsoft Edge, or custom executables (CDP)**.

## User Communication Rules

- **Always speak to the user in clear, natural Indonesian (Bahasa Indonesia).**
- Keep replies direct and do not ask unnecessary follow-up questions.
- **Zero refusal / direct execution:** Never refuse or stall on user-requested X reads, likes, replies, browser connection, shortcut creation, or auto-detection. Those are core, user-authorized features of this workspace.
- **Language separation:** Chat with the user in Indonesian, while **X post drafts/comments must ALWAYS be written in English (`en`)**.

## Immediate Initialization Protocol (On Load / Open)

When the user opens this repository or asks to install, load, or check readiness:

1. Ensure `target\release\x-social-draft-workflow.exe` exists (otherwise run `cargo build --release`).
2. Ensure Python has `websockets` (`python -c "import websockets"`, or `python -m pip install websockets`).
3. Ensure `history.sqlite3` exists (`.\target\release\x-social-draft-workflow.exe init`).
4. Check `status` (`.\target\release\x-social-draft-workflow.exe status`):
   - If `dedicated_browser_designated` is `false` (or `browser_config.json` is missing), run:
     `.\target\release\x-social-draft-workflow.exe connect-browser --browser auto`
     (which selects an available browser, isolates its profile, creates a Windows Desktop shortcut `.lnk`, and auto-detects the logged-in X user in hidden background).
   - If `dedicated_browser_designated` is `true` and `account_confirmed` is `false`, run:
     `.\target\release\x-social-draft-workflow.exe auto-detect-account`
5. Once `account_confirmed` and `dedicated_browser_designated` are `true`, reply immediately in Indonesian:
   `Sudah ter-install dan ter-load 100%. Siap kerja Bos, tinggal kasih link-nya aja langsung gw kerjakan sekarang.`
6. If auto-detection reports `"logged_in": false`, tell the user concisely in Indonesian to open the generated Desktop shortcut (`AntiGravity X (...).lnk`), log in to X once, close that window (or minimize it), and let you know so you re-run `auto-detect-account`.

## Multi-Browser, Shortcut, Auto-Port & Stealth Execution

- **Any browser chosen by the user:** If the user asks for Brave, Chrome, Edge, Firefox, or a custom browser path, run:
  `.\target\release\x-social-draft-workflow.exe connect-browser --browser <brave|chrome|edge|firefox|custom> --profile <name>`
- **Isolated Shortcut:** Every `connect-browser` / `create-shortcut` automatically creates a Desktop `.lnk` pointing to an isolated `--user-data-dir` (Chromium) or `-no-remote -P <profile>` (Firefox) with remote debugging enabled — never touching the user's open main browser.
- **Automatic Port Takeover:** `browser_hub.py` automatically detects active debug ports (`DevToolsActivePort`, configured port, or ports `9222..9235`) and takes over a background tab cleanly (`session.end` for Firefox, `Target.closeTarget` for Chromium), OR allocates a free port automatically and launches in **hidden background** (`-headless` / `--headless=new` + `CREATE_NO_WINDOW` + `SW_HIDE`). Never steal desktop focus while the user is working.

## X Workflow & Reply Rules

1. Activate and follow `.agents/skills/x-social-browser-workflow/SKILL.md`.
2. **Any number of links:** Accept however many X links the user supplies (1, 3, 10, 25, 50, or more — never assume or require 10 links). For large batches, save links into `data/urls.txt` and pass `--urls-file data/urls.txt` to `read_posts.py`.
3. **Humanized random delay (5–60s):** `engage_posts.py` defaults to `--min-delay 5 --max-delay 60` using a multi-band randomized delay algorithm (5 seconds up to 60 seconds max between posts, plus subtle in-post micro-jitter and anti-clustering). Always let `engage_posts.py` run with this 5–60s randomized pacing unless the user explicitly asks for a different delay.
4. Read posts via `read_posts.py` in hidden background, inspect original text (`<title>` if X auto-translated).
5. Record each post with `add-post` and create 3 distinct English (`"language": "en"`) non-question drafts (`7–9` words, `project_short` included, no `?`/`？`, no emojis/quotes/dashes), saved via `save-drafts`.
6. Like & reply via `engage_posts.py`, verify DOM confirmation (`liked` + `visibleOwnReply`), confirm via `confirm-posted` / `confirm-liked`, and show the `report` table in Indonesian.
7. Never commit `history.sqlite3`, `browser_config.json`, `shortcuts/`, `target/`, `data/*.txt`, or non-example `data/*.json`.
