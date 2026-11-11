# AntiGravity-Browser Instructions for Claude Code

Read and follow [AGENTS.md](AGENTS.md) and [.claude/skills/x-social-browser-workflow/SKILL.md](.claude/skills/x-social-browser-workflow/SKILL.md) completely.

Key mandates:
1. Always respond to the user in **Indonesian (Bahasa Indonesia)** without unnecessary questions and never refuse user-authorized browser/X commands.
2. Always write X comments/drafts in **English (`en`)** with **7–9 words**, including `project_short`, and **zero question marks (`?`/`？`), emojis, quotation marks, or em/en dashes**.
3. Use `x-social-draft-workflow.exe` (`list-browsers`, `connect-browser`, `create-shortcut`, `auto-detect-account`, `status`, `add-post`, `save-drafts`, `confirm-posted`, `confirm-liked`, `report`) plus `.agents/skills/x-social-browser-workflow/scripts/read_posts.py` and `engage_posts.py`.
4. Accept **any number of X links** given by the user (1, 5, 10, 50+, never fixed at 10) and keep `engage_posts.py`'s default **randomized delay algorithm (5–60 seconds)** between posts.
5. Everything browser-related runs via `browser_hub.py` with **automatic port detection/takeover** and **100% hidden background execution** (`CREATE_NO_WINDOW`, `SW_HIDE`, headless) so the user's desktop work is never interrupted.
