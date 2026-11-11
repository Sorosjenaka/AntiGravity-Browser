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


def build_browser_launch_args(cfg: dict) -> tuple[str, list[str]]:
    exe = cfg["executable"]
    profile = cfg.get("profile", "Agent")
    port = int(cfg.get("port") or 9223)
    origin = f"http://127.0.0.1:{port}"
    if cfg["engine"] == "bidi":
        args_list = [
            "-no-remote",
            "-P",
            profile,
            "--remote-debugging-port",
            str(port),
            "--remote-allow-hosts",
            "localhost,127.0.0.1",
            "--remote-allow-origins",
            origin,
            "https://x.com/home",
        ]
    else:
        ud = cfg["user_data_dir"]
        pdir = cfg.get("profile_directory", "Default")
        args_list = [
            f"--user-data-dir={ud}",
            f"--profile-directory={pdir}",
            f"--remote-debugging-port={port}",
            f"--remote-allow-origins={origin}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://x.com/home",
        ]
    return exe, args_list


def build_shortcut_spec(cfg: dict) -> tuple[str, str, str]:
    kind = cfg["browser"]
    profile = cfg.get("profile", "Agent")
    exe, args_list = build_browser_launch_args(cfg)
    port = int(cfg.get("port") or 9223)
    origin = f"http://127.0.0.1:{port}"
    if _platform_key() == "win32":
        if cfg["engine"] == "bidi":
            args = (
                f'-no-remote -P "{profile}" '
                f'--remote-debugging-port {port} '
                f'--remote-allow-hosts localhost,127.0.0.1 '
                f'--remote-allow-origins {origin} '
                f'https://x.com/home'
            )
        else:
            ud = cfg["user_data_dir"]
            pdir = cfg.get("profile_directory", "Default")
            args = (
                f'--user-data-dir="{ud}" '
                f'--profile-directory="{pdir}" '
                f'--remote-debugging-port={port} '
                f'--remote-allow-origins={origin} '
                f'--no-first-run --no-default-browser-check '
                f'https://x.com/home'
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
            await self._call("browsingContext.activate", {"context": self.ctx})

    async def navigate(self, url: str):
        await self._call(
            "browsingContext.navigate",
            {"context": self.ctx, "url": url, "wait": "complete"},
        )

    async def evaluate_dom(self, expr: str):
        res = await self._call(
            "script.evaluate",
            {
                "expression": expr,
                "target": {"context": self.ctx},
                "awaitPromise": False,
            },
        )
        if res.get("type") == "error":
            raise RuntimeError(f"BiDi script error: {res}")
        r = res.get("result", {})
        if r.get("type") == "exception":
            raise RuntimeError(f"DOM exception: {r}")
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
        self.ws = await websockets.connect(
            self.ws_url,
            origin=f"http://127.0.0.1:{self.port}",
            max_size=16 * 1024 * 1024,
        )
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
            state = await self.evaluate_dom("document.readyState")
            if state == "complete":
                break
            await asyncio.sleep(0.25)

    async def evaluate_dom(self, expr: str):
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
            raise RuntimeError(f"DOM exception: {r['exceptionDetails']}")
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


def _default_user_agent() -> str:
    plat = _platform_key()
    if plat == "darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    if plat == "linux":
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"


def _start_headless_process(cfg: dict, port: int) -> tuple[subprocess.Popen, str]:
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
        for _ in range(36):
            time.sleep(0.5)
            probe = probe_bidi_port(port, timeout=1.0)
            if probe:
                return proc, probe["ws_url"]
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Firefox headless exited early (code {proc.returncode}). "
                    f"Pastikan jendela login profil '{profile}' sudah ditutup sebelum menjalankan mode headless."
                )
        proc.terminate()
        raise RuntimeError(f"Timed out waiting for headless Firefox BiDi on port {port}")

    ud = Path(cfg["user_data_dir"])
    ud.mkdir(parents=True, exist_ok=True)
    pdir = cfg.get("profile_directory", "Default")
    cmd = [
        exe,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-agent={_default_user_agent()}",
        f"--user-data-dir={ud}",
        f"--profile-directory={pdir}",
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins={origin}",
    ]
    if _platform_key() == "linux":
        cmd.append("--disable-dev-shm-usage")
    cmd.append("about:blank")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
            return _BiDiSession(info["ws_url"], info["port"], owns_process=False, proc=None)
        return _CDPSession(info["ws_url"], info["port"], owns_process=False, proc=None)

    port = find_free_port(int(pref_port) if pref_port else None)
    proc, ws_url = _start_headless_process(cfg, port)
    if engine == "bidi":
        return _BiDiSession(ws_url, port, owns_process=True, proc=proc)
    return _CDPSession(ws_url, port, owns_process=True, proc=proc)


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
            return {
                "logged_in": False,
                "url": (home_data or {}).get("url"),
                "browser": cfg["browser"],
                "profile": cfg.get("profile"),
                "message": "Akun X belum login di profil terisolasi ini. Buka shortcut/launcher profil terpisah lalu login sekali dan tutup jendelanya.",
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
    if kind == "auto":
        ff = resolve_browser_exe("firefox")
        ff_profiles = {p["name"].lower() for p in list_firefox_profiles()}
        selected = None
        if ff and "raid" in ff_profiles:
            selected = "firefox"
        else:
            for cand in ("brave", "chrome", "edge", "firefox"):
                if resolve_browser_exe(cand):
                    selected = cand
                    break
        if not selected:
            raise FileNotFoundError(
                "Tidak ada browser (Firefox/Brave/Chrome/Edge) yang terdeteksi di perangkat ini. "
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
            raise ValueError(f"Browser tidak dikenal: {kind}. Pilih: auto, firefox, brave, chrome, edge, custom")
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
        cfg["user_data_dir"] = str(ud.resolve())
        cfg["profile_directory"] = args.profile_directory or "Default"

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
    p_conn.add_argument("--browser", default="auto", help="auto | firefox | brave | chrome | edge | custom")
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
