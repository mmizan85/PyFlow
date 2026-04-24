#!/usr/bin/env python3
"""
PyFlow - Universal Video & Audio  Downloader v1.1


Usage
-----
  pyflow              Launch GUI (default, requires tkinter)
  pyflow --cli        Headless terminal server with Rich UI
  pyflow --hidden     Background daemon (no window, no terminal)
  pyflow --stop       Stop background daemon
  pyflow --status     Print server status
  pyflow --path DIR   Set download directory
  pyflow --port N     Server port (default 8000)
  pyflow --host H     Server host (default 127.0.0.1)
  pyflow --check      Dependency check and exit
  pyflow -v           Print version
"""
import sys, os, asyncio, argparse, json, logging, platform, signal, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# -- Version -------------------------------------------------------------------
VERSION      = "1.4.24"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PID_FILE     = Path(__file__).parent / ".pyflow.pid"
HELP_EPILOG  = """\
Usage:
  pyflow              Launch GUI (default, requires tkinter)
  pyflow --cli        Headless terminal server with Rich UI
  pyflow --hidden     Background daemon (no window, no terminal)
  pyflow --stop       Stop background daemon
  pyflow --status     Print server status
  pyflow --path DIR   Set download directory
  pyflow --port N     Server port (default 8000)
  pyflow --host H     Server host (default 127.0.0.1)
  pyflow --check      Dependency check and exit
  pyflow -v           Print version
"""


# -- Logging -------------------------------------------------------------------
def _init_logging(console=False):
    handlers = [logging.FileHandler("pyflow.log", encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=handlers, force=True)


# -- Argument Parser -----------------------------------------------------------
def _parser():
    p = argparse.ArgumentParser(prog="pyflow",
        description="PyFlow - Universal Video Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_EPILOG)
    
    # Positional URL support
    p.add_argument("url", nargs="?", help="Video URL to download (triggers interactive CLI)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--gui",    action="store_true", help="Launch Modern GUI (default)")
    mode.add_argument("--cli",    action="store_true", help="Headless terminal server")
    mode.add_argument("--i",      action="store_true", help="Interactive TV-style CLI")
    mode.add_argument("--config", action="store_true", help="Interactive settings manager")
    mode.add_argument("--hidden", action="store_true", help="Background daemon")
    mode.add_argument("--stop",   action="store_true", help="Stop background daemon")
    mode.add_argument("--status", action="store_true", help="Server status check")
    p.add_argument("--path",      metavar="DIR", help="Download directory")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, metavar="PORT")
    p.add_argument("--host",      default=DEFAULT_HOST, metavar="HOST")
    p.add_argument("--check",     action="store_true", help="Check dependencies")
    p.add_argument("--no-update", action="store_true", help="Skip yt-dlp auto-update")
    p.add_argument("-v", "--version", action="version", version=f"PyFlow {VERSION}")
    p.add_argument("--_daemon",   action="store_true", help=argparse.SUPPRESS)
    return p


# -- Utility: download directory -----------------------------------------------
def _setup_dir(args):
    from utils import get_download_directory, set_download_directory
    if args.path:
        return set_download_directory(args.path)
    return get_download_directory()


# ----------------------------------------------------------------------
# GUI MODE
# ----------------------------------------------------------------------

def run_gui(args):
    try:
        import tkinter as tk
    except ImportError:
        print("âŒ  tkinter is not available.\n"
              "   Linux:   sudo apt install python3-tk\n"
              "   Windows/macOS: reinstall Python with tk support")
        sys.exit(1)

    _init_logging(console=False)
    from download_manager import DownloadManager
    from utils import get_download_directory

    # GUI startup is independent from terminal-only flags.
    dl_dir = get_download_directory()
    dm = DownloadManager(download_dir=dl_dir)

    from gui_app import AppWindow
    win = AppWindow(dm)
    win.run()


# ----------------------------------------------------------------------
# CLI MODE  (headless, with optional Rich terminal UI)
# ----------------------------------------------------------------------

def run_cli(args, show_ui=True):
    _init_logging(console=not show_ui)
    from utils import get_download_directory
    from download_manager import DownloadManager

    dl_dir = _setup_dir(args)
    dm = DownloadManager(download_dir=dl_dir)

    if args.no_update:
        async def _noop(): pass
        dm._background_update_ytdlp = _noop

    async def _main():
        from server import create_app
        import uvicorn

        app = create_app(dm)
        config = uvicorn.Config(app, host=args.host, port=args.port,
                                log_level="critical", access_log=False)
        srv = uvicorn.Server(config)

        if show_ui:
            print(f"\n  PyFlow {VERSION} - CLI Server")
            print(f"  âš¡  http://{args.host}:{args.port}")
            print(f"  ðŸ“  {dl_dir}")
            print(f"  Press Ctrl+C to stop\n")

        tasks = [
            asyncio.create_task(dm.process_queue()),
            asyncio.create_task(srv.serve()),
        ]

        if show_ui:
            try:
                from ui import UIManager
                tasks.append(asyncio.create_task(UIManager(dm).run()))
            except Exception:
                pass   # Rich UI optional

        try:
            await asyncio.gather(*tasks)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            dm.shutdown()
            PID_FILE.unlink(missing_ok=True)

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        if show_ui:
            from rich.console import Console
            Console().print("\n[#ff4b4b]🛑 Operation cancelled. Exiting PyFlow...[/]")


# ----------------------------------------------------------------------
# DAEMON MODE
# ----------------------------------------------------------------------

def _save_pid(pid): PID_FILE.write_text(str(pid))

def _read_pid():
    try:
        return int(PID_FILE.read_text().strip()) if PID_FILE.exists() else None
    except ValueError:
        return None

def cmd_stop():
    pid = _read_pid()
    if not pid:
        print("â„¹ï¸   No daemon PID file found.")
        return
    try:
        if platform.system() == "Windows":
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=True)
        else:
            os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        print(f"âœ…  Stopped daemon (PID {pid})")
    except ProcessLookupError:
        print(f"âš ï¸   PID {pid} not running.")
        PID_FILE.unlink(missing_ok=True)

def cmd_status():
    import urllib.request
    pid = _read_pid()
    print(f"PID file: {pid or 'none'}")
    try:
        with urllib.request.urlopen(
            f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health", timeout=2
        ) as r:
            d = json.loads(r.read())
            print(f"âœ…  Server online - yt-dlp {d.get('ytdlp_version','?')}  "
                  f"| Queue: {d.get('queue_size',0)}  "
                  f"| Active: {d.get('active_downloads',0)}")
    except Exception:
        print("âŒ  Server not responding")

def run_daemon(args):
    if platform.system() == "Windows":
        import subprocess
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            [sys.executable, __file__, "--cli", "--_daemon",
             "--host", args.host, "--port", str(args.port)],
            creationflags=CREATE_NO_WINDOW)
        _save_pid(proc.pid)
        print(f"PyFlow background server started (PID {proc.pid})")
        print(f"   Use:  pyflow --stop  to stop.")
    else:
        pid = os.fork()
        if pid > 0:
            _save_pid(pid)
            print(f"PyFlow background server started (PID {pid})")
            print(f"   Use:  pyflow --stop  to stop.")
            sys.exit(0)
        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            sys.exit(0)
        sys.stdin  = open(os.devnull)
        sys.stdout = open("pyflow.log", "a", buffering=1)
        sys.stderr = sys.stdout
        run_cli(args, show_ui=False)


# -- Interactive CLI Mode ------------------------------------------------------

def run_interactive(args):
    _init_logging(console=False)
    from download_manager import DownloadManager
    from cli_interactive import InteractiveCLI
    
    dl_dir = _setup_dir(args)
    dm = DownloadManager(download_dir=dl_dir)
    
    cli = InteractiveCLI(dm)
    
    if args.config:
        cli.manage_settings()
        return

    async def _start():
        # Start the background workers
        worker_task = asyncio.create_task(dm.process_queue())
        
        # Run the interactive CLI
        await cli.start(initial_url=args.url)
        
        # We need to wait for downloads to finish if any are active
        while any(t.status in ["Queued", "Downloading", "Processing"] for t in dm.active_tasks.values()):
            await asyncio.sleep(1)
            
        dm.shutdown()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(_start())
    except KeyboardInterrupt:
        from rich.console import Console
        Console().print("\n[#ff4b4b]🛑 Operation cancelled. Exiting PyFlow...[/]")


# ----------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------

def main():
    parser = _parser()
    args   = parser.parse_args()

    # -- One-shot commands ------------------------------------------
    if args.check:
        from utils import print_dependency_status
        print_dependency_status()
        sys.exit(0)

    if args.stop:
        cmd_stop()
        sys.exit(0)

    if args.status:
        cmd_status()
        sys.exit(0)

    # -- Interactive Mode (Explicit --i, --config, or Positional URL) ---
    if args.i or args.config or args.url:
        run_interactive(args)
        return

    # -- Daemon (hidden) --------------------------------------------
    if args.hidden and not args._daemon:
        run_daemon(args)
        return

    # -- CLI mode (explicit or daemon subprocess) -------------------
    if args.cli or args._daemon:
        run_cli(args, show_ui=not args._daemon)
        return

    # -- GUI (default) ----------------------------------------------
    try:
        import tkinter
        run_gui(args)
    except ImportError:
        print("âš ï¸   tkinter not found - falling back to CLI mode")
        run_cli(args, show_ui=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        from rich.console import Console
        Console().print("\n[#ff4b4b]🛑 Operation cancelled. Exiting PyFlow...[/]")
        sys.exit(0)




