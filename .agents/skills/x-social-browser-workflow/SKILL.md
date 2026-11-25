---
name: x-social-browser-workflow
description: >-
  Cross-OS isolated headless X workflow (Chrome/Edge/Brave CDP and Firefox WebDriver BiDi):
  let the user choose their preferred browser and custom vs repo prompt (with sample outputs & logic
  clarification), configure an anti-throttled isolated profile, read X posts in parallel, validate
  drafts in SQLite, execute fault-tolerant Likes/Replies with 5-60s pacing, and run strict
  parallel post-completion verification with Markdown table reports.
---

# X Social Browser Workflow

This skill operates exclusively on the user's own confirmed account inside an isolated workspace browser profile (`AntiGravity-Browser/profiles/` for Chromium, or a named `-P` profile for Firefox) using localhost loopback (`127.0.0.1`) with strict origin pinning (`--remote-allow-origins=http://127.0.0.1:<port>`). Never modify or read the user's personal browser profile directories.

## Step 0: User Browser & Prompt Selection (Mandatory Before Connecting)

- **Windows CLI:** `.\target\release\x-social-draft-workflow.exe`
- **Linux / VPS / macOS CLI:** `./target/release/x-social-draft-workflow`
- **Python runner:** `.venv/bin/python` or `python3` (Linux/macOS), `.venv\Scripts\python.exe` or `python` (Windows)

1. List installed browsers and workspace isolated profiles first:
   ```bash
   ./target/release/x-social-draft-workflow list-browsers
   ```
2. **Offer browser choice to the user** (`chrome`, `edge`, `brave`, `firefox`, or `custom`) before running `connect-browser`:
   ```bash
   ./target/release/x-social-draft-workflow connect-browser --browser <chosen> --profile Agent
   ```
3. **Offer prompt choice (user custom vs repo default `reply_prompt.md`):**
   - If the user has their own prompt:
     ```bash
     ./target/release/x-social-draft-workflow set-prompt --file custom_prompt.md
     # Optional clarification / penegasan logika tambahan:
     ./target/release/x-social-draft-workflow set-prompt --append-rule "<user clarification>"
     ```
   - If the user wants the repo's built-in prompt:
     ```bash
     ./target/release/x-social-draft-workflow set-prompt --default
     ```
4. **Sample Output & Logic Confirmation Gate:**
   - Show 3 realistic sample draft outputs matching the active prompt/policy (`show-prompt --json`) and ask the user in Indonesian whether the output matches, needs edits, or needs extra logic clarifications (`--append-rule`).

## Step 1: Pre-Flight Status & Guidelines

```bash
./target/release/x-social-draft-workflow status
./target/release/x-social-draft-workflow show-prompt --json
```

## Step 2: Read X Posts in Isolated Parallel Headless Tabs (Flexible Link Count)

Accept **any number of links** supplied by the user (1, 3, 10, 25, 50+, or more):

```bash
python3 .agents/skills/x-social-browser-workflow/scripts/read_posts.py \
  --concurrency 3 \
  --out data/observed_posts.json \
  --urls-file data/urls.txt \
  --strict
```

## Step 3: Record Posts & Validated Drafts

For each observed post:
1. Save observed text to `data/post_<n>.txt` and run:
   ```bash
   ./target/release/x-social-draft-workflow add-post --url "<url>" --text-file data/post_<n>.txt --language <lang>
   ```
2. Author `data/drafts_<n>.json` strictly following the active prompt (`show-prompt --json`). When using `repo_default` (`reply_prompt.md`):
   - `"language": "en"` ALWAYS, 3 distinct one-line statements (`7-9` words each, containing `project_short`), zero `?`/`？`/quotes/dashes/emojis.
3. Validate and save to SQLite:
   ```bash
   ./target/release/x-social-draft-workflow save-drafts --post-id <id> --file data/drafts_<n>.json
   ```

## Step 4: Execute Fault-Tolerant Likes & Replies + Parallel Post-Run Verification

Prepare `data/action_plan.json` (`index`, `post_id`, `draft_id`, `status_id`, `url`, `reply_text`) for ALL user-supplied links.

- **When browser execution is enabled**, `engage_posts.py` runs with default randomized `5.0–60.0`s pacing, per-item timeouts/retries, session recovery, AND automatic **parallel post-completion live verification + auto-repair**:
  ```bash
  python3 -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py \
    --plan data/action_plan.json \
    --out data/engage_results.json \
    --verify-out data/verify_report.json \
    --min-delay 5 \
    --max-delay 60 \
    --verify-concurrency 3 \
    --strict
  ```
- **When running in a sandboxed or draft-only runtime**, hand off `data/action_plan.json` and instruct the user in Indonesian to execute `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).

## Step 5: Strict Completeness Audit & Markdown Table Reports

Always run strict parallel verification (standalone if needed via `verify_work.py`), sync DB confirmations, run `audit`, and print Markdown tables to the user:

```bash
python3 .agents/skills/x-social-browser-workflow/scripts/verify_work.py \
  --plan data/action_plan.json \
  --results data/engage_results.json \
  --out data/verify_report.json \
  --concurrency 3 \
  --strict
./target/release/x-social-draft-workflow audit --plan data/action_plan.json --strict
./target/release/x-social-draft-workflow report
```

Communicate all explanations, sample previews, audit tables, and summaries to the user in clear Indonesian (Bahasa Indonesia).
