---
name: x-social-browser-workflow
description: >-
  Multi-browser X automation in hidden background (Firefox BiDi & Brave/Chrome/Edge CDP):
  auto-detect installed browsers, create isolated Desktop shortcuts, auto-takeover debug ports,
  auto-detect logged-in X user, read X posts, save validated non-question English drafts to SQLite,
  and run verified Likes & Replies without touching the user's desktop work window.
---

# X Social Browser Workflow

Use this skill whenever the user wants to connect a browser, create a Desktop shortcut, auto-detect their X account, or supply X (`x.com`) status URLs to read, draft, like, or reply.

## Step 0: Cross-OS Browser Connection, Shortcut/Launcher & X Account Auto-Detection

Supports **Windows**, **Linux Desktop / headless Linux VPS**, and **macOS**.
Use `<CLI>` = `.\target\release\x-social-draft-workflow.exe` (Windows) or `./target/release/x-social-draft-workflow` (Linux/macOS), and `<PYTHON>` = `.venv/bin/python` / `python3` (Linux/macOS) or `python` (Windows).

Supported browsers: `firefox` (WebDriver BiDi), `brave`, `chrome`, `edge`, or `custom` (Chromium CDP, including macOS `.app` bundles).

- Inspect installed browsers, profiles, and active debug ports:
  ```bash
  ./target/release/x-social-draft-workflow list-browsers
  ```
- Connect to the user's chosen browser (creates isolated profile, generates OS shortcut/launcher `.lnk`/`.desktop`/`.command`/`.sh`, designates browser in SQLite, and auto-detects logged-in X user in hidden background):
  ```bash
  ./target/release/x-social-draft-workflow connect-browser --browser brave --profile Agent
  ```
  (Replace `brave` with `firefox`, `chrome`, `edge`, or `auto`.)
- Auto-detect logged-in X handle & display name in hidden background anytime:
  ```bash
  ./target/release/x-social-draft-workflow auto-detect-account
  ```
- Recreate/refresh OS shortcut/launcher:
  ```bash
  ./target/release/x-social-draft-workflow create-shortcut
  ```

### Port & Stealth Guarantees
- `browser_hub.py` automatically detects active debug ports (`DevToolsActivePort`, configured port in `browser_config.json`, or `9222..9235`) and attaches to a background tab without activating/focusing user windows.
- If no dedicated browser port is open, it allocates a free port automatically and spawns the isolated profile in hidden background (`MOZ_HEADLESS=1` + `-headless` / `--headless=new`, `--disable-dev-shm-usage` on Linux VPS, Windows `CREATE_NO_WINDOW` + `SW_HIDE`, POSIX `start_new_session=True`), never touching the user's active desktop browser.

## Step 1: Pre-Flight Check

```powershell
.\target\release\x-social-draft-workflow.exe status
.\target\release\x-social-draft-workflow.exe show-prompt
```

## Step 2: Read X Posts in Hidden Background (Any Count)

Accept **any number of links** supplied by the user (1, 3, 10, 25, 50+, never assume 10):

```powershell
# Pass URLs directly (1 or several):
python .agents/skills/x-social-browser-workflow/scripts/read_posts.py `
  --out data/observed_posts.json `
  --urls "<url1>" "<url2>" ...

# Or for large lists, put 1 URL per line in data/urls.txt:
python .agents/skills/x-social-browser-workflow/scripts/read_posts.py `
  --out data/observed_posts.json `
  --urls-file data/urls.txt
```

## Step 3: Record Posts & Validated English Drafts

For each post:
1. Save observed text to `data/post_<n>.txt` and run:
   ```powershell
   .\target\release\x-social-draft-workflow.exe add-post --url "<url>" --text-file data/post_<n>.txt --language <lang>
   ```
2. Author `data/drafts_<n>.json` strictly following `reply_prompt.md`:
   - `"language": "en"` ALWAYS, even when the source post is Indonesian or another language.
   - Exactly 3 distinct one-line statements (`7-9` words each, including `project_short`).
   - ZERO question marks (`?`/`？`), ZERO quotes, ZERO em/en dashes, ZERO emojis.
3. Validate & store:
   ```powershell
   .\target\release\x-social-draft-workflow.exe save-drafts --post-id <id> --file data/drafts_<n>.json
   ```

## Step 4: Execute Verified Likes & Replies in Hidden Background (Random 5–60s Pacing)

Create `data/action_plan.json` (`index`, `post_id`, `draft_id`, `status_id`, `url`, `reply_text`) for all links provided by the user, then run:

```powershell
python -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py `
  --plan data/action_plan.json `
  --out data/engage_results.json `
  --min-delay 5 `
  --max-delay 60
```

`engage_posts.py` automatically uses the randomized `5.0–60.0`s multi-band anti-clustering delay algorithm (even if `--min-delay` / `--max-delay` are omitted), adds in-post micro-jitter, auto-reads/detects `@handle`, uses WebDriver BiDi or Chromium CDP events, verifies `liked` + `visibleOwnReply`, and closes its tab/headless browser cleanly.

If running in a restricted runtime without browser execution, let the user run `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS) locally after `data/action_plan.json` is written.

## Step 5: Confirm & Print Report in Indonesian

For verified rows (`"liked": true` and `"replied": true`):
```powershell
.\target\release\x-social-draft-workflow.exe confirm-posted --draft-id <draft_id>
.\target\release\x-social-draft-workflow.exe confirm-liked --post-id <post_id>
.\target\release\x-social-draft-workflow.exe report
```
