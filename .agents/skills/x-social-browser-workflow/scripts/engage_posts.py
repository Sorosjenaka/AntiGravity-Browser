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
    compute_random_delay,
    detect_and_confirm_account,
    load_config,
    open_headless_session,
    resolve_browser_exe,
    run_workflow_cli,
    sanitize_slug,
)
from verify_work import (  # noqa: E402
    format_verification_table,
    verify_execution_parallel,
)

WAIT_READY_JS = r"""((statusId) => {
    const prof = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
    let main = null;
    for (const art of articles) {
        const links = Array.from(art.querySelectorAll('a[href*="/status/"]'));
        if (links.some(a => (a.getAttribute('href') || '').includes('/status/' + statusId) && a.querySelector('time'))) {
            main = art;
            break;
        }
    }
    if (!main && articles.length > 0) main = articles[0];
    const emptyState = document.querySelector('[data-testid="empty_state_header_text"], [data-testid="error-detail"]');
    const bodyText = document.body ? document.body.innerText.slice(0, 800) : '';
    const terminalMissing = !!emptyState
        || bodyText.includes("doesn’t exist")
        || bodyText.includes("doesn't exist")
        || (document.title || '').includes("Post Not Found");
    if (!main) {
        return {
            ready: false,
            terminalMissing,
            emptyState: emptyState ? emptyState.innerText : null,
            profileHref: prof ? prof.getAttribute('href') : null
        };
    }
    const likeBtn = main.querySelector('button[data-testid="like"]');
    const unlikeBtn = main.querySelector('button[data-testid="unlike"]');
    const replyBtn = main.querySelector('button[data-testid="reply"]');
    return {
        ready: !!(likeBtn || unlikeBtn) && !!replyBtn,
        terminalMissing: false,
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


def _toast_indicates_success(toast: str | None) -> bool:
    if not toast:
        return False
    low = toast.lower()
    return any(
        tok in low
        for tok in ("sent", "your post", "dikirim", "terkirim", "balasan anda")
    )


def _toast_indicates_error(toast: str | None) -> bool:
    if not toast:
        return False
    low = toast.lower()
    return any(
        tok in low
        for tok in (
            "something went wrong",
            "whoops",
            "already said",
            "try again",
            "rate limit",
            "terjadi kesalahan",
            "coba lagi",
            "tidak dapat",
        )
    )


async def _check_own_reply_visible(sess, expected_handle: str, reply_text: str) -> bool:
    return bool(
        await sess.evaluate_dom(
            f"""(() => {{
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const expH = norm({json.dumps(expected_handle)});
                const expT = norm({json.dumps(reply_text)});
                const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                for (const art of articles) {{
                    const u = norm(art.querySelector('[data-testid="User-Name"]')?.innerText || '');
                    const t = norm(art.querySelector('[data-testid="tweetText"]')?.innerText || '');
                    if (u.includes(expH) && (t === expT || t.includes(expT))) {{
                        return true;
                    }}
                }}
                return false;
            }})()""",
            timeout=12.0,
        )
    )


async def engage_one(sess, item: dict, expected_handle: str, scroll_check: bool = False):
    idx = item["index"]
    status_id = str(item["status_id"])
    url = item["url"]
    reply_text = item["reply_text"]
    expected_path = "/" + expected_handle.lstrip("@")
    print(f"\n=== [{idx}] post_id={item['post_id']} draft_id={item['draft_id']} ===")

    await sess.navigate(url, timeout=35.0)

    state = None
    for _ in range(22):
        await asyncio.sleep(0.85)
        state = await sess.evaluate_dom(f"({WAIT_READY_JS})({json.dumps(status_id)})", timeout=15.0)
        if state and (state.get("ready") or state.get("terminalMissing")):
            break

    if state and state.get("terminalMissing"):
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": False,
            "replied": False,
            "terminal_error": True,
            "status": "post_unavailable",
            "state": state,
        }

    if not state or not state.get("ready"):
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": False,
            "replied": False,
            "status": "failed_load",
            "state": state,
        }

    if (state.get("profileHref") or "").lower() != expected_path.lower():
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": False,
            "replied": False,
            "terminal_error": True,
            "status": "wrong_account",
            "state": state,
        }

    liked_verified = False
    like_note = ""
    if state.get("alreadyLiked"):
        liked_verified = True
        like_note = "already_liked"
    else:
        like_rect = await sess.evaluate_dom(
            f"""(() => {{
                const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                let main = articles.find(art => Array.from(art.querySelectorAll('a[href*="/status/"]')).some(a => (a.getAttribute('href') || '').includes('/status/{status_id}') && a.querySelector('time'))) || articles[0];
                const btn = main ? main.querySelector('button[data-testid="like"]') : null;
                if (!btn) return null;
                btn.scrollIntoView({{block: 'center'}});
                btn.click();
                const r = btn.getBoundingClientRect();
                return {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }};
            }})()""",
            timeout=15.0,
        )
        for poll_i in range(8):
            await asyncio.sleep(0.55)
            chk = await sess.evaluate_dom(f"({WAIT_READY_JS})({json.dumps(status_id)})", timeout=12.0)
            if chk and chk.get("alreadyLiked"):
                liked_verified = True
                like_note = "liked_now"
                break
            if poll_i == 3 and like_rect:
                try:
                    await sess.click_point(like_rect["x"], like_rect["y"])
                except Exception:
                    pass

    already_replied = await _check_own_reply_visible(sess, expected_handle, reply_text)
    if not already_replied and scroll_check:
        try:
            await sess.evaluate_dom("window.scrollBy(0, 650);", timeout=8.0)
            await asyncio.sleep(0.8)
            already_replied = await _check_own_reply_visible(sess, expected_handle, reply_text)
        except Exception:
            pass

    if already_replied:
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": liked_verified,
            "like_note": like_note,
            "replied": True,
            "reply_note": "already_replied",
        }

    await asyncio.sleep(compute_random_delay(0.45, 1.25))

    reply_btn_rect = await sess.evaluate_dom(
        f"""(() => {{
            const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
            let main = articles.find(art => Array.from(art.querySelectorAll('a[href*="/status/"]')).some(a => (a.getAttribute('href') || '').includes('/status/{status_id}') && a.querySelector('time'))) || articles[0];
            const btn = main ? main.querySelector('button[data-testid="reply"]') : null;
            if (!btn) return null;
            btn.scrollIntoView({{block: 'center'}});
            btn.click();
            const r = btn.getBoundingClientRect();
            return {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }};
        }})()""",
        timeout=15.0,
    )
    if not reply_btn_rect:
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": liked_verified,
            "like_note": like_note,
            "replied": False,
            "reply_note": "no_reply_btn",
        }

    ta_rect = None
    for poll_dlg in range(14):
        await asyncio.sleep(0.45)
        ta_rect = await sess.evaluate_dom(
            """(() => {
                const dlg = document.querySelector('[role="dialog"]');
                if (!dlg) return null;
                const ta = dlg.querySelector('[data-testid="tweetTextarea_0"]');
                if (!ta) return null;
                ta.focus();
                const r = ta.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return null;
                return { x: r.left + Math.min(24, r.width / 2), y: r.top + Math.min(20, r.height / 2) };
            })()""",
            timeout=12.0,
        )
        if ta_rect:
            break
        if poll_dlg == 5:
            try:
                await sess.click_point(reply_btn_rect["x"], reply_btn_rect["y"])
            except Exception:
                pass

    if not ta_rect:
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": liked_verified,
            "like_note": like_note,
            "replied": False,
            "reply_note": "no_reply_dialog",
        }

    await asyncio.sleep(0.2)
    await sess.click_point(ta_rect["x"], ta_rect["y"])
    await asyncio.sleep(compute_random_delay(0.25, 0.55))
    await sess.type_text(reply_text)
    await asyncio.sleep(compute_random_delay(0.45, 1.0))

    btn_info = await sess.evaluate_dom(
        """(() => {
            const dlg = document.querySelector('[role="dialog"]');
            if (!dlg) return { ok: false, reason: 'no_dialog' };
            const ta = dlg.querySelector('[data-testid="tweetTextarea_0"]');
            const btn = dlg.querySelector('[data-testid="tweetButton"]');
            if (!ta || !btn) return { ok: false, reason: 'missing_ta_or_btn' };
            const r = btn.getBoundingClientRect();
            return {
                ok: true,
                text: ta.innerText,
                disabled: !!btn.disabled,
                ariaDisabled: btn.getAttribute('aria-disabled'),
                btnX: r.left + r.width / 2,
                btnY: r.top + r.height / 2
            };
        })()""",
        timeout=12.0,
    )

    # Fallback: if Draft.js did not activate after Input.insertText, re-focus and type key-by-key
    needs_key_fallback = (
        not btn_info
        or not btn_info.get("ok")
        or btn_info.get("disabled")
        or btn_info.get("ariaDisabled") == "true"
        or reply_text.strip() not in (btn_info.get("text") or "")
    )
    if needs_key_fallback and hasattr(sess, "type_text_keys"):
        existing_txt = (btn_info or {}).get("text") or ""
        if reply_text.strip() in existing_txt:
            # Draft.js already received text via insertText; a space + backspace wakes state
            await sess.click_point(ta_rect["x"], ta_rect["y"])
            await sess.type_text_keys(" ")
            await asyncio.sleep(0.15)
            if hasattr(sess, "_call") and getattr(sess, "session_id", None):
                await sess._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
                    sess.session_id,
                )
                await sess._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
                    sess.session_id,
                )
        else:
            await sess.evaluate_dom(
                """(() => {
                    const ta = document.querySelector('[role="dialog"] [data-testid="tweetTextarea_0"]');
                    if (ta) {
                        ta.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                    }
                })()""",
                timeout=10.0,
            )
            await sess.click_point(ta_rect["x"], ta_rect["y"])
            await sess.type_text_keys(reply_text)
        await asyncio.sleep(0.6)
        btn_info = await sess.evaluate_dom(
            """(() => {
                const dlg = document.querySelector('[role="dialog"]');
                if (!dlg) return { ok: false, reason: 'no_dialog' };
                const ta = dlg.querySelector('[data-testid="tweetTextarea_0"]');
                const btn = dlg.querySelector('[data-testid="tweetButton"]');
                if (!ta || !btn) return { ok: false, reason: 'missing_ta_or_btn' };
                const r = btn.getBoundingClientRect();
                return {
                    ok: true,
                    text: ta.innerText,
                    disabled: !!btn.disabled,
                    ariaDisabled: btn.getAttribute('aria-disabled'),
                    btnX: r.left + r.width / 2,
                    btnY: r.top + r.height / 2
                };
            })()""",
            timeout=12.0,
        )

    if (
        not btn_info
        or not btn_info.get("ok")
        or btn_info.get("disabled")
        or btn_info.get("ariaDisabled") == "true"
        or reply_text.strip() not in (btn_info.get("text") or "")
    ):
        return {
            "index": idx,
            "post_id": item["post_id"],
            "draft_id": item["draft_id"],
            "status_id": status_id,
            "url": url,
            "liked": liked_verified,
            "like_note": like_note,
            "replied": False,
            "reply_note": "pre_submit_check_failed",
            "btn_info": btn_info,
        }

    await sess.evaluate_dom(
        """(() => {
            const btn = document.querySelector('[role="dialog"] [data-testid="tweetButton"]');
            if (btn) btn.click();
        })()""",
        timeout=12.0,
    )

    reply_sent = False
    reply_note = ""
    post_submit_state = None
    for poll_sub in range(24):
        await asyncio.sleep(0.5)
        post_submit_state = await sess.evaluate_dom(
            f"""(() => {{
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const dlg = document.querySelector('[role="dialog"]');
                const toast = document.querySelector('[data-testid="toast"]')?.innerText || null;
                const expH = norm({json.dumps(expected_handle)});
                const expT = norm({json.dumps(reply_text)});
                const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                const visibleOwnReply = articles.some(art => {{
                    const u = norm(art.querySelector('[data-testid="User-Name"]')?.innerText || '');
                    const t = norm(art.querySelector('[data-testid="tweetText"]')?.innerText || '');
                    return u.includes(expH) && (t === expT || t.includes(expT));
                }});
                const btnStill = dlg ? dlg.querySelector('[data-testid="tweetButton"]') : null;
                const btnReady = !!(btnStill && !btnStill.disabled && btnStill.getAttribute('aria-disabled') !== 'true');
                return {{ dialogOpen: !!dlg, toast, visibleOwnReply, btnReady }};
            }})()""",
            timeout=12.0,
        )
        toast_txt = post_submit_state.get("toast") if post_submit_state else None
        if _toast_indicates_error(toast_txt):
            reply_note = f"submit_error_toast: {toast_txt}"
            break
        if post_submit_state and not post_submit_state.get("dialogOpen"):
            if post_submit_state.get("visibleOwnReply") or _toast_indicates_success(toast_txt):
                reply_sent = True
                reply_note = "replied_now"
                break
        if poll_sub == 5 and post_submit_state and post_submit_state.get("dialogOpen") and post_submit_state.get("btnReady"):
            try:
                await sess.click_point(btn_info["btnX"], btn_info["btnY"])
            except Exception:
                pass

    # If dialog closed cleanly with no error toast, scroll down once to check if reply rendered below fold
    if not reply_sent and not reply_note and post_submit_state and not post_submit_state.get("dialogOpen"):
        try:
            await sess.evaluate_dom("window.scrollBy(0, 650);", timeout=8.0)
            await asyncio.sleep(1.0)
            if await _check_own_reply_visible(sess, expected_handle, reply_text):
                reply_sent = True
                reply_note = "verified_after_dialog_close"
            else:
                reply_note = "post_submit_uncertain"
        except Exception:
            reply_note = "post_submit_uncertain"

    print(f"  liked={liked_verified} ({like_note or '-'}) replied={reply_sent} ({reply_note or '-'})")
    return {
        "index": idx,
        "post_id": item["post_id"],
        "draft_id": item["draft_id"],
        "status_id": status_id,
        "url": url,
        "liked": liked_verified,
        "like_note": like_note,
        "replied": reply_sent,
        "reply_note": reply_note or ("replied_now" if reply_sent else "not_confirmed"),
        "reply_state": post_submit_state,
    }


def _write_results(out_path: Path, results: list[dict]):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def run_engage(
    cfg: dict,
    plan: list[dict],
    expected_handle: str,
    port_override: int | None,
    out_path: Path,
    min_delay: float = 5.0,
    max_delay: float = 60.0,
    fixed_delay: float | None = None,
    item_timeout: float = 75.0,
    max_retries: int = 2,
    recycle_every: int = 12,
    verify_parallel: bool = True,
    verify_concurrency: int = 3,
    auto_repair: bool = True,
    verify_out_path: Path | None = None,
    cli_path: Path = DEFAULT_CLI_PATH,
    db_path: Path | None = None,
    plan_path: Path | None = None,
    strict: bool = False,
):
    if not plan:
        raise ValueError("Action plan kosong; minimal harus ada 1 link postingan X.")
    if fixed_delay is None and (min_delay < 0 or max_delay < min_delay):
        raise ValueError(f"Range jeda tidak valid: min={min_delay}, max={max_delay}")

    results_by_idx: dict[int, dict] = {}
    prev_delay = None
    total = len(plan)
    if fixed_delay is not None:
        print(f"Memproses {total} link dengan jeda tetap {fixed_delay:.2f} detik.")
    else:
        print(f"Memproses {total} link dengan jeda acak {min_delay:.1f}-{max_delay:.1f} detik antar link.")

    sess = open_headless_session(cfg, port_override=port_override)
    await sess.start()

    async def _ensure_healthy_session(force_restart: bool = False):
        nonlocal sess
        if not force_restart:
            try:
                if await sess.ping(timeout=7.0):
                    return sess
            except Exception:
                pass
        try:
            await sess.close()
        except Exception:
            pass
        sess = open_headless_session(cfg, port_override=port_override)
        await sess.start()
        return sess

    async def _run_item_with_retry(item: dict, is_repair: bool = False) -> dict:
        nonlocal sess
        idx = item["index"]
        last_res = None
        for attempt in range(max_retries + 1):
            try:
                sess = await _ensure_healthy_session(force_restart=(attempt > 0 and last_res is None))
                scroll_chk = is_repair or attempt > 0 or (
                    last_res is not None and last_res.get("reply_note") == "post_submit_uncertain"
                )
                res = await asyncio.wait_for(
                    engage_one(sess, item, expected_handle, scroll_check=scroll_chk),
                    timeout=item_timeout,
                )
                last_res = res
                if res.get("terminal_error"):
                    return res
                if res.get("liked") and res.get("replied"):
                    return res
                if attempt < max_retries:
                    print(f"  [retry {attempt + 1}/{max_retries}] item #{idx} belum lengkap ({res.get('status') or res.get('reply_note')}), mengulang...")
                    await asyncio.sleep(compute_random_delay(1.2, 3.0))
            except Exception as exc:
                print(f"  [recovery {attempt + 1}/{max_retries}] item #{idx} error: {exc}")
                last_res = {
                    "index": idx,
                    "post_id": item["post_id"],
                    "draft_id": item["draft_id"],
                    "status_id": item["status_id"],
                    "url": item["url"],
                    "liked": False,
                    "replied": False,
                    "status": "exception",
                    "error": str(exc),
                }
                try:
                    sess = await _ensure_healthy_session(force_restart=True)
                except Exception as restart_exc:
                    last_res["error"] = f"{exc}; restart_failed={restart_exc}"
                if attempt < max_retries:
                    await asyncio.sleep(compute_random_delay(1.5, 3.5))
        return last_res

    try:
        for i, item in enumerate(plan):
            if i > 0 and recycle_every > 0 and i % recycle_every == 0:
                try:
                    await sess.reset_tab()
                except Exception:
                    sess = await _ensure_healthy_session(force_restart=True)

            res = await _run_item_with_retry(item)
            wait_sec = 0.0
            if i < total - 1:
                wait_sec = (
                    round(fixed_delay, 2)
                    if fixed_delay is not None
                    else compute_random_delay(min_delay, max_delay, prev_delay)
                )
                prev_delay = wait_sec
                res["delay_after_sec"] = wait_sec
            else:
                res["delay_after_sec"] = 0.0

            results_by_idx[item["index"]] = res
            ordered_now = [results_by_idx[it["index"]] for it in plan if it["index"] in results_by_idx]
            _write_results(out_path, ordered_now)

            if wait_sec > 0:
                print(f"[{i + 1}/{total}] Jeda acak {wait_sec:.2f} detik sebelum link berikutnya...")
                await asyncio.sleep(wait_sec)

        # End-of-batch automatic pass for any incomplete non-terminal items
        incomplete = [
            it for it in plan
            if not results_by_idx[it["index"]].get("terminal_error")
            and not (
                results_by_idx[it["index"]].get("liked")
                and results_by_idx[it["index"]].get("replied")
            )
        ]
        if incomplete:
            print(f"\n[Auto-Check] Menemukan {len(incomplete)} item belum lengkap; menjalankan pass ulang terisolasi...")
            sess = await _ensure_healthy_session(force_restart=True)
            for it in incomplete:
                res_retry = await _run_item_with_retry(it, is_repair=True)
                res_retry["delay_after_sec"] = results_by_idx[it["index"]].get("delay_after_sec", 0.0)
                results_by_idx[it["index"]] = res_retry
                ordered_now = [results_by_idx[x["index"]] for x in plan if x["index"] in results_by_idx]
                _write_results(out_path, ordered_now)
                await asyncio.sleep(compute_random_delay(1.0, 3.0))
    finally:
        await sess.close()

    final_results = [results_by_idx[it["index"]] for it in plan]
    _write_results(out_path, final_results)

    if verify_parallel:
        print(f"\n[Parallel Audit] Memverifikasi seluruh {total} target secara paralel (concurrency={verify_concurrency})...")
        v_report = await verify_execution_parallel(
            cfg=cfg,
            plan=plan,
            expected_handle=expected_handle,
            exec_results=final_results,
            port_override=port_override,
            concurrency=verify_concurrency,
            cli_path=cli_path,
            db_path=db_path,
            plan_path=plan_path,
            sync_db=True,
        )

        if auto_repair and not v_report["all_passed"]:
            repair_indices = {
                r["index"]
                for r in v_report["rows"]
                if (not r["live_liked"] or not r["live_replied"])
                and r.get("account_ok", True)
                and not (results_by_idx[r["index"]].get("terminal_error"))
            }
            if repair_indices:
                repair_items = [it for it in plan if it["index"] in repair_indices]
                print(f"\n[Auto-Repair] Memperbaiki {len(repair_items)} item yang terdeteksi terlewat oleh audit paralel...")
                sess = open_headless_session(cfg, port_override=port_override)
                await sess.start()
                try:
                    for it in repair_items:
                        res_rep = await asyncio.wait_for(
                            engage_one(sess, it, expected_handle, scroll_check=True),
                            timeout=item_timeout,
                        )
                        res_rep["delay_after_sec"] = 0.0
                        results_by_idx[it["index"]] = res_rep
                        await asyncio.sleep(compute_random_delay(2.0, 5.0))
                finally:
                    await sess.close()

                final_results = [results_by_idx[it["index"]] for it in plan]
                _write_results(out_path, final_results)
                v_report = await verify_execution_parallel(
                    cfg=cfg,
                    plan=plan,
                    expected_handle=expected_handle,
                    exec_results=final_results,
                    port_override=port_override,
                    concurrency=verify_concurrency,
                    cli_path=cli_path,
                    db_path=db_path,
                    plan_path=plan_path,
                    sync_db=True,
                )

        if verify_out_path:
            verify_out_path.parent.mkdir(parents=True, exist_ok=True)
            verify_out_path.write_text(json.dumps(v_report, indent=2, ensure_ascii=False), encoding="utf-8")

        print()
        print(format_verification_table(v_report))
        if strict and not v_report["all_passed"]:
            raise RuntimeError(
                f"Strict parallel audit gagal: {v_report['passed_count']}/{v_report['total_plan']} lengkap."
            )
    return final_results


def main():
    parser = argparse.ArgumentParser(
        description="Like and reply on any number of X posts via isolated headless browser with randomized 5-60s pacing, fault recovery, and parallel post-run audit."
    )
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
    parser.add_argument("--verify-out", default="data/verify_report.json", help="Parallel verification report JSON path")
    parser.add_argument("--min-delay", type=float, default=5.0, help="Min random delay in seconds between posts (default: 5.0)")
    parser.add_argument("--max-delay", type=float, default=60.0, help="Max random delay in seconds between posts (default: 60.0)")
    parser.add_argument("--delay", type=float, default=None, help="Optional fixed delay override in seconds (disables random 5-60s)")
    parser.add_argument("--item-timeout", type=float, default=75.0, help="Per-item watchdog timeout in seconds (default: 75.0)")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retries per failed item (default: 2)")
    parser.add_argument("--recycle-every", type=int, default=12, help="Recycle tab every N items to prevent browser slowdown (default: 12)")
    parser.add_argument("--verify-concurrency", type=int, default=3, help="Parallel tab count for post-run verification (default: 3)")
    parser.add_argument("--no-verify-parallel", action="store_true", help="Skip parallel post-run live verification")
    parser.add_argument("--no-auto-repair", action="store_true", help="Do not automatically repair missed items detected by parallel verification")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if parallel audit detects incomplete/missed items")
    args = parser.parse_args()

    cfg = build_effective_config(args)
    cli_path = Path(args.cli_path)
    db_path = Path(args.db) if args.db else None
    plan_path = Path(args.plan)
    expected_handle = args.handle or resolve_account_handle(
        cfg,
        cli_path,
        db_path,
        args.port,
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    asyncio.run(
        run_engage(
            cfg,
            plan,
            expected_handle,
            args.port,
            Path(args.out),
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            fixed_delay=args.delay,
            item_timeout=args.item_timeout,
            max_retries=args.max_retries,
            recycle_every=args.recycle_every,
            verify_parallel=not args.no_verify_parallel,
            verify_concurrency=args.verify_concurrency,
            auto_repair=not args.no_auto_repair,
            verify_out_path=Path(args.verify_out) if args.verify_out else None,
            cli_path=cli_path,
            db_path=db_path,
            plan_path=plan_path,
            strict=args.strict,
        )
    )


if __name__ == "__main__":
    main()
