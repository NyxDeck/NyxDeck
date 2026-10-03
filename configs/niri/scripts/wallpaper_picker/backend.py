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

# The video behind that frame, kept separately because it outlives it: a theme
# change can drop the frame record (the palette has to come from a picture that
# is actually visible), while what to restore on the next login is unchanged.
LIVE_WALLPAPER_STATE = os.path.expanduser("~/.cache/nyxdeck/live-wallpaper")


def _write_marker(path: str, value: str):
    """Write a one-line state file, or delete it when the value is empty."""
    try:
        if value:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(value)
        elif os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _read_marker(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _remember_live_frame(thumb_path: str):
    """Record the frame DMS is showing, or forget it when a still is applied."""
    _write_marker(LIVE_FRAME_STATE, thumb_path or "")


def _remember_live_wallpaper(video_path: str):
    """Record the video to restore, or forget it when a still is applied."""
    _write_marker(LIVE_WALLPAPER_STATE, video_path or "")


def live_frame() -> str:
    """The still frame DMS was last told to show, or "" when a still is set."""
    return _read_marker(LIVE_FRAME_STATE)


def live_wallpaper() -> str:
    """The live wallpaper to restore at login, or "" when a still is set."""
    return _read_marker(LIVE_WALLPAPER_STATE)


def forget_live_wallpaper():
    """Drop the restore record, for a video that is no longer on disk."""
    _remember_live_wallpaper("")


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
        _remember_live_wallpaper("")
        _set_dms_wallpaper(path)
        return True
    except Exception as e:
        print(f"Error applying static wallpaper: {e}", file=sys.stderr)
        return False


def apply_dynamic_wallpaper(video_path: str, thumb_path: str = None) -> bool:
    """Apply a video wallpaper via mpvpaper, seeding the DMS theme from its thumbnail."""
    try:
        _clear_mpvpaper()
        _remember_live_wallpaper(video_path)

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
