"""
PyFlow download and conversion manager.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from converter import ConversionCancelledError, FileConverter
from utils import find_ffmpeg, find_ytdlp_binary, get_download_directory

logger = logging.getLogger(__name__)

try:
    import yt_dlp

    _YTDLP_VERSION = yt_dlp.version.__version__
    logger.info("yt-dlp library loaded v%s", _YTDLP_VERSION)
except ImportError:
    yt_dlp = None
    _YTDLP_VERSION = "not installed"
    logger.warning("yt-dlp library not found, falling back to binary when available")


@dataclass
class DownloadTask:
    task_id: str
    url: str
    title: str
    download_type: str
    quality: str
    format_type: str
    is_playlist: bool
    status: str = "Queued"
    progress: float = 0.0
    speed: str = "--"
    eta: str = "--"
    file_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    task_kind: str = "download"
    source_path: Optional[str] = None
    source_size: Optional[int] = None
    preset_key: Optional[str] = None
    output_format: Optional[str] = None
    cancel_requested: bool = False


class DownloadManager:
    MAX_CONCURRENT = 3

    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir: Path = download_dir or get_download_directory()
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._ffmpeg_path, ffmpeg_message = find_ffmpeg()
        self._ytdlp_binary, ytdlp_message = find_ytdlp_binary()
        self.converter = FileConverter()

        logger.info(ffmpeg_message)
        logger.info(ytdlp_message)

        self.ytdlp_version: str = _YTDLP_VERSION
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, DownloadTask] = {}
        self.completed_tasks: List[DownloadTask] = []
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        self._shutdown = False
        self._conversion_processes: Dict[str, subprocess.Popen] = {}

        logger.info(
            "DownloadManager ready dir=%s max_concurrent=%s",
            self.download_dir,
            self.MAX_CONCURRENT,
        )

    async def add_download(
        self,
        url: str,
        download_type: str,
        is_playlist: bool,
        quality: str,
        format_type: str,
        title: str,
    ) -> str:
        if not is_playlist:
            url = self._strip_playlist_params(url)

        task_id = str(uuid.uuid4())[:8]
        task = DownloadTask(
            task_id=task_id,
            url=url,
            title=title,
            download_type=download_type,
            quality=quality,
            format_type=format_type,
            is_playlist=is_playlist,
            task_kind="download",
            output_format=format_type,
        )
        self.active_tasks[task_id] = task
        await self.queue.put(task)
        logger.info("Queued download [%s] %s", task_id, title)
        return task_id

    async def add_conversion(
        self,
        source_path: str,
        output_format: str,
        preset_key: str,
        title: Optional[str] = None,
    ) -> str:
        source = Path(source_path).expanduser()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Source file not found: {source}")

        output_format = output_format.lower()
        preset = self.converter.get_preset(output_format, preset_key)
        source_info = self.converter.probe_source(source)

        if self.converter.is_video_format(output_format) and not source_info.get("has_video"):
            raise ValueError("Audio-only files can only be converted to audio formats.")
        if self.converter.is_audio_format(output_format) and not source_info.get("has_audio"):
            raise ValueError("The selected file does not contain an audio stream.")
        if preset.requires_video and not source_info.get("has_video"):
            raise ValueError("The selected preset requires a video source file.")

        task_id = str(uuid.uuid4())[:8]
        task = DownloadTask(
            task_id=task_id,
            url=str(source),
            title=title or source.name,
            download_type="audio" if self.converter.is_audio_format(output_format) else "video",
            quality=preset.label,
            format_type=output_format,
            is_playlist=False,
            task_kind="convert",
            source_path=str(source),
            source_size=source_info.get("size"),
            preset_key=preset_key,
            output_format=output_format,
        )
        self.active_tasks[task_id] = task
        await self.queue.put(task)
        logger.info("Queued conversion [%s] %s", task_id, source.name)
        return task_id

    async def process_queue(self):
        workers = [asyncio.create_task(self._worker(index)) for index in range(self.MAX_CONCURRENT)]
        updater = asyncio.create_task(self._background_update_ytdlp())
        await asyncio.gather(*workers, updater, return_exceptions=True)

    def cancel_task(self, task_id: str) -> bool:
        task = self.active_tasks.get(task_id)
        if not task:
            return False

        task.cancel_requested = True

        if task.task_kind == "convert":
            if task.status == "Queued":
                self.active_tasks.pop(task_id, None)
                task.status = "Cancelled"
                logger.info("Cancelled queued conversion [%s]", task_id)
                return True

            task.status = "Cancelled"
            process = self._conversion_processes.get(task_id)
            if process and process.poll() is None:
                self._terminate_process(process)
            logger.info("Cancellation requested for conversion [%s]", task_id)
            return True

        self.active_tasks.pop(task_id, None)
        task.status = "Cancelled"
        logger.info("Cancelled download [%s]", task_id)
        return True

    def shutdown(self):
        self._shutdown = True
        for process in list(self._conversion_processes.values()):
            if process and process.poll() is None:
                self._terminate_process(process)
        logger.info("DownloadManager shutdown requested")

    async def _worker(self, worker_id: int):
        logger.debug("Worker-%s started", worker_id)
        while not self._shutdown:
            try:
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if task.status == "Cancelled" or task.cancel_requested:
                self.queue.task_done()
                continue

            async with self.semaphore:
                await self._process_task(task)

            self.queue.task_done()

        logger.debug("Worker-%s stopped", worker_id)

    async def _process_task(self, task: DownloadTask):
        try:
            if task.cancel_requested:
                raise ConversionCancelledError("Task cancelled before start")

            if task.task_kind == "convert":
                task.status = "Converting"
                task.speed = "--"
                await self._convert_local_file(task)
            else:
                task.status = "Downloading"
                if yt_dlp is not None:
                    await self._download_via_library(task)
                elif self._ytdlp_binary:
                    await self._download_via_binary(task)
                else:
                    raise RuntimeError(
                        "Neither yt-dlp library nor binary is available. Install yt-dlp with 'pip install yt-dlp'."
                    )

            if task.cancel_requested:
                raise ConversionCancelledError("Task cancelled")

            task.status = "Completed"
            task.progress = 100.0
            logger.info("Completed [%s] %s", task.task_id, task.title)
        except ConversionCancelledError:
            task.status = "Cancelled"
            task.error = None
            if task.task_kind == "convert":
                self._remove_partial_output(task)
            logger.info("Cancelled [%s] %s", task.task_id, task.title)
        except asyncio.CancelledError:
            task.status = "Cancelled"
            task.error = None
            if task.task_kind == "convert":
                self._remove_partial_output(task)
            logger.info("Cancelled [%s] %s", task.task_id, task.title)
        except Exception as exc:
            task.status = "Failed"
            task.error = str(exc)
            if task.task_kind == "convert":
                self._remove_partial_output(task)
            logger.error("Failed [%s] %s: %s", task.task_id, task.title, exc, exc_info=True)
        finally:
            self.completed_tasks.append(task)
            self.active_tasks.pop(task.task_id, None)
            self._conversion_processes.pop(task.task_id, None)

    async def _convert_local_file(self, task: DownloadTask):
        loop = asyncio.get_event_loop()

        def _run_conversion() -> Path:
            if not task.source_path:
                raise RuntimeError("Missing source path for conversion task.")

            def _on_process(process: subprocess.Popen, output_path: Path):
                task.file_path = str(output_path)
                self._conversion_processes[task.task_id] = process

            def _on_progress(progress: float, speed: str):
                task.progress = progress
                task.speed = speed or "--"

            return self.converter.convert(
                source_path=task.source_path,
                output_format=task.output_format or task.format_type,
                preset_key=task.preset_key or "",
                output_dir=self.download_dir,
                progress_callback=_on_progress,
                process_callback=_on_process,
                cancel_check=lambda: task.cancel_requested,
            )

        output_path = await loop.run_in_executor(None, _run_conversion)
        task.file_path = str(output_path)
        task.progress = 100.0

    async def _download_via_library(self, task: DownloadTask):
        opts = self._build_ydl_options(task)

        def _progress_hook(data: dict):
            if data["status"] == "downloading":
                if "downloaded_bytes" in data and "total_bytes" in data and data["total_bytes"]:
                    task.progress = data["downloaded_bytes"] / data["total_bytes"] * 100
                elif "_percent_str" in data:
                    try:
                        task.progress = float(data["_percent_str"].strip().rstrip("%"))
                    except ValueError:
                        pass
                task.speed = data.get("_speed_str", "--")
                task.eta = data.get("_eta_str", "--")
            elif data["status"] == "finished":
                task.status = "Processing"
                task.progress = 100.0
                task.file_path = data.get("filename")

        opts["progress_hooks"] = [_progress_hook]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ydl, task.url, opts)

    def _run_ydl(self, url: str, opts: dict):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    async def _download_via_binary(self, task: DownloadTask):
        logger.info("Using yt-dlp binary for [%s]", task.task_id)
        cmd = self._build_binary_command(task)
        loop = asyncio.get_event_loop()

        def _run_binary():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.download_dir),
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500] or "yt-dlp binary failed")

        await loop.run_in_executor(None, _run_binary)
        task.progress = 100.0

    def _build_binary_command(self, task: DownloadTask) -> list[str]:
        cmd = [self._ytdlp_binary]

        if task.download_type == "audio":
            cmd += ["-x", "--audio-format", task.format_type, "--audio-quality", task.quality]
        else:
            if task.quality == "F-video":
                cmd += [
                    "-f",
                    "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/bestvideo[height<=420]+bestaudio/bestvideo+bestaudio/best",
                ]
                cmd += [
                    "--postprocessor-args",
                    "ffmpeg = ", "-vf",
                    "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2:black",
                    "-r",
                    "15",
                    "-c:v",
                    "libx264",
                    "-profile:v",
                    "baseline",
                    "-level",
                    "3.0",
                    "-preset",
                    "veryfast",
                    "-b:v",
                    "220k",
                    "-maxrate",
                    "240k",
                    "-bufsize",
                    "480k",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-ac",
                    "1",
                    "-ar",
                    "22050",
                    "-b:a",
                    "48k",
                    "-movflags",
                    "+faststart",
                ]
                cmd += ["--merge-output-format", "mp4"]
            else:
                height = task.quality.replace("p", "")
                cmd += ["-f", f"bestvideo[height<={height}]+bestaudio/best"]
                cmd += ["--merge-output-format", task.format_type]

        if self._ffmpeg_path:
            cmd += ["--ffmpeg-location", str(Path(self._ffmpeg_path).parent)]

        cmd += ["--add-metadata", "-o", "%(title)s.%(ext)s", task.url]
        return cmd

    def _build_ydl_options(self, task: DownloadTask) -> dict:
        out_template = str(self.download_dir / "%(title)s.%(ext)s")

        opts: dict = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "extract_flat": False,
            "writethumbnail": False,
            "logger": None,
        }

        if self._ffmpeg_path:
            opts["ffmpeg_location"] = str(Path(self._ffmpeg_path).parent)

        if task.download_type == "audio":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": task.format_type,
                    "preferredquality": task.quality,
                },
                {"key": "FFmpegMetadata"},
            ]
        else:
            if task.quality == "best":
                fmt = "bestvideo+bestaudio/best"
            elif task.quality == "F-video":
                fmt = "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/bestvideo[height<=360]+bestaudio/bestvideo[height<=420]+bestaudio/bestvideo+bestaudio/best"
                opts["postprocessor_args"] = [
                     "-vf",
                "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2:black",
                "-r",
                "15",
                "-c:v",
                "libx264",
                "-profile:v",
                "baseline",
                "-level",
                "3.0",
                "-preset",
                "veryfast",
                "-b:v",
                "220k",
                "-maxrate",
                "240k",
                "-bufsize",
                "480k",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-b:a",
                "48k",
                "-movflags",
                "+faststart",
                ]
                opts["merge_output_format"] = "mp4"
            else:
                height = task.quality.replace("p", "")
                fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
            opts["format"] = fmt
            opts["merge_output_format"] = task.format_type

        opts["noplaylist"] = not task.is_playlist
        return opts

    async def _background_update_ytdlp(self):
        await asyncio.sleep(5)
        logger.info("Background yt-dlp update started")

        loop = asyncio.get_event_loop()

        def _update_library():
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "yt-dlp",
                        "--quiet",
                        "--disable-pip-version-check",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    import importlib
                    import yt_dlp as _ydl

                    importlib.reload(_ydl.version)
                    self.ytdlp_version = _ydl.version.__version__
                    logger.info("yt-dlp library updated to v%s", self.ytdlp_version)
                else:
                    logger.warning("yt-dlp library update failed: %s", result.stderr[:200])
            except Exception as exc:
                logger.warning("yt-dlp library update error: %s", exc)

        await loop.run_in_executor(None, _update_library)

        if self._ytdlp_binary:
            def _update_binary():
                try:
                    result = subprocess.run(
                        [self._ytdlp_binary, "-U"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    logger.info("yt-dlp binary update: %s", result.stdout.strip()[:100])
                except Exception as exc:
                    logger.warning("yt-dlp binary update error: %s", exc)

            await loop.run_in_executor(None, _update_binary)

    def _remove_partial_output(self, task: DownloadTask):
        if not task.file_path:
            return
        try:
            partial = Path(task.file_path)
            if partial.exists() and partial.is_file():
                partial.unlink()
        except Exception as exc:
            logger.debug("Could not remove partial output for %s: %s", task.task_id, exc)

    @staticmethod
    def _terminate_process(process: subprocess.Popen):
        try:
            process.terminate()
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        except Exception:
            pass

    @staticmethod
    def _strip_playlist_params(url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params.pop("list", None)
        params.pop("index", None)
        clean_query = urlencode(params, doseq=True)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                clean_query,
                parsed.fragment,
            )
        )
