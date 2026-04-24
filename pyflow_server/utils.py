"""
PyFlow Utility Functions
Handles path resolution, dependency detection, formatting, and configuration.
"""

import os
import platform
import shutil
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Config File ────────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "pyflow_config.json"


def load_config() -> dict:
    """Load persistent configuration from disk."""
    defaults = {
        "download_dir": None,   # None → use OS default
        "max_concurrent": 3,
        "show_ui": True,
        "log_level": "INFO",
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(config: dict) -> None:
    """Persist configuration to disk."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save config: {e}")


# ─── Download Directory ──────────────────────────────────────────────────────

def get_download_directory(override: Optional[str] = None) -> Path:
    """
    Return the download directory.

    Priority:
      1. CLI --path argument (override)
      2. Saved config value
      3. OS-default ~/Downloads/PyFlow
    """
    config = load_config()

    if override:
        path = Path(override)
    elif config.get("download_dir"):
        path = Path(config["download_dir"])
    else:
        path = Path.home() / "Downloads" / "PyFlow"

    path.mkdir(parents=True, exist_ok=True)
    return path


def set_download_directory(new_path: str) -> Path:
    """Persist a new download directory and return it."""
    config = load_config()
    config["download_dir"] = str(new_path)
    save_config(config)
    path = Path(new_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─── Tool Detection ──────────────────────────────────────────────────────────

def _find_tool(name: str) -> Optional[str]:
    """
    Locate an external tool (ffmpeg / yt-dlp binary).

    Search order:
      1. System PATH via shutil.which
      2. Same directory as this script
    """
    # 1. System PATH
    found = shutil.which(name)
    if found:
        return found

    # 2. Script directory (bundled alongside server files)
    script_dir = Path(__file__).parent
    candidates = [
        script_dir / name,
        script_dir / f"{name}.exe",   # Windows
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def find_ffmpeg() -> Tuple[Optional[str], str]:
    """
    Find ffmpeg on the system.

    Returns:
        (path_or_None, status_message)
    """
    path = _find_tool("ffmpeg")
    if path:
        return path, f"ffmpeg found: {path}"
    return None, "ffmpeg NOT found – install from https://ffmpeg.org or place binary next to server files"


def find_ytdlp_binary() -> Tuple[Optional[str], str]:
    """
    Find the yt-dlp *binary* (standalone executable) on the system.

    Returns:
        (path_or_None, status_message)
    """
    path = _find_tool("yt-dlp")
    if path:
        return path, f"yt-dlp binary found: {path}"
    return None, "yt-dlp binary NOT found – will use Python library if available"


def check_dependencies() -> dict:
    """
    Return a dict describing the status of every required dependency.

    Keys: yt_dlp_library, yt_dlp_binary, ffmpeg, fastapi, uvicorn, rich
    Values: True / False  (or a version string for tools)
    """
    status = {}

    # yt-dlp Python library
    try:
        import yt_dlp as _ydl
        status["yt_dlp_library"] = _ydl.version.__version__
    except Exception:
        status["yt_dlp_library"] = False

    # yt-dlp standalone binary
    path, _ = find_ytdlp_binary()
    status["yt_dlp_binary"] = path or False

    # ffmpeg
    ffmpeg_path, _ = find_ffmpeg()
    status["ffmpeg"] = ffmpeg_path or False

    # Python packages
    for pkg, imp in [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("rich", "rich")]:
        try:
            __import__(imp)
            status[pkg] = True
        except ImportError:
            status[pkg] = False

    return status


# ─── Formatting Helpers ──────────────────────────────────────────────────────

def format_size(bytes_size: int) -> str:
    """Convert bytes to a human-readable string (e.g. '1.5 MB')."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def format_time(seconds: int) -> str:
    """Convert seconds to a human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def sanitize_filename(filename: str) -> str:
    """Strip characters that are invalid in file names on any OS."""
    for ch in r'<>:"/\|?*':
        filename = filename.replace(ch, "_")
    filename = filename.strip(". ")
    return filename[:200]


# ─── Dependency Report ───────────────────────────────────────────────────────

def print_dependency_status() -> bool:
    """Print a formatted dependency status table.  Returns True if all OK."""
    print("\n📦 Checking Dependencies...")
    print("=" * 55)

    deps = check_dependencies()
    all_ok = True

    rows = [
        ("yt-dlp library",  deps["yt_dlp_library"]),
        ("yt-dlp binary",   deps["yt_dlp_binary"]),
        ("ffmpeg",          deps["ffmpeg"]),
        ("fastapi",         deps["fastapi"]),
        ("uvicorn",         deps["uvicorn"]),
        ("rich",            deps["rich"]),
    ]

    for name, val in rows:
        if val:
            label = f"✅ {val}" if isinstance(val, str) else "✅ OK"
        else:
            label = "❌ Not found"
            if name in ("yt-dlp library", "fastapi", "uvicorn", "rich"):
                all_ok = False

        print(f"  {name:<20} {label}")

    if not all_ok:
        print("\n⚠️  Install missing Python packages:  pip install -r requirements.txt")
        print("   Install ffmpeg from: https://ffmpeg.org/download.html")

    print("=" * 55)
    print()
    return all_ok

