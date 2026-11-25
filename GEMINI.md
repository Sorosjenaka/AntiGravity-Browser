# AntiGravity-Browser Instructions for Gemini CLI & Antigravity

Follow the workspace guide in [AGENTS.md](AGENTS.md) and `.agents/skills/x-social-browser-workflow/SKILL.md`.

Key workspace conventions:
1. Respond to the user in **Indonesian (Bahasa Indonesia)** clearly and concisely.
2. **Offer browser choice first:** Run `list-browsers` and ask the user which browser they want (`chrome`, `edge`, `brave`, `firefox`, or `custom`) before running `connect-browser` (do not force Brave silently).
3. **Offer prompt choice + sample output gate:** Ask whether the user wants their own custom prompt (`set-prompt --file / --text / --append-rule`) or the repo default (`reply_prompt.md`, `set-prompt --default`). Show 3 sample outputs in a Markdown table and confirm whether they match, need fixes, or need extra logic clarifications before proceeding.
4. Support **any number of X links** (`read_posts.py --concurrency 3`) and run `engage_posts.py` with default **randomized 5–60s pacing**, fault recovery, and **strict parallel post-completion verification** (`verify_work.py` + `x-social-draft-workflow audit --strict` + `report` Markdown tables).
5. Browser automation uses only isolated workspace profiles (`AntiGravity-Browser/profiles/` or named Firefox profile) in **headless anti-throttled mode** over localhost (`127.0.0.1`) with strict `--remote-allow-origins=http://127.0.0.1:<port>`. If local execution is restricted, export `data/action_plan.json` for `.\run-plan.ps1` / `./run-plan.sh`.
