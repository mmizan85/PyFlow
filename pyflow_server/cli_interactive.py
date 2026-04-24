"""
PyFlow CLI - Interactive "TV-Style" Mode v4.2
Powered by Rich: metadata previews, menu navigation, and live dashboards.
Fixes: Ctrl+C graceful handling, case-insensitive back navigation, yt_dlp option keys,
       UI modernization, expanded format/quality categories, and typo/artifact resolution.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import yt_dlp
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.status import Status
from rich.table import Table
from rich.text import Text

from download_manager import DownloadManager, DownloadTask
from utils import get_download_directory, load_config, save_config, set_download_directory

console = Console()
logger = logging.getLogger(__name__)

# Theme Palette
RED = "#ff4b4b"
WHITE = "#ffffff"
ASH = "#666666"
TEAL = "#00d4ff"
GREEN = "#2ecc71"
YELLOW = "#f1c40f"
BLUE = "#3498db"

BACK = "B"
ACTION_BACK_TO_URL = "back_to_url"
ACTION_COMPLETE = "complete"
ACTION_CONTINUE = "continue"
CANCEL_MSG = f"[{ASH}]🛑 Operation cancelled. Returning to previous menu...[/]"

SUPPORTED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be", "facebook.com", "www.facebook.com", "fb.watch",
    "twitter.com", "www.twitter.com", "vimeo.com", "www.vimeo.com",
    "dailymotion.com", "www.dailymotion.com", "tiktok.com", "www.tiktok.com",
    "instagram.com", "www.instagram.com",
}

def _is_supported_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return host in SUPPORTED_HOSTS

def _extract_video_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    path_parts = [p for p in parsed.path.split("/") if p]
    query = parse_qs(parsed.query)

    if host in {"youtu.be", "www.youtu.be"} and path_parts:
        return path_parts[0]
    if not path_parts:
        return query.get("v", [None])[0]
    if path_parts[0] == "watch":
        return query.get("v", [None])[0]
    if path_parts[0] in {"shorts", "live", "embed", "v"} and len(path_parts) > 1:
        return path_parts[1]
    return query.get("v", [None])[0]

def sanitize_media_url(url: str, playlist_mode: bool = False) -> Tuple[str, Optional[str]]:
    raw_url = url.strip()
    if not raw_url:
        raise ValueError("URL cannot be empty.")
    if not _is_supported_url(raw_url):
        return raw_url, None

    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)
    video_id = _extract_video_id(raw_url)
    playlist_id = query.get("list", [None])[0]

    if playlist_id and not video_id and not playlist_mode:
        raise ValueError("Playlist-only URLs are disabled in single-video mode. Open a specific video instead.")

    if not video_id:
        return raw_url, None

    clean_url = f"https://www.youtube.com/watch?v={video_id}"
    note = None
    if raw_url != clean_url:
        note = "Targeting the single video and trimming extra parameters."
    if playlist_id and not playlist_mode:
        note = "Playlist parameters removed. Targeting the selected video only."
    return clean_url, note

def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "Unknown"
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"

def _format_upload_date(value: Optional[str]) -> str:
    if not value:
        return "Unknown"
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%b %d, %Y")
    except ValueError:
        return value

class MetadataFetcher:
    """Fetch video metadata quickly without downloading media."""
    FAST_OPTS = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": True, "noplaylist": True, "playlist_items": "1",
        "lazy_playlist": True, "cachedir": False,
    }
    FALLBACK_OPTS = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": False, "noplaylist": True, "playlist_items": "1",
        "lazy_playlist": True, "cachedir": False,
    }

    @classmethod
    def fetch(cls, url: str) -> Dict[str, Any]:
        for opts in (cls.FAST_OPTS, cls.FALLBACK_OPTS):
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                except Exception as exc:
                    logger.debug(f"Metadata fetch failed for {url}: {exc}")
                    continue
            normalized = cls._normalize_info(info)
            if normalized.get("title"):
                return normalized
        logger.error(f"Unable to retrieve metadata for {url}")
        return {}

    @staticmethod
    def _normalize_info(info: Dict[str, Any]) -> Dict[str, Any]:
        if not info:
            return {}
        if info.get("entries"):
            entries = [e for e in info["entries"] if e]
            if entries:
                info = entries[0]

        if not info.get("duration_string") and info.get("duration"):
            info["duration_string"] = _format_duration(info.get("duration"))

        thumbs = info.get("thumbnails") or []
        if not info.get("thumbnail") and thumbs:
            info["thumbnail"] = thumbs[-1].get("url")

        info.setdefault("formats", [])
        return info

class InteractiveCLI:
    def __init__(self, dm: DownloadManager):
        self.dm = dm
        self._stop_event = threading.Event()

    def _safe_prompt(self, prompt_func, *args, **kwargs):
        """Wrapper to catch Ctrl+C and gracefully return to previous menu."""
        try:
            return prompt_func(*args, **kwargs)
        except KeyboardInterrupt:
            console.print(f"\n{CANCEL_MSG}")
            return BACK

    async def start(self, initial_url: Optional[str] = None):
        """Main entry point for the interactive session."""
        pending_input = initial_url
        while True:
            console.clear()
            self._print_banner()

            raw_input = pending_input if pending_input is not None else self._get_url_input()
            pending_input = None

            if raw_input is None or raw_input.strip().upper() in {"Q", "QUIT", "EXIT"}:
                console.print(f"\n[{YELLOW}]👋 Goodbye! Thank you for using PyFlow.[/]")
                return

            urls = [item.strip() for item in raw_input.split(",") if item.strip()]
            if not urls:
                continue

            completed_any = False
            restart_url_prompt = False

            for raw_url in urls:
                result = await self._process_single_url(raw_url)
                if result == ACTION_BACK_TO_URL:
                    restart_url_prompt = True
                    break
                if result == ACTION_COMPLETE:
                    completed_any = True

            if restart_url_prompt:
                continue

            if completed_any:
                choice = self._safe_prompt(
                    Confirm.ask,
                    f"\n[{WHITE}]📥 Download another link?[/] ",
                    default=True,
                )
                if choice is False or choice == BACK:
                    console.print(f"\n[{YELLOW}]👋 Goodbye! Thank you for using PyFlow.[/]")
                    return

    def _print_banner(self):
        banner = Panel(
            Text.assemble(
                ("PyFlow", f"bold {RED}"), (" Pro ", WHITE),
                (" - Interactive CLI", ASH),
            ),
            subtitle=f"[{ASH}]The Ultimate Terminal Downloading Experience[/]",
            box=box.DOUBLE_EDGE,
            border_style=RED,
            padding=(1, 2),
        )
        console.print(banner)

    def _get_url_input(self) -> str:
        try:
            import pyperclip
            clipboard_value = pyperclip.paste().strip()
            if clipboard_value.startswith(("http://", "https://")):
                use_clip = self._safe_prompt(
                    Confirm.ask,
                    f"\n[{WHITE}]📋 Clipboard URL detected:[/] [cyan]{clipboard_value}[/]\n[{ASH}]Use it?[/] ",
                    default=True,
                )
                if use_clip is True:
                    return clipboard_value
        except Exception:
            pass

        return self._safe_prompt(
            Prompt.ask,
            f"\n[{WHITE}]🔗 Enter Video URL(s) (comma-separated) or 'Q' to quit[/] "
        ).strip()

    async def _process_single_url(self, raw_url: str) -> str:
        try:
            url, note = sanitize_media_url(raw_url)
        except ValueError as exc:
            console.print(f"\n[{RED}]❌ Error:[/] {exc}")
            return ACTION_BACK_TO_URL

        with Status(f"[{TEAL}]⚡ Fetching stream metadata...[/]", spinner="dots", console=console):
            info = await asyncio.to_thread(MetadataFetcher.fetch, url)

        if not info:
            console.print(f"[{RED}]❌ Failed to retrieve metadata for this URL.[/]")
            return ACTION_CONTINUE

        if note:
            console.print(f"[{ASH}]ℹ️ {note}[/]")

        self._show_video_profile(info)

        plan = self._resolve_download_plan(info)
        if plan is None or plan == BACK:
            return ACTION_BACK_TO_URL

        task_id = await self.dm.add_download(
            url=url,
            download_type=plan["download_type"],
            is_playlist=False,
            quality=plan["quality"],
            format_type=plan["format_type"],
            title=info.get("title", "Untitled Video"),
        )

        await self._show_live_dashboard(task_id)
        return ACTION_COMPLETE

    def _resolve_download_plan(self, info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        while True:
            category = self._select_category()
            if category == BACK:
                return None

            if category == "1":
                preset = self._select_quick_preset()
                if preset == BACK:
                    continue
                return preset

            if category == "2":
                while True:
                    quality = self._select_video_quality()
                    if quality == BACK:
                        break
                    fmt = self._select_video_format()
                    if fmt == BACK:
                        continue
                    return {"download_type": "video", "quality": quality, "format_type": fmt}

            if category == "3":
                while True:
                    quality = self._select_audio_quality()
                    if quality == BACK:
                        break
                    fmt = self._select_audio_format()
                    if fmt == BACK:
                        continue
                    return {"download_type": "audio", "quality": quality, "format_type": fmt}

            if category == "4":  # Archive/Preserve
                return {"download_type": "video", "quality": "F-video", "format_type": "mp4"}


    def _select_category(self) -> str:
        console.print(f"\n[{WHITE}]📂 Download Categories[/]")
        options = [
            ("1", "⚡ Quick Preset", "Device-optimized auto-selection"),
            ("2", "🎬 Video Manual", "Custom resolution & container"),
            ("3", "🎵 Audio Manual", "Custom bitrate & codec"),
            ("4", "📱 Feature Phones", "Optimized for older devices"),
            ("B", "🔙 Back", "Return to URL input"),
        ]
        return self._prompt_menu("🎯 Select Category", "Option", options, "1")

    def _select_quick_preset(self) -> Dict[str, str] | str:
        options = [
            ("1", "💻 PC Best", "Up to 4K MP4 (H.264)"),
            ("2", "📱 iPhone/Android", "iOS/Android 720p MP4 (H.264)"),
            ("3", "📺 TV", "Full HD MP4 (H.264)"),
            ("4", "🎞️ Archive/Preserve", "Best quality MKV with subtitles"),
            ("5", "🎙️ Podcast/Voice", "Small size, clear speech AAC"),
            ("6", "📟 Feature Phones", "Optimized for older devices"),
            ("7", "🎵 Audio Quick", "Best MP3"),
            ("B", "🔙 Back", "Return to categories"),
        ]
        choice = self._prompt_menu("⚡ Quick Preset", "Preset", options, "1")
        if choice == BACK:
            return BACK
        return {
            "1": {"download_type": "video", "quality": "2160p", "format_type": "mp4"},
            "2": {"download_type": "video", "quality": "720p", "format_type": "mp4"},
            "3": {"download_type": "video", "quality": "1080p", "format_type": "mp4"},
            "4": {"download_type": "video", "quality": "best", "format_type": "mkv"},
            "5": {"download_type": "audio", "quality": "best", "format_type": "aac"},
            "6": {"download_type": "video", "quality": "F-video", "format_type": "mp4"},
            "7": {"download_type": "audio", "quality": "best", "format_type": "mp3"},
        }[choice]

    def _select_video_quality(self) -> str:
        options = [
            ("1", "2160p60", "4K 60FPS"), ("2", "2160p", "4K Standard"),
            ("3", "1440p60", "2K 60FPS"), ("4", "1440p", "2K Standard"),
            ("5", "1080p60", "Full HD 60FPS"), ("6", "1080p", "Full HD"),
            ("7", "720p", "HD"), ("8", "480p", "SD"),
            ("9", "360p", "Low Data"), ("10", "best", "Max Source"),
            ("B", "🔙 Back", "Return"),
        ]
        choice = self._prompt_menu("🚀 Video Resolution", "Res", options, "6")
        if choice == BACK:
            return BACK
        return {k: v for k, v, _ in options}[choice]

    def _select_video_format(self) -> str:
        options = [
            ("1", "mp4", "MP4 - Universal"),
            ("2", "mkv", "MKV - Archival/Subtitles"),
            ("3", "webm", "WebM - Efficient/VP9"),
            ("4", "best", "Auto-Best"),
            ("B", "🔙 Back", "Return"),
        ]
        choice = self._prompt_menu("🎬 Container Format", "Ext", options, "1")
        if choice == BACK:
            return BACK
        return {k: v for k, v, _ in options}[choice]

    def _select_audio_quality(self) -> str:
        options = [
            ("1", "best", "Max Bitrate"),
            ("2", "320", "320 kbps"), ("3", "256", "256 kbps"),
            ("4", "192", "192 kbps"), ("5", "128", "128 kbps"),
            ("6", "96", "96 kbps"), ("7", "64", "64 kbps"),
            ("B", "🔙 Back", "Return"),
        ]
        choice = self._prompt_menu("🎵 Audio Bitrate", "kbps", options, "1")
        if choice == BACK:
            return BACK
        return {k: v for k, v, _ in options}[choice]

    def _select_audio_format(self) -> str:
        options = [
            ("1", "mp3", "MP3 - Universal"),
            ("2", "aac", "AAC - High Quality"),
            ("3", "flac", "FLAC - Lossless"),
            ("4", "opus", "OPUS - Efficient"),
            ("5", "wav", "WAV - Uncompressed"),
            ("6", "best", "Auto-Best"),
            ("B", "🔙 Back", "Return"),
        ]
        choice = self._prompt_menu("🎧 Audio Codec", "Codec", options, "1")
        if choice == BACK:
            return BACK
        return {k: v for k, v, _ in options}[choice]

    def _prompt_menu(self, title: str, header: str, options: List[Tuple[str, str, str]], default: str) -> str:
        table = Table(show_header=True, header_style=f"bold {RED}", box=box.ROUNDED, expand=True)
        table.add_column("Key", justify="center", no_wrap=True, width=4)
        table.add_column(header, style=WHITE, width=12)
        table.add_column("Description", style=ASH, overflow="Truncate")

        for key, label, desc in options:
            table.add_row(key, label, desc)

        console.print(table)
        choice = self._safe_prompt(Prompt.ask, f"\n[{WHITE}]{title}[/] ", choices=[k for k, _, _ in options], default=default)
        return choice.strip().upper() if isinstance(choice, str) else BACK

    def _show_video_profile(self, info: Dict[str, Any]):
        title = info.get("title", "Unknown Title")
        channel = info.get("uploader") or info.get("channel") or "Unknown Channel"
        duration = info.get("duration_string") or _format_duration(info.get("duration"))
        views = f"{info.get('view_count', 0):,}" if info.get("view_count") else "Unknown"
        date = _format_upload_date(info.get("upload_date"))
        thumb = "✅ Ready" if info.get("thumbnail") else "⚠️ Unavailable"
        streams = f"🔹 {len(info.get('formats', []))} streams" if info.get("formats") else "🔄 Optimized auto-detect"

        profile = Table.grid(expand=True)
        profile.add_column(style=RED, justify="right", width=14)
        profile.add_column(style=WHITE)
        profile.add_row("Title", f"[bold]{title}[/]")
        profile.add_row("Channel", channel)
        profile.add_row("Duration", duration)
        profile.add_row("Views", views)
        profile.add_row("Date", date)
        profile.add_row("Thumbnail", thumb)
        profile.add_row("Streams", streams)

        console.print(
            Panel(
                profile,
                title=f"[{RED}]📺 Video Intelligence Profile[/]",
                border_style=ASH,
                padding=(1, 2),
            )
        )

    async def _show_live_dashboard(self, task_id: str):
        console.print()
        with Live(self._generate_dashboard_table(task_id), refresh_per_second=4, console=console) as live:
            while True:
                task = self.dm.active_tasks.get(task_id) or next(
                    (t for t in self.dm.completed_tasks if t.task_id == task_id), None
                )
                if not task:
                    await asyncio.sleep(0.4)
                    continue

                live.update(self._generate_dashboard_table(task_id))
                if task.status in {"Completed", "Failed", "Cancelled"}:
                    break
                await asyncio.sleep(0.25)

        final = next((t for t in self.dm.completed_tasks if t.task_id == task_id), None)
        if final:
            if final.status == "Completed":
                self._show_success_card(final)
            elif final.status == "Failed":
                console.print(Panel(f"[bold {RED}]Download Failed[/]\n{final.error}", border_style=RED))
            else:
                console.print(Panel("[bold red]Download Cancelled[/]", border_style=RED))

    def _generate_dashboard_table(self, task_id: str) -> Table:
        task = self.dm.active_tasks.get(task_id) or next(
            (t for t in self.dm.completed_tasks if t.task_id == task_id), None
        )
        table = Table(show_header=True, header_style=f"bold {RED}", box=box.SIMPLE_HEAD, expand=True)
        table.add_column("File", ratio=3, overflow="ellipsis")
        table.add_column("Progress", ratio=2)
        table.add_column("Speed", justify="right", ratio=1)
        table.add_column("ETA", justify="right", ratio=1)
        table.add_column("Status", justify="center", ratio=1)

        if not task:
            table.add_row("Connecting...", "", "", "", "⏳")
            return table

        width = console.size.width
        title_limit = 22 if width < 100 else 38
        title = task.title if len(task.title) <= title_limit else f"{task.title[:title_limit-2]}..."
        pbar = self._render_progress_bar(task.progress, width)

        status_icons = {"Downloading": "📥", "Processing": "⚙️", "Completed": "✅", "Failed": "❌", "Cancelled": "🛑", "Queued": "🕒"}
        icon = status_icons.get(task.status, "•")

        table.add_row(title, pbar, f"[bold {GREEN}]{task.speed}[/]", task.eta, f"{icon} {task.status}")
        return table

    def _render_progress_bar(self, percent: float, width: int) -> str:
        bar_width = 16 if width < 100 else 28
        filled = max(0, min(bar_width, int(round((percent / 100.0) * bar_width))))
        empty = bar_width - filled
        return f"[{YELLOW}]{'█' * filled}{'░' * empty}[/] {percent: >5.1f}%"

    def _show_success_card(self, task: DownloadTask):
        console.clear()
        card = Panel(
            Text.assemble(
                ("✅ Download Completed Successfully!", f"bold {GREEN}"),
                "\n\n",
                ("📄 File: ", WHITE), (f"{task.title}", "bold"),
                "\n",
                ("📍 Path: ", WHITE), (task.file_path, TEAL),
                "\n",
                ("📦 Type: ", WHITE), f"{task.download_type.upper()} ({task.format_type.upper()})",
                "\n\n",
                (f"Thank you for using PyFlow Pro!", ASH)
            ),
            title=f"[{GREEN}]🎉 Success[/]",
            border_style=GREEN,
            padding=(1, 2),
        )
        console.print(card)

    def manage_settings(self):
        while True:
            console.clear()
            self._print_banner()
            console.print(f"\n[{WHITE}]🛠️ Interactive Settings Manager[/]\n")

            cfg = load_config()
            table = Table(box=box.ROUNDED)
            table.add_column("Setting", style=RED)
            table.add_column("Current Value", style=WHITE)
            table.add_row("Download Path", str(get_download_directory()))
            table.add_row("Max Concurrent", str(cfg.get("max_concurrent", 3)))
            console.print(table)

            action = self._safe_prompt(
                Prompt.ask,
                f"\n[{WHITE}]Choose Action[/] (1: Path, 2: Concurrency, B: Back) ",
                choices=["1", "2", "B"],
                default="B",
            ).upper()

            if action == BACK:
                return
            if action == "1":
                new_path = self._safe_prompt(Prompt.ask, "Enter new download path: ").strip()
                if os.path.isdir(new_path):
                    set_download_directory(new_path)
                    console.print(f"[{GREEN}]✅ Path updated![/]")
                else:
                    console.print(f"[{RED}]❌ Invalid directory![/]")
            elif action == "2":
                new_val = self._safe_prompt(Prompt.ask, "Enter limit (1-5): ", choices=["1", "2", "3", "4", "5"])
                if new_val != BACK:
                    cfg["max_concurrent"] = int(new_val)
                    save_config(cfg)
                    console.print(f"[{GREEN}]✅ Concurrency limit updated![/]")

            self._safe_prompt(Prompt.ask, f"\n[{ASH}]Press Enter to continue[/] ", default=" ")
