import argparse
import asyncio
import configparser
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import websockets

DEFAULT_CONFIG_PATH = Path("browser_config.json")
DEFAULT_CLI_PATH = Path("target/release/x-social-draft-workflow.exe")

BROWSER_META = {
    "firefox": {
        "display": "Mozilla Firefox",
        "engine": "bidi",
        "default_port": 9223,
        "candidates": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "which": ["firefox"],
    },
    "brave": {
        "display": "Brave Browser",
        "engine": "cdp",
        "default_port": 9224,
        "candidates": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"{LOCALAPPDATA}\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "which": ["brave", "brave-browser"],
    },
    "chrome": {
        "display": "Google Chrome",
        "engine": "cdp",
        "default_port": 9222,
        "candidates": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"{LOCALAPPDATA}\Google\Chrome\Application\chrome.exe",
        ],
        "which": ["chrome", "google-chrome", "chromium"],
    },
    "edge": {
        "display": "Microsoft Edge",
        "engine": "cdp",
        "default_port": 9225,
        "candidates": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"{LOCALAPPDATA}\Microsoft\Edge\Application\msedge.exe",
        ],
        "which": ["msedge", "edge"],
    },
}


def hidden_popen_kwargs() -> dict:
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {
        "startupinfo": si,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


_RNG = random.SystemRandom()


def compute_random_delay(
    min_sec: float = 5.0,
    max_sec: float = 60.0,
    prev_delay: float | None = None,
) -> float:
    """
    Human-like multi-band randomized delay algorithm strictly within [min_sec, max_sec].
    Default range: 5.0s to 60.0s with anti-clustering against prev_delay.
    """
    if min_sec < 0 or max_sec < min_sec:
        raise ValueError(f"Invalid delay range: min={min_sec}, max={max_sec}")
    if max_sec == min_sec:
        return round(min_sec, 2)

    span = max_sec - min_sec
    bands = [
        (0.00, 0.25, 0.25),  # quick cadence (e.g. 5s - 18.75s)
        (0.25, 0.65, 0.45),  # normal cadence (e.g. 18.75s - 40.75s)
        (0.65, 1.00, 0.30),  # resting pause (e.g. 40.75s - 60s)
    ]
    min_gap = min(3.0, span * 0.12)

    candidate = min_sec + _RNG.uniform(0.0, span)
    for _ in range(5):
        roll = _RNG.random()
        acc = 0.0
        lo, hi = 0.0, 1.0
        for b_lo, b_hi, weight in bands:
            acc += weight
            if roll <= acc:
                lo, hi = b_lo, b_hi
                break
        frac = _RNG.uniform(lo, hi)
        candidate = min_sec + frac * span
        if prev_delay is None or span <= 1.0 or abs(candidate - prev_delay) >= min_gap:
            break

    clamped = max(min_sec, min(max_sec, candidate))
    return round(clamped, 2)


def expand_candidate(path_tmpl: str) -> Path:
    local_app = os.environ.get("LOCALAPPDATA", "")
    return Path(path_tmpl.replace("{LOCALAPPDATA}", local_app))


def resolve_browser_exe(kind: str, override: str | None = None) -> str | None:
    if override:
        p = Path(override)
        return str(p) if p.exists() else shutil.which(override)
    meta = BROWSER_META.get(kind)
    if not meta:
        return None
    for tmpl in meta["candidates"]:
        p = expand_candidate(tmpl)
        if p.exists():
            return str(p)
    for w in meta["which"]:
        found = shutil.which(w)
        if found:
            return found
    return None


def list_firefox_profiles() -> list[dict]:
    appdata = os.environ.get("APPDATA", "")
    ini_path = Path(appdata) / "Mozilla" / "Firefox" / "profiles.ini"
    out = []
    if not ini_path.exists():
        return out
    cp = configparser.ConfigParser()
    cp.read(ini_path, encoding="utf-8")
    for sec in cp.sections():
        if sec.startswith("Profile") and cp.has_option(sec, "Name"):
            out.append(
                {
                    "name": cp.get(sec, "Name"),
                    "path": cp.get(sec, "Path", fallback=""),
                    "is_default": cp.get(sec, "Default", fallback="0") == "1",
                }
            )
    return out


def list_chromium_profiles(user_data_dir: Path) -> list[dict]:
    ls = user_data_dir / "Local State"
    out = []
    if not ls.exists():
        return out
    try:
        data = json.loads(ls.read_text(encoding="utf-8"))
        cache = data.get("profile", {}).get("info_cache", {})
        for dir_name, info in cache.items():
            out.append(
                {
                    "directory": dir_name,
                    "name": info.get("name", dir_name),
                }
            )
    except Exception:
        pass
    return out


def agent_profiles_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "AntiGravity-Browser" / "profiles"


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "Agent"


def probe_cdp_port(port: int, timeout: float = 0.4) -> dict | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("webSocketDebuggerUrl"):
                return {
                    "engine": "cdp",
                    "port": port,
                    "browser": data.get("Browser"),
                    "ws_url": data["webSocketDebuggerUrl"],
                }
    except Exception:
        pass
    return None


def cdp_has_x_tab(port: int, timeout: float = 0.4) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=timeout
        ) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))
            if isinstance(tabs, list):
                for tab in tabs:
                    url = (tab.get("url") or "").lower()
                    if "x.com" in url or "twitter.com" in url:
                        return True
    except Exception:
        pass
    return False


def probe_bidi_port(port: int, timeout: float = 0.4) -> dict | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/session", timeout=timeout
        ) as _:
            return {
                "engine": "bidi",
                "port": port,
                "ws_url": f"ws://127.0.0.1:{port}/session",
            }
    except urllib.error.HTTPError as exc:
        # Firefox WebDriver BiDi returns HTTP 400 Upgrade Required on GET /session
        if exc.code in (400, 426):
            return {
                "engine": "bidi",
                "port": port,
                "ws_url": f"ws://127.0.0.1:{port}/session",
            }
    except Exception:
        pass
    return None


def find_free_port(preferred: int | None = None) -> int:
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def read_devtools_active_port(user_data_dir: Path | None) -> int | None:
    if not user_data_dir:
        return None
    f = user_data_dir / "DevToolsActivePort"
    if not f.exists():
        return None
    try:
        first_line = f.read_text(encoding="utf-8").splitlines()[0].strip()
        port = int(first_line)
        return port if 1 <= port <= 65535 else None
    except Exception:
        return None


def _is_port_open(port: int, timeout: float = 0.12) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def scan_active_debug_ports(
    extra_ports: list[int] | None = None,
    user_data_dir: Path | None = None,
) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor

    ports = []
    dt_port = read_devtools_active_port(user_data_dir)
    if dt_port:
        ports.append(dt_port)
    for p in (extra_ports or []):
        if p and p not in ports:
            ports.append(p)
    for p in range(9222, 9236):
        if p not in ports:
            ports.append(p)

    with ThreadPoolExecutor(max_workers=len(ports) or 1) as ex:
        open_flags = list(ex.map(_is_port_open, ports))

    active = []
    for p, is_open in zip(ports, open_flags):
        if not is_open:
            continue
        info = probe_cdp_port(p, timeout=0.35) or probe_bidi_port(p, timeout=0.35)
        if info:
            active.append(info)
    return active


def discover_browsers() -> dict:
    browsers = {}
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    default_ud_dirs = {
        "brave": local_app / "BraveSoftware" / "Brave-Browser" / "User Data",
        "chrome": local_app / "Google" / "Chrome" / "User Data",
        "edge": local_app / "Microsoft" / "Edge" / "User Data",
    }
    for kind, meta in BROWSER_META.items():
        exe = resolve_browser_exe(kind)
        profiles = []
        if kind == "firefox":
            profiles = list_firefox_profiles()
        else:
            ud = default_ud_dirs.get(kind)
            if ud and ud.exists():
                profiles = list_chromium_profiles(ud)
        browsers[kind] = {
            "display": meta["display"],
            "engine": meta["engine"],
            "installed": exe is not None,
            "executable": exe,
            "desktop_profiles": profiles,
        }

    agent_dirs = []
    root = agent_profiles_root()
    if root.exists():
        agent_dirs = [str(p) for p in sorted(root.iterdir()) if p.is_dir()]

    return {
        "browsers": browsers,
        "agent_isolated_profiles": agent_dirs,
        "active_debug_ports": scan_active_debug_ports(),
    }


def ensure_firefox_profile(firefox_exe: str, profile_name: str):
    existing = {p["name"].lower(): p["name"] for p in list_firefox_profiles()}
    if profile_name.lower() in existing:
        return existing[profile_name.lower()]
    cmd = [firefox_exe, "-no-remote", "-headless", "-CreateProfile", profile_name]
    env = os.environ.copy()
    env["MOZ_HEADLESS"] = "1"
    subprocess.run(
        cmd,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_popen_kwargs(),
    )
    return profile_name


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    # Backward-compatible default matching Firefox Raid profile if installed
    ff = resolve_browser_exe("firefox")
    if ff:
        return {
            "browser": "firefox",
            "display": "Mozilla Firefox",
            "engine": "bidi",
            "executable": ff,
            "profile": "Raid",
            "port": 9223,
            "allow_hosts": "localhost,127.0.0.1",
        }
    for kind in ("brave", "chrome", "edge"):
        exe = resolve_browser_exe(kind)
        if exe:
            ud = agent_profiles_root() / f"{kind}-Agent"
            return {
                "browser": kind,
                "display": BROWSER_META[kind]["display"],
                "engine": "cdp",
                "executable": exe,
                "profile": "Agent",
                "user_data_dir": str(ud),
                "profile_directory": "Default",
                "port": BROWSER_META[kind]["default_port"],
            }
    raise FileNotFoundError(
        "Tidak ada browser yang terdeteksi (Firefox/Brave/Chrome/Edge). Jalankan connect-browser --exe-path <path>."
    )


def build_shortcut_spec(cfg: dict) -> tuple[str, str, str]:
    kind = cfg["browser"]
    profile = cfg.get("profile", "Agent")
    exe = cfg["executable"]
    port = int(cfg.get("port") or 9223)
    if cfg["engine"] == "bidi":
        args = (
            f'-no-remote -P "{profile}" '
            f'--remote-debugging-port {port} '
            f'--remote-allow-hosts localhost,127.0.0.1 '
            f'--remote-allow-origins http://127.0.0.1:{port} '
            f'https://x.com/home'
        )
    else:
        ud = cfg["user_data_dir"]
        pdir = cfg.get("profile_directory", "Default")
        args = (
            f'--user-data-dir="{ud}" '
            f'--profile-directory="{pdir}" '
            f'--remote-debugging-port={port} '
            f'--remote-allow-origins=* '
            f'--no-first-run --no-default-browser-check '
            f'https://x.com/home'
        )
    short_name = f"AntiGravity X ({kind.capitalize()} - {profile}).lnk"
    return short_name, exe, args


def create_windows_shortcut(cfg: dict, also_repo_dir: bool = True) -> dict:
    short_name, target_exe, args = build_shortcut_spec(cfg)
    desktop_dir = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    try:
        # Respect localized or redirected Windows Desktop path via Shell
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[Environment]::GetFolderPath('Desktop')",
            ],
            capture_output=True,
            text=True,
            **hidden_popen_kwargs(),
        )
        if res.returncode == 0 and res.stdout.strip():
            desktop_dir = Path(res.stdout.strip())
    except Exception:
        pass

    targets = [desktop_dir / short_name]
    if also_repo_dir:
        repo_short_dir = Path("shortcuts")
        repo_short_dir.mkdir(parents=True, exist_ok=True)
        targets.append((repo_short_dir / short_name).resolve())

    def ps_quote(val: str) -> str:
        return "'" + val.replace("'", "''") + "'"

    import base64

    created = []
    for lnk in targets:
        lnk.parent.mkdir(parents=True, exist_ok=True)
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"$sc = $ws.CreateShortcut({ps_quote(str(lnk))}); "
            f"$sc.TargetPath = {ps_quote(str(target_exe))}; "
            f"$sc.Arguments = {ps_quote(args)}; "
            f"$sc.WorkingDirectory = {ps_quote(str(Path(target_exe).parent))}; "
            f"$sc.Description = {ps_quote('Profil terpisah X AntiGravity (tidak mengganggu browser kerja utama)')}; "
            "$sc.Save()"
        )
        encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            **hidden_popen_kwargs(),
        )
        created.append(str(lnk))

    return {
        "shortcut_name": short_name,
        "desktop_shortcut": created[0] if created else None,
        "all_shortcuts": created,
        "arguments": args,
    }


def run_workflow_cli(args: list[str], cli_path: Path = DEFAULT_CLI_PATH, db_path: Path | None = None) -> str:
    exe = cli_path
    if not exe.exists():
        # Fall back to cargo run if release binary was not built yet
        cmd = ["cargo", "run", "--quiet", "--"]
    else:
        cmd = [str(exe)]
    if db_path:
        cmd.extend(["--db", str(db_path)])
    cmd.extend(args)
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        **hidden_popen_kwargs(),
    )
    if res.returncode != 0:
        raise RuntimeError(f"CLI error ({' '.join(cmd)}): {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


# ============================================================================
# Unified Hidden Background Browser Session (Firefox BiDi + Chromium CDP)
# ============================================================================


def from_bidi_val(v):
    if not isinstance(v, dict):
        return v
    t = v.get("type")
    if t in ("string", "number", "boolean"):
        return v.get("value")
    if t in ("null", "undefined"):
        return None
    if t == "array":
        return [from_bidi_val(x) for x in v.get("value", [])]
    if t == "object":
        return {k: from_bidi_val(val) for k, val in v.get("value", [])}
    return v


class _BiDiSession:
    def __init__(self, ws_url: str, port: int, owns_process: bool, proc: subprocess.Popen | None):
        self.ws_url = ws_url
        self.port = port
        self.owns_process = owns_process
        self.proc = proc
        self.ws = None
        self.ctx = None
        self._next_id = 1

    async def _call(self, method: str, params: dict | None = None):
        msg_id = self._next_id
        self._next_id += 1
        await self.ws.send(
            json.dumps({"id": msg_id, "method": method, "params": params or {}})
        )
        while True:
            raw = await self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                return data

    async def start(self):
        self.ws = await websockets.connect(
            self.ws_url, origin=f"http://127.0.0.1:{self.port}"
        )
        res = await self._call(
            "session.new", {"capabilities": {"alwaysMatch": {"webSocketUrl": True}}}
        )
        if res.get("type") == "error":
            raise RuntimeError(f"BiDi session.new failed: {res}")
        tab = await self._call(
            "browsingContext.create", {"type": "tab", "background": True}
        )
        self.ctx = tab["result"]["context"]
        if self.owns_process:
            # In headless mode, activating the isolated context improves input focus reliability
            await self._call("browsingContext.activate", {"context": self.ctx})

    async def navigate(self, url: str):
        await self._call(
            "browsingContext.navigate",
            {"context": self.ctx, "url": url, "wait": "complete"},
        )

    async def eval_js(self, expr: str):
        res = await self._call(
            "script.evaluate",
            {
                "expression": expr,
                "target": {"context": self.ctx},
                "awaitPromise": False,
            },
        )
        if res.get("type") == "error":
            raise RuntimeError(f"BiDi JS error: {res}")
        r = res.get("result", {})
        if r.get("type") == "exception":
            raise RuntimeError(f"JS exception: {r}")
        return from_bidi_val(r.get("result"))

    async def click_point(self, x: float, y: float):
        await self._call(
            "input.performActions",
            {
                "context": self.ctx,
                "actions": [
                    {
                        "type": "pointer",
                        "id": "mouse",
                        "parameters": {"pointerType": "mouse"},
                        "actions": [
                            {
                                "type": "pointerMove",
                                "x": int(round(x)),
                                "y": int(round(y)),
                                "origin": "viewport",
                            },
                            {"type": "pointerDown", "button": 0},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ],
            },
        )

    async def type_text(self, text: str):
        actions = []
        for ch in text:
            actions.append({"type": "keyDown", "value": ch})
            actions.append({"type": "keyUp", "value": ch})
        await self._call(
            "input.performActions",
            {
                "context": self.ctx,
                "actions": [{"type": "key", "id": "keyboard", "actions": actions}],
            },
        )

    async def close(self):
        try:
            if self.ctx and self.ws:
                await self._call("browsingContext.close", {"context": self.ctx})
        except Exception:
            pass
        try:
            if self.ws:
                if self.owns_process:
                    await self._call("browser.close")
                else:
                    await self._call("session.end")
        except Exception:
            pass
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
        if self.owns_process and self.proc:
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.terminate()


class _CDPSession:
    def __init__(self, ws_url: str, port: int, owns_process: bool, proc: subprocess.Popen | None):
        self.ws_url = ws_url
        self.port = port
        self.owns_process = owns_process
        self.proc = proc
        self.ws = None
        self.target_id = None
        self.session_id = None
        self._next_id = 1

    async def _call(self, method: str, params: dict | None = None, session_id: str | None = None):
        msg_id = self._next_id
        self._next_id += 1
        payload = {"id": msg_id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        await self.ws.send(json.dumps(payload))
        while True:
            raw = await self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id:
                return data

    async def start(self):
        self.ws = await websockets.connect(self.ws_url, max_size=16 * 1024 * 1024)
        created = await self._call(
            "Target.createTarget",
            {"url": "about:blank", "background": True},
        )
        if "error" in created:
            raise RuntimeError(f"CDP Target.createTarget failed: {created}")
        self.target_id = created["result"]["targetId"]
        attached = await self._call(
            "Target.attachToTarget",
            {"targetId": self.target_id, "flatten": True},
        )
        self.session_id = attached["result"]["sessionId"]
        await self._call("Page.enable", {}, self.session_id)
        await self._call("Runtime.enable", {}, self.session_id)

    async def navigate(self, url: str):
        res = await self._call("Page.navigate", {"url": url}, self.session_id)
        if res.get("result", {}).get("errorText"):
            raise RuntimeError(f"Navigation error: {res['result']['errorText']}")
        for _ in range(30):
            state = await self.eval_js("document.readyState")
            if state == "complete":
                break
            await asyncio.sleep(0.25)

    async def eval_js(self, expr: str):
        res = await self._call(
            "Runtime.evaluate",
            {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": False,
            },
            self.session_id,
        )
        if "error" in res:
            raise RuntimeError(f"CDP Runtime.evaluate error: {res['error']}")
        r = res.get("result", {})
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS exception: {r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    async def click_point(self, x: float, y: float):
        px = float(round(x))
        py = float(round(y))
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": px, "y": py, "button": "left", "clickCount": 1},
            self.session_id,
        )
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": px, "y": py, "button": "left", "clickCount": 1},
            self.session_id,
        )

    async def type_text(self, text: str):
        for ch in text:
            if ch == "\n":
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                    self.session_id,
                )
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                    self.session_id,
                )
            elif ord(ch) < 128 and ch.isprintable():
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "text": ch, "unmodifiedText": ch},
                    self.session_id,
                )
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "text": ch},
                    self.session_id,
                )
            else:
                await self._call("Input.insertText", {"text": ch}, self.session_id)

    async def close(self):
        try:
            if self.target_id and self.ws:
                await self._call("Target.closeTarget", {"targetId": self.target_id})
        except Exception:
            pass
        try:
            if self.owns_process and self.ws:
                await self._call("Browser.close")
        except Exception:
            pass
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
        if self.owns_process and self.proc:
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.terminate()


def _start_hidden_process(cfg: dict, port: int) -> tuple[subprocess.Popen, str]:
    exe = cfg["executable"]
    if not Path(exe).exists() and not shutil.which(exe):
        raise FileNotFoundError(f"Browser executable not found: {exe}")

    if cfg["engine"] == "bidi":
        profile = ensure_firefox_profile(exe, cfg.get("profile", "Raid"))
        allow_hosts = cfg.get("allow_hosts", "localhost,127.0.0.1")
        env = os.environ.copy()
        env["MOZ_HEADLESS"] = "1"
        proc = subprocess.Popen(
            [
                exe,
                "-no-remote",
                "-P",
                profile,
                "-headless",
                "--remote-debugging-port",
                str(port),
                "--remote-allow-hosts",
                allow_hosts,
                "--remote-allow-origins",
                f"http://127.0.0.1:{port}",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_popen_kwargs(),
        )
        for _ in range(36):
            time.sleep(0.5)
            probe = probe_bidi_port(port, timeout=1.0)
            if probe:
                return proc, probe["ws_url"]
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Firefox headless exited early (code {proc.returncode}). "
                    f"Pastikan jendela login profil '{profile}' sudah ditutup sebelum menjalankan mode background."
                )
        proc.terminate()
        raise RuntimeError(f"Timed out waiting for headless Firefox BiDi on port {port}")

    # Chromium CDP (Brave, Chrome, Edge)
    ud = Path(cfg["user_data_dir"])
    ud.mkdir(parents=True, exist_ok=True)
    pdir = cfg.get("profile_directory", "Default")
    proc = subprocess.Popen(
        [
            exe,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "--window-position=-32000,-32000",
            f"--user-data-dir={ud}",
            f"--profile-directory={pdir}",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_popen_kwargs(),
    )
    for _ in range(36):
        time.sleep(0.4)
        probe = probe_cdp_port(port, timeout=1.0)
        if probe:
            return proc, probe["ws_url"]
        if proc.poll() is not None:
            raise RuntimeError(
                f"Browser headless exited early (code {proc.returncode}). "
                f"Jika jendela login profil '{ud}' masih terbuka tanpa debug port, tutup dulu jendela login-nya."
            )
    proc.terminate()
    raise RuntimeError(f"Timed out waiting for headless Chromium CDP on port {port}")


def open_hidden_session(cfg: dict, port_override: int | None = None):
    """
    Auto-takeover logic for any agent (Antigravity, Gemini, Codex, Claude, Hermes):
    1. If an active matching debug port already exists (configured port, DevToolsActivePort, or 9222-9235),
       attach directly to it in background without touching user's main desktop window.
    2. Otherwise, allocate a free localhost port and launch the configured browser profile
       100% hidden in background (headless + CREATE_NO_WINDOW + SW_HIDE).
    """
    engine = cfg["engine"]
    ud_path = Path(cfg["user_data_dir"]) if cfg.get("user_data_dir") else None
    dt_port = read_devtools_active_port(ud_path)
    pref_port = port_override or cfg.get("port")

    active_ports = scan_active_debug_ports(
        extra_ports=[int(pref_port)] if pref_port else None,
        user_data_dir=ud_path,
    )
    for info in active_ports:
        p = info["port"]
        if info["engine"] != engine:
            continue
        if engine == "bidi":
            if (pref_port and p == int(pref_port)) or port_override == p:
                return _BiDiSession(info["ws_url"], p, owns_process=False, proc=None)
        else:
            if p == dt_port or p == int(pref_port or -1) or cdp_has_x_tab(p):
                return _CDPSession(info["ws_url"], p, owns_process=False, proc=None)

    # Step 2: Nothing listening for our isolated browser profile -> pick a free port and launch completely hidden
    port = find_free_port(int(pref_port) if pref_port else None)
    proc, ws_url = _start_hidden_process(cfg, port)
    if engine == "bidi":
        return _BiDiSession(ws_url, port, owns_process=True, proc=proc)
    return _CDPSession(ws_url, port, owns_process=True, proc=proc)


# ============================================================================
# Auto-Detect Logged-In X Account
# ============================================================================

DETECT_HOME_JS = r"""(() => {
    const prof = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    const loginBtn = document.querySelector('[data-testid="loginButton"], a[href="/login"], a[href="/i/flow/login"], input[autocomplete="username"]');
    const sw = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
    return {
        url: location.href,
        title: document.title,
        profileHref: prof ? prof.getAttribute('href') : null,
        switcherText: sw ? sw.innerText : null,
        hasLoginPrompt: !prof && (
            !!loginBtn
            || location.pathname === '/'
            || location.pathname.includes('/login')
            || location.pathname.includes('/i/flow/login')
        )
    };
})()"""

DETECT_PROFILE_JS = r"""(() => {
    const un = document.querySelector('[data-testid="UserName"]');
    return {
        url: location.href,
        title: document.title,
        userNameText: un ? un.innerText : null
    };
})()"""


def parse_display_name(profile_info: dict, handle_clean: str) -> str:
    un_text = (profile_info or {}).get("userNameText") or ""
    for line in un_text.splitlines():
        s = line.strip()
        if s and not s.startswith("@"):
            return s
    title = (profile_info or {}).get("title") or ""
    m = re.match(r"^(.*?)\s*\(@" + re.escape(handle_clean) + r"\)", title, re.IGNORECASE)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return handle_clean


async def _detect_account_async(cfg: dict, port_override: int | None):
    sess = open_hidden_session(cfg, port_override=port_override)
    await sess.start()
    try:
        await sess.navigate("https://x.com/home")
        home_data = None
        for _ in range(18):
            await asyncio.sleep(0.8)
            home_data = await sess.eval_js(DETECT_HOME_JS)
            if isinstance(home_data, dict) and (
                home_data.get("profileHref") or home_data.get("hasLoginPrompt")
            ):
                break

        profile_href = (home_data or {}).get("profileHref")
        if not profile_href or home_data.get("hasLoginPrompt"):
            return {
                "logged_in": False,
                "url": (home_data or {}).get("url"),
                "browser": cfg["browser"],
                "profile": cfg.get("profile"),
                "message": "Akun X belum login di profil browser ini. Buka shortcut di Desktop lalu login sekali, setelah itu tutup jendelanya.",
            }

        handle_clean = profile_href.strip("/").split("/")[0]
        handle = f"@{handle_clean}"

        # Navigate to the user's profile page in the same hidden tab to read exact Display Name
        await sess.navigate(f"https://x.com/{handle_clean}")
        prof_info = None
        for _ in range(12):
            await asyncio.sleep(0.6)
            prof_info = await sess.eval_js(DETECT_PROFILE_JS)
            if isinstance(prof_info, dict) and (
                prof_info.get("userNameText")
                or f"@{handle_clean}".lower() in (prof_info.get("title") or "").lower()
            ):
                break

        display_name = parse_display_name(prof_info, handle_clean)
        return {
            "logged_in": True,
            "handle": handle,
            "display_name": display_name,
            "browser": cfg["browser"],
            "profile": cfg.get("profile"),
            "engine": cfg["engine"],
            "port_used": sess.port,
        }
    finally:
        await sess.close()


def detect_and_confirm_account(
    cfg: dict,
    cli_path: Path = DEFAULT_CLI_PATH,
    db_path: Path | None = None,
    port_override: int | None = None,
    confirm_in_db: bool = True,
) -> dict:
    info = asyncio.run(_detect_account_async(cfg, port_override))
    if info.get("logged_in") and confirm_in_db:
        run_workflow_cli(
            [
                "confirm-account",
                "--handle",
                info["handle"],
                "--display-name",
                info["display_name"],
            ],
            cli_path=cli_path,
            db_path=db_path,
        )
        info["auto_confirmed"] = True
    return info


# ============================================================================
# CLI Entrypoint
# ============================================================================


def cmd_connect(args):
    kind = args.browser.lower()
    if kind == "auto":
        # Prefer already-installed browser in order: firefox (if Raid exists), brave, chrome, edge, firefox
        ff = resolve_browser_exe("firefox")
        ff_profiles = {p["name"].lower() for p in list_firefox_profiles()}
        if ff and "raid" in ff_profiles:
            kind = "firefox"
        else:
            for cand in ("brave", "chrome", "edge", "firefox"):
                if resolve_browser_exe(cand):
                    kind = cand
                    break

    if kind == "custom":
        if not args.exe_path:
            raise ValueError("--exe-path wajib diisi jika --browser custom")
        exe = args.exe_path
        engine = args.engine or "cdp"
        default_port = 9224 if engine == "cdp" else 9223
        display = Path(exe).stem
    else:
        if kind not in BROWSER_META:
            raise ValueError(f"Browser tidak dikenal: {kind}. Pilih: auto, firefox, brave, chrome, edge, custom")
        meta = BROWSER_META[kind]
        exe = resolve_browser_exe(kind, args.exe_path)
        if not exe:
            raise FileNotFoundError(f"Browser {meta['display']} tidak ditemukan di PC ini.")
        engine = meta["engine"]
        default_port = meta["default_port"]
        display = meta["display"]

    profile = args.profile or ("Raid" if engine == "bidi" else "Agent")
    port = args.port or default_port

    cfg = {
        "browser": kind,
        "display": display,
        "engine": engine,
        "executable": exe,
        "profile": profile,
        "port": port,
    }

    if engine == "bidi":
        ensure_firefox_profile(exe, profile)
        cfg["allow_hosts"] = "localhost,127.0.0.1"
    else:
        ud = Path(args.user_data_dir) if args.user_data_dir else (agent_profiles_root() / f"{kind}-{sanitize_slug(profile)}")
        ud.mkdir(parents=True, exist_ok=True)
        cfg["user_data_dir"] = str(ud.resolve())
        cfg["profile_directory"] = args.profile_directory or "Default"

    cfg_path = Path(args.config)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    shortcut_info = None
    if not args.no_shortcut:
        shortcut_info = create_windows_shortcut(cfg, also_repo_dir=True)
        cfg["shortcut"] = shortcut_info.get("desktop_shortcut")
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    cli_path = Path(args.cli_path)
    db_path = Path(args.db) if args.db else None
    run_workflow_cli(
        [
            "designate-browser",
            "--label",
            f"{display} hidden background ({profile})",
        ],
        cli_path=cli_path,
        db_path=db_path,
    )

    detect_info = None
    if not args.no_detect:
        detect_info = detect_and_confirm_account(
            cfg, cli_path=cli_path, db_path=db_path, confirm_in_db=True
        )

    print(
        json.dumps(
            {
                "connected": True,
                "config_file": str(cfg_path.resolve()),
                "browser": cfg,
                "shortcut": shortcut_info,
                "account_detection": detect_info,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Multi-browser hidden hub, Desktop shortcut creator, auto port takeover, and X account auto-detector."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Browser config JSON path")
    parser.add_argument("--cli-path", default=str(DEFAULT_CLI_PATH), help="Workflow Rust CLI path")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-browsers", help="Detect installed browsers, profiles, and active debug ports")

    p_conn = sub.add_parser("connect", help="Connect to user's chosen browser, create isolated profile & shortcut, and auto-detect X user")
    p_conn.add_argument("--browser", default="auto", help="auto | firefox | brave | chrome | edge | custom")
    p_conn.add_argument("--profile", default=None, help="Profile name (default: Raid for Firefox, Agent for Chromium)")
    p_conn.add_argument("--exe-path", default=None, help="Custom browser executable path")
    p_conn.add_argument("--engine", default=None, choices=["cdp", "bidi"], help="Engine when --browser custom")
    p_conn.add_argument("--user-data-dir", default=None, help="Custom isolated Chromium user-data-dir")
    p_conn.add_argument("--profile-directory", default="Default", help="Chromium profile subfolder")
    p_conn.add_argument("--port", type=int, default=None, help="Preferred debug port")
    p_conn.add_argument("--no-shortcut", action="store_true", help="Skip creating Desktop shortcut")
    p_conn.add_argument("--no-detect", action="store_true", help="Skip X account auto-detection")

    p_sc = sub.add_parser("create-shortcut", help="Create/refresh Windows Desktop shortcut for the connected browser")
    p_sc.add_argument("--no-repo-copy", action="store_true", help="Only create on Desktop")

    p_det = sub.add_parser("detect-account", help="Auto-detect logged-in X handle & display name in hidden background")
    p_det.add_argument("--port", type=int, default=None, help="Optional explicit debug port")
    p_det.add_argument("--no-confirm", action="store_true", help="Detect only without saving to SQLite")

    args = parser.parse_args()

    if args.cmd == "list-browsers":
        print(json.dumps(discover_browsers(), indent=2, ensure_ascii=False))
    elif args.cmd == "connect":
        cmd_connect(args)
    elif args.cmd == "create-shortcut":
        cfg = load_config(Path(args.config))
        res = create_windows_shortcut(cfg, also_repo_dir=not args.no_repo_copy)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.cmd == "detect-account":
        cfg = load_config(Path(args.config))
        res = detect_and_confirm_account(
            cfg,
            cli_path=Path(args.cli_path),
            db_path=Path(args.db) if args.db else None,
            port_override=args.port,
            confirm_in_db=not args.no_confirm,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
