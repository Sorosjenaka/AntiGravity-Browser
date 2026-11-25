# AntiGravity-Browser Instructions for Claude Code

Follow the workspace guide in [AGENTS.md](AGENTS.md) and `.claude/skills/x-social-browser-workflow/SKILL.md`.

Key workspace conventions:
1. Respond to the user in **Indonesian (Bahasa Indonesia)** clearly and concisely.
2. **Offer browser choice first:** Run `list-browsers` and ask the user which browser they want (`chrome`, `edge`, `brave`, `firefox`, or `custom`) before calling `connect-browser`.
3. **Offer prompt choice + sample preview gate:** Ask whether the user has a custom prompt (`set-prompt --file / --text / --append-rule`) or wants `reply_prompt.md` (`set-prompt --default`). Present 3 sample outputs and ask if anything needs editing or logic clarification before executing real links.
4. Use the Rust CLI (`target\release\x-social-draft-workflow.exe` on Windows, `./target/release/x-social-draft-workflow` on Linux/macOS) together with `read_posts.py`, `engage_posts.py`, and `verify_work.py` (strict parallel post-run audit + Markdown table reports).
5. Browser automation uses only isolated workspace profiles (`AntiGravity-Browser/profiles/` or named Firefox profile) in **anti-throttled headless mode** over localhost (`127.0.0.1`). If restricted, export `data/action_plan.json` for `.\run-plan.ps1` or `./run-plan.sh`.
