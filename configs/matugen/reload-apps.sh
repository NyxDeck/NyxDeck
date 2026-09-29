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
