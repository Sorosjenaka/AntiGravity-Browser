---
name: x-social-browser-workflow
description: >-
  Cross-OS isolated headless X workflow (Firefox WebDriver BiDi and Brave/Chrome/Edge CDP):
  configure a dedicated workspace browser profile, generate OS launchers, connect on a loopback
  debug port, detect the user's logged-in X account, read X posts, validate English drafts in SQLite,
  and execute verified Likes and Replies or export a local action plan without disturbing desktop work.
---

# X Social Browser Workflow

This skill operates exclusively on the user's own confirmed account inside an isolated workspace browser profile (`AntiGravity-Browser/profiles/` for Chromium, or a named `-P` profile for Firefox) using localhost loopback (`127.0.0.1`) with strict origin pinning (`--remote-allow-origins=http://127.0.0.1:<port>`). Never modify or inspect personal desktop browser profiles.

## Cross-OS Commands (`Windows` / `Linux` / `VPS` / `macOS`)

Use `.\target\release\x-social-draft-workflow.exe` on Windows or `./target/release/x-social-draft-workflow` on Linux/macOS:

- List installed browsers & isolated workspace profiles: `x-social-draft-workflow list-browsers`
- Connect chosen browser + create OS launcher (`.lnk`/`.desktop`/`.command`/`.sh`) + detect logged-in X user:
  `x-social-draft-workflow connect-browser --browser <auto|brave|chrome|edge|firefox|custom> --profile <NAME>`
- Refresh launcher or detect X account anytime: `create-shortcut` / `auto-detect-account`
- Read any count of X posts (1, 5, 10, 50+): `read_posts.py --out data/observed_posts.json --urls "<url1>" ...` (or `--urls-file data/urls.txt`)
- Record posts & English non-question drafts: `add-post`, `save-drafts` (`"language": "en"`, `7-9` words, `project_short`, zero `?`/`？`/emojis/quotes/dashes)
- Execute headless engagement with randomized 5–60s pacing:
  `engage_posts.py --plan data/action_plan.json --out data/engage_results.json --min-delay 5 --max-delay 60`
- Fallback local executor (for sandboxed or draft-only assistants): write `data/action_plan.json` and ask the user to run `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).
- Confirm & print report: `confirm-posted`, `confirm-liked`, `report`.

Respond to the user in clear Indonesian (Bahasa Indonesia), keeping all X post drafts in English (`en`).
