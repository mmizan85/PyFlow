"""
PyFlow GUI — Settings Panel v4.0 (CustomTkinter Edition)
Full-screen settings view: Directory, Tools, Queue, and About.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading, subprocess, os, platform, logging
from pathlib import Path

from gui_theme import C, F, D, APP_VERSION
from gui_widgets import OptionPill
from utils import (load_config, save_config, find_ffmpeg, find_ytdlp_binary,
                   check_dependencies, get_download_directory, set_download_directory)

logger = logging.getLogger(__name__)

class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, download_manager, **kw):
        super().__init__(parent, fg_color=C.BG_MAIN, corner_radius=0, **kw)
        self._dm = download_manager
        self._cfg = load_config()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Scrollable container
        sf = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        sf.grid(row=0, column=0, sticky="nsew", padx=30, pady=30)
        sf.grid_columnconfigure(0, weight=1)
        
        # ── SECTION: General ──────────────────────────────────
        self._section_hdr(sf, "📁  General Settings", 0)
        
        # Download Directory Row
        dir_f = ctk.CTkFrame(sf, fg_color=C.BG_CARD, corner_radius=8, 
                             border_width=1, border_color=C.BORDER)
        dir_f.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        dir_f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(dir_f, text="Download Directory", font=F.BODY, text_color=C.T2, 
                      width=180, anchor="w").grid(row=0, column=0, padx=15, pady=15)
        
        self.dir_var = ctk.StringVar(value=str(get_download_directory()))
        self.dir_entry = ctk.CTkEntry(dir_f, textvariable=self.dir_var, 
                                       font=F.MONO, fg_color=C.BG_HOVER, 
                                       border_width=0, state="readonly", 
                                       text_color=C.T1)
        self.dir_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        
        ctk.CTkButton(dir_f, text="Browse", width=80, height=32, 
                       fg_color=C.ACCENT, hover_color=C.ACCENT_HOVER, 
                       command=self._browse_dir).grid(row=0, column=2, padx=15)

        # ── SECTION: Performance ──────────────────────────────
        self._section_hdr(sf, "🚀  Performance & Queue", 2)
        
        perf_f = ctk.CTkFrame(sf, fg_color=C.BG_CARD, corner_radius=8, 
                              border_width=1, border_color=C.BORDER)
        perf_f.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        perf_f.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(perf_f, text="Max downloads (1-5)", font=F.BODY, text_color=C.T2, 
                      width=180, anchor="w").grid(row=0, column=0, padx=15, pady=20)
        
        self.conc_slider = ctk.CTkSlider(perf_f, from_=1, to=5, number_of_steps=4, 
                                         button_color=C.ACCENT, 
                                         button_hover_color=C.ACCENT_HOVER,
                                         progress_color=C.ACCENT,
                                         command=self._save_conc)
        self.conc_slider.set(self._cfg.get("max_concurrent", 3))
        self.conc_slider.grid(row=0, column=1, sticky="ew", padx=(0, 20))

        # ── SECTION: Tools ────────────────────────────────────
        self._section_hdr(sf, "🛠️  Tools & Dependencies", 4)
        
        tools_f = ctk.CTkFrame(sf, fg_color=C.BG_CARD, corner_radius=8, 
                               border_width=1, border_color=C.BORDER)
        tools_f.grid(row=5, column=0, sticky="ew", pady=(0, 15))
        
        self.yt_lbl = self._tool_row(tools_f, "yt-dlp Library", 0)
        self.ff_lbl = self._tool_row(tools_f, "FFmpeg", 1)

        # ── SECTION: About ────────────────────────────────────
        self._section_hdr(sf, "ℹ️  About PyFlow", 6)
        
        about_f = ctk.CTkFrame(sf, fg_color=C.BG_CARD, corner_radius=8, 
                               border_width=1, border_color=C.BORDER)
        about_f.grid(row=7, column=0, sticky="ew", pady=(0, 30))
        
        ctk.CTkLabel(about_f, text=f"PyFlow Pro v{APP_VERSION}", font=F.H3, text_color=C.T1).pack(side="left", padx=20, pady=20)
        ctk.CTkLabel(about_f, text="Universal Downloader", font=F.BODY_SM, text_color=C.T3).pack(side="left")
        
        ctk.CTkButton(about_f, text="Open Logs", width=100, 
                       fg_color=C.BG_HOVER, hover_color=C.BORDER, 
                       text_color=C.T2, command=self._open_log).pack(side="right", padx=20)

        # Check tools in bg
        threading.Thread(target=self._check_tools, daemon=True).start()

    def _section_hdr(self, parent, text, row):
        lbl = ctk.CTkLabel(parent, text=text, font=F.H3, text_color=C.ACCENT)
        lbl.grid(row=row, column=0, sticky="w", padx=5, pady=(20, 10))

    def _tool_row(self, parent, label, row):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(f, text=label, font=F.BODY, text_color=C.T2, width=150, anchor="w").pack(side="left")
        lbl = ctk.CTkLabel(f, text="Checking...", font=F.MONO, text_color=C.T2)
        lbl.pack(side="left")
        return lbl

    def _browse_dir(self):
        p = filedialog.askdirectory(title="Select Download Directory")
        if p:
            set_download_directory(p)
            if self._dm: self._dm.download_dir = Path(p)
            self.dir_var.set(p)

    def _save_conc(self, v):
        cfg = load_config(); cfg["max_concurrent"] = int(v); save_config(cfg)
        if self._dm: self._dm.MAX_CONCURRENT = int(v)

    def _open_log(self):
        p = Path("pyflow.log").absolute()
        try:
            s = platform.system()
            if s == "Windows": os.startfile(str(p))
            elif s == "Darwin": subprocess.Popen(["open", str(p)])
            else: subprocess.Popen(["xdg-open", str(p)])
        except: pass

    def _check_tools(self):
        deps = check_dependencies()
        def _upd():
            lib = deps.get("yt_dlp_library")
            self.yt_lbl.configure(text=f"v{lib} ✅" if lib else "Not found ❌", 
                                  text_color=C.SUCCESS if lib else C.ERROR)
            ff = deps.get("ffmpeg")
            self.ff_lbl.configure(text=f"{ff} ✅" if ff else "Not found ❌", 
                                  text_color=C.SUCCESS if ff else C.ERROR)
        self.after(0, _upd)