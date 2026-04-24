"""
PyFlow GUI — Theme System v4.0 (CustomTkinter Edition)
Modern Premium Interface: Black, Red, White, and Ash.
"""
import platform as _plat

# ══════════════════════════════════════════════════════════════════════
# COLORS (Premium Dark Mode: Red & Black)
# ══════════════════════════════════════════════════════════════════════
class C:
    # Backgrounds
    BG_DEEP     = "#121212"  # Deepest Black
    BG_MAIN     = "#1a1a1a"  # Main Background (Ash/Black)
    BG_SIDEBAR  = "#141414"  # Sidebar Background
    BG_CARD     = "#242424"  # Card / Surface Background
    BG_HOVER    = "#2d2d2d"  # Hover state for cards/buttons
    
    # Accents
    ACCENT      = "#ff4b4b"  # Vibrant Red
    ACCENT_HOVER= "#ff6666"  # Lighter Red for hover
    ACCENT_DIM  = "#3d1414"  # Dim Red for backgrounds
    
    # Status
    SUCCESS     = "#22d65a"
    WARNING     = "#ffb830"
    ERROR       = "#ff4b4b"
    
    # Text
    T1          = "#ffffff"  # Pure White (Primary)
    T2          = "#b0b0b0"  # Light Grey (Secondary)
    T3          = "#666666"  # Ash / Dark Grey (Disabled/Muted)
    
    # Border
    BORDER      = "#333333"
    BORDER_RED  = "#ff4b4b"

Colors = C


# ══════════════════════════════════════════════════════════════════════
# FONTS
# ══════════════════════════════════════════════════════════════════════
def _sf():
    s = _plat.system()
    if s == "Windows": return "Segoe UI"
    if s == "Darwin": return "SF Pro Display"
    return "Inter"

_B = _sf()

class F:
    H1        = (_B, 24, "bold")
    H2        = (_B, 18, "bold")
    H3        = (_B, 14, "bold")
    BODY_LG   = (_B, 13, "normal")
    BODY      = (_B, 12, "normal")
    BODY_SM   = (_B, 11, "normal")
    TINY      = (_B, 10, "normal")
    MONO      = ("Consolas" if _plat.system()=="Windows" else "Courier", 11)

Fonts = F


# ══════════════════════════════════════════════════════════════════════
# DIMENSIONS
# ══════════════════════════════════════════════════════════════════════
class D:
    WIN_W     = 1000
    WIN_H     = 700
    WIN_MIN_W = 900
    WIN_MIN_H = 600
    SIDEBAR_W = 180
    RADIUS    = 12

Dims = D

APP_NAME    = "PyFlow Pro"
APP_VERSION = "1.0.2"
SERVER_PORT = 8000
SERVER_HOST = "127.0.0.1"