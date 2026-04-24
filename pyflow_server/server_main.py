#!/usr/bin/env python3
"""
PyFlow server-only entrypoint for building pyflow.exe.
This excludes GUI runtime paths and keeps the packaged binary smaller.
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PID_FILE = Path(__file__).parent / ".pyflow_server.pid"


def _init_logging(console=True):
    handlers = [logging.FileHandler("pyflow.log", encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=handlers,
        force=True,
    )


def _parser():
    p = argparse.ArgumentParser(
        prog="pyflow",
        description="PyFlow server-only executable (no GUI)",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--hidden", action="store_true", help="Run server in background")
    mode.add_argument("--stop", action="store_true", help="Stop background server")
    mode.add_argument("--status", action="store_true", help="Print server status")
    p.add_argument("--host", default=DEFAULT_HOST, metavar="HOST")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, metavar="PORT")
    p.add_argument("--path", metavar="DIR", help="Download directory")
    p.add_argument("--no-update", action="store_true", help="Skip yt-dlp auto-update")
    p.add_argument("--_daemon", action="store_true", help=argparse.SUPPRESS)
    return p


def _save_pid(pid):
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _read_pid():
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip()) if PID_FILE.exists() else None
    except ValueError:
        return None


def cmd_stop():
    pid = _read_pid()
    if not pid:
        print("No server PID found.")
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True)
        else:
            os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        print(f"Stopped server (PID {pid})")
    except ProcessLookupError:
        print(f"PID {pid} is not running.")
        PID_FILE.unlink(missing_ok=True)


def cmd_status(host, port):
    import urllib.request

    pid = _read_pid()
    print(f"PID file: {pid or 'none'}")
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2) as r:
            d = json.loads(r.read())
            print(
                f"Online | yt-dlp {d.get('ytdlp_version', '?')} "
                f"| Queue: {d.get('queue_size', 0)} "
                f"| Active: {d.get('active_downloads', 0)}"
            )
    except Exception:
        print("Server not responding")


def run_daemon(args):
    if platform.system() == "Windows":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
        proc = subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--_daemon",
                "--host",
                args.host,
                "--port",
                str(args.port),
            ],
            creationflags=flags,
        )
        _save_pid(proc.pid)
        print(f"Background server started (PID {proc.pid})")
        print("Use: pyflow.exe --stop")
    else:
        pid = os.fork()
        if pid > 0:
            _save_pid(pid)
            print(f"Background server started (PID {pid})")
            print("Use: pyflow --stop")
            sys.exit(0)
        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            sys.exit(0)
        sys.stdin = open(os.devnull)
        sys.stdout = open("pyflow.log", "a", buffering=1)
        sys.stderr = sys.stdout
        run_server(args, show_console=False)


def run_server(args, show_console=True):
    _init_logging(console=show_console)

    from utils import get_download_directory, set_download_directory
    from download_manager import DownloadManager
    from server import create_app

    dl_dir = set_download_directory(args.path) if args.path else get_download_directory()
    dm = DownloadManager(download_dir=dl_dir)

    if args.no_update:
        async def _noop():
            return None
        dm._background_update_ytdlp = _noop

    async def _main():
        import uvicorn

        app = create_app(dm)
        cfg = uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_level="critical",
            access_log=False,
        )
        srv = uvicorn.Server(cfg)
        tasks = [
            asyncio.create_task(dm.process_queue()),
            asyncio.create_task(srv.serve()),
        ]
        try:
            await asyncio.gather(*tasks)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            dm.shutdown()
            PID_FILE.unlink(missing_ok=True)

    if show_console:
        print(f"PyFlow server listening on http://{args.host}:{args.port}")
        print(f"Download dir: {dl_dir}")
        print("Press Ctrl+C to stop.")

    asyncio.run(_main())


def main():
    args = _parser().parse_args()
    if args.stop:
        cmd_stop()
        return
    if args.status:
        cmd_status(args.host, args.port)
        return
    if args.hidden and not args._daemon:
        run_daemon(args)
        return
    run_server(args, show_console=not args._daemon)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nGoodbye")
