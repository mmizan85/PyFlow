"""
PyFlow GUI dashboard.
"""

import asyncio
import logging
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gui_download_card import DownloadCard, HistoryRow
from gui_theme import C, D, F
from gui_widgets import OptionPill, StatChip, URLInput
from utils import format_size

logger = logging.getLogger(__name__)

try:
    import windnd

    DND_SUPPORT = True
except ImportError:
    windnd = None
    DND_SUPPORT = False


ONLINE_MODE = "Online Downloader"
LOCAL_MODE = "Local Converter"

_VIDEO_QUALITIES = ["Best Video", "4K (2160p)", "1080p", "720p", "480p", "360p", "F-Phone"]
_AUDIO_QUALITIES = ["Best Audio", "320 kbps", "256 kbps", "192 kbps", "128 kbps"]
_VIDEO_FORMATS = ["MP4", "MKV", "WebM"]
_AUDIO_FORMATS = ["MP3", "M4A", "FLAC"]

_VIDEO_QUALITY_MAP = {
    "Best Video": "best",
    "4K (2160p)": "2160p",
    "1080p": "1080p",
    "720p": "720p",
    "480p": "480p",
    "360p": "360p",
    "F-Phone": "F-video",
}
_AUDIO_QUALITY_MAP = {
    "Best Audio": "best",
    "320 kbps": "320",
    "256 kbps": "256",
    "192 kbps": "192",
    "128 kbps": "128",
}


class CompletionToast(ctk.CTkFrame):
    def __init__(self, parent, title: str, message: str, **kwargs):
        super().__init__(
            parent,
            fg_color=C.BG_CARD,
            border_width=1,
            border_color=C.BORDER,
            corner_radius=D.RADIUS,
            **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=F.H3, text_color=C.ACCENT).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4)
        )
        ctk.CTkLabel(
            self,
            text=message,
            font=F.BODY_SM,
            text_color=C.T2,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))


class Dashboard(ctk.CTkFrame):
    def __init__(self, parent, download_manager, **kw):
        super().__init__(parent, fg_color=C.BG_MAIN, corner_radius=0, **kw)
        self._dm = download_manager
        self._cards = {}
        self._history_signature = ()
        self._mode = ONLINE_MODE
        self._local_source_path = None
        self._local_source_info = None
        self._local_preset_map = {}
        self._completed_conversion_notices = set()
        self._toast = None
        self._toast_after_id = None
        self._build()
        self._sync_mode_ui()
        self._tick()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        hero = ctk.CTkFrame(self, fg_color="transparent")
        hero.grid(row=0, column=0, sticky="ew", padx=30, pady=(30, 20))
        hero.grid_columnconfigure(0, weight=1)

        self.mode_title_lbl = ctk.CTkLabel(
            hero,
            text="Download",
            font=F.H2,
            text_color=C.T1,
        )
        self.mode_title_lbl.grid(row=0, column=0, sticky="w")

        self.online_panel = ctk.CTkFrame(hero, fg_color="transparent")
        self.online_panel.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        self.online_panel.grid_columnconfigure(0, weight=1)

        self.url_input = URLInput(self.online_panel)
        self.url_input.grid(row=0, column=0, sticky="ew")

        online_ctrl = ctk.CTkFrame(self.online_panel, fg_color="transparent")
        online_ctrl.grid(row=1, column=0, sticky="ew", pady=(15, 0))

        self.type_pill = OptionPill(online_ctrl, values=["Video", "Audio"], command=self._type_changed, width=100)
        self.type_pill.set("Video")
        self.type_pill.pack(side="left", padx=(0, 10))

        self.quality_pill = OptionPill(online_ctrl, values=_VIDEO_QUALITIES, width=130)
        self.quality_pill.set("1080p")
        self.quality_pill.pack(side="left", padx=(0, 10))

        self.format_pill = OptionPill(online_ctrl, values=_VIDEO_FORMATS, width=90)
        self.format_pill.set("MP4")
        self.format_pill.pack(side="left", padx=(0, 10))

        self.playlist_cb = ctk.CTkCheckBox(
            online_ctrl,
            text="Playlist",
            font=F.BODY_SM,
            fg_color=C.ACCENT,
            hover_color=C.ACCENT_HOVER,
            text_color=C.T2,
        )
        self.playlist_cb.pack(side="left", padx=10)

        self.online_start_btn = ctk.CTkButton(
            online_ctrl,
            text="Download",
            font=F.H3,
            fg_color=C.ACCENT,
            hover_color=C.ACCENT_HOVER,
            text_color=C.T1,
            corner_radius=10,
            width=180,
            height=45,
            command=self._start_download,
        )
        self.online_start_btn.pack(side="right")

        self.local_panel = ctk.CTkFrame(
            hero,
            fg_color=C.BG_CARD,
            border_width=1,
            border_color=C.BORDER,
            corner_radius=D.RADIUS,
        )
        self.local_panel.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        self.local_panel.grid_columnconfigure(0, weight=1)

        local_top = ctk.CTkFrame(self.local_panel, fg_color="transparent")
        local_top.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        local_top.grid_columnconfigure(1, weight=1)

        self.select_file_btn = ctk.CTkButton(
            local_top,
            text="Select File",
            font=F.H3,
            fg_color=C.ACCENT,
            hover_color=C.ACCENT_HOVER,
            text_color=C.T1,
            corner_radius=10,
            width=140,
            height=40,
            command=self._select_local_file,
        )
        self.select_file_btn.grid(row=0, column=0, sticky="w")

        info_wrap = ctk.CTkFrame(local_top, fg_color="transparent")
        info_wrap.grid(row=0, column=1, sticky="ew", padx=(16, 0))
        info_wrap.grid_columnconfigure(0, weight=1)

        self.local_file_name_lbl = ctk.CTkLabel(
            info_wrap,
            text="No file selected",
            font=F.H3,
            text_color=C.T1,
            anchor="w",
        )
        self.local_file_name_lbl.grid(row=0, column=0, sticky="w")

        self.local_file_meta_lbl = ctk.CTkLabel(
            info_wrap,
            text="Choose a local video or audio file to convert.",
            font=F.BODY_SM,
            text_color=C.T2,
            anchor="w",
        )
        self.local_file_meta_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.drop_zone = ctk.CTkFrame(
            self.local_panel,
            fg_color=C.BG_HOVER,
            border_width=1,
            border_color=C.BORDER,
            corner_radius=D.RADIUS,
            height=110,
        )
        self.drop_zone.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.drop_zone.grid_propagate(False)

        self.drop_title_lbl = ctk.CTkLabel(
            self.drop_zone,
            text="Drop a file here or click to browse",
            font=F.H3,
            text_color=C.T1,
        )
        self.drop_title_lbl.place(relx=0.5, rely=0.42, anchor="center")

        drop_subtitle = (
            "Drop onto any part of this card or click to browse."
            if DND_SUPPORT
            else "Drag and drop helper is unavailable right now. Click to browse instead."
        )
        self.drop_subtitle_lbl = ctk.CTkLabel(
            self.drop_zone,
            text=drop_subtitle,
            font=F.BODY_SM,
            text_color=C.T2,
        )
        self.drop_subtitle_lbl.place(relx=0.5, rely=0.62, anchor="center")

        for widget in (self.drop_zone, self.drop_title_lbl, self.drop_subtitle_lbl):
            widget.bind("<Button-1>", lambda _event: self._select_local_file())

        local_ctrl = ctk.CTkFrame(self.local_panel, fg_color="transparent")
        local_ctrl.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))

        self.local_format_pill = OptionPill(
            local_ctrl,
            values=[fmt.upper() for fmt in self._dm.converter.list_formats()],
            command=self._local_format_changed,
            width=120,
        )
        self.local_format_pill.pack(side="left", padx=(0, 10))
        self.local_format_pill.set(self.local_format_pill.cget("values")[0])

        self.local_preset_pill = OptionPill(
            local_ctrl,
            values=["Choose preset"],
            command=self._local_preset_changed,
            width=180,
        )
        self.local_preset_pill.pack(side="left", padx=(0, 10))
        self.local_preset_pill.set("Choose preset")

        self.local_start_btn = ctk.CTkButton(
            local_ctrl,
            text="Convert",
            font=F.H3,
            fg_color=C.ACCENT,
            hover_color=C.ACCENT_HOVER,
            text_color=C.T1,
            corner_radius=10,
            width=180,
            height=45,
            command=self._start_local_conversion,
            state="disabled",
        )
        self.local_start_btn.pack(side="right")

        self.local_desc_lbl = ctk.CTkLabel(
            self.local_panel,
            text="Choose an output format to see preset details.",
            font=F.BODY_SM,
            text_color=C.T2,
            anchor="w",
            justify="left",
        )
        self.local_desc_lbl.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))

        self._install_drop_support()
        self._local_format_changed(self.local_format_pill.get())

        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 15))

        self.stat_active = StatChip(stats, "ACT", "Active", "0/3")
        self.stat_active.pack(side="left", padx=(0, 10))

        self.stat_queued = StatChip(stats, "Q", "Queued", "0")
        self.stat_queued.pack(side="left", padx=(0, 10))

        self.stat_done = StatChip(stats, "OK", "Completed", "0")
        self.stat_done.pack(side="left")

        lists = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        lists.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        lists.grid_columnconfigure(0, weight=1)

        self.active_hdr = ctk.CTkLabel(lists, text="Active Tasks", font=F.H3, text_color=C.T1)
        self.active_hdr.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        self.active_container = ctk.CTkFrame(lists, fg_color="transparent")
        self.active_container.grid(row=1, column=0, sticky="ew")
        self.active_container.grid_columnconfigure(0, weight=1)

        self.no_active_lbl = ctk.CTkLabel(
            self.active_container,
            text="No active tasks.",
            font=F.BODY_SM,
            text_color=C.T3,
        )
        self.no_active_lbl.grid(row=0, column=0, pady=20)

        hist_hdr = ctk.CTkLabel(lists, text="Recent History", font=F.H3, text_color=C.T1)
        hist_hdr.grid(row=2, column=0, sticky="w", padx=10, pady=(20, 5))

        self.history_container = ctk.CTkFrame(lists, fg_color="transparent")
        self.history_container.grid(row=3, column=0, sticky="ew")
        self.history_container.grid_columnconfigure(0, weight=1)

    def set_mode(self, value):
        if value not in (ONLINE_MODE, LOCAL_MODE):
            raise ValueError(f"Unsupported dashboard mode: {value}")
        self._mode = value
        self._sync_mode_ui()

    def _switch_mode(self, value):
        self.set_mode(value)

    def _sync_mode_ui(self):
        if self._mode == LOCAL_MODE:
            self.mode_title_lbl.configure(text="Convert")
            self.online_panel.grid_remove()
            self.local_panel.grid()
        else:
            self.mode_title_lbl.configure(text="Download")
            self.local_panel.grid_remove()
            self.online_panel.grid()

    def _type_changed(self, value):
        if value == "Audio":
            self.quality_pill.configure(values=_AUDIO_QUALITIES)
            self.quality_pill.set("Best Audio")
            self.format_pill.configure(values=_AUDIO_FORMATS)
            self.format_pill.set("MP3")
        else:
            self.quality_pill.configure(values=_VIDEO_QUALITIES)
            self.quality_pill.set("1080p")
            self.format_pill.configure(values=_VIDEO_FORMATS)
            self.format_pill.set("MP4")

    def _install_drop_support(self):
        if not DND_SUPPORT:
            return
        for widget in (self.drop_zone, self.drop_title_lbl, self.drop_subtitle_lbl):
            try:
                windnd.hook_dropfiles(widget, func=self._handle_drop_files)
            except Exception as exc:
                logger.debug("Drag and drop hook unavailable for %s: %s", widget, exc)

    def _handle_drop_files(self, files):
        decoded = []
        for item in files:
            normalized = self._normalize_dropped_path(item)
            if normalized:
                decoded.append(normalized)
        if decoded:
            self.after(0, lambda path=decoded[0]: self._set_local_file(path))
        else:
            self.after(0, self._flash_drop_zone)

    def _normalize_dropped_path(self, item):
        text = self._decode_drop_item(item).replace("\x00", "").strip()
        if text.startswith("{") and text.endswith("}"):
            text = text[1:-1].strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
        return text

    def _decode_drop_item(self, item):
        if isinstance(item, bytes):
            for encoding in ("utf-8", "mbcs", "utf-16-le", "latin-1"):
                try:
                    return item.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    continue
            return item.decode(errors="ignore")
        return str(item)

    def _select_local_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Media File",
            filetypes=[
                (
                    "Media Files",
                    "*.mp4 *.mkv *.avi *.mov *.3gp *.mp3 *.wav *.flac *.m4a *.webm *.aac *.ogg *.opus",
                ),
                ("All Files", "*.*"),
            ],
        )
        if file_path:
            self._set_local_file(file_path)

    def _set_local_file(self, file_path: str):
        source = Path(file_path).expanduser()
        if not source.exists() or not source.is_file():
            messagebox.showerror("File Error", f"File not found:\n{source}")
            return

        try:
            info = self._dm.converter.probe_source(source)
        except Exception as exc:
            messagebox.showerror("Probe Error", str(exc))
            return

        self._local_source_path = str(source)
        self._local_source_info = info
        self.local_file_name_lbl.configure(text=source.name)
        self.local_file_meta_lbl.configure(text=self._build_source_meta(info))
        self.drop_title_lbl.configure(text="Ready to convert")
        self.drop_subtitle_lbl.configure(text="Change the output format or preset, then start conversion.")

        allowed_formats = self._allowed_formats_for_source(info)
        display_formats = [fmt.upper() for fmt in allowed_formats]
        self.local_format_pill.configure(values=display_formats)
        current = self.local_format_pill.get()
        if current not in display_formats:
            self.local_format_pill.set(display_formats[0])
        self._local_format_changed(self.local_format_pill.get())
        self.local_start_btn.configure(state="normal")

    def _build_source_meta(self, info: dict) -> str:
        parts = [format_size(info.get("size", 0))]
        has_video = bool(info.get("has_video"))
        has_audio = bool(info.get("has_audio"))
        if has_video and has_audio:
            parts.append("Video + Audio")
        elif has_video:
            parts.append("Video")
        elif has_audio:
            parts.append("Audio")
        return " | ".join(parts)

    def _allowed_formats_for_source(self, info: dict) -> list[str]:
        allowed = []
        for fmt in self._dm.converter.list_formats():
            if self._dm.converter.is_video_format(fmt) and info.get("has_video"):
                allowed.append(fmt)
            elif self._dm.converter.is_audio_format(fmt) and info.get("has_audio"):
                allowed.append(fmt)
        return allowed or self._dm.converter.list_formats()

    def _local_format_changed(self, value):
        output_format = value.lower()
        presets = self._dm.converter.list_presets(output_format)
        if not presets:
            self._local_preset_map = {}
            self.local_preset_pill.configure(values=["No presets"])
            self.local_preset_pill.set("No presets")
            self.local_desc_lbl.configure(text="No presets available for this format.")
            self.local_start_btn.configure(state="disabled")
            return

        labels = [preset["label"] for preset in presets]
        self._local_preset_map = {preset["label"]: preset for preset in presets}
        self.local_preset_pill.configure(values=labels)
        current = self.local_preset_pill.get()
        if current not in labels:
            self.local_preset_pill.set(labels[0])
        self._local_preset_changed(self.local_preset_pill.get())
        if self._local_source_path:
            self.local_start_btn.configure(state="normal")

    def _local_preset_changed(self, label):
        preset = self._local_preset_map.get(label)
        if preset:
            self.local_desc_lbl.configure(text=f"{preset['label']}: {preset['description']}")
        else:
            self.local_desc_lbl.configure(text="Choose an output format to see preset details.")

    def _start_download(self):
        url = self.url_input.get()
        if not url:
            self.url_input.flash_error()
            return

        download_type = self.type_pill.get().lower()
        if download_type == "video":
            quality = _VIDEO_QUALITY_MAP.get(self.quality_pill.get(), "best")
        else:
            quality = _AUDIO_QUALITY_MAP.get(self.quality_pill.get(), "best")
        output_format = self.format_pill.get().lower()
        playlist = bool(self.playlist_cb.get())

        self.online_start_btn.configure(text="Queuing...", state="disabled")
        self.url_input.clear()

        threading.Thread(
            target=self._queue_download,
            args=(url, download_type, playlist, quality, output_format),
            daemon=True,
        ).start()

    def _queue_download(self, url, download_type, playlist, quality, output_format):
        try:
            loop = getattr(self._dm, "_loop", None)
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._dm.add_download(
                        url=url,
                        download_type=download_type,
                        is_playlist=playlist,
                        quality=quality,
                        format_type=output_format,
                        title="Video",
                    ),
                    loop,
                )
                future.result(timeout=10)
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("Queue Error", str(exc)))
        finally:
            self.after(0, lambda: self.online_start_btn.configure(text="Download", state="normal"))

    def _start_local_conversion(self):
        if not self._local_source_path:
            self._flash_drop_zone()
            return

        preset = self._local_preset_map.get(self.local_preset_pill.get())
        if not preset:
            messagebox.showerror("Preset Error", "Choose a conversion preset before starting.")
            return

        output_format = self.local_format_pill.get().lower()
        preset_key = preset["key"]

        self.local_start_btn.configure(text="Queuing...", state="disabled")
        threading.Thread(
            target=self._queue_conversion,
            args=(self._local_source_path, output_format, preset_key),
            daemon=True,
        ).start()

    def _queue_conversion(self, source_path: str, output_format: str, preset_key: str):
        try:
            loop = getattr(self._dm, "_loop", None)
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._dm.add_conversion(
                        source_path=source_path,
                        output_format=output_format,
                        preset_key=preset_key,
                        title=Path(source_path).name,
                    ),
                    loop,
                )
                future.result(timeout=10)
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("Conversion Error", str(exc)))
        finally:
            self.after(0, lambda: self.local_start_btn.configure(text="Convert", state="normal" if self._local_source_path else "disabled"))

    def _flash_drop_zone(self):
        self.drop_zone.configure(border_color=C.ERROR)
        self.after(1000, lambda: self.drop_zone.configure(border_color=C.BORDER))

    def _tick(self):
        try:
            self._update_ui()
        except Exception as exc:
            logger.debug("Dashboard tick error: %s", exc)
        self.after(500, self._tick)

    def _update_ui(self):
        active = dict(self._dm.active_tasks)

        self.stat_active.set_value(f"{len(active)}/{self._dm.MAX_CONCURRENT}")
        self.stat_queued.set_value(self._dm.queue.qsize() if hasattr(self._dm.queue, "qsize") else 0)
        self.stat_done.set_value(len(self._dm.completed_tasks))

        current_ids = set(self._cards.keys())
        new_ids = set(active.keys())

        for task_id in list(current_ids - new_ids):
            self._cards[task_id].destroy()
            del self._cards[task_id]

        if active:
            self.no_active_lbl.grid_forget()
            for row_index, (task_id, task) in enumerate(active.items()):
                if task_id not in self._cards:
                    card = DownloadCard(self.active_container, task, on_cancel=self._dm.cancel_task)
                    self._cards[task_id] = card
                else:
                    self._cards[task_id].update(task)
                self._cards[task_id].grid(row=row_index, column=0, sticky="ew", pady=5)
        else:
            self.no_active_lbl.grid(row=0, column=0, pady=20)

        history = list(reversed(self._dm.completed_tasks[-10:]))
        signature = tuple((task.task_id, task.status, task.file_path) for task in history)
        if signature != self._history_signature:
            self._history_signature = signature
            for widget in self.history_container.winfo_children():
                widget.destroy()
            if not history:
                ctk.CTkLabel(self.history_container, text="No history yet.", font=F.BODY_SM, text_color=C.T3).pack(pady=10)
            else:
                for task in history:
                    HistoryRow(self.history_container, task).pack(fill="x", pady=2)

        self._notify_completed_conversions()

    def _notify_completed_conversions(self):
        for task in self._dm.completed_tasks:
            if getattr(task, "task_kind", "download") != "convert":
                continue
            if task.status != "Completed":
                continue
            if task.task_id in self._completed_conversion_notices:
                continue
            self._completed_conversion_notices.add(task.task_id)
            output_name = Path(task.file_path).name if task.file_path else task.title
            self._show_toast("Task Complete", f"{output_name} is ready.")

    def _show_toast(self, title: str, message: str):
        if self._toast_after_id:
            self.after_cancel(self._toast_after_id)
            self._toast_after_id = None
        if self._toast is not None:
            self._toast.destroy()

        self._toast = CompletionToast(self, title=title, message=message)
        self._toast.place(relx=1.0, x=-22, y=22, anchor="ne")
        self._toast_after_id = self.after(4200, self._clear_toast)

    def _clear_toast(self):
        self._toast_after_id = None
        if self._toast is not None:
            self._toast.destroy()
            self._toast = None

    def update_status(self, data):
        return data

