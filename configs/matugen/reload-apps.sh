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

# A live wallpaper keeps drawing over whatever DMS sets next, and the palette
# then comes from a picture nobody can see. The picker's backend records the
# still frame it handed to DMS, so a different path here means DMS' own picker
# or cycler set a still image: drop the live layer. Delete this block once DMS
# handles live wallpapers itself (DMS#1323).
if command -v pgrep >/dev/null 2>&1 && command -v dms >/dev/null 2>&1 \
        && pgrep -x mpvpaper >/dev/null 2>&1; then
    live_frame="$(cat "$HOME/.cache/nyxdeck/live-wallpaper-frame" 2>/dev/null || true)"
    current="$(dms ipc call wallpaper get 2>/dev/null | head -1 || true)"
    if [ -n "$live_frame" ] && [ -n "$current" ] && [ "$current" != "$live_frame" ]; then
        # mpvpaper runs one process per output, and they do not all go on the
        # first signal, so retry briefly rather than assume the kill landed.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            pgrep -x mpvpaper >/dev/null 2>&1 || break
            pkill -x mpvpaper 2>/dev/null || true
            sleep 0.2
        done
        pgrep -x mpvpaper >/dev/null 2>&1 && pkill -9 -x mpvpaper 2>/dev/null || true
        rm -f "$HOME/.cache/nyxdeck/live-wallpaper-frame"
    fi
fi
