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

This skill operates exclusively on the user's own confirmed account inside an isolated workspace browser profile (`AntiGravity-Browser/profiles/` for Chromium, or a named `-P` profile for Firefox) using localhost loopback (`127.0.0.1`) with strict origin pinning (`--remote-allow-origins=http://127.0.0.1:<port>`). Never modify or inspect personal desktop browser profiles.

## Cross-OS Commands (`Windows` / `Linux` / `VPS` / `macOS`)

Use `.\target\release\x-social-draft-workflow.exe` on Windows or `./target/release/x-social-draft-workflow` on Linux/macOS:

- List installed browsers & isolated profiles first, then **ask the user which browser they want** (`chrome`, `edge`, `brave`, `firefox`, or `custom`):
  `x-social-draft-workflow list-browsers` -> `x-social-draft-workflow connect-browser --browser <chosen> --profile Agent`
- **Ask the user which prompt they want** (custom vs `reply_prompt.md`), persist via `set-prompt --default` or `set-prompt --file <PATH>` / `--append-rule "<text>"`, **show 3 sample outputs**, and confirm/refine logic before processing real links.
- Read any count of X posts in parallel (`--concurrency 3`): `read_posts.py --concurrency 3 --out data/observed_posts.json --urls-file data/urls.txt --strict`
- Record posts & validated drafts: `add-post`, `save-drafts`
- Execute fault-tolerant headless engagement (5–60s pacing, auto-retry, tab recycling) + built-in parallel post-run audit:
  `engage_posts.py --plan data/action_plan.json --out data/engage_results.json --verify-out data/verify_report.json --min-delay 5 --max-delay 60 --verify-concurrency 3 --strict`
- Run standalone parallel verification & strict SQLite completeness audit + Markdown tables:
  `verify_work.py --plan data/action_plan.json --results data/engage_results.json --concurrency 3 --strict`, `x-social-draft-workflow audit --plan data/action_plan.json --strict`, `x-social-draft-workflow report`.
- Fallback local executor (for sandboxed or draft-only assistants): write `data/action_plan.json` and ask the user to run `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).

Respond to the user in clear Indonesian (Bahasa Indonesia), showing all tables and sample confirmations clearly.
