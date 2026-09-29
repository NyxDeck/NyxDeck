#!/usr/bin/env bash
# Brightness keys: laptop backlight via DMS, external DDC via ddcutil.
#
# DMS drives the internal panel through logind and shows its own OSD; it does
# not scan I2C/DDC by default, and internal panels do not speak DDC/CI anyway.
# External monitors still go through ddcutil here, so the two paths never
# stack on the same panel.

set -uo pipefail

dir="${1:-}"
case "$dir" in
    up|down) ;;
    *)
        printf 'usage: niri-brightness.sh up|down\n' >&2
        exit 2
        ;;
esac

if command -v dms >/dev/null 2>&1; then
    if [ "$dir" = up ]; then
        dms ipc call brightness increment 5 "" >/dev/null 2>&1 || true
    else
        dms ipc call brightness decrement 5 "" >/dev/null 2>&1 || true
    fi
fi

connector=""
if command -v niri >/dev/null 2>&1; then
    connector="$(niri msg focused-output 2>/dev/null | sed -n '1s/.*(\([^)]*\))$/\1/p')"
fi

case "$connector" in
    eDP-*|LVDS-*|DSI-*)
        exit 0
        ;;
esac

backlight_dir="${NYXDECK_BACKLIGHT_DIR:-/sys/class/backlight}"
has_backlight=false
if [ -d "$backlight_dir" ]; then
    for dev in "$backlight_dir"/*; do
        if [ -e "$dev" ]; then
            has_backlight=true
            break
        fi
    done
fi

# Unknown connector on a machine that already has a sysfs backlight: treat
# as internal so NVIDIA laptops do not hit an I2C timeout on every keypress.
if [ -z "$connector" ] && [ "$has_backlight" = true ]; then
    exit 0
fi

if ! command -v ddcutil >/dev/null 2>&1; then
    exit 0
fi

if [ "$dir" = up ]; then
    ddcutil setvcp 10 + 10 >/dev/null 2>&1 || true
else
    ddcutil setvcp 10 - 10 >/dev/null 2>&1 || true
fi
