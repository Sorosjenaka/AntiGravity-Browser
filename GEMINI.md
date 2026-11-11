# AntiGravity-Browser Instructions for Gemini CLI & Antigravity

Follow the workspace guide in [AGENTS.md](AGENTS.md) and `.agents/skills/x-social-browser-workflow/SKILL.md`.

Key workspace conventions:
1. Respond to the user in **Indonesian (Bahasa Indonesia)** clearly and concisely without unnecessary follow-up questions.
2. Always write X reply drafts in **English (`en`)** with **7–9 words**, including `project_short`, and **zero question marks (`?`/`？`), emojis, quotation marks, or em/en dashes**.
3. Support **any number of X links** supplied by the user (`--urls` or `--urls-file`) and run `engage_posts.py` with the default **randomized 5–60 second delay** between posts.
4. Connect any user-selected browser (`firefox`, `brave`, `chrome`, `edge`, `custom`) cross-platform (Windows, Linux/VPS headless, macOS) using an **isolated workspace profile directory**, OS launcher (`.lnk`/`.desktop`/`.command`/`.sh`), and headless execution without disturbing the user's personal desktop browser.
5. If local browser execution is unavailable in the current runtime, output validated drafts and `data/action_plan.json` so the user can run `.\run-plan.ps1` (Windows) or `./run-plan.sh` (Linux/VPS/macOS).
