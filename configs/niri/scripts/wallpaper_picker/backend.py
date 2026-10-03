"""
NyxDeck Wallpaper Picker Backend Engine
Executes wallpaper switching for static images and live video wallpapers,
driving DMS's wallpaper IPC so its Material You theme follows along.
"""

import os
import sys
import subprocess
import time


# What DMS is showing for the running video (a still frame, since the palette
# cannot come from a video). The matugen hook reads this to tell a wallpaper we
# set from one DMS' own picker or cycler set.
LIVE_FRAME_STATE = os.path.expanduser("~/.cache/nyxdeck/live-wallpaper-frame")


def _remember_live_frame(thumb_path: str):
    """Record the frame DMS is showing, or forget it when a still is applied."""
    try:
        os.makedirs(os.path.dirname(LIVE_FRAME_STATE), exist_ok=True)
        if thumb_path:
            with open(LIVE_FRAME_STATE, "w", encoding="utf-8") as handle:
                handle.write(thumb_path)
        elif os.path.exists(LIVE_FRAME_STATE):
            os.remove(LIVE_FRAME_STATE)
    except OSError:
        pass


def _clear_mpvpaper():
    """Terminate every mpvpaper instance and wait for it to actually be gone.

    A 4K video with hardware decoding takes longer to tear down than a short
    sleep allows, and a process still holding the layer when the next one starts
    leaves two of them drawing over each other.
    """
    try:
        for _ in range(10):
            res = subprocess.run(["pgrep", "-x", "mpvpaper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if res.returncode != 0:
                return
            subprocess.run(["pkill", "-x", "mpvpaper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            time.sleep(0.2)
        # Still there after two seconds: take it down.
        subprocess.run(["pkill", "-9", "-x", "mpvpaper"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        time.sleep(0.2)
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
        _remember_live_frame("")
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
            _remember_live_frame(thumb_path)
            _set_dms_wallpaper(thumb_path)

        # --auto-pause is deliberately NOT passed. Under niri every window spans
        # the full output height, so two columns already cover the output and
        # mpvpaper's "wallpaper is hidden" check fires almost always, leaving the
        # video frozen on a single frame (--auto-mode FULL does not help either).
        # Export NYXDECK_MPVPAPER_AUTOPAUSE=1 to restore the old behaviour.
        auto_pause = ["--auto-pause"] if os.environ.get("NYXDECK_MPVPAPER_AUTOPAUSE") == "1" else []
        mpv_opts = "config=no load-scripts=no loop-file=inf panscan=1.0 no-audio hwdec=auto"
        cmd = ["mpvpaper", *auto_pause, "-o", mpv_opts, "*", video_path]
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
