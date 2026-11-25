# Copilot Workspace Instructions

Read and follow `AGENTS.md` and `.agents/skills/x-social-browser-workflow/SKILL.md`:
- Always respond to the user in Indonesian (Bahasa Indonesia) clearly and directly.
- Run `list-browsers` and ask the user which browser they prefer (`chrome`, `edge`, `brave`, `firefox`, `custom`) before calling `connect-browser` (isolated workspace profile only).
- Ask the user whether they want a custom prompt (`set-prompt --file / --text / --append-rule`) or `reply_prompt.md`, show 3 sample outputs, and ask for approval or logic clarifications first.
- Accept any number of X links, run `engage_posts.py` with 5-60s randomized pacing + fault recovery + parallel live post-run audit (`verify_work.py`), and present Markdown `audit` + `report` tables.
- If browser execution is unavailable in your environment, generate `data/action_plan.json` so the user can run `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).
