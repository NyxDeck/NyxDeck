#!/usr/bin/env bash
# matugen post_hook — nudge the programs that do not watch their theme files.
#
# DMS re-renders every matugen target when the wallpaper or the theme changes,
# but a program that is already running keeps the palette it read at startup.
# kitty reloads its configuration on SIGUSR1 and fcitx5 re-reads its theme
# directory only after a config reload.
# Both are best-effort: nothing here should ever fail a theme change.
set -u

if command -v pkill >/dev/null 2>&1; then
    pkill -SIGUSR1 -x kitty 2>/dev/null || true
fi

if command -v fcitx5-remote >/dev/null 2>&1; then
    fcitx5-remote -r >/dev/null 2>&1 || true
fi

# DMS re-renders from its own stored wallpaper, and the palette then comes from a
# picture nobody can see, because what is really behind the video is the still
# frame the picker handed to DMS. Put that frame back in charge and raise the
# live layer again if it died, instead of dropping the video: setting a still in
# the picker clears the record, so an explicit static wallpaper is never
# overridden here. Delete this block once DMS handles live wallpapers itself
# (DMS#1323).
if command -v dms >/dev/null 2>&1; then
    live_frame="$(cat "$HOME/.cache/nyxdeck/live-wallpaper-frame" 2>/dev/null || true)"
    if [ -n "$live_frame" ]; then
        current="$(dms ipc call wallpaper get 2>/dev/null | head -1 || true)"
        if [ -n "$current" ] && [ "$current" != "$live_frame" ]; then
            dms ipc call wallpaper set "$live_frame" >/dev/null 2>&1 || true
        fi
        if ! pgrep -x mpvpaper >/dev/null 2>&1 && [ -x "$HOME/.local/bin/nyxdeck" ]; then
            "$HOME/.local/bin/nyxdeck" wallpaper restore >/dev/null 2>&1 || true
        fi
    fi
fi
