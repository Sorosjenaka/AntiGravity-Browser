---
name: x-social-browser-workflow
description: >-
  Cross-OS isolated headless X workflow (Firefox WebDriver BiDi and Brave/Chrome/Edge CDP):
  configure a dedicated workspace browser profile, generate OS launchers, connect on a loopback
  debug port, detect the user's logged-in X account, read X posts, validate English drafts in SQLite,
  and execute verified Likes and Replies or export a local action plan without disturbing desktop work.
---

# X Social Browser Workflow

This skill operates exclusively on the user's own confirmed account inside an isolated workspace browser profile (`AntiGravity-Browser/profiles/` for Chromium, or a named `-P` profile for Firefox) using localhost loopback (`127.0.0.1`) with strict origin pinning (`--remote-allow-origins=http://127.0.0.1:<port>`). Never modify or read the user's personal browser profile directories.

## Step 0: Cross-OS Browser Profile & Account Setup

- **Windows CLI:** `.\target\release\x-social-draft-workflow.exe`
- **Linux / VPS / macOS CLI:** `./target/release/x-social-draft-workflow`
- **Python runner:** `.venv/bin/python` or `python3` (Linux/macOS), `.venv\Scripts\python.exe` or `python` (Windows)

Supported browsers: `firefox` (WebDriver BiDi), `brave`, `chrome`, `edge`, or `custom` (including macOS `.app` bundles).

- List installed browsers and workspace isolated profiles:
  ```bash
  ./target/release/x-social-draft-workflow list-browsers
  ```
- Connect a dedicated isolated profile, create an OS launcher (`.lnk` on Windows, `.desktop` + `.sh` on Linux, `.command` + `.sh` on macOS), and detect the logged-in X user in headless mode:
  ```bash
  ./target/release/x-social-draft-workflow connect-browser --browser brave --profile Agent
  ```
- Refresh launcher or re-run X user detection:
  ```bash
  ./target/release/x-social-draft-workflow create-shortcut
  ./target/release/x-social-draft-workflow auto-detect-account
  ```

## Step 1: Pre-Flight Status & Guidelines

```bash
./target/release/x-social-draft-workflow status
./target/release/x-social-draft-workflow show-prompt
```

## Step 2: Read X Posts in Headless Mode (Flexible Link Count)

Accept **any number of links** supplied by the user (1, 3, 10, 25, 50+, or more):

```bash
# Pass links directly:
python3 .agents/skills/x-social-browser-workflow/scripts/read_posts.py \
  --out data/observed_posts.json \
  --urls "<url1>" "<url2>"

# Or read from data/urls.txt (one URL per line):
python3 .agents/skills/x-social-browser-workflow/scripts/read_posts.py \
  --out data/observed_posts.json \
  --urls-file data/urls.txt
```

## Step 3: Record Posts & Validated English Drafts

For each observed post:
1. Save observed text to `data/post_<n>.txt` and run:
   ```bash
   ./target/release/x-social-draft-workflow add-post --url "<url>" --text-file data/post_<n>.txt --language <lang>
   ```
2. Author `data/drafts_<n>.json` following `reply_prompt.md`:
   - `"language": "en"` ALWAYS (even if the source post is in Indonesian or another language).
   - Exactly 3 distinct one-line statements (`7-9` words each, containing `project_short`).
   - Zero question marks (`?`/`？`), quotes, em/en dashes, or emojis.
3. Validate and save to SQLite:
   ```bash
   ./target/release/x-social-draft-workflow save-drafts --post-id <id> --file data/drafts_<n>.json
   ```

## Step 4: Execute Verified Likes & Replies or Provide Local Plan Runner

Prepare `data/action_plan.json` (`index`, `post_id`, `draft_id`, `status_id`, `url`, `reply_text`) for all user-supplied links.

- **When browser execution is enabled in this workspace**, run with default randomized `5.0–60.0`s pacing:
  ```bash
  python3 -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py \
    --plan data/action_plan.json \
    --out data/engage_results.json \
    --min-delay 5 \
    --max-delay 60
  ```
- **When running in a sandboxed or draft-only runtime**, hand off `data/action_plan.json` and instruct the user in Indonesian to execute `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).

## Step 5: Confirm & Print Report

For verified rows (`"liked": true` and `"replied": true`):
```bash
./target/release/x-social-draft-workflow confirm-posted --draft-id <draft_id>
./target/release/x-social-draft-workflow confirm-liked --post-id <post_id>
./target/release/x-social-draft-workflow report
```

Communicate all explanations and summaries to the user in clear Indonesian (Bahasa Indonesia).
