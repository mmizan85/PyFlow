"""
PyFlow GUI download cards and history rows.
"""

import logging
import os
import platform
import subprocess
from tkinter import messagebox

import customtkinter as ctk

from gui_theme import C, F, D
from utils import format_size

logger = logging.getLogger(__name__)


class DownloadCard(ctk.CTkFrame):
    def __init__(self, parent, task, on_cancel=None, **kw):
        super().__init__(
            parent,
            fg_color=C.BG_CARD,
            corner_radius=D.RADIUS,
            border_width=1,
            border_color=C.BORDER,
            **kw,
        )
        self._task = task
        self._on_cancel = on_cancel
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        self.thumb = ctk.CTkFrame(self, width=100, height=60, corner_radius=8, fg_color=C.BG_HOVER)
        self.thumb.grid(row=0, column=0, rowspan=2, padx=15, pady=15)
        self.thumb.grid_propagate(False)
        ctk.CTkLabel(
            self.thumb,
            text=self._thumb_text(),
            font=F.H2,
            text_color=C.ACCENT,
        ).place(relx=0.5, rely=0.5, anchor="center")

        self.title_lbl = ctk.CTkLabel(
            self,
            text=self._clip(self._task.title, 40),
            font=F.H3,
            text_color=C.T1,
            anchor="w",
        )
        self.title_lbl.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(15, 0))

        self.pct_lbl = ctk.CTkLabel(self, text=f"{self._task.progress:.1f}%", font=F.H2, text_color=C.ACCENT)
        self.pct_lbl.grid(row=0, column=2, sticky="e", padx=20, pady=(15, 0))

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 20), pady=(5, 15))
        mid.grid_columnconfigure(0, weight=1)

        self.pbar = ctk.CTkProgressBar(mid, height=8, corner_radius=4, progress_color=C.ACCENT, fg_color=C.BG_HOVER)
        self.pbar.set(self._task.progress / 100)
        self.pbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))

        self.stats_lbl = ctk.CTkLabel(mid, text=self._status_text(), font=F.TINY, text_color=C.T2, anchor="w")
        self.stats_lbl.grid(row=1, column=0, sticky="w")

        self.speed_lbl = ctk.CTkLabel(mid, text=self._speed_text(), font=F.TINY, text_color=C.ACCENT, anchor="e")
        self.speed_lbl.grid(row=1, column=1, sticky="e")

        self.cancel_btn = ctk.CTkButton(
            self,
            text="X",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=C.ACCENT_DIM,
            text_color=C.T3,
            command=self._cancel,
        )
        self.cancel_btn.place(relx=1.0, rely=0.0, x=-10, y=10, anchor="ne")

    def _thumb_text(self) -> str:
        return "CV" if getattr(self._task, "task_kind", "download") == "convert" else "DL"

    def _speed_text(self) -> str:
        prefix = "Conversion Speed" if getattr(self._task, "task_kind", "download") == "convert" else "Speed"
        return f"{prefix}: {self._task.speed}"

    def _status_text(self) -> str:
        task = self._task
        parts = [task.status or "Queued"]
        if getattr(task, "task_kind", "download") == "convert":
            if getattr(task, "output_format", None):
                parts.append(f"OUT {task.output_format.upper()}")
            if getattr(task, "source_size", None):
                parts.append(format_size(task.source_size))
        else:
            if task.eta and task.eta != "--":
                parts.append(f"ETA {task.eta}")
            parts.append(task.download_type.upper())
        return " | ".join(parts)

    def _cancel(self):
        if self._on_cancel and messagebox.askyesno("Cancel Task", f"Cancel task #{self._task.task_id[:8]}?"):
            self._on_cancel(self._task.task_id)

    @staticmethod
    def _clip(text, limit):
        text = text or "Untitled"
        return text[:limit] + ("..." if len(text) > limit else "")

    def update(self, task):
        self._task = task
        self.title_lbl.configure(text=self._clip(task.title, 40))
        self.pct_lbl.configure(text=f"{task.progress:.1f}%")
        self.pbar.set(task.progress / 100)
        self.stats_lbl.configure(text=self._status_text())
        self.speed_lbl.configure(text=self._speed_text())


class HistoryRow(ctk.CTkFrame):
    def __init__(self, parent, task, **kw):
        super().__init__(parent, fg_color=C.BG_CARD, corner_radius=8, border_width=0, **kw)
        self._task = task
        self._build()

    def _build(self):
        task = self._task
        completed = task.status == "Completed"

        self.grid_columnconfigure(1, weight=1)

        icon_text = "OK" if completed else "ERR"
        icon_color = C.SUCCESS if completed else C.ERROR
        ctk.CTkLabel(self, text=icon_text, font=F.H3, text_color=icon_color).grid(row=0, column=0, padx=12, pady=10)

        ctk.CTkLabel(self, text=(task.title or "Untitled")[:50], font=F.BODY, text_color=C.T1, anchor="w").grid(
            row=0,
            column=1,
            sticky="w",
        )

        badge = ctk.CTkFrame(self, fg_color=C.ACCENT_DIM, corner_radius=4)
        badge.grid(row=0, column=2, padx=5)
        badge_text = self._badge_text(task)
        ctk.CTkLabel(badge, text=badge_text, font=F.TINY, text_color=C.ACCENT, padx=6, pady=2).pack()

        if completed and task.file_path:
            btn = ctk.CTkButton(
                self,
                text="Open Folder",
                width=92,
                height=30,
                fg_color="transparent",
                hover_color=C.BG_HOVER,
                text_color=C.T2,
                command=self._open_folder,
            )
            btn.grid(row=0, column=3, padx=10)

    @staticmethod
    def _badge_text(task) -> str:
        if getattr(task, "task_kind", "download") == "convert" and getattr(task, "output_format", None):
            return task.output_format.upper()
        return task.download_type.upper()

    def _open_folder(self):
        try:
            folder = os.path.dirname(os.path.abspath(self._task.file_path))
            system_name = platform.system()
            if system_name == "Windows":
                os.startfile(folder)
            elif system_name == "Darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            logger.debug("Open folder failed: %s", exc)
