# AntiGravity-Browser Instructions for Claude Code

Follow the workspace guide in [AGENTS.md](AGENTS.md) and `.claude/skills/x-social-browser-workflow/SKILL.md`.

Key workspace conventions:
1. Respond to the user in **Indonesian (Bahasa Indonesia)** clearly and concisely.
2. Write all X reply drafts strictly in **English (`en`)** (`7–9` words, including `project_short`, zero question marks `?`/`？`, emojis, quotation marks, or dashes).
3. Use the Rust CLI (`target\release\x-social-draft-workflow.exe` on Windows, `./target/release/x-social-draft-workflow` on Linux/macOS) together with `.agents/skills/x-social-browser-workflow/scripts/read_posts.py` and `engage_posts.py`.
4. Accept **any number of X links** given by the user (1, 5, 10, 50+) and preserve `engage_posts.py`'s default **5–60 second randomized pacing** between posts.
5. Browser automation uses only isolated workspace profiles (`AntiGravity-Browser/profiles/` or named Firefox profile) in **headless mode** over localhost (`127.0.0.1`) with strict `--remote-allow-origins=http://127.0.0.1:<port>`. If running in a draft-only/sandbox environment, export `data/action_plan.json` for local execution via `.\run-plan.ps1` or `./run-plan.sh`.
