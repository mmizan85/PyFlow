"""
PyFlow – Terminal UI
─────────────────────
Rich-based live dashboard.
Columns never wrap or break regardless of title language.
Works correctly on Windows (cp1252/UTF-8), Linux, and macOS terminals.
"""

import asyncio
import logging
from datetime import datetime

from rich import box
from rich.cells import cell_len, set_cell_size
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)

# ── Status colour map ─────────────────────────────────────────────────────────
_STATUS_STYLE: dict = {
    "Queued":      "#ff4b4b",
    "Downloading": "#00d4ff",
    "Processing":  "#ff00ff",
    "Completed":   "bold green",
    "Failed":      "bold red",
    "Cancelled":   "dim",
}

# Safe ASCII progress bar – avoids multi-byte rendering issues on some terminals
_BAR_FILL = "█"
_BAR_EMPTY = "░"
_BAR_WIDTH = 18


def _progress_bar(pct: float) -> str:
    filled = int(pct / 100 * _BAR_WIDTH)
    bar = _BAR_FILL * filled + _BAR_EMPTY * (_BAR_WIDTH - filled)
    return f"{bar} {pct:5.1f}%"


class UIManager:
    """Manages the live terminal dashboard."""

    def __init__(self, download_manager, update_interval: float = 0.5):
        self.dm = download_manager
        self.update_interval = update_interval
        self._shutdown = False
        self._layout = None
        self._last_header_sig = None
        self._last_active_sig = None
        self._last_completed_sig = None
        self._last_footer_sig = None

        # Force safe encoding on Windows
        self.console = Console(
            highlight=False,
            emoji=True,
            # On Windows force UTF-8 output so box-drawing chars render
            force_terminal=True,
        )
        self._table_box = box.ASCII if (self.console.encoding or "").lower() in {"ascii", "us-ascii"} else box.ROUNDED

    @staticmethod
    def _fit_cell(text: str, max_cells: int) -> str:
        """Clip to terminal cell width so Unicode titles never break table layout."""
        clean = str(text or "").replace("\r", " ").replace("\n", " ").strip()
        if max_cells <= 1:
            return ""
        if cell_len(clean) <= max_cells:
            return clean
        return f"{set_cell_size(clean, max_cells - 1)}…"

    # ── Header ────────────────────────────────────────────────────────────────

    def _header(self) -> Panel:
        q   = self.dm.queue.qsize()
        act = len(self.dm.active_tasks)
        done = len(self.dm.completed_tasks)
        ver = getattr(self.dm, "ytdlp_version", "?")

        t = Text(justify="center")
        t.append("PyFlow ", style="#ff4b4b")
        t.append("Downloader\n", style="bold white")
        t.append(f"  Queued: ", style="dim"); t.append(f"{q}", style="yellow bold")
        t.append(f"  |  Active: ", style="dim"); t.append(f"{act}", style="cyan bold")
        t.append(f"  |  Done: ", style="dim"); t.append(f"{done}", style="green bold")
        t.append(f"  |  yt-dlp: ", style="dim"); t.append(f"v{ver}", style="bright_blue")
        t.append(f"  |  {datetime.now():%H:%M:%S}", style="dim")

        return Panel(t, title="[bold cyan]PyFlow Status[/bold cyan]",
                     border_style="#ff4b4b", padding=(0, 2))

    # ── Active Downloads Table ────────────────────────────────────────────────

    def _active_table(self) -> Table:
        tbl = Table(
            title="[bold cyan]⬇  Active Downloads[/bold cyan]",
            title_justify="left",
            show_header=True,
            header_style="bold white on dark_blue",
            border_style="bright_blue",
            box=self._table_box,
            show_lines=False,
            expand=True,
            padding=(0, 1),
        )

        # Fixed widths prevent column wrapping with long Unicode titles
        tbl.add_column("ID",       style="cyan", min_width= 3, max_width= 8, no_wrap=True)
        tbl.add_column("Title",    style="white", min_width=8, max_width=15,
                       no_wrap=True, overflow="ellipsis")
        tbl.add_column("Type",     style="yellow",        width=7,  no_wrap=True)
        tbl.add_column("Quality",  style="bright_yellow", width=7,  no_wrap=True)
        tbl.add_column("Status", min_width=8, max_width=12, no_wrap=True, overflow="ellipsis")
        tbl.add_column("Progress", min_width=18, max_width=27, no_wrap=True, overflow="ellipsis")
        tbl.add_column("Speed",    style="bright_cyan", min_width=10, max_width=13, no_wrap=True, overflow="ellipsis")
        tbl.add_column("ETA",      style="magenta",       width=5,  no_wrap=True)

        tasks = list(self.dm.active_tasks.values())
        if not tasks:
            tbl.add_row("[dim]-[/dim]", "[dim]No active downloads[/dim]",
                        *["[dim]-[/dim]"] * 6)
            return tbl

        for task in tasks:
            style = _STATUS_STYLE.get(task.status, "white")
            safe_title = escape(self._fit_cell(task.title, 30))
            tbl.add_row(
                escape(task.task_id),
                safe_title,
                escape(task.download_type.upper()),
                escape(task.quality),
                f"[{style}]{task.status}[/{style}]",
                _progress_bar(task.progress),
                escape(task.speed),
                escape(task.eta),
            )

        return tbl

    # ── Completed Table ───────────────────────────────────────────────────────

    def _completed_table(self) -> Table:
        tbl = Table(
            title="[bold green]✔  Recently Completed[/bold green]",
            title_justify="left",
            show_header=True,
            header_style="bold white on dark_green",
            border_style="green",
            box=self._table_box,
            show_lines=False,
            expand=True,
            padding=(0, 1),
        )

        tbl.add_column("ID",     style="cyan",   width=10, no_wrap=True)
        tbl.add_column("Title",  style="white",   min_width=15, max_width=25,
                       no_wrap=True, overflow="ellipsis")
        tbl.add_column("Type",   style="yellow",  width=7,  no_wrap=True)
        tbl.add_column("Quality", style="bright_yellow", width=7,  no_wrap=True)
        tbl.add_column("Status", width=10, no_wrap=True)
        tbl.add_column("File",   style="dim",     min_width=10, max_width=35,
                       no_wrap=True, overflow="ellipsis")

        recent = list(reversed(self.dm.completed_tasks[-8:]))
        if not recent:
            tbl.add_row("[dim]-[/dim]", "[dim]No completed downloads yet[/dim]",
                        *["[dim]-[/dim]"] * 3)
            return tbl

        for task in recent:
            style = _STATUS_STYLE.get(task.status, "white")
            file_name = ""
            if task.file_path:
                from pathlib import Path
                file_name = Path(task.file_path).name
            elif task.error:
                file_name = f"ERR: {task.error[:30]}"

            safe_title = escape(self._fit_cell(task.title, 50))
            tbl.add_row(
                escape(task.task_id),
                safe_title,
                escape(task.download_type.upper()),
                escape(task.quality),

                f"[{style}]{task.status}[/{style}]",
                escape(self._fit_cell(file_name, 35)),
            )

        return tbl

    # ── Footer ────────────────────────────────────────────────────────────────

    def _footer(self) -> Panel:
        t = Text()
        t.append("📁 ", style="dim")
        t.append(str(self.dm.download_dir), style="cyan")
        t.append("   |   Press ", style="dim")
        t.append("Ctrl+C", style="bold yellow")
        t.append(" to stop  |  pyflow --help for CLI options", style="dim")
        return Panel(t, border_style="dim", padding=(0, 1))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header",    size=5),
            Layout(name="active",    ratio=2),
            Layout(name="completed", ratio=2),
            Layout(name="footer",    size=3),
        )
        layout["header"].update(self._header())
        layout["active"].update(self._active_table())
        layout["completed"].update(self._completed_table())
        layout["footer"].update(self._footer())
        return layout

    def _header_sig(self):
        return (
            self.dm.queue.qsize(),
            len(self.dm.active_tasks),
            len(self.dm.completed_tasks),
            getattr(self.dm, "ytdlp_version", "?"),
            datetime.now().strftime("%H:%M:%S"),
        )

    def _active_sig(self):
        return tuple(
            (
                t.task_id, t.title, t.download_type, t.quality, t.status,
                round(t.progress, 1), t.speed, t.eta,
            )
            for t in self.dm.active_tasks.values()
        )

    def _completed_sig(self):
        recent = list(reversed(self.dm.completed_tasks[-8:]))
        return tuple(
            (t.task_id, t.title, t.download_type, t.status, t.file_path, t.error)
            for t in recent
        )

    def _footer_sig(self):
        return (str(self.dm.download_dir),)

    # ── Run Loop ──────────────────────────────────────────────────────────────

    async def run(self):
        """Render the live dashboard until shutdown."""
        self._layout = self._build_layout()
        with Live(
            self._layout,
            console=self.console,
            refresh_per_second=int(1 / self.update_interval),
            screen=True,
            auto_refresh=False,
        ) as live:
            while not self._shutdown:
                try:
                    await asyncio.sleep(self.update_interval)
                    header_sig = self._header_sig()
                    active_sig = self._active_sig()
                    completed_sig = self._completed_sig()
                    footer_sig = self._footer_sig()

                    changed = False
                    if header_sig != self._last_header_sig:
                        self._layout["header"].update(self._header())
                        self._last_header_sig = header_sig
                        changed = True
                    if active_sig != self._last_active_sig:
                        self._layout["active"].update(self._active_table())
                        self._last_active_sig = active_sig
                        changed = True
                    if completed_sig != self._last_completed_sig:
                        self._layout["completed"].update(self._completed_table())
                        self._last_completed_sig = completed_sig
                        changed = True
                    if footer_sig != self._last_footer_sig:
                        self._layout["footer"].update(self._footer())
                        self._last_footer_sig = footer_sig
                        changed = True

                    if changed:
                        live.refresh()
                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    logger.error(f"UI render error: {exc}", exc_info=True)

    def shutdown(self):
        self._shutdown = True
