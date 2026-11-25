import argparse
import asyncio
import configparser
import http.client
import json
import os
import random
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import websockets


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def default_cli_path() -> Path:
    name = "x-social-draft-workflow.exe" if _platform_key() == "win32" else "x-social-draft-workflow"
    return Path("target/release") / name


DEFAULT_CONFIG_PATH = Path("browser_config.json")
DEFAULT_CLI_PATH = default_cli_path()

BROWSER_META = {
    "firefox": {
        "display": "Mozilla Firefox",
        "engine": "bidi",
        "default_port": 9223,
        "candidates": {
            "win32": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "linux": [
                "/usr/bin/firefox",
                "/usr/local/bin/firefox",
                "/usr/bin/firefox-esr",
                "/snap/bin/firefox",
                "/var/lib/flatpak/exports/bin/org.mozilla.firefox",
            ],
            "darwin": [
                "/Applications/Firefox.app/Contents/MacOS/firefox",
                "{HOME}/Applications/Firefox.app/Contents/MacOS/firefox",
            ],
        },
        "which": ["firefox", "firefox-esr"],
    },
    "brave": {
        "display": "Brave Browser",
        "engine": "cdp",
        "default_port": 9224,
        "candidates": {
            "win32": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"{HOME}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
            "linux": [
                "/usr/bin/brave-browser",
                "/usr/bin/brave-browser-stable",
                "/opt/brave.com/brave/brave-browser",
                "/opt/brave.com/brave/brave",
                "/snap/bin/brave",
            ],
            "darwin": [
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "{HOME}/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            ],
        },
        "which": ["brave-browser", "brave-browser-stable", "brave"],
    },
    "chrome": {
        "display": "Google Chrome",
        "engine": "cdp",
        "default_port": 9222,
        "candidates": {
            "win32": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"{HOME}\AppData\Local\Google\Chrome\Application\chrome.exe",
            ],
            "linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/opt/google/chrome/chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ],
            "darwin": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "{HOME}/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ],
        },
        "which": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"],
    },
    "edge": {
        "display": "Microsoft Edge",
        "engine": "cdp",
        "default_port": 9225,
        "candidates": {
            "win32": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"{HOME}\AppData\Local\Microsoft\Edge\Application\msedge.exe",
            ],
            "linux": [
                "/usr/bin/microsoft-edge",
                "/usr/bin/microsoft-edge-stable",
                "/opt/microsoft/msedge/msedge",
            ],
            "darwin": [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "{HOME}/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ],
        },
        "which": ["microsoft-edge", "microsoft-edge-stable", "msedge", "edge"],
    },
}

_RNG = random.SystemRandom()


def compute_random_delay(
    min_sec: float = 5.0,
    max_sec: float = 60.0,
    prev_delay: float | None = None,
) -> float:
    """
    Human-like multi-band randomized delay strictly within [min_sec, max_sec].
    Default range: 5.0s to 60.0s with anti-clustering against prev_delay.
    """
    if min_sec < 0 or max_sec < min_sec:
        raise ValueError(f"Invalid delay range: min={min_sec}, max={max_sec}")
    if max_sec == min_sec:
        return round(min_sec, 2)

    span = max_sec - min_sec
    bands = [
        (0.00, 0.25, 0.25),
        (0.25, 0.65, 0.45),
        (0.65, 1.00, 0.30),
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
    return Path(path_tmpl.replace("{HOME}", str(Path.home())))


def _resolve_macos_app_binary(app_path: Path) -> str | None:
    if app_path.suffix == ".app" and app_path.is_dir():
        macos_dir = app_path / "Contents" / "MacOS"
        stem_bin = macos_dir / app_path.stem
        if stem_bin.exists() and stem_bin.is_file():
            return str(stem_bin)
        if macos_dir.is_dir():
            for child in sorted(macos_dir.iterdir()):
                if child.is_file() and os.access(child, os.X_OK):
                    return str(child)
    return None


def resolve_browser_exe(kind: str, override: str | None = None) -> str | None:
    if override:
        p = Path(override)
        app_bin = _resolve_macos_app_binary(p)
        if app_bin:
            return app_bin
        return str(p) if p.exists() else shutil.which(override)
    meta = BROWSER_META.get(kind)
    if not meta:
        return None
    raw_cands = meta["candidates"]
    cand_list = raw_cands.get(_platform_key(), []) if isinstance(raw_cands, dict) else raw_cands
    for tmpl in cand_list:
        p = expand_candidate(tmpl)
        if p.exists():
            return str(p)
    for w in meta["which"]:
        found = shutil.which(w)
        if found:
            return found
    return None


def firefox_profile_ini_paths() -> list[Path]:
    plat = _platform_key()
    home = Path.home()
    if plat == "win32":
        return [home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "profiles.ini"]
    if plat == "darwin":
        return [home / "Library" / "Application Support" / "Firefox" / "profiles.ini"]
    return [
        home / ".mozilla" / "firefox" / "profiles.ini",
        home / "snap" / "firefox" / "common" / ".mozilla" / "firefox" / "profiles.ini",
        home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox" / "profiles.ini",
    ]


def list_firefox_profiles() -> list[dict]:
    out = []
    seen = set()
    for ini_path in firefox_profile_ini_paths():
        if not ini_path.exists():
            continue
        cp = configparser.ConfigParser()
        cp.read(ini_path, encoding="utf-8")
        for sec in cp.sections():
            if sec.startswith("Profile") and cp.has_option(sec, "Name"):
                name = cp.get(sec, "Name")
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "name": name,
                        "path": cp.get(sec, "Path", fallback=""),
                        "is_default": cp.get(sec, "Default", fallback="0") == "1",
                    }
                )
    return out


def agent_profiles_root() -> Path:
    plat = _platform_key()
    home = Path.home()
    if plat == "win32":
        base = home / "AppData" / "Local"
    elif plat == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = home / ".local" / "share"
    return base / "AntiGravity-Browser" / "profiles"


def resolve_desktop_dir() -> Path | None:
    home = Path.home()
    if _platform_key() == "win32":
        for cand in (home / "OneDrive" / "Desktop", home / "Desktop"):
            if cand.is_dir():
                return cand
        return home / "Desktop"
    desk = home / "Desktop"
    return desk if desk.is_dir() else None


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "Agent"


def _loopback_get(port: int, path: str, timeout: float = 0.5) -> tuple[int, str] | None:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def probe_cdp_port(port: int, timeout: float = 0.4) -> dict | None:
    res = _loopback_get(port, "/json/version", timeout=timeout)
    if not res or res[0] != 200:
        return None
    try:
        data = json.loads(res[1])
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


def probe_bidi_port(port: int, timeout: float = 0.4) -> dict | None:
    res = _loopback_get(port, "/session", timeout=timeout)
    if res and res[0] in (200, 400, 426):
        return {
            "engine": "bidi",
            "port": port,
            "ws_url": f"ws://127.0.0.1:{port}/session",
        }
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


def check_configured_ports(
    cfg: dict | None = None,
    port_override: int | None = None,
) -> list[dict]:
    """Check only explicit/configured dedicated profile loopback ports."""
    ports: list[int] = []
    if port_override:
        ports.append(int(port_override))
    if cfg:
        ud = Path(cfg["user_data_dir"]) if cfg.get("user_data_dir") else None
        dt_port = read_devtools_active_port(ud)
        if dt_port and dt_port not in ports:
            ports.append(dt_port)
        cfg_port = cfg.get("port")
        if cfg_port and int(cfg_port) not in ports:
            ports.append(int(cfg_port))

    active = []
    for p in ports:
        if not _is_port_open(p):
            continue
        info = probe_cdp_port(p, timeout=0.35) or probe_bidi_port(p, timeout=0.35)
        if info:
            active.append(info)
    return active


def discover_browsers(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    browsers = {}
    for kind, meta in BROWSER_META.items():
        exe = resolve_browser_exe(kind)
        profiles = list_firefox_profiles() if kind == "firefox" else []
        browsers[kind] = {
            "display": meta["display"],
            "engine": meta["engine"],
            "installed": exe is not None,
            "executable": exe,
            "profiles": profiles,
        }

    agent_dirs = []
    root = agent_profiles_root()
    if root.exists():
        agent_dirs = [str(p) for p in sorted(root.iterdir()) if p.is_dir()]

    cfg = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else None
    active_ports = check_configured_ports(cfg) if cfg else []

    return {
        "platform": _platform_key(),
        "browsers": browsers,
        "agent_isolated_profiles": agent_dirs,
        "active_configured_ports": active_ports,
    }


def _tune_isolated_chromium_prefs(user_data_dir: Path, browser_kind: str, profile_directory: str = "Default"):
    """
    Safely pre-configure ONLY our isolated workspace profile preferences so
    Edge/Brave do not keep background tray locks alive or throttle/sleep tabs.
    Never touches personal browser profile directories.
    """
    try:
        prof_dir = user_data_dir / profile_directory
        prof_dir.mkdir(parents=True, exist_ok=True)
        prefs_path = prof_dir / "Preferences"
        prefs: dict = {}
        if prefs_path.exists():
            try:
                prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
                if not isinstance(prefs, dict):
                    prefs = {}
            except Exception:
                prefs = {}

        prefs.setdefault("background_mode", {})
        if isinstance(prefs["background_mode"], dict):
            prefs["background_mode"]["enabled"] = False

        if browser_kind == "edge":
            prefs.setdefault("browser", {})
            if isinstance(prefs["browser"], dict):
                prefs["browser"]["edge_efficiency_mode_enabled"] = False
            prefs.setdefault("edge", {})
            if isinstance(prefs["edge"], dict):
                prefs["edge"].setdefault("sleeping_tabs", {})
                if isinstance(prefs["edge"]["sleeping_tabs"], dict):
                    prefs["edge"]["sleeping_tabs"]["enabled"] = False
            prefs.setdefault("startup_boost", {})
            if isinstance(prefs["startup_boost"], dict):
                prefs["startup_boost"]["enabled"] = False
        elif browser_kind == "brave":
            prefs.setdefault("brave", {})
            if isinstance(prefs["brave"], dict):
                prefs["brave"].setdefault("p3a", {})["enabled"] = False
                prefs["brave"].setdefault("stats", {})["reporting_enabled"] = False
                prefs["brave"].setdefault("today", {})["opted_in"] = False

        prefs_path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def choose_auto_browser() -> str | None:
    ff = resolve_browser_exe("firefox")
    ff_profiles = {p["name"].lower() for p in list_firefox_profiles()}
    if ff and "raid" in ff_profiles:
        return "firefox"
    for cand in ("chrome", "firefox", "edge", "brave"):
        if resolve_browser_exe(cand):
            return cand
    return None


def prompt_browser_choice(default_kind: str | None = None) -> str:
    """Interactive terminal menu letting the user pick their preferred browser before setup."""
    ordered = ["chrome", "edge", "brave", "firefox"]
    discovery = discover_browsers()["browsers"]
    installed = [k for k in ordered if discovery[k]["installed"]]
    if not default_kind or default_kind not in ordered:
        default_kind = installed[0] if installed else "chrome"

    print("\n=== Pilih Browser untuk AntiGravity-Browser ===")
    for idx, kind in enumerate(ordered, 1):
        info = discovery[kind]
        status = "TERPASANG" if info["installed"] else "Belum terpasang"
        rec = " [Disarankan]" if kind == "chrome" and info["installed"] else ""
        exe_str = f" ({info['executable']})" if info["executable"] else ""
        print(f"  [{idx}] {info['display']:16s} - {status}{rec}{exe_str}")
    print("  [5] Custom browser    - Masukkan path executable manual")

    mapping = {
        "1": "chrome", "chrome": "chrome", "google chrome": "chrome",
        "2": "edge", "edge": "edge", "microsoft edge": "edge", "msedge": "edge",
        "3": "brave", "brave": "brave", "brave browser": "brave",
        "4": "firefox", "firefox": "firefox", "mozilla firefox": "firefox",
        "5": "custom", "custom": "custom",
    }
    while True:
        try:
            raw = input(f"Pilih browser [1-5 atau nama, Enter = {default_kind}]: ").strip().lower()
        except EOFError:
            return default_kind
        if not raw:
            chosen = default_kind
        else:
            chosen = mapping.get(raw)
        if not chosen:
            print("Pilihan tidak dikenali. Ketik angka 1-5 atau chrome/edge/brave/firefox/custom.")
            continue
        if chosen != "custom" and not discovery[chosen]["installed"]:
            print(f"{discovery[chosen]['display']} belum terdeteksi di perangkat ini. Pilih browser lain yang terpasang atau pilih [5] Custom.")
            continue
        return chosen


def ensure_firefox_profile(firefox_exe: str, profile_name: str):
    existing = {p["name"].lower(): p["name"] for p in list_firefox_profiles()}
    if profile_name.lower() in existing:
        return existing[profile_name.lower()]
    cmd = [firefox_exe, "-no-remote", "-headless", "-CreateProfile", profile_name]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return profile_name


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    for kind in ("chrome", "firefox", "edge", "brave"):
        exe = resolve_browser_exe(kind)
        if not exe:
            continue
        if kind == "firefox":
            return {
                "browser": "firefox",
                "display": "Mozilla Firefox",
                "engine": "bidi",
                "executable": exe,
                "profile": "Raid",
                "port": 9223,
                "allow_hosts": "localhost,127.0.0.1",
            }
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
        "Tidak ada browser yang terdeteksi (Chrome/Firefox/Edge/Brave). Jalankan connect-browser --exe-path <path>."
    )


def build_browser_launch_args(cfg: dict) -> tuple[str, list[str]]:
    """
    Build clean GUI login arguments WITHOUT debug ports/flags so X login never
    flags the interactive browser window at the username/password prompt.
    Headless automation enables its loopback debug port only in _start_headless_process().
    """
    exe = cfg["executable"]
    profile = cfg.get("profile", "Agent")
    if cfg["engine"] == "bidi":
        args_list = [
            "-no-remote",
            "-P",
            profile,
            "https://x.com",
        ]
    else:
        ud = cfg["user_data_dir"]
        pdir = cfg.get("profile_directory", "Default")
        args_list = [
            f"--user-data-dir={ud}",
            f"--profile-directory={pdir}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://x.com",
        ]
    return exe, args_list


def build_shortcut_spec(cfg: dict) -> tuple[str, str, str]:
    kind = cfg["browser"]
    profile = cfg.get("profile", "Agent")
    exe, args_list = build_browser_launch_args(cfg)
    if _platform_key() == "win32":
        if cfg["engine"] == "bidi":
            args = f'-no-remote -P "{profile}" https://x.com'
        else:
            ud = cfg["user_data_dir"]
            pdir = cfg.get("profile_directory", "Default")
            args = (
                f'--user-data-dir="{ud}" '
                f'--profile-directory="{pdir}" '
                f'--no-first-run --no-default-browser-check '
                f'https://x.com'
            )
        short_name = f"AntiGravity X ({kind.capitalize()} - {profile}).lnk"
    elif _platform_key() == "darwin":
        args = " ".join(shlex.quote(a) for a in args_list)
        short_name = f"AntiGravity X ({kind.capitalize()} - {profile}).command"
    else:
        args = " ".join(shlex.quote(a) for a in args_list)
        short_name = f"AntiGravity X ({kind.capitalize()} - {profile}).desktop"
    return short_name, exe, args


def _build_windows_idlist(target_path: str) -> bytes:
    p = Path(target_path)
    items = [bytes.fromhex("14001f50e04fd020ea3a6910a2d808002b30309d")]
    drive_str = (p.drive + "\\") if p.drive else "C:\\"
    drive_bytes = drive_str.encode("ascii", errors="replace")
    drive_item = b"\x2f" + drive_bytes + b"\x00" * max(1, 22 - len(drive_bytes))
    items.append(struct.pack("<H", 2 + len(drive_item)) + drive_item)

    parts = [part for part in p.parts[1:]] if len(p.parts) > 1 else []
    for idx, part in enumerate(parts):
        is_file = idx == len(parts) - 1
        flags_byte = b"\x32" if is_file else b"\x31"
        short_name = part.encode("ascii", errors="replace") + b"\x00"
        if len(short_name) % 2 == 1:
            short_name += b"\x00"
        u_name = part.encode("utf-16-le") + b"\x00\x00"
        beef_body = (
            struct.pack("<HHI", 0x0009, 0x0004, 0xBEEF0004)
            + b"\x00" * 12
            + struct.pack("<H", 0x002E)
            + b"\x00" * 16
            + u_name
            + struct.pack("<H", 0x16)
        )
        beef = struct.pack("<H", len(beef_body) + 2) + beef_body
        entry_body = (
            flags_byte
            + b"\x00"
            + struct.pack("<IHHH", 0, 0, 0, 0x20 if is_file else 0x10)
            + short_name
            + beef
        )
        items.append(struct.pack("<H", 2 + len(entry_body)) + entry_body)

    raw = b"".join(items) + b"\x00\x00"
    return struct.pack("<H", len(raw)) + raw


def write_windows_lnk(
    lnk_path: Path,
    target_exe: str,
    arguments: str,
    working_dir: str,
    description: str,
):
    """Write standard [MS-SHLLINK] .lnk binary shortcut directly in pure Python."""

    def counted_utf16(text: str) -> bytes:
        return struct.pack("<H", len(text)) + text.encode("utf-16-le")

    flags = 0x01 | 0x02 | 0x04 | 0x10 | 0x20 | 0x80
    header = bytearray(76)
    struct.pack_into("<I", header, 0, 0x4C)
    header[4:20] = bytes.fromhex("0114020000000000c000000000000046")
    struct.pack_into("<I", header, 20, flags)
    struct.pack_into("<I", header, 24, 0x20)
    struct.pack_into("<I", header, 60, 1)

    idlist = _build_windows_idlist(target_exe)

    vol_id_body = struct.pack("<III", 3, 0, 16) + b"\x00"
    vol_id = struct.pack("<I", 4 + len(vol_id_body)) + vol_id_body
    local_base = target_exe.encode("mbcs", errors="replace") + b"\x00"
    common_suffix = b"\x00"
    li_hdr_size = 28
    vol_offset = li_hdr_size
    base_offset = vol_offset + len(vol_id)
    suffix_offset = base_offset + len(local_base)
    link_info_size = suffix_offset + len(common_suffix)
    link_info = (
        struct.pack(
            "<IIIIIII",
            link_info_size,
            li_hdr_size,
            0x01,
            vol_offset,
            base_offset,
            0,
            suffix_offset,
        )
        + vol_id
        + local_base
        + common_suffix
    )

    string_data = (
        counted_utf16(description)
        + counted_utf16(working_dir)
        + counted_utf16(arguments)
    )
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    lnk_path.write_bytes(bytes(header) + idlist + link_info + string_data)


def _write_unix_executable(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass


def create_shortcut(cfg: dict, also_repo_dir: bool = True) -> dict:
    plat = _platform_key()
    kind = cfg["browser"]
    profile = cfg.get("profile", "Agent")
    short_name, target_exe, args = build_shortcut_spec(cfg)
    _, args_list = build_browser_launch_args(cfg)

    if plat == "win32":
        desktop_dir = resolve_desktop_dir() or (Path.home() / "Desktop")
        targets = [desktop_dir / short_name]
        if also_repo_dir:
            repo_short_dir = Path("shortcuts")
            repo_short_dir.mkdir(parents=True, exist_ok=True)
            targets.append((repo_short_dir / short_name).resolve())

        created = []
        work_dir = str(Path(target_exe).parent)
        desc = f"Isolated X profile ({kind} - {profile})"
        for lnk in targets:
            write_windows_lnk(lnk, str(target_exe), args, work_dir, desc)
            created.append(str(lnk))

        return {
            "platform": plat,
            "shortcut_name": short_name,
            "desktop_shortcut": created[0] if created else None,
            "all_shortcuts": created,
            "arguments": args,
        }

    slug = f"{sanitize_slug(kind).lower()}-{sanitize_slug(profile).lower()}"
    cmd_line = " ".join(shlex.quote(a) for a in [str(target_exe), *args_list])
    shell_script = (
        "#!/usr/bin/env bash\n"
        f"# Isolated X profile launcher ({kind} - {profile})\n"
        f"{cmd_line}\n"
    )

    repo_short_dir = Path("shortcuts")
    shell_path = None
    created = []

    if also_repo_dir:
        shell_path = (repo_short_dir / f"antigravity-x-{slug}.sh").resolve()
        _write_unix_executable(shell_path, shell_script)
        created.append(str(shell_path))

    if plat == "darwin":
        desktop_dir = resolve_desktop_dir()
        desktop_file = None
        if desktop_dir and desktop_dir.is_dir():
            df = desktop_dir / short_name
            _write_unix_executable(df, shell_script)
            desktop_file = str(df)
            created.insert(0, desktop_file)
        if also_repo_dir:
            repo_cmd = (repo_short_dir / short_name).resolve()
            _write_unix_executable(repo_cmd, shell_script)
            created.append(str(repo_cmd))
        return {
            "platform": plat,
            "shortcut_name": short_name,
            "desktop_shortcut": desktop_file or (str(shell_path) if shell_path else None),
            "shell_launcher": str(shell_path) if shell_path else None,
            "all_shortcuts": created,
            "arguments": args,
        }

    def desktop_exec_token(val: str) -> str:
        if any(ch in val for ch in (" ", "\t", '"', "\\")):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return val

    exec_line = " ".join(desktop_exec_token(a) for a in [str(target_exe), *args_list])
    desktop_entry = (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name=AntiGravity X ({kind.capitalize()} - {profile})\n"
        "Comment=Isolated X browser profile\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "Categories=Network;WebBrowser;\n"
    )

    desktop_file = None
    linux_desktop = resolve_desktop_dir()
    if linux_desktop and linux_desktop.is_dir():
        df = linux_desktop / short_name
        _write_unix_executable(df, desktop_entry)
        desktop_file = str(df)
        created.insert(0, desktop_file)

    apps_dir = Path.home() / ".local" / "share" / "applications"
    app_entry = apps_dir / f"antigravity-x-{slug}.desktop"
    _write_unix_executable(app_entry, desktop_entry)
    created.append(str(app_entry))

    if also_repo_dir:
        repo_desk = (repo_short_dir / short_name).resolve()
        _write_unix_executable(repo_desk, desktop_entry)
        created.append(str(repo_desk))

    return {
        "platform": plat,
        "shortcut_name": short_name,
        "desktop_shortcut": desktop_file or (str(shell_path) if shell_path else str(app_entry)),
        "shell_launcher": str(shell_path) if shell_path else None,
        "all_shortcuts": created,
        "arguments": args,
    }


def _resolve_cli_exe(cli_path: Path) -> Path | None:
    candidates = [cli_path]
    if _platform_key() == "win32":
        if cli_path.suffix != ".exe":
            candidates.append(cli_path.with_suffix(".exe"))
    else:
        if cli_path.suffix == ".exe":
            candidates.append(cli_path.with_suffix(""))
    candidates.append(default_cli_path())
    for c in candidates:
        if c.exists():
            return c
    return None


def run_workflow_cli(args: list[str], cli_path: Path = DEFAULT_CLI_PATH, db_path: Path | None = None) -> str:
    exe = _resolve_cli_exe(cli_path)
    if exe is None:
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
    )
    if res.returncode != 0:
        raise RuntimeError(f"CLI error ({' '.join(cmd)}): {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


# ============================================================================
# Headless Isolated Browser Session (Firefox BiDi + Chromium CDP)
# ============================================================================


def _terminate_process_tree(proc: subprocess.Popen | None):
    if not proc:
        return
    if proc.poll() is not None:
        return
    try:
        proc.wait(timeout=4)
        return
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=3)
        return
    except Exception:
        pass
    if _platform_key() == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass
    else:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


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


class _BiDiTab:
    def __init__(self, session: "_BiDiSession", ctx: str):
        self._session = session
        self.ctx = ctx

    async def navigate(self, url: str, timeout: float = 35.0):
        await self._session._navigate_ctx(self.ctx, url, timeout=timeout)

    async def evaluate_dom(self, expr: str, timeout: float = 20.0):
        return await self._session._evaluate_ctx(self.ctx, expr, timeout=timeout)

    async def click_point(self, x: float, y: float, timeout: float = 15.0):
        await self._session._click_ctx(self.ctx, x, y, timeout=timeout)

    async def type_text(self, text: str, timeout: float = 30.0):
        await self._session._type_ctx(self.ctx, text, timeout=timeout)

    async def ping(self, timeout: float = 8.0) -> bool:
        try:
            val = await self.evaluate_dom("1 + 1", timeout=timeout)
            return val == 2
        except Exception:
            return False

    async def close(self):
        await self._session.close_tab(self)


class _BiDiSession:
    def __init__(self, ws_url: str, port: int, owns_process: bool, proc: subprocess.Popen | None, cfg: dict | None = None):
        self.ws_url = ws_url
        self.port = port
        self.owns_process = owns_process
        self.proc = proc
        self.cfg = cfg or {}
        self.ws = None
        self.ctx = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()

    async def _reader_loop(self):
        try:
            while self.ws is not None:
                raw = await self.ws.recv()
                data = json.loads(raw)
                msg_id = data.get("id")
                if msg_id is not None:
                    fut = self._pending.pop(msg_id, None)
                    if fut and not fut.done():
                        fut.set_result(data)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError(f"BiDi connection lost: {exc}"))
            self._pending.clear()

    async def _call(self, method: str, params: dict | None = None, timeout: float = 30.0):
        if not self.ws:
            raise ConnectionError("BiDi WebSocket is not connected")
        msg_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[msg_id] = fut
        try:
            async with self._send_lock:
                await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self._pending.pop(msg_id, None)
            raise

    async def start(self):
        self.ws = await websockets.connect(
            self.ws_url,
            origin=f"http://127.0.0.1:{self.port}",
            ping_interval=15,
            ping_timeout=15,
            close_timeout=4,
            max_size=16 * 1024 * 1024,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        res = await self._call(
            "session.new", {"capabilities": {"alwaysMatch": {"webSocketUrl": True}}}, timeout=20.0
        )
        if res.get("type") == "error":
            raise RuntimeError(f"BiDi session.new failed: {res}")
        tab = await self.open_tab()
        self.ctx = tab.ctx

    async def open_tab(self) -> _BiDiTab:
        tab = await self._call(
            "browsingContext.create", {"type": "tab", "background": False}, timeout=20.0
        )
        if tab.get("type") == "error":
            raise RuntimeError(f"BiDi browsingContext.create failed: {tab}")
        ctx = tab["result"]["context"]
        try:
            await self._call("browsingContext.activate", {"context": ctx}, timeout=10.0)
        except Exception:
            pass
        return _BiDiTab(self, ctx)

    async def close_tab(self, tab: _BiDiTab):
        if tab and tab.ctx and self.ws:
            try:
                await self._call("browsingContext.close", {"context": tab.ctx}, timeout=5.0)
            except Exception:
                pass

    async def reset_tab(self):
        old_ctx = self.ctx
        new_tab = await self.open_tab()
        self.ctx = new_tab.ctx
        if old_ctx and self.ws:
            try:
                await self._call("browsingContext.close", {"context": old_ctx}, timeout=5.0)
            except Exception:
                pass

    async def _navigate_ctx(self, ctx: str, url: str, timeout: float = 35.0):
        res = await self._call(
            "browsingContext.navigate",
            {"context": ctx, "url": url, "wait": "complete"},
            timeout=timeout,
        )
        if res.get("type") == "error":
            raise RuntimeError(f"BiDi navigation error: {res}")

    async def navigate(self, url: str, timeout: float = 35.0):
        await self._navigate_ctx(self.ctx, url, timeout=timeout)

    async def _evaluate_ctx(self, ctx: str, expr: str, timeout: float = 20.0):
        res = await self._call(
            "script.evaluate",
            {
                "expression": expr,
                "target": {"context": ctx},
                "awaitPromise": False,
            },
            timeout=timeout,
        )
        if res.get("type") == "error":
            raise RuntimeError(f"BiDi script error: {res}")
        r = res.get("result", {})
        if r.get("type") == "exception":
            raise RuntimeError(f"DOM exception: {r}")
        return from_bidi_val(r.get("result"))

    async def evaluate_dom(self, expr: str, timeout: float = 20.0):
        return await self._evaluate_ctx(self.ctx, expr, timeout=timeout)

    async def _click_ctx(self, ctx: str, x: float, y: float, timeout: float = 15.0):
        await self._call(
            "input.performActions",
            {
                "context": ctx,
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
            timeout=timeout,
        )

    async def click_point(self, x: float, y: float, timeout: float = 15.0):
        await self._click_ctx(self.ctx, x, y, timeout=timeout)

    async def _type_ctx(self, ctx: str, text: str, timeout: float = 30.0):
        actions = []
        for ch in text:
            actions.append({"type": "keyDown", "value": ch})
            actions.append({"type": "keyUp", "value": ch})
        await self._call(
            "input.performActions",
            {
                "context": ctx,
                "actions": [{"type": "key", "id": "keyboard", "actions": actions}],
            },
            timeout=timeout,
        )

    async def type_text(self, text: str, timeout: float = 30.0):
        await self._type_ctx(self.ctx, text, timeout=timeout)

    async def type_text_keys(self, text: str, timeout: float = 30.0):
        await self._type_ctx(self.ctx, text, timeout=timeout)

    async def ping(self, timeout: float = 8.0) -> bool:
        try:
            return await self.evaluate_dom("1 + 1", timeout=timeout) == 2
        except Exception:
            return False

    async def close(self):
        try:
            if self.ctx and self.ws:
                await self._call("browsingContext.close", {"context": self.ctx}, timeout=3.0)
        except Exception:
            pass
        try:
            if self.ws:
                if self.owns_process:
                    await self._call("browser.close", timeout=3.0)
                else:
                    await self._call("session.end", timeout=3.0)
        except Exception:
            pass
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except Exception:
                pass
            self._reader_task = None
        try:
            if self.ws:
                await asyncio.wait_for(self.ws.close(), timeout=3.0)
        except Exception:
            pass
        self.ws = None
        if self.owns_process:
            _terminate_process_tree(self.proc)


def _extract_chromium_ua_parts(browser_product: str | None) -> tuple[str, str]:
    text = browser_product or ""
    m = re.search(r"(?:Chrome|Edg|Brave)/(\d+\.\d+\.\d+\.\d+)", text)
    full_ver = m.group(1) if m else "136.0.0.0"
    major = full_ver.split(".")[0]
    return full_ver, major


def _build_ua_override_params(browser_product: str | None, browser_kind: str = "chrome") -> dict:
    full_ver, major = _extract_chromium_ua_parts(browser_product)
    plat = _platform_key()
    if plat == "darwin":
        ua_os = "Macintosh; Intel Mac OS X 10_15_7"
        meta_platform = "macOS"
        meta_platform_ver = "14.5.0"
        nav_platform = "MacIntel"
        arch = "arm"
    elif plat == "linux":
        ua_os = "X11; Linux x86_64"
        meta_platform = "Linux"
        meta_platform_ver = "6.8.0"
        nav_platform = "Linux x86_64"
        arch = "x86"
    else:
        ua_os = "Windows NT 10.0; Win64; x64"
        meta_platform = "Windows"
        meta_platform_ver = "15.0.0"
        nav_platform = "Win32"
        arch = "x86"

    edge_suffix = f" Edg/{full_ver}" if browser_kind == "edge" else ""
    ua = f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36{edge_suffix}"
    primary_brand = "Microsoft Edge" if browser_kind == "edge" else "Google Chrome"
    return {
        "userAgent": ua,
        "acceptLanguage": "en-US,en;q=0.9",
        "platform": nav_platform,
        "userAgentMetadata": {
            "brands": [
                {"brand": "Chromium", "version": major},
                {"brand": "Not_A Brand", "version": "24"},
                {"brand": primary_brand, "version": major},
            ],
            "fullVersionList": [
                {"brand": "Chromium", "version": full_ver},
                {"brand": "Not_A Brand", "version": "24.0.0.0"},
                {"brand": primary_brand, "version": full_ver},
            ],
            "platform": meta_platform,
            "platformVersion": meta_platform_ver,
            "architecture": arch,
            "model": "",
            "mobile": False,
            "bitness": "64",
            "wow64": False,
        },
    }


class _CDPTab:
    def __init__(self, session: "_CDPSession", target_id: str, session_id: str):
        self._session = session
        self.target_id = target_id
        self.session_id = session_id

    async def navigate(self, url: str, timeout: float = 35.0):
        await self._session._navigate_tab(self.session_id, url, timeout=timeout)

    async def evaluate_dom(self, expr: str, timeout: float = 20.0):
        return await self._session._evaluate_tab(self.session_id, expr, timeout=timeout)

    async def click_point(self, x: float, y: float, timeout: float = 15.0):
        await self._session._click_tab(self.session_id, x, y, timeout=timeout)

    async def type_text(self, text: str, timeout: float = 20.0):
        await self._session._type_tab(self.session_id, text, timeout=timeout)

    async def type_text_keys(self, text: str, timeout: float = 30.0):
        await self._session._type_tab_keys(self.session_id, text, timeout=timeout)

    async def ping(self, timeout: float = 8.0) -> bool:
        try:
            return await self.evaluate_dom("1 + 1", timeout=timeout) == 2
        except Exception:
            return False

    async def close(self):
        await self._session.close_tab(self)


class _CDPSession:
    def __init__(self, ws_url: str, port: int, owns_process: bool, proc: subprocess.Popen | None, cfg: dict | None = None):
        self.ws_url = ws_url
        self.port = port
        self.owns_process = owns_process
        self.proc = proc
        self.cfg = cfg or {}
        self.ws = None
        self.target_id = None
        self.session_id = None
        self.browser_version: str | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._crashed_sessions: set[str] = set()
        self._reader_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()

    async def _handle_event(self, data: dict):
        method = data.get("method")
        sid = data.get("sessionId")
        if method == "Page.javascriptDialogOpening" and sid:
            asyncio.create_task(
                self._fire_and_forget(
                    "Page.handleJavaScriptDialog", {"accept": False}, session_id=sid
                )
            )
        elif method in ("Target.targetCrashed", "Inspector.detached"):
            if sid:
                self._crashed_sessions.add(sid)

    async def _fire_and_forget(self, method: str, params: dict | None = None, session_id: str | None = None):
        try:
            await self._call(method, params, session_id=session_id, timeout=5.0)
        except Exception:
            pass

    async def _reader_loop(self):
        try:
            while self.ws is not None:
                raw = await self.ws.recv()
                data = json.loads(raw)
                msg_id = data.get("id")
                if msg_id is not None:
                    fut = self._pending.pop(msg_id, None)
                    if fut and not fut.done():
                        fut.set_result(data)
                elif "method" in data:
                    await self._handle_event(data)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError(f"CDP connection lost: {exc}"))
            self._pending.clear()

    async def _call(
        self,
        method: str,
        params: dict | None = None,
        session_id: str | None = None,
        timeout: float = 30.0,
    ):
        if not self.ws:
            raise ConnectionError("CDP WebSocket is not connected")
        if session_id and session_id in self._crashed_sessions:
            raise RuntimeError(f"CDP target crashed for session {session_id}")
        msg_id = self._next_id
        self._next_id += 1
        payload = {"id": msg_id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[msg_id] = fut
        try:
            async with self._send_lock:
                await self.ws.send(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self._pending.pop(msg_id, None)
            raise

    async def _setup_tab_session(self, target_id: str) -> _CDPTab:
        attached = await self._call(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            timeout=15.0,
        )
        if "error" in attached:
            raise RuntimeError(f"CDP attachToTarget failed: {attached}")
        session_id = attached["result"]["sessionId"]
        await self._call("Page.enable", {}, session_id, timeout=15.0)
        await self._call("Runtime.enable", {}, session_id, timeout=15.0)
        try:
            await self._call("Target.activateTarget", {"targetId": target_id}, timeout=8.0)
            await self._call("Page.bringToFront", {}, session_id, timeout=8.0)
        except Exception:
            pass
        try:
            ua_params = _build_ua_override_params(
                self.browser_version, self.cfg.get("browser", "chrome")
            )
            await self._call("Emulation.setUserAgentOverride", ua_params, session_id, timeout=8.0)
        except Exception:
            pass
        return _CDPTab(self, target_id, session_id)

    async def start(self):
        self.ws = await websockets.connect(
            self.ws_url,
            origin=f"http://127.0.0.1:{self.port}",
            ping_interval=15,
            ping_timeout=15,
            close_timeout=4,
            max_size=16 * 1024 * 1024,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        try:
            ver = await self._call("Browser.getVersion", {}, timeout=8.0)
            self.browser_version = ver.get("result", {}).get("product")
        except Exception:
            self.browser_version = None

        # Prefer creating a foreground (background=False) tab or reusing initial about:blank
        # so Edge/Brave never apply background-tab timer throttling or Sleeping Tabs.
        reused_target_id = None
        if self.owns_process:
            try:
                targets = await self._call("Target.getTargets", {}, timeout=8.0)
                pages = [
                    t
                    for t in targets.get("result", {}).get("targetInfos", [])
                    if t.get("type") == "page" and not t.get("attached")
                ]
                if pages:
                    reused_target_id = pages[0]["targetId"]
            except Exception:
                reused_target_id = None

        if reused_target_id:
            tab = await self._setup_tab_session(reused_target_id)
        else:
            tab = await self.open_tab()
        self.target_id = tab.target_id
        self.session_id = tab.session_id

    async def open_tab(self) -> _CDPTab:
        created = await self._call(
            "Target.createTarget",
            {"url": "about:blank", "background": False},
            timeout=15.0,
        )
        if "error" in created:
            raise RuntimeError(f"CDP Target.createTarget failed: {created}")
        tid = created["result"]["targetId"]
        return await self._setup_tab_session(tid)

    async def close_tab(self, tab: _CDPTab):
        if tab and tab.target_id and self.ws:
            try:
                await self._call("Target.closeTarget", {"targetId": tab.target_id}, timeout=5.0)
            except Exception:
                pass

    async def reset_tab(self):
        old_target = self.target_id
        new_tab = await self.open_tab()
        self.target_id = new_tab.target_id
        self.session_id = new_tab.session_id
        if old_target and self.ws:
            try:
                await self._call("Target.closeTarget", {"targetId": old_target}, timeout=5.0)
            except Exception:
                pass

    async def _navigate_tab(self, session_id: str, url: str, timeout: float = 35.0):
        deadline = time.monotonic() + timeout
        res = await self._call("Page.navigate", {"url": url}, session_id, timeout=min(25.0, timeout))
        err_text = res.get("result", {}).get("errorText")
        if err_text and err_text != "net::ERR_ABORTED":
            raise RuntimeError(f"Navigation error: {err_text}")
        while time.monotonic() < deadline:
            try:
                state = await self._evaluate_tab(session_id, "document.readyState", timeout=8.0)
                if state == "complete":
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)

    async def navigate(self, url: str, timeout: float = 35.0):
        await self._navigate_tab(self.session_id, url, timeout=timeout)

    async def _evaluate_tab(self, session_id: str, expr: str, timeout: float = 20.0):
        res = await self._call(
            "Runtime.evaluate",
            {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": False,
            },
            session_id,
            timeout=timeout,
        )
        if "error" in res:
            raise RuntimeError(f"CDP Runtime.evaluate error: {res['error']}")
        r = res.get("result", {})
        if "exceptionDetails" in r:
            raise RuntimeError(f"DOM exception: {r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    async def evaluate_dom(self, expr: str, timeout: float = 20.0):
        return await self._evaluate_tab(self.session_id, expr, timeout=timeout)

    async def _click_tab(self, session_id: str, x: float, y: float, timeout: float = 15.0):
        px = float(round(x))
        py = float(round(y))
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": px, "y": py, "button": "left", "clickCount": 1},
            session_id,
            timeout=timeout,
        )
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": px, "y": py, "button": "left", "clickCount": 1},
            session_id,
            timeout=timeout,
        )

    async def click_point(self, x: float, y: float, timeout: float = 15.0):
        await self._click_tab(self.session_id, x, y, timeout=timeout)

    async def _type_tab(self, session_id: str, text: str, timeout: float = 20.0):
        parts = text.split("\n")
        for idx, line in enumerate(parts):
            if line:
                await self._call("Input.insertText", {"text": line}, session_id, timeout=timeout)
            if idx < len(parts) - 1:
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                    session_id,
                    timeout=timeout,
                )
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                    session_id,
                    timeout=timeout,
                )

    async def _type_tab_keys(self, session_id: str, text: str, timeout: float = 30.0):
        for ch in text:
            if ch == "\n":
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                    session_id,
                    timeout=timeout,
                )
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                    session_id,
                    timeout=timeout,
                )
            elif ord(ch) < 128 and ch.isprintable():
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyDown", "text": ch, "unmodifiedText": ch},
                    session_id,
                    timeout=timeout,
                )
                await self._call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "text": ch},
                    session_id,
                    timeout=timeout,
                )
            else:
                await self._call("Input.insertText", {"text": ch}, session_id, timeout=timeout)

    async def type_text(self, text: str, timeout: float = 20.0):
        await self._type_tab(self.session_id, text, timeout=timeout)

    async def type_text_keys(self, text: str, timeout: float = 30.0):
        await self._type_tab_keys(self.session_id, text, timeout=timeout)

    async def ping(self, timeout: float = 8.0) -> bool:
        try:
            return await self.evaluate_dom("1 + 1", timeout=timeout) == 2
        except Exception:
            return False

    async def close(self):
        try:
            if self.target_id and self.ws and not self.owns_process:
                await self._call("Target.closeTarget", {"targetId": self.target_id}, timeout=3.0)
        except Exception:
            pass
        try:
            if self.owns_process and self.ws:
                await self._call("Browser.close", timeout=3.0)
        except Exception:
            pass
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except Exception:
                pass
            self._reader_task = None
        try:
            if self.ws:
                await asyncio.wait_for(self.ws.close(), timeout=3.0)
        except Exception:
            pass
        self.ws = None
        if self.owns_process:
            _terminate_process_tree(self.proc)


def _default_user_agent(browser_kind: str = "chrome") -> str:
    plat = _platform_key()
    if plat == "darwin":
        os_tok = "Macintosh; Intel Mac OS X 10_15_7"
    elif plat == "linux":
        os_tok = "X11; Linux x86_64"
    else:
        os_tok = "Windows NT 10.0; Win64; x64"
    edge_tok = " Edg/136.0.0.0" if browser_kind == "edge" else ""
    return f"Mozilla/5.0 ({os_tok}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36{edge_tok}"


def _start_headless_process(cfg: dict, port: int) -> tuple[subprocess.Popen | None, str]:
    exe = cfg["executable"]
    if not Path(exe).exists() and not shutil.which(exe):
        raise FileNotFoundError(f"Browser executable not found: {exe}")

    origin = f"http://127.0.0.1:{port}"
    if cfg["engine"] == "bidi":
        profile = ensure_firefox_profile(exe, cfg.get("profile", "Raid"))
        allow_hosts = cfg.get("allow_hosts", "localhost,127.0.0.1")
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
                origin,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            time.sleep(0.4)
            probe = probe_bidi_port(port, timeout=1.0)
            if probe:
                return proc, probe["ws_url"]
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Firefox headless exited early (code {proc.returncode}). "
                    f"Pastikan jendela login profil '{profile}' sudah ditutup sebelum menjalankan mode headless."
                )
        _terminate_process_tree(proc)
        raise RuntimeError(f"Timed out waiting for headless Firefox BiDi on port {port}")

    ud = Path(cfg["user_data_dir"])
    ud.mkdir(parents=True, exist_ok=True)
    pdir = cfg.get("profile_directory", "Default")
    kind = cfg.get("browser", "chrome")
    _tune_isolated_chromium_prefs(ud, kind, pdir)

    # Clear stale DevToolsActivePort if nothing is actually listening on it
    dt_port = read_devtools_active_port(ud)
    if dt_port and not _is_port_open(dt_port):
        try:
            (ud / "DevToolsActivePort").unlink(missing_ok=True)
        except OSError:
            pass

    cmd = [
        exe,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-mode",
        "--disable-component-update",
        "--disable-sync",
        "--disable-default-apps",
        "--no-service-autorun",
        "--disable-hang-monitor",
        "--metrics-recording-only",
        "--no-pings",
        "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled",
        (
            "--disable-features=CalculateNativeWinOcclusion,OptimizationHints,"
            "MediaRouter,DialMediaRouteProvider,Translate,BackForwardCache,"
            "IntensiveWakeUpThrottling,SleepingTabsOnBackground,msEdgeSleepingTabs,"
            "msEdgeEfficiencyMode,BraveRewards,BraveWallet,BraveNews,BraveVPN,"
            "BraveAIChat,BraveSpeedreader"
        ),
        f"--user-agent={_default_user_agent(kind)}",
        f"--user-data-dir={ud}",
        f"--profile-directory={pdir}",
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins={origin}",
    ]
    if kind == "edge":
        cmd.append("--edge-skip-compat-layer-relaunch")
    if _platform_key() == "linux":
        cmd.append("--disable-dev-shm-usage")
    cmd.append("about:blank")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(75):
        time.sleep(0.25)
        probe = probe_cdp_port(port, timeout=0.8)
        if probe:
            return proc, probe["ws_url"]
        if proc.poll() is not None:
            # If handed off to an already running debug session on this isolated profile, attach cleanly.
            existing_port = read_devtools_active_port(ud)
            if existing_port:
                existing_probe = probe_cdp_port(existing_port, timeout=0.8)
                if existing_probe:
                    return None, existing_probe["ws_url"]
            raise RuntimeError(
                f"Browser headless exited early (code {proc.returncode}). "
                f"Kemungkinan jendela login atau proses background {cfg.get('display', kind)} masih mengunci profil '{ud}'. "
                f"Tutup penuh browser/tray icon profil tersebut lalu jalankan ulang."
            )
    _terminate_process_tree(proc)
    raise RuntimeError(f"Timed out waiting for headless Chromium CDP on port {port}")


def open_headless_session(cfg: dict, port_override: int | None = None):
    """
    Attach to this workspace's own configured loopback port if already active,
    otherwise allocate a free localhost port and launch the isolated profile in headless mode.
    """
    engine = cfg["engine"]
    pref_port = port_override or cfg.get("port")
    active = check_configured_ports(cfg, port_override=port_override)
    for info in active:
        if info["engine"] != engine:
            continue
        if engine == "bidi":
            return _BiDiSession(info["ws_url"], info["port"], owns_process=False, proc=None, cfg=cfg)
        return _CDPSession(info["ws_url"], info["port"], owns_process=False, proc=None, cfg=cfg)

    port = find_free_port(int(pref_port) if pref_port else None)
    proc, ws_url = _start_headless_process(cfg, port)
    owns_proc = proc is not None
    if engine == "bidi":
        return _BiDiSession(ws_url, port, owns_process=owns_proc, proc=proc, cfg=cfg)
    return _CDPSession(ws_url, port, owns_process=owns_proc, proc=proc, cfg=cfg)


# ============================================================================
# Auto-Detect Logged-In X Account in Isolated Headless Profile
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
    sess = open_headless_session(cfg, port_override=port_override)
    await sess.start()
    try:
        await sess.navigate("https://x.com/home")
        home_data = None
        for _ in range(18):
            await asyncio.sleep(0.8)
            home_data = await sess.evaluate_dom(DETECT_HOME_JS)
            if isinstance(home_data, dict) and (
                home_data.get("profileHref") or home_data.get("hasLoginPrompt")
            ):
                break

        profile_href = (home_data or {}).get("profileHref")
        if not profile_href or home_data.get("hasLoginPrompt"):
            hint = (
                " Jika Firefox baru menolak login di shortcut, buka Firefox biasa lalu akses about:profiles -> Launch profile in new browser pada profil "
                f"'{cfg.get('profile')}' -> login X -> tutup jendelanya."
                if cfg.get("engine") == "bidi"
                else ""
            )
            return {
                "logged_in": False,
                "url": (home_data or {}).get("url"),
                "browser": cfg["browser"],
                "profile": cfg.get("profile"),
                "message": (
                    "Akun X belum login di profil terisolasi ini. Buka shortcut/launcher profil terpisah "
                    "(diluncurkan sebagai browser normal tanpa debug flag) lalu login X sekali dan tutup jendelanya."
                    + hint
                ),
            }

        handle_clean = profile_href.strip("/").split("/")[0]
        handle = f"@{handle_clean}"

        await sess.navigate(f"https://x.com/{handle_clean}")
        prof_info = None
        for _ in range(12):
            await asyncio.sleep(0.6)
            prof_info = await sess.evaluate_dom(DETECT_PROFILE_JS)
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
    if kind == "ask":
        kind = prompt_browser_choice()
        if kind == "custom" and not args.exe_path:
            args.exe_path = input("Masukkan path executable browser custom (atau .app di macOS): ").strip().strip('"')
    elif kind == "auto":
        selected = choose_auto_browser()
        if not selected:
            raise FileNotFoundError(
                "Tidak ada browser (Chrome/Firefox/Edge/Brave) yang terdeteksi di perangkat ini. "
                "Install salah satu browser atau pakai --browser custom --exe-path <path>."
            )
        kind = selected

    if kind == "custom":
        if not args.exe_path:
            raise ValueError("--exe-path wajib diisi jika --browser custom")
        custom_path = Path(args.exe_path)
        exe = _resolve_macos_app_binary(custom_path) or args.exe_path
        engine = args.engine or "cdp"
        default_port = 9224 if engine == "cdp" else 9223
        display = custom_path.stem
    else:
        if kind not in BROWSER_META:
            raise ValueError(f"Browser tidak dikenal: {kind}. Pilih: auto, ask, chrome, edge, brave, firefox, custom")
        meta = BROWSER_META[kind]
        exe = resolve_browser_exe(kind, args.exe_path)
        if not exe:
            raise FileNotFoundError(f"Browser {meta['display']} tidak ditemukan di perangkat ini.")
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
        pdir = args.profile_directory or "Default"
        _tune_isolated_chromium_prefs(ud, kind, pdir)
        cfg["user_data_dir"] = str(ud.resolve())
        cfg["profile_directory"] = pdir

    cfg_path = Path(args.config)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    shortcut_info = None
    if not args.no_shortcut:
        shortcut_info = create_shortcut(cfg, also_repo_dir=True)
        cfg["shortcut"] = shortcut_info.get("desktop_shortcut")
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    cli_path = Path(args.cli_path)
    db_path = Path(args.db) if args.db else None
    run_workflow_cli(
        [
            "designate-browser",
            "--label",
            f"{display} headless isolated ({profile})",
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
        description="Cross-OS isolated headless browser connector, launcher creator, and X account detector."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Browser config JSON path")
    parser.add_argument("--cli-path", default=str(DEFAULT_CLI_PATH), help="Workflow Rust CLI path")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-browsers", help="Detect installed browsers, isolated workspace profiles, and configured ports")

    p_conn = sub.add_parser("connect", help="Connect chosen browser, create isolated profile & shortcut, and detect X user")
    p_conn.add_argument("--browser", default="auto", help="auto | ask | chrome | edge | brave | firefox | custom")
    p_conn.add_argument("--profile", default=None, help="Profile name (default: Raid for Firefox, Agent for Chromium)")
    p_conn.add_argument("--exe-path", default=None, help="Custom browser executable path")
    p_conn.add_argument("--engine", default=None, choices=["cdp", "bidi"], help="Engine when --browser custom")
    p_conn.add_argument("--user-data-dir", default=None, help="Custom isolated Chromium user-data-dir")
    p_conn.add_argument("--profile-directory", default="Default", help="Chromium profile subfolder")
    p_conn.add_argument("--port", type=int, default=None, help="Preferred debug port")
    p_conn.add_argument("--no-shortcut", action="store_true", help="Skip creating Desktop shortcut")
    p_conn.add_argument("--no-detect", action="store_true", help="Skip X account auto-detection")

    p_sc = sub.add_parser("create-shortcut", help="Create/refresh Desktop shortcut/launcher (.lnk/.desktop/.command/.sh) for the connected browser")
    p_sc.add_argument("--no-repo-copy", action="store_true", help="Only create on user Desktop")

    p_det = sub.add_parser("detect-account", help="Auto-detect logged-in X handle & display name in headless mode")
    p_det.add_argument("--port", type=int, default=None, help="Optional explicit debug port")
    p_det.add_argument("--no-confirm", action="store_true", help="Detect only without saving to SQLite")

    args = parser.parse_args()

    if args.cmd == "list-browsers":
        print(json.dumps(discover_browsers(Path(args.config)), indent=2, ensure_ascii=False))
    elif args.cmd == "connect":
        cmd_connect(args)
    elif args.cmd == "create-shortcut":
        cfg = load_config(Path(args.config))
        res = create_shortcut(cfg, also_repo_dir=not args.no_repo_copy)
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
