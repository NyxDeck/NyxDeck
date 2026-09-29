"""
NyxDeck Wallpaper Picker Backend Engine
Executes wallpaper switching for static images and live video wallpapers,
driving DMS's wallpaper IPC so its Material You theme follows along.
"""

import os
import sys
import subprocess
import time


def _clear_mpvpaper():
    """Cleanly terminate running mpvpaper instances and wait for process exit."""
    try:
        subprocess.run(["pkill", "-x", "mpvpaper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        for _ in range(10):
            res = subprocess.run(["pgrep", "-x", "mpvpaper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if res.returncode != 0:
                break
            time.sleep(0.05)
    except Exception:
        pass


def _set_dms_wallpaper(path: str):
    """Hand an image to DMS so it extracts the palette and re-renders the theme."""
    try:
        subprocess.Popen(
            ["dms", "ipc", "call", "wallpaper", "set", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def apply_static_wallpaper(path: str) -> bool:
    """Apply a static wallpaper, dropping any live video layer first."""
    try:
        _clear_mpvpaper()
        _set_dms_wallpaper(path)
        return True
    except Exception as e:
        print(f"Error applying static wallpaper: {e}", file=sys.stderr)
        return False


def apply_dynamic_wallpaper(video_path: str, thumb_path: str = None) -> bool:
    """Apply a video wallpaper via mpvpaper, seeding the DMS theme from its thumbnail."""
    try:
        _clear_mpvpaper()

        # A video frame cannot be color-extracted directly; feed DMS the
        # thumbnail so the Material You theme still tracks the wallpaper.
        if thumb_path and os.path.isfile(thumb_path):
            _set_dms_wallpaper(thumb_path)

        mpv_opts = "config=no load-scripts=no loop-file=inf panscan=1.0 no-audio hwdec=auto"
        cmd = ["mpvpaper", "--auto-pause", "-o", mpv_opts, "*", video_path]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"Error applying live wallpaper: {e}", file=sys.stderr)
        return False


def apply_wallpaper(item) -> bool:
    """Polymorphic wallpaper application dispatcher."""
    if item.is_video:
        return apply_dynamic_wallpaper(item.path, item.thumb_path)
    else:
        return apply_static_wallpaper(item.path)
