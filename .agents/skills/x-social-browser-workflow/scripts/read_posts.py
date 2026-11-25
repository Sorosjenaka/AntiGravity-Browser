import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_hub import (  # noqa: E402
    BROWSER_META,
    DEFAULT_CONFIG_PATH,
    agent_profiles_root,
    compute_random_delay,
    load_config,
    open_headless_session,
    resolve_browser_exe,
    sanitize_slug,
)

EXTRACT_POST_JS = r"""(() => {
    const statusMatch = location.pathname.match(/\/status\/(\d+)/);
    const statusId = statusMatch ? statusMatch[1] : null;
    const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
    let mainArticle = null;
    for (const art of articles) {
        const links = Array.from(art.querySelectorAll('a[href*="/status/"]'));
        if (statusId && links.some(a => (a.getAttribute('href') || '').includes('/status/' + statusId) && a.querySelector('time'))) {
            mainArticle = art;
            break;
        }
    }
    if (!mainArticle && articles.length > 0) {
        mainArticle = articles[0];
    }
    const prof = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    const emptyState = document.querySelector('[data-testid="empty_state_header_text"], [data-testid="error-detail"]');
    if (!mainArticle) {
        return {
            found: false,
            profileHref: prof ? prof.getAttribute('href') : null,
            url: location.href,
            title: document.title,
            bodySample: document.body ? document.body.innerText.slice(0, 1200) : '',
            emptyState: emptyState ? emptyState.innerText : null
        };
    }
    const userNames = mainArticle.querySelector('[data-testid="User-Name"]');
    const tweetTexts = Array.from(mainArticle.querySelectorAll('[data-testid="tweetText"]')).map(el => ({
        lang: el.getAttribute('lang'),
        text: el.innerText
    }));
    const card = mainArticle.querySelector('[data-testid="card.wrapper"]');
    const likeBtn = mainArticle.querySelector('button[data-testid="like"]');
    const unlikeBtn = mainArticle.querySelector('button[data-testid="unlike"]');
    const replyBtn = mainArticle.querySelector('button[data-testid="reply"]');
    return {
        found: true,
        profileHref: prof ? prof.getAttribute('href') : null,
        url: location.href,
        title: document.title,
        statusId: statusId,
        authorInfo: userNames ? userNames.innerText : null,
        tweetTexts: tweetTexts,
        cardText: card ? card.innerText : null,
        liked: !!unlikeBtn,
        hasLikeBtn: !!likeBtn,
        hasReplyBtn: !!replyBtn,
        articleText: mainArticle.innerText
    };
})()"""


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


def _is_terminal_post_state(val: dict | None) -> bool:
    if not isinstance(val, dict):
        return False
    body = val.get("bodySample") or ""
    title = val.get("title") or ""
    return bool(
        val.get("found")
        or val.get("emptyState")
        or ("Something went wrong" in body)
        or ("doesn’t exist" in body)
        or ("doesn't exist" in body)
        or ("Post Not Found" in title)
    )


async def _read_single_url(
    tab,
    idx: int,
    url: str,
    item_timeout: float,
) -> dict:
    async def _run():
        await tab.navigate(url, timeout=min(35.0, item_timeout))
        post_data = None
        for _ in range(18):
            await asyncio.sleep(0.8)
            val = await tab.evaluate_dom(EXTRACT_POST_JS, timeout=15.0)
            post_data = val
            if _is_terminal_post_state(val):
                break
        return post_data

    post_data = await asyncio.wait_for(_run(), timeout=item_timeout)
    return {
        "index": idx,
        "input_url": url,
        "ok": bool(isinstance(post_data, dict) and post_data.get("found")),
        "data": post_data,
    }


def _format_read_table(results: list[dict]) -> str:
    lines = [
        "| # | URL | Found | Author | Notes |",
        "|---:|---|---|---|---|",
    ]
    for r in results:
        d = r.get("data") or {}
        found = "OK" if r.get("ok") else "FAIL"
        author = (d.get("authorInfo") or "—").splitlines()[0].replace("|", "\\|")
        note = r.get("error") or d.get("emptyState") or ("ok" if r.get("ok") else "not_found")
        note = str(note).replace("|", "\\|").replace("\n", " ")[:80]
        url_clean = str(r.get("input_url", "")).replace("|", "\\|")
        lines.append(f"| {r['index']} | {url_clean} | {found} | {author} | {note} |")
    ok_count = sum(1 for r in results if r.get("ok"))
    lines.append(f"\nRead summary: {ok_count}/{len(results)} posts extracted.")
    return "\n".join(lines)


async def read_all(
    cfg: dict,
    urls: list[str],
    port_override: int | None,
    out_path: Path,
    min_delay: float = 0.8,
    max_delay: float = 2.5,
    concurrency: int = 3,
    item_timeout: float = 45.0,
    max_retries: int = 2,
    strict: bool = False,
):
    concurrency = max(1, min(6, int(concurrency)))
    sess = open_headless_session(cfg, port_override=port_override)
    await sess.start()
    sess_lock = asyncio.Lock()
    results_map: dict[int, dict] = {}
    sem = asyncio.Semaphore(concurrency if len(urls) > 1 else 1)

    async def _ensure_session():
        nonlocal sess
        async with sess_lock:
            if await sess.ping(timeout=6.0):
                return sess
            try:
                await sess.close()
            except Exception:
                pass
            sess = open_headless_session(cfg, port_override=port_override)
            await sess.start()
            return sess

    async def _relaunch_session():
        nonlocal sess
        async with sess_lock:
            try:
                if await sess.ping(timeout=5.0):
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

    async def _process_one(idx: int, url: str):
        async with sem:
            last_err = None
            for attempt in range(max_retries + 1):
                tab = None
                try:
                    cur_sess = await _ensure_session()
                    if concurrency > 1 and len(urls) > 1:
                        tab = await cur_sess.open_tab()
                        row = await _read_single_url(tab, idx, url, item_timeout)
                    else:
                        row = await _read_single_url(cur_sess, idx, url, item_timeout)
                    if row.get("ok") or attempt == max_retries:
                        results_map[idx] = row
                        status_lbl = "OK" if row.get("ok") else "FAIL"
                        print(f"[{idx}/{len(urls)}] {status_lbl} {url}")
                        return
                    last_err = "post_not_found_retrying"
                except Exception as exc:
                    last_err = str(exc)
                    print(f"[{idx}/{len(urls)}] retry {attempt + 1}/{max_retries} ({last_err})")
                    try:
                        await _relaunch_session()
                    except Exception:
                        pass
                finally:
                    if tab is not None:
                        try:
                            await tab.close()
                        except Exception:
                            pass
                if max_delay > 0:
                    await asyncio.sleep(compute_random_delay(min(0.4, min_delay), min(1.5, max_delay)))

            results_map[idx] = {
                "index": idx,
                "input_url": url,
                "ok": False,
                "error": last_err or "read_failed",
                "data": None,
            }
            print(f"[{idx}/{len(urls)}] FAIL {url}: {last_err}")

    try:
        if concurrency == 1 or len(urls) == 1:
            prev_delay = None
            for idx, url in enumerate(urls, 1):
                await _process_one(idx, url)
                if idx < len(urls) and max_delay > 0:
                    delay = compute_random_delay(min_delay, max_delay, prev_delay)
                    prev_delay = delay
                    await asyncio.sleep(delay)
        else:
            await asyncio.gather(*(_process_one(idx, url) for idx, url in enumerate(urls, 1)))

        ordered_results = [results_map[i] for i in range(1, len(urls) + 1)]
        ok_count = sum(1 for r in ordered_results if r.get("ok"))
        missing_urls = [r["input_url"] for r in ordered_results if not r.get("ok")]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "browser": cfg.get("browser"),
                    "engine": cfg.get("engine"),
                    "port_used": sess.port,
                    "total_urls": len(urls),
                    "success_count": ok_count,
                    "failed_count": len(urls) - ok_count,
                    "missing_urls": missing_urls,
                    "posts": ordered_results,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print()
        print(_format_read_table(ordered_results))
        print(f"Saved {len(urls)} observations to {out_path} (port {sess.port}, headless mode)")
        if strict and missing_urls:
            sys.exit(1)
    finally:
        await sess.close()


def collect_urls(urls_arg: list[str] | None, urls_file: str | None) -> list[str]:
    raw = []
    if urls_arg:
        raw.extend(urls_arg)
    if urls_file:
        for line in Path(urls_file).read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                raw.append(s)
    seen = set()
    out = []
    for u in raw:
        s = u.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    if not out:
        raise ValueError("Minimal 1 URL harus diberikan lewat --urls atau --urls-file")
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Read any number of X posts in an isolated headless browser (Firefox BiDi or Chromium CDP)."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Browser config JSON path")
    parser.add_argument("--browser", default=None, choices=["firefox", "brave", "chrome", "edge"], help="Override browser")
    parser.add_argument("--profile", default=None, help="Dedicated profile name")
    parser.add_argument("--port", type=int, default=None, help="Override debug port (auto if omitted)")
    parser.add_argument("--allow-hosts", default="localhost,127.0.0.1", help="Allowed hosts (Firefox BiDi)")
    parser.add_argument("--firefox-path", default=None, help="Explicit browser binary path")
    parser.add_argument("--out", default="data/observed_posts.json", help="Output JSON path")
    parser.add_argument("--urls", nargs="*", default=[], help="X status URLs (any count)")
    parser.add_argument("--urls-file", default=None, help="Text file containing X status URLs (one per line)")
    parser.add_argument("--min-delay", type=float, default=0.8, help="Min random delay between reads (seconds)")
    parser.add_argument("--max-delay", type=float, default=2.5, help="Max random delay between reads (seconds)")
    parser.add_argument("--concurrency", type=int, default=3, help="Parallel headless tabs for reading (1-6, default: 3)")
    parser.add_argument("--item-timeout", type=float, default=45.0, help="Per-URL timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries per failed URL")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any URL fails to load")
    args = parser.parse_args()

    urls = collect_urls(args.urls, args.urls_file)
    cfg = build_effective_config(args)
    asyncio.run(
        read_all(
            cfg,
            urls,
            args.port,
            Path(args.out),
            args.min_delay,
            args.max_delay,
            args.concurrency,
            args.item_timeout,
            args.max_retries,
            args.strict,
        )
    )


if __name__ == "__main__":
    main()
