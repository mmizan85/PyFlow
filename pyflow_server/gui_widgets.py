"""
PyFlow GUI — CustomTkinter Widget Library v4.0
Reusable components: Inputs, Buttons, Progress, etc.
"""
from tkinter import messagebox

import customtkinter as ctk
from gui_theme import C, F, D

# ═══════════════════════════════════════════════════════════
# URL INPUT (with Paste button)
# ═══════════════════════════════════════════════════════════

class URLInput(ctk.CTkFrame):
    def __init__(self, parent, placeholder="Paste any video URL here...", **kw):
        super().__init__(parent, fg_color=C.BG_CARD, border_width=1, 
                         border_color=C.BORDER, corner_radius=D.RADIUS, **kw)
        
        self.grid_columnconfigure(1, weight=1)
        
        # Link Icon (simple text)
        self.icon = ctk.CTkLabel(self, text="🔗", font=F.H3, text_color=C.T3)
        self.icon.grid(row=0, column=0, padx=(15, 0), pady=10)
        
        # Entry field
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder,
                                  fg_color="transparent", border_width=0,
                                  font=F.BODY_LG, text_color=C.T1,
                                  placeholder_text_color=C.T3)
        self.entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        
        # Paste Button
        self.paste_btn = ctk.CTkButton(self, text="Paste", width=60, height=28,
                                       fg_color=C.ACCENT, hover_color=C.ACCENT_HOVER,
                                       font=F.BODY_SM, text_color=C.T1,
                                       corner_radius=8, command=self._paste)
        self.paste_btn.grid(row=0, column=2, padx=10, pady=5)
        
        # Clear Button
        self.clear_btn = ctk.CTkButton(self, text="✕", width=30, height=28,
                                        fg_color="transparent", hover_color=C.BG_HOVER,
                                        font=F.BODY_SM, text_color=C.T3,
                                        corner_radius=8, command=self.clear)
        self.clear_btn.grid(row=0, column=3, padx=(0, 10), pady=5)

    def _paste(self):
        try:
            txt = self.clipboard_get()
            if txt.strip():
                self.entry.delete(0, "end")
                self.entry.insert(0, txt.strip())
        except Exception:
            pass

    def get(self): return self.entry.get().strip()
    def clear(self): self.entry.delete(0, "end")
    def flash_error(self):
        self.configure(border_color=C.ERROR)
        self.after(1000, lambda: self.configure(border_color=C.BORDER))


# ═══════════════════════════════════════════════════════════
# PILL BUTTON (Dropdown substitute or Toggle)
# ═══════════════════════════════════════════════════════════

class OptionPill(ctk.CTkOptionMenu):
    def __init__(self, parent, values, **kw):
        super().__init__(parent, values=values, 
                         fg_color=C.BG_CARD, 
                         button_color=C.BG_CARD,
                         button_hover_color=C.BG_HOVER,
                         dropdown_fg_color=C.BG_CARD,
                         dropdown_hover_color=C.BG_HOVER,
                         dropdown_text_color=C.T1,
                         text_color=C.T1, 
                         font=F.BODY,
                         corner_radius=8,
                         **kw)


# ═══════════════════════════════════════════════════════════
# STAT CHIP
# ═══════════════════════════════════════════════════════════

class StatChip(ctk.CTkFrame):
    def __init__(self, parent, icon, label, value="0", **kw):
        super().__init__(parent, fg_color=C.BG_CARD, corner_radius=10, 
                         border_width=1, border_color=C.BORDER, **kw)
        
        self.icon_lbl = ctk.CTkLabel(self, text=icon, font=F.H3, text_color=C.ACCENT)
        self.icon_lbl.pack(side="left", padx=(12, 5), pady=8)
        
        self.label_lbl = ctk.CTkLabel(self, text=f"{label}:", font=F.BODY_SM, text_color=C.T2)
        self.label_lbl.pack(side="left", padx=2, pady=8)
        
        self.value_lbl = ctk.CTkLabel(self, text=value, font=F.H3, text_color=C.T1)
        self.value_lbl.pack(side="left", padx=(2, 12), pady=8)

    def set_value(self, v): self.value_lbl.configure(text=str(v))


# ═══════════════════════════════════════════════════════════
# STATUS INDICATOR
# ═══════════════════════════════════════════════════════════

class StatusIndicator(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        
        self.dot = ctk.CTkFrame(self, width=10, height=10, corner_radius=5, 
                                 fg_color=C.WARNING)
        self.dot.pack(side="left", padx=5)
        
        self.text = ctk.CTkLabel(self, text="Connecting...", font=F.TINY, text_color=C.T2)
        self.text.pack(side="left")

    def set_status(self, text, color):
        self.dot.configure(fg_color=color)
        self.text.configure(text=text)
        
class HistoryRow(ctk.CTkFrame):
    def __init__(self, parent, task, **kw):
        super().__init__(parent, fg_color=C.BG_CARD, corner_radius=8, 
                         border_width=0, **kw)
        self._task = task
        self._build()

    def _build(self):
        t = self._task
        ok = (t.status == "Completed")
        
        self.grid_columnconfigure(1, weight=1)
        
        # Icon
        icon_text = "✅" if ok else "❌"
        icon_color = C.SUCCESS if ok else C.ERROR
        ctk.CTkLabel(self, text=icon_text, font=F.H3, text_color=icon_color).grid(row=0, column=0, padx=12, pady=10)
        
        # Title
        ctk.CTkLabel(self, text=t.title[:50], font=F.BODY, text_color=C.T1, anchor="w").grid(row=0, column=1, sticky="w")
        
        # Type Badge
        badge = ctk.CTkFrame(self, fg_color=C.ACCENT_DIM, corner_radius=4)
        badge.grid(row=0, column=2, padx=5)
        ctk.CTkLabel(badge, text=t.download_type.upper(), font=F.TINY, text_color=C.ACCENT, padx=6, pady=2).pack()
        
        # Open Folder
        if ok:
            btn = ctk.CTkButton(self, text="📂", width=30, height=30, 
                                 fg_color="transparent", hover_color=C.BG_HOVER, 
                                 text_color=C.T2, command=self._open_folder)
            btn.grid(row=0, column=3, padx=10)

    def _open_folder(self):
        try:
            import os
            import subprocess
            path = os.path.abspath(self._task.output_path)
            if os.path.exists(path):
                if os.name == 'nt':
                    os.startfile(path)
                elif os.name == 'posix':
                    subprocess.run(['xdg-open', path])
                else:
                    messagebox.showinfo("Unsupported OS", "Opening folder is not supported on this OS.")
            else:
                messagebox.showerror("File Not Found", f"The file does not exist:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while trying to open the folder:\n{e}")