import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_hub import (  # noqa: E402
    BROWSER_META,
    DEFAULT_CLI_PATH,
    DEFAULT_CONFIG_PATH,
    agent_profiles_root,
    detect_and_confirm_account,
    load_config,
    open_hidden_session,
    resolve_browser_exe,
    run_workflow_cli,
    sanitize_slug,
)

WAIT_READY_JS = r"""((statusId) => {
    const prof = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
    let main = null;
    for (const art of articles) {
        const links = Array.from(art.querySelectorAll('a[href*="/status/"]'));
        if (links.some(a => a.getAttribute('href').includes('/status/' + statusId) && a.querySelector('time'))) {
            main = art;
            break;
        }
    }
    if (!main && articles.length > 0) main = articles[0];
    if (!main) return { ready: false, profileHref: prof ? prof.getAttribute('href') : null };
    const likeBtn = main.querySelector('button[data-testid="like"]');
    const unlikeBtn = main.querySelector('button[data-testid="unlike"]');
    const replyBtn = main.querySelector('button[data-testid="reply"]');
    return {
        ready: !!(likeBtn || unlikeBtn) && !!replyBtn,
        profileHref: prof ? prof.getAttribute('href') : null,
        alreadyLiked: !!unlikeBtn,
        hasLike: !!likeBtn,
        hasReply: !!replyBtn
    };
})"""


def resolve_account_handle(
    cfg: dict,
    cli_path: Path,
    db_path: Path | None,
    port_override: int | None,
) -> str:
    raw = run_workflow_cli(["status"], cli_path=cli_path, db_path=db_path)
    status = json.loads(raw)
    handle = status.get("account_handle")
    if handle:
        return handle

    # Auto-detect active X user in hidden background and record in SQLite
    detected = detect_and_confirm_account(
        cfg,
        cli_path=cli_path,
        db_path=db_path,
        port_override=port_override,
        confirm_in_db=True,
    )
    if not detected.get("logged_in"):
        raise RuntimeError(
            detected.get("message")
            or "No active X session found; click Desktop shortcut to login once."
        )
    return detected["handle"]


def build_effective_config(args) -> dict:
    if args.browser:
        kind = args.browser.lower()
        meta = BROWSER_META[kind]
        exe = resolve_browser_exe(kind, args.firefox_path)
        if not exe:
            raise FileNotFoundError(f"{meta['display']} executable not found")
        profile = args.profile or ("Raid" if meta["engine"] == "bidi" else "Agent")
        cfg = {
            "browser": kind,
            "display": meta["display"],
            "engine": meta["engine"],
            "executable": exe,
            "profile": profile,
            "port": args.port or meta["default_port"],
            "allow_hosts": args.allow_hosts,
        }
        if meta["engine"] == "cdp":
            cfg["user_data_dir"] = str(agent_profiles_root() / f"{kind}-{sanitize_slug(profile)}")
            cfg["profile_directory"] = "Default"
        return cfg

    cfg = load_config(Path(args.config))
    if args.profile:
        cfg["profile"] = args.profile
        if cfg["engine"] == "cdp":
            cfg["user_data_dir"] = str(
                agent_profiles_root() / f"{cfg['browser']}-{sanitize_slug(args.profile)}"
            )
    if args.firefox_path:
        cfg["executable"] = args.firefox_path
    if args.port:
        cfg["port"] = args.port
    if args.allow_hosts:
        cfg["allow_hosts"] = args.allow_hosts
    return cfg


async def engage_one(sess, item: dict, expected_handle: str):
    idx = item["index"]
    status_id = item["status_id"]
    url = item["url"]
    reply_text = item["reply_text"]
    expected_path = "/" + expected_handle.lstrip("@")
    print(f"\n=== [{idx}] post_id={item['post_id']} draft_id={item['draft_id']} ===")

    await sess.navigate(url)

    state = None
    for _ in range(20):
        await asyncio.sleep(1.0)
        state = await sess.eval_js(f"({WAIT_READY_JS})({json.dumps(status_id)})")
        if state and state.get("ready"):
            break

    if not state or not state.get("ready"):
        return {"index": idx, "liked": False, "replied": False, "status": "failed_load", "state": state}

    if (state.get("profileHref") or "").lower() != expected_path.lower():
        return {"index": idx, "liked": False, "replied": False, "status": "wrong_account", "state": state}

    liked_verified = False
    like_note = ""
    if state.get("alreadyLiked"):
        liked_verified = True
        like_note = "already_liked"
    else:
        await sess.eval_js(
            f"""(() => {{
                const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                let main = articles.find(art => Array.from(art.querySelectorAll('a[href*="/status/"]')).some(a => a.getAttribute('href').includes('/status/{status_id}') && a.querySelector('time'))) || articles[0];
                const btn = main.querySelector('button[data-testid="like"]');
                if (!btn) return false;
                btn.scrollIntoView({{block: 'center'}});
                btn.click();
                return true;
            }})()"""
        )
        for _ in range(8):
            await asyncio.sleep(0.6)
            chk = await sess.eval_js(f"({WAIT_READY_JS})({json.dumps(status_id)})")
            if chk and chk.get("alreadyLiked"):
                liked_verified = True
                like_note = "liked_now"
                break

    already_replied = await sess.eval_js(
        f"""(() => {{
            const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
            for (const art of articles) {{
                const u = art.querySelector('[data-testid="User-Name"]')?.innerText || '';
                const t = art.querySelector('[data-testid="tweetText"]')?.innerText || '';
                if (u.toLowerCase().includes({json.dumps(expected_handle.lower())}) && t.trim() === {json.dumps(reply_text)}) {{
                    return true;
                }}
            }}
            return false;
        }})()"""
    )
    if already_replied:
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "liked": liked_verified,
            "like_note": like_note,
            "replied": True,
            "reply_note": "already_replied",
        }

    clicked_reply = await sess.eval_js(
        f"""(() => {{
            const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
            let main = articles.find(art => Array.from(art.querySelectorAll('a[href*="/status/"]')).some(a => a.getAttribute('href').includes('/status/{status_id}') && a.querySelector('time'))) || articles[0];
            const btn = main.querySelector('button[data-testid="reply"]');
            if (!btn) return false;
            btn.scrollIntoView({{block: 'center'}});
            btn.click();
            return true;
        }})()"""
    )
    if not clicked_reply:
        return {"index": idx, "liked": liked_verified, "replied": False, "reply_note": "no_reply_btn"}

    ta_rect = None
    for _ in range(12):
        await asyncio.sleep(0.5)
        ta_rect = await sess.eval_js(
            """(() => {
                const dlg = document.querySelector('[role="dialog"]');
                if (!dlg) return null;
                const ta = dlg.querySelector('[data-testid="tweetTextarea_0"]');
                if (!ta) return null;
                ta.focus();
                const r = ta.getBoundingClientRect();
                return { x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2 };
            })()"""
        )
        if ta_rect:
            break

    if not ta_rect:
        return {"index": idx, "liked": liked_verified, "replied": False, "reply_note": "no_reply_dialog"}

    await sess.click_point(ta_rect["x"], ta_rect["y"])
    await asyncio.sleep(0.3)
    await sess.type_text(reply_text)
    await asyncio.sleep(0.8)

    btn_info = await sess.eval_js(
        """(() => {
            const dlg = document.querySelector('[role="dialog"]');
            if (!dlg) return { ok: false, reason: 'no_dialog' };
            const ta = dlg.querySelector('[data-testid="tweetTextarea_0"]');
            const btn = dlg.querySelector('[data-testid="tweetButton"]');
            if (!ta || !btn) return { ok: false, reason: 'missing_ta_or_btn' };
            return {
                ok: true,
                text: ta.innerText,
                disabled: !!btn.disabled,
                ariaDisabled: btn.getAttribute('aria-disabled')
            };
        })()"""
    )
    if (
        not btn_info
        or not btn_info.get("ok")
        or btn_info.get("disabled")
        or btn_info.get("ariaDisabled") == "true"
        or reply_text not in (btn_info.get("text") or "")
    ):
        return {
            "index": idx,
            "liked": liked_verified,
            "replied": False,
            "reply_note": "pre_submit_check_failed",
            "btn_info": btn_info,
        }

    await sess.eval_js(
        """(() => {
            const btn = document.querySelector('[role="dialog"] [data-testid="tweetButton"]');
            if (btn) btn.click();
        })()"""
    )

    reply_sent = False
    post_submit_state = None
    for _ in range(18):
        await asyncio.sleep(0.7)
        post_submit_state = await sess.eval_js(
            f"""(() => {{
                const dlg = document.querySelector('[role="dialog"]');
                const toast = document.querySelector('[data-testid="toast"]')?.innerText || null;
                const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                const visibleOwnReply = articles.some(art => {{
                    const u = art.querySelector('[data-testid="User-Name"]')?.innerText || '';
                    const t = art.querySelector('[data-testid="tweetText"]')?.innerText || '';
                    return u.toLowerCase().includes({json.dumps(expected_handle.lower())}) && t.trim() === {json.dumps(reply_text)};
                }});
                return {{ dialogOpen: !!dlg, toast, visibleOwnReply }};
            }})()"""
        )
        if not post_submit_state.get("dialogOpen") and (
            post_submit_state.get("visibleOwnReply")
            or (post_submit_state.get("toast") and "sent" in post_submit_state.get("toast", "").lower())
        ):
            reply_sent = True
            break

    print(f"  liked={liked_verified} replied={reply_sent}")
    return {
        "index": idx,
        "post_id": item["post_id"],
        "draft_id": item["draft_id"],
        "liked": liked_verified,
        "like_note": like_note,
        "replied": reply_sent,
        "reply_state": post_submit_state,
    }


async def run_engage(cfg: dict, plan: list[dict], expected_handle: str, port_override: int | None, out_path: Path, delay: float):
    results = []
    sess = open_hidden_session(cfg, port_override=port_override)
    await sess.start()
    try:
        for i, item in enumerate(plan):
            res = await engage_one(sess, item, expected_handle)
            results.append(res)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(results, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if i < len(plan) - 1:
                await asyncio.sleep(delay)
    finally:
        await sess.close()


def main():
    parser = argparse.ArgumentParser(description="Like and reply on X posts via hidden background browser.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Browser config JSON path")
    parser.add_argument("--browser", default=None, choices=["firefox", "brave", "chrome", "edge"], help="Override browser")
    parser.add_argument("--profile", default=None, help="Dedicated profile name")
    parser.add_argument("--port", type=int, default=None, help="Override debug port (auto if omitted)")
    parser.add_argument("--allow-hosts", default="localhost,127.0.0.1", help="Allowed hosts (Firefox BiDi)")
    parser.add_argument("--firefox-path", default=None, help="Explicit browser binary path")
    parser.add_argument("--cli-path", default=str(DEFAULT_CLI_PATH), help="Workflow CLI path")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path")
    parser.add_argument("--handle", default=None, help="Override X @handle (auto-read/auto-detect if omitted)")
    parser.add_argument("--plan", default="data/action_plan.json", help="Action plan JSON path")
    parser.add_argument("--out", default="data/engage_results.json", help="Output results JSON path")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay in seconds between posts")
    args = parser.parse_args()

    cfg = build_effective_config(args)
    expected_handle = args.handle or resolve_account_handle(
        cfg,
        Path(args.cli_path),
        Path(args.db) if args.db else None,
        args.port,
    )
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    asyncio.run(run_engage(cfg, plan, expected_handle, args.port, Path(args.out), args.delay))


if __name__ == "__main__":
    main()
