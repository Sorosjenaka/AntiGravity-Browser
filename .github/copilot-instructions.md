# Copilot Workspace Instructions

Read and follow `AGENTS.md` and `.agents/skills/x-social-browser-workflow/SKILL.md`:
- Always respond to the user in Indonesian (Bahasa Indonesia) clearly and directly.
- Operates exclusively on the user's confirmed X account (`confirm-account`) inside an isolated, headless workspace browser profile (`designate-browser`), leaving the user's personal desktop browser untouched.
- Accept any number of X links supplied by the user, run `engage_posts.py` with the default 5-60s randomized pacing, and generate English (`en`) non-question drafts (7-9 words, `project_short`, zero `?`/`？`/emojis/quotes/dashes).
- If browser execution is unavailable or restricted in your environment, generate `data/action_plan.json` so the user can run `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).
