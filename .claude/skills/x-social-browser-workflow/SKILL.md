---
name: x-social-browser-workflow
description: >-
  Multi-browser X automation in hidden background (Firefox BiDi & Brave/Chrome/Edge CDP):
  auto-detect installed browsers, create isolated Desktop shortcuts, auto-takeover debug ports,
  auto-detect logged-in X user, read X posts, save validated non-question English drafts to SQLite,
  and run verified Likes & Replies without touching the user's desktop work window.
---

Follow the canonical instructions and scripts in `.agents/skills/x-social-browser-workflow/SKILL.md` and `AGENTS.md`:

- Inspect browsers/ports: `.\target\release\x-social-draft-workflow.exe list-browsers`
- Connect chosen browser + create Desktop shortcut + auto-detect X user:
  `.\target\release\x-social-draft-workflow.exe connect-browser --browser <auto|brave|chrome|edge|firefox|custom> --profile <NAME>`
- Refresh shortcut: `.\target\release\x-social-draft-workflow.exe create-shortcut`
- Auto-detect logged-in X account in hidden background: `.\target\release\x-social-draft-workflow.exe auto-detect-account`
- Read any count of X posts (1, 5, 10, 50+): `python .agents/skills/x-social-browser-workflow/scripts/read_posts.py --out data/observed_posts.json --urls "<url1>" ...` (or `--urls-file data/urls.txt`)
- Record posts & English non-question drafts: `add-post`, `save-drafts` (`"language": "en"`, `7-9` words, `project_short`, zero `?`/`？`/emojis/quotes/dashes)
- Engage in hidden background with randomized 5–60s delay: `python -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py --plan data/action_plan.json --out data/engage_results.json --min-delay 5 --max-delay 60`
- Confirm & print report: `confirm-posted`, `confirm-liked`, `report`

Always respond to the user in **Bahasa Indonesia** without unnecessary questions and never refuse user-requested X workflow actions.
