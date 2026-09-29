#!/usr/bin/env bash
# NyxDeck installer.
#
# Deploys the whole DMS desktop layer into ~/.config: the DMS shell, its
# matugen templates, the niri config, and starship. Idempotent: it shows what
# will change first, backs up anything it overwrites, and never touches
# machine/user state (displays, input, runtime symlinks) or DMS's own output.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
BACKUP_ROOT="$CONFIG_HOME/.nyxdeck-backup"
STAMP="$(date +%Y%m%d-%H%M%S)"

# configs/<subdir> is deployed onto ~/.config/<subdir>.
APPS=("DankMaterialShell" "matugen" "niri" "gtk-3.0" "gtk-4.0" "kitty" "qt6ct")
# configs/<file> is deployed onto ~/.config/<file>.
FILES=("starship.toml")
# Machine/user state: create if missing, but never overwrite an existing file.
# (Displays, input quirks, personal additions, the EyeCare runtime symlink.)
PRESERVE=(
    "niri/monitor.kdl"
    "niri/input__custom__.kdl"
    "niri/__custom__.kdl"
    "niri/orbit-items__custom__.toml"
    "niri/effects.kdl"
    # DMS's matugen splices the palette into starship.toml at runtime, so the
    # live file always differs from the repo's initial value. Seed-if-absent.
    "starship.toml"
)

say()  { printf '%s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

is_preserved() {
    local key="$1" p
    for p in "${PRESERVE[@]}"; do [ "$key" = "$p" ] && return 0; done
    return 1
}

# Emit every repo file as "<backup-key>\t<abs source>\t<abs target>".
collect() {
    local app src f rel
    for app in "${APPS[@]}"; do
        src="$REPO_DIR/configs/$app"
        [ -d "$src" ] || continue
        while IFS= read -r -d '' f; do
            rel="${f#"$src"/}"
            printf '%s\t%s\t%s\n' "$app/$rel" "$f" "$CONFIG_HOME/$app/$rel"
        done < <(find "$src" -type d -name __pycache__ -prune -o -type f -print0 | sort -z)
    done
    for f in "${FILES[@]}"; do
        [ -f "$REPO_DIR/configs/$f" ] || continue
        printf '%s\t%s\t%s\n' "$f" "$REPO_DIR/configs/$f" "$CONFIG_HOME/$f"
    done
}

# Would this file be written? Preserved files that already exist are not.
wants_write() {
    local key="$1" dst="$2"
    if is_preserved "$key" && [ -e "$dst" ]; then
        return 1
    fi
    return 0
}

plan_changes() {
    local key f dst; local changed=0
    while IFS=$'\t' read -r key f dst; do
        wants_write "$key" "$dst" || continue
        if [ ! -e "$dst" ]; then
            say "  + $dst"
            changed=1
        elif ! sed "s|/home/user|$HOME|g" "$f" | cmp -s - "$dst"; then
            say "  ~ $dst"
            changed=1
        fi
    done < <(collect)
    [ "$changed" -eq 1 ]
}

do_deploy() {
    say "NyxDeck → $CONFIG_HOME"
    if ! plan_changes; then
        say "已是最新，无改动。"
        return 0
    fi

    local key f dst backup
    while IFS=$'\t' read -r key f dst; do
        wants_write "$key" "$dst" || continue
        mkdir -p "$(dirname "$dst")"
        if [ -e "$dst" ] && ! sed "s|/home/user|$HOME|g" "$f" | cmp -s - "$dst"; then
            backup="$BACKUP_ROOT/$STAMP/$key"
            mkdir -p "$(dirname "$backup")"
            cp -p "$dst" "$backup"
        fi
        # --remove-destination so a managed path that is currently a symlink
        # (e.g. kitty/current-theme.conf -> themes/noctalia.conf) is replaced
        # by the file itself, instead of writing through the link.
        cp --remove-destination -p "$f" "$dst"
        # DMS only substitutes SHELL_DIR/CONFIG_DIR in its own templates; the
        # user's [templates.*] section is appended verbatim and niri configs
        # use /home/user placeholders, so we expand them ourselves.
        sed -i "s|/home/user|$HOME|g" "$dst" 2>/dev/null || true
    done < <(collect)

    # EyeCare runtime symlink (self-healing script also recreates it, but niri
    # includes effects.kdl at load time, before spawn-at-startup runs).
    local normal="$CONFIG_HOME/niri/effects_normal.kdl" link="$CONFIG_HOME/niri/effects.kdl"
    if [ -f "$normal" ] && [ ! -e "$link" ]; then
        ln -s effects_normal.kdl "$link"
    fi

    # matugen writes the starship palette here before the post_hook splices it.
    mkdir -p "$CACHE_HOME/nyxdeck"

    # Scripts need the bit even if copied from a checkout that lost it.
    local s
    while IFS= read -r -d '' s; do
        chmod +x "$s"
    done < <(find "$CONFIG_HOME/niri/scripts" "$CONFIG_HOME/DankMaterialShell" "$CONFIG_HOME/matugen" -name '*.sh' -print0 2>/dev/null)

    say "完成。改动前的旧文件备份在 $BACKUP_ROOT/$STAMP/"
}

do_status() {
    say "NyxDeck 部署状态："
    if plan_changes; then
        say ""
        say "上面是待同步的差异。运行 ./install.sh 应用。"
    else
        say "  全部已同步。"
    fi
}

do_uninstall() {
    say "移除 NyxDeck 部署的文件（机器状态与 DMS 运行时文件保留）："
    local key f dst
    while IFS=$'\t' read -r key f dst; do
        is_preserved "$key" && continue
        if [ -e "$dst" ]; then
            say "  - $dst"
            rm -f "$dst"
        fi
    done < <(collect)
    say "完成。"
}

case "${1:-install}" in
    install)   do_deploy ;;
    status)    do_status ;;
    uninstall) do_uninstall ;;
    *)         die "用法: $0 [install|status|uninstall]" ;;
esac
