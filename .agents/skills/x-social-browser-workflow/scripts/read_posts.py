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
    open_hidden_session,
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
        if (statusId && links.some(a => a.getAttribute('href').includes('/status/' + statusId) && a.querySelector('time'))) {
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


async def read_all(
    cfg: dict,
    urls: list[str],
    port_override: int | None,
    out_path: Path,
    min_delay: float = 0.8,
    max_delay: float = 2.5,
):
    sess = open_hidden_session(cfg, port_override=port_override)
    await sess.start()
    results = []
    prev_delay = None
    try:
        for idx, url in enumerate(urls, 1):
            print(f"[{idx}/{len(urls)}] Reading {url}")
            await sess.navigate(url)
            post_data = None
            for _ in range(16):
                await asyncio.sleep(1.0)
                val = await sess.eval_js(EXTRACT_POST_JS)
                if isinstance(val, dict) and (
                    val.get("found")
                    or val.get("emptyState")
                    or ("Something went wrong" in (val.get("bodySample") or ""))
                    or ("doesn’t exist" in (val.get("bodySample") or ""))
                    or ("doesn't exist" in (val.get("bodySample") or ""))
                ):
                    post_data = val
                    break
                post_data = val
            results.append({"index": idx, "input_url": url, "data": post_data})
            if idx < len(urls) and max_delay > 0:
                delay = compute_random_delay(min_delay, max_delay, prev_delay)
                prev_delay = delay
                await asyncio.sleep(delay)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "browser": cfg.get("browser"),
                    "engine": cfg.get("engine"),
                    "port_used": sess.port,
                    "total_urls": len(urls),
                    "posts": results,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Saved {len(urls)} observations to {out_path} (port {sess.port}, hidden background)")
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
        description="Read any number of X posts in hidden background browser (Firefox BiDi or Chromium CDP)."
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
    args = parser.parse_args()

    urls = collect_urls(args.urls, args.urls_file)
    cfg = build_effective_config(args)
    asyncio.run(read_all(cfg, urls, args.port, Path(args.out), args.min_delay, args.max_delay))


if __name__ == "__main__":
    main()
