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

## Step 0: Browser Connection, Shortcut & X Account Auto-Detection

Supported browsers: `firefox` (WebDriver BiDi), `brave`, `chrome`, `edge`, or `custom` (Chromium CDP).

- Inspect installed browsers, profiles, and active debug ports:
  ```powershell
  .\target\release\x-social-draft-workflow.exe list-browsers
  ```
- Connect to the user's chosen browser (creates isolated profile, generates Desktop `.lnk` shortcut, designates browser in SQLite, and auto-detects logged-in X user in hidden background):
  ```powershell
  .\target\release\x-social-draft-workflow.exe connect-browser --browser brave --profile Agent
  ```
  (Replace `brave` with `firefox`, `chrome`, `edge`, or `auto`.)
- Auto-detect logged-in X handle & display name in hidden background anytime:
  ```powershell
  .\target\release\x-social-draft-workflow.exe auto-detect-account
  ```
- Recreate/refresh Desktop `.lnk` shortcut:
  ```powershell
  .\target\release\x-social-draft-workflow.exe create-shortcut
  ```

### Port & Stealth Guarantees
- `browser_hub.py` automatically detects active debug ports (`DevToolsActivePort`, configured port in `browser_config.json`, or `9222..9235`) and attaches to a background tab without activating/focusing user windows.
- If no dedicated browser port is open, it allocates a free port automatically and spawns the isolated profile in hidden background (`-headless` / `--headless=new` + Windows `CREATE_NO_WINDOW` + `SW_HIDE`), never touching the user's active desktop browser.

## Step 1: Pre-Flight Check

```powershell
.\target\release\x-social-draft-workflow.exe status
.\target\release\x-social-draft-workflow.exe show-prompt
```

## Step 2: Read X Posts in Hidden Background

```powershell
python .agents/skills/x-social-browser-workflow/scripts/read_posts.py `
  --out data/observed_posts.json `
  --urls "<url1>" "<url2>" ...
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

## Step 4: Execute Verified Likes & Replies in Hidden Background

Create `data/action_plan.json` (`index`, `post_id`, `draft_id`, `status_id`, `url`, `reply_text`) and run:

```powershell
python -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py `
  --plan data/action_plan.json `
  --out data/engage_results.json
```

`engage_posts.py` auto-reads (or auto-detects) `@handle`, uses real WebDriver BiDi or Chromium CDP events, verifies `liked` + `visibleOwnReply`, and closes its tab/headless browser cleanly.

## Step 5: Confirm & Print Report in Indonesian

For verified rows (`"liked": true` and `"replied": true`):
```powershell
.\target\release\x-social-draft-workflow.exe confirm-posted --draft-id <draft_id>
.\target\release\x-social-draft-workflow.exe confirm-liked --post-id <post_id>
.\target\release\x-social-draft-workflow.exe report
```
