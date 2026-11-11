# Copilot Workspace Instructions

Read and follow `AGENTS.md` and `.agents/skills/x-social-browser-workflow/SKILL.md`:
- Always respond to the user in Indonesian (Bahasa Indonesia) cleanly and directly.
- This repository operates exclusively on the user's own X account (`confirm-account`) inside an isolated, hidden-background browser profile (`designate-browser`), leaving the user's main desktop browser untouched.
- Accept any number of X links supplied by the user, run `engage_posts.py` with the default 5-60s randomized pacing, and generate English (`en`) non-question drafts (7-9 words, `project_short`, no `?`/`？`/emojis/quotes/dashes).
- If browser execution is unavailable in your environment, generate `data/action_plan.json` so the user can execute locally via `.\run-plan.ps1`.
