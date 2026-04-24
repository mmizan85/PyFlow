"""
PyFlow GUI application window.
"""

import asyncio
import json
import logging
import threading
import urllib.request
from tkinter import messagebox
import os
import customtkinter as ctk
from PIL import Image, ImageDraw
from pathlib import Path

try:
    import pystray
    from pystray import MenuItem as item

    TRA_SUPPORT = True
except ImportError:
    TRA_SUPPORT = False

from gui_dashboard import Dashboard, LOCAL_MODE, ONLINE_MODE
from gui_settings import SettingsPanel
from gui_theme import APP_NAME, APP_VERSION, C, D, F, SERVER_HOST, SERVER_PORT

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("Dark")


class AppWindow(ctk.CTk):
    def __init__(self, download_manager):
        super().__init__()
        self._dm = download_manager
        self._tray_icon = None
        self.current_view = None
        
        self.title(APP_NAME)
        icon_path = Path(__file__).parent / "app_icon.ico" 
        if icon_path.exists():
            if os.name == 'nt':  
                self.iconbitmap(str(icon_path))
            else:  
                icon_image = ctk.CTkImage(light_image=Image.open(icon_path), size=(32, 32))
                self.iconphoto(False, icon_image)

        self.title(APP_NAME)
        self.geometry(f"{D.WIN_W}x{D.WIN_H}")
        self.minsize(D.WIN_MIN_W, D.WIN_MIN_H)
        self.configure(fg_color=C.BG_DEEP)

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x_pos = (screen_width - D.WIN_W) // 2
        y_pos = (screen_height - D.WIN_H) // 2
        self.geometry(f"+{x_pos}+{y_pos}")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self,
            width=D.SIDEBAR_W,
            corner_radius=0,
            fg_color=C.BG_SIDEBAR,
            border_width=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        self.logo_lbl = ctk.CTkLabel(self.sidebar, text="PyFlow", font=F.H1, text_color=C.ACCENT)
        self.logo_lbl.grid(row=0, column=0, padx=20, pady=(20, 20))

        self.home_btn = self._sidebar_btn("Home", self._show_home, 1)
        self.downloads_btn = self._sidebar_btn("Downloads", self._show_downloads, 2)
        self.convert_btn = self._sidebar_btn("Convert", self._show_convert, 3)
        self.settings_btn = self._sidebar_btn("Settings", self._show_settings, 4)

        self.v_lbl = ctk.CTkLabel(self.sidebar, text=f"v{APP_VERSION}", font=F.TINY, text_color=C.T3)
        self.v_lbl.grid(row=6, column=0, padx=20, pady=10)

        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=C.BG_MAIN, border_width=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.dashboard = Dashboard(self.main_frame, self._dm)
        self.settings = SettingsPanel(self.main_frame, self._dm)

        self._show_home()

        if TRA_SUPPORT:
            self._setup_tray()

        self._loop = asyncio.new_event_loop()
        self._dm._loop = self._loop
        threading.Thread(target=self._run_loop, daemon=True).start()

        self.after(1000, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Unmap>", self._on_unmap)

    def _sidebar_btn(self, text, command, row):
        btn = ctk.CTkButton(
            self.sidebar,
            text=text,
            font=F.H3,
            fg_color="transparent",
            text_color=C.T2,
            hover_color=C.BG_HOVER,
            corner_radius=8,
            anchor="w",
            command=command,
            height=45,
        )
        btn.grid(row=row, column=0, padx=10, pady=5, sticky="ew")
        return btn

    def _show_view(self, view, active_btn):
        self._set_active_btn(active_btn)
        if self.current_view:
            self.current_view.grid_forget()
        view.grid(row=0, column=0, sticky="nsew")
        self.current_view = view

    def _show_home(self):
        self.dashboard.set_mode(ONLINE_MODE)
        self._show_view(self.dashboard, self.home_btn)

    def _show_downloads(self):
        self.dashboard.set_mode(ONLINE_MODE)
        self._show_view(self.dashboard, self.downloads_btn)

    def _show_convert(self):
        self.dashboard.set_mode(LOCAL_MODE)
        self._show_view(self.dashboard, self.convert_btn)

    def _show_settings(self):
        self._show_view(self.settings, self.settings_btn)

    def _set_active_btn(self, active_btn):
        for btn in (self.home_btn, self.downloads_btn, self.convert_btn, self.settings_btn):
            btn.configure(fg_color="transparent", text_color=C.T2)
        active_btn.configure(fg_color=C.ACCENT_DIM, text_color=C.ACCENT)

    def _setup_tray(self):
        image = Image.new("RGB", (64, 64), color=C.ACCENT)
        drawer = ImageDraw.Draw(image)
        drawer.rectangle([16, 16, 48, 48], fill="white")

        menu = (item("Show App", self._show_window), item("Exit", self._close))
        self._tray_icon = pystray.Icon("PyFlow", image, "PyFlow Downloader", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_unmap(self, _event):
        if self.state() == "iconic":
            return

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)

        async def _main():
            try:
                from server import create_app
                import uvicorn

                app = create_app(self._dm)
                config = uvicorn.Config(
                    app,
                    host=SERVER_HOST,
                    port=SERVER_PORT,
                    log_level="critical",
                    access_log=False,
                )
                server = uvicorn.Server(config)
                await asyncio.gather(self._dm.process_queue(), server.serve())
            except Exception as exc:
                logger.error("Async loop error: %s", exc)

        try:
            self._loop.run_until_complete(_main())
        except Exception:
            pass

    def _poll(self):
        try:
            with urllib.request.urlopen(f"http://{SERVER_HOST}:{SERVER_PORT}/health", timeout=1) as response:
                data = json.loads(response.read())
                self.dashboard.update_status(data)
        except Exception:
            pass
        self.after(3000, self._poll)

    def _close(self):
        if self._dm.active_tasks:
            if not messagebox.askyesno("Quit PyFlow", "Tasks are in progress. Exit anyway?"):
                return
        self._dm.shutdown()
        if self._tray_icon:
            self._tray_icon.stop()
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        self.destroy()

    def run(self):
        self.mainloop()

