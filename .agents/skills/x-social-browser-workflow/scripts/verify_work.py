import argparse
import asyncio
import json
import re
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
    open_headless_session,
    resolve_browser_exe,
    run_workflow_cli,
    sanitize_slug,
)

VERIFY_POST_JS = r"""((statusId, expectedHandle, replyText) => {
    const normalize = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const prof = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    const profileHref = prof ? prof.getAttribute('href') : null;
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
    if (!main) {
        const emptyState = document.querySelector('[data-testid="empty_state_header_text"], [data-testid="error-detail"]');
        return {
            ready: false,
            profileHref,
            emptyState: emptyState ? emptyState.innerText : null,
            liked: false,
            replied: false
        };
    }
    const unlikeBtn = main.querySelector('button[data-testid="unlike"]');
    const likeBtn = main.querySelector('button[data-testid="like"]');
    const targetHandle = normalize(expectedHandle);
    const targetReply = normalize(replyText);
    let replied = false;
    for (const art of articles) {
        const u = normalize(art.querySelector('[data-testid="User-Name"]')?.innerText || '');
        const t = normalize(art.querySelector('[data-testid="tweetText"]')?.innerText || '');
        if (targetHandle && u.includes(targetHandle) && targetReply && (t === targetReply || t.includes(targetReply))) {
            replied = true;
            break;
        }
    }
    return {
        ready: !!(unlikeBtn || likeBtn),
        profileHref,
        liked: !!unlikeBtn,
        replied,
        articlesCount: articles.length
    };
})"""


def _normalize_status_id(url_or_id: str) -> str:
    m = re.search(r"/status/(\d+)", str(url_or_id))
    return m.group(1) if m else str(url_or_id)


def build_effective_config(args) -> dict:
    if getattr(args, "browser", None):
        kind = args.browser.lower()
        meta = BROWSER_META[kind]
        exe = resolve_browser_exe(kind, getattr(args, "firefox_path", None))
        if not exe:
            raise FileNotFoundError(f"{meta['display']} executable not found")
        profile = getattr(args, "profile", None) or ("Raid" if meta["engine"] == "bidi" else "Agent")
        cfg = {
            "browser": kind,
            "display": meta["display"],
            "engine": meta["engine"],
            "executable": exe,
            "profile": profile,
            "port": getattr(args, "port", None) or meta["default_port"],
            "allow_hosts": getattr(args, "allow_hosts", "localhost,127.0.0.1"),
        }
        if meta["engine"] == "cdp":
            cfg["user_data_dir"] = str(agent_profiles_root() / f"{kind}-{sanitize_slug(profile)}")
            cfg["profile_directory"] = "Default"
        return cfg

    cfg = load_config(Path(args.config))
    if getattr(args, "profile", None):
        cfg["profile"] = args.profile
        if cfg["engine"] == "cdp":
            cfg["user_data_dir"] = str(
                agent_profiles_root() / f"{cfg['browser']}-{sanitize_slug(args.profile)}"
            )
    if getattr(args, "firefox_path", None):
        cfg["executable"] = args.firefox_path
    if getattr(args, "port", None):
        cfg["port"] = args.port
    if getattr(args, "allow_hosts", None):
        cfg["allow_hosts"] = args.allow_hosts
    return cfg


async def _verify_single_tab(
    sess,
    sem: asyncio.Semaphore,
    item: dict,
    expected_handle: str,
    timeout: float = 40.0,
) -> dict:
    idx = item.get("index", 0)
    status_id = str(item.get("status_id") or _normalize_status_id(item.get("url", "")))
    url = item["url"]
    reply_text = item.get("reply_text", "")
    expected_path = "/" + expected_handle.lstrip("@")

    async with sem:
        last_err = None
        for attempt_outer in range(2):
            tab = None
            try:
                tab = await sess.open_tab()

                async def _run():
                    await tab.navigate(url, timeout=30.0)
                    state = None
                    for attempt in range(16):
                        await asyncio.sleep(0.8)
                        state = await tab.evaluate_dom(
                            f"({VERIFY_POST_JS})({json.dumps(status_id)}, {json.dumps(expected_handle)}, {json.dumps(reply_text)})",
                            timeout=15.0,
                        )
                        if isinstance(state, dict) and state.get("ready"):
                            if state.get("liked") and state.get("replied"):
                                return state
                            # Scroll down on later polls so lazy-loaded reply threads appear in DOM
                            if attempt in (3, 7, 11):
                                try:
                                    await tab.evaluate_dom("window.scrollBy(0, 650);", timeout=8.0)
                                except Exception:
                                    pass
                        if isinstance(state, dict) and state.get("emptyState"):
                            return state
                    return state

                state = await asyncio.wait_for(_run(), timeout=timeout)
                ready = bool(state and state.get("ready"))
                acct_ok = (
                    bool(state and state.get("profileHref"))
                    and state.get("profileHref", "").lower() == expected_path.lower()
                )
                liked_ok = bool(state and state.get("liked"))
                replied_ok = bool(state and state.get("replied"))
                if ready or attempt_outer == 1:
                    return {
                        "index": idx,
                        "post_id": item.get("post_id"),
                        "draft_id": item.get("draft_id"),
                        "status_id": status_id,
                        "url": url,
                        "ready": ready,
                        "account_ok": acct_ok,
                        "live_liked": liked_ok,
                        "live_replied": replied_ok,
                        "error": None if ready else (state.get("emptyState") if state else "timeout_or_not_ready"),
                    }
            except Exception as exc:
                last_err = str(exc)
            finally:
                if tab is not None:
                    try:
                        await tab.close()
                    except Exception:
                        pass
            await asyncio.sleep(0.6)
        return {
            "index": idx,
            "post_id": item.get("post_id"),
            "draft_id": item.get("draft_id"),
            "status_id": status_id,
            "url": url,
            "ready": False,
            "account_ok": False,
            "live_liked": False,
            "live_replied": False,
            "error": last_err or "verification_failed",
        }


def _run_db_audit_json(cli_path: Path, db_path: Path | None, plan_path: Path | None, urls_file: Path | None) -> dict:
    args = ["audit", "--json"]
    if plan_path and plan_path.exists():
        args.extend(["--plan", str(plan_path)])
    elif urls_file and urls_file.exists():
        args.extend(["--urls-file", str(urls_file)])
    raw = run_workflow_cli(args, cli_path=cli_path, db_path=db_path)
    return json.loads(raw)


def sync_verified_to_db(
    rows: list[dict],
    cli_path: Path = DEFAULT_CLI_PATH,
    db_path: Path | None = None,
):
    for row in rows:
        if row.get("live_liked") and row.get("post_id") is not None:
            try:
                run_workflow_cli(["confirm-liked", "--post-id", str(row["post_id"])], cli_path=cli_path, db_path=db_path)
            except Exception:
                pass
        if row.get("live_replied") and row.get("draft_id") is not None:
            try:
                run_workflow_cli(["confirm-posted", "--draft-id", str(row["draft_id"])], cli_path=cli_path, db_path=db_path)
            except Exception:
                pass


def format_verification_table(report: dict) -> str:
    lines = [
        "| # | Post ID | Status ID | URL | Exec Like/Reply | Live X Like | Live X Reply | DB Audit | Status | Notes |",
        "|---:|---:|---|---|---|---|---|---|---|---|",
    ]
    rows = report.get("rows", [])
    if not rows:
        lines.append("| — | — | — | — | false/false | false | false | missing | FAIL | Plan kosong |")
    else:
        for r in rows:
            exec_str = f"{'OK' if r.get('exec_liked') else 'NO'}/{'OK' if r.get('exec_replied') else 'NO'}"
            live_like = "OK" if r.get("live_liked") else "NO"
            live_reply = "OK" if r.get("live_replied") else "NO"
            db_str = "OK" if r.get("db_complete") else "MISSING"
            verdict = "PASS" if r.get("all_ok") else "FAIL"
            notes = "; ".join(r.get("issues") or []) or "verified_complete"
            url_clean = str(r.get("url", "")).replace("|", "\\|")
            notes_clean = notes.replace("|", "\\|").replace("\n", " ")
            pid = r.get("post_id") if r.get("post_id") is not None else "—"
            lines.append(
                f"| {r.get('index')} | {pid} | {r.get('status_id')} | {url_clean} | {exec_str} | {live_like} | {live_reply} | {db_str} | {verdict} | {notes_clean} |"
            )
    lines.append("")
    lines.append(
        f"Parallel Audit Verdict: {'PASS' if report.get('all_passed') else 'FAIL'} "
        f"({report.get('passed_count', 0)}/{report.get('total_plan', 0)} complete, "
        f"{report.get('failed_count', 0)} missed/incomplete, concurrency={report.get('concurrency', 1)})"
    )
    return "\n".join(lines)


async def verify_execution_parallel(
    cfg: dict,
    plan: list[dict],
    expected_handle: str,
    exec_results: list[dict] | None = None,
    port_override: int | None = None,
    concurrency: int = 3,
    cli_path: Path = DEFAULT_CLI_PATH,
    db_path: Path | None = None,
    plan_path: Path | None = None,
    urls_file: Path | None = None,
    sync_db: bool = True,
) -> dict:
    concurrency = max(1, min(6, int(concurrency)))
    sem = asyncio.Semaphore(concurrency)

    exec_by_sid: dict[str, dict] = {}
    for er in exec_results or []:
        sid = str(er.get("status_id") or _normalize_status_id(er.get("url", "")))
        if sid:
            exec_by_sid[sid] = er
        elif er.get("index") is not None:
            exec_by_sid[f"idx:{er['index']}"] = er

    sess = open_headless_session(cfg, port_override=port_override)
    await sess.start()
    try:
        live_task = asyncio.gather(
            *(_verify_single_tab(sess, sem, item, expected_handle) for item in plan)
        )
        db_task = asyncio.to_thread(_run_db_audit_json, cli_path, db_path, plan_path, urls_file)
        live_rows, db_audit_before = await asyncio.gather(live_task, db_task)
    finally:
        await sess.close()

    if sync_db:
        sync_verified_to_db(live_rows, cli_path=cli_path, db_path=db_path)
        db_audit = _run_db_audit_json(cli_path, db_path, plan_path, urls_file)
    else:
        db_audit = db_audit_before

    db_by_sid = {str(it["status_id"]): it for it in db_audit.get("items", [])}
    merged_rows = []
    passed = 0
    for item, live in zip(plan, live_rows):
        sid = str(live["status_id"])
        er = exec_by_sid.get(sid) or exec_by_sid.get(f"idx:{item.get('index')}") or {}
        db_item = db_by_sid.get(sid) or {}

        exec_liked = bool(er.get("liked", False))
        exec_replied = bool(er.get("replied", False))
        db_complete = bool(db_item.get("complete", False))

        issues = []
        if live.get("error"):
            issues.append(f"live_err={live['error']}")
        if not live.get("account_ok"):
            issues.append("account_mismatch_or_logged_out")
        if not live.get("live_liked"):
            issues.append("missing_live_like")
        if not live.get("live_replied"):
            issues.append("missing_live_reply")
        if not db_complete:
            issues.extend(db_item.get("issues") or ["db_incomplete"])

        all_ok = (
            bool(live.get("live_liked"))
            and bool(live.get("live_replied"))
            and bool(live.get("account_ok"))
            and db_complete
        )
        if all_ok:
            passed += 1

        merged_rows.append(
            {
                "index": item.get("index"),
                "post_id": item.get("post_id"),
                "draft_id": item.get("draft_id"),
                "status_id": sid,
                "url": item["url"],
                "exec_liked": exec_liked,
                "exec_replied": exec_replied,
                "live_liked": bool(live.get("live_liked")),
                "live_replied": bool(live.get("live_replied")),
                "account_ok": bool(live.get("account_ok")),
                "db_complete": db_complete,
                "all_ok": all_ok,
                "issues": issues,
            }
        )

    total = len(plan)
    failed = total - passed
    return {
        "total_plan": total,
        "passed_count": passed,
        "failed_count": failed,
        "all_passed": total > 0 and failed == 0 and bool(db_audit.get("all_complete", False)),
        "concurrency": concurrency,
        "browser": cfg.get("browser"),
        "expected_handle": expected_handle,
        "db_audit": db_audit,
        "rows": merged_rows,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parallel post-completion verification across live isolated browser tabs and SQLite DB."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--browser", default=None, choices=["firefox", "brave", "chrome", "edge"])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--allow-hosts", default="localhost,127.0.0.1")
    parser.add_argument("--firefox-path", default=None)
    parser.add_argument("--cli-path", default=str(DEFAULT_CLI_PATH))
    parser.add_argument("--db", default=None)
    parser.add_argument("--handle", default=None)
    parser.add_argument("--plan", default="data/action_plan.json")
    parser.add_argument("--results", default="data/engage_results.json")
    parser.add_argument("--urls-file", default=None)
    parser.add_argument("--out", default="data/verify_report.json")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--no-sync-db", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = build_effective_config(args)
    cli_path = Path(args.cli_path)
    db_path = Path(args.db) if args.db else None
    plan_path = Path(args.plan)
    urls_file = Path(args.urls_file) if args.urls_file else None
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    exec_results = (
        json.loads(Path(args.results).read_text(encoding="utf-8"))
        if args.results and Path(args.results).exists()
        else []
    )

    expected_handle = args.handle
    if not expected_handle:
        raw = run_workflow_cli(["status"], cli_path=cli_path, db_path=db_path)
        expected_handle = json.loads(raw).get("account_handle")
    if not expected_handle:
        det = detect_and_confirm_account(cfg, cli_path=cli_path, db_path=db_path, port_override=args.port)
        if not det.get("logged_in"):
            raise RuntimeError(det.get("message") or "Akun X belum login.")
        expected_handle = det["handle"]

    report = asyncio.run(
        verify_execution_parallel(
            cfg=cfg,
            plan=plan,
            expected_handle=expected_handle,
            exec_results=exec_results,
            port_override=args.port,
            concurrency=args.concurrency,
            cli_path=cli_path,
            db_path=db_path,
            plan_path=plan_path,
            urls_file=urls_file,
            sync_db=not args.no_sync_db,
        )
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(format_verification_table(report))
    if args.strict and not report["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
