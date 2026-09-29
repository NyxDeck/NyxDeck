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
APPS=("DankMaterialShell" "matugen" "niri" "gtk-3.0" "gtk-4.0" "kitty" "qt6ct" "fastfetch" "fish" "nyxdeck")
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
    # The user's own shell additions live here; the rest of config.fish is ours
    # and does get refreshed.
    "fish/conf.d/__custom__.fish"
    # fisher's state: which plugins are wanted, and fish's universal variables.
    "fish/fish_plugins"
    "fish/fish_variables"
)

say()  { printf '%s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# Bilingual output. NYXDECK_LANG overrides the locale; otherwise Chinese when
# the locale is Chinese, English otherwise.
case "${NYXDECK_LANG:-${LC_ALL:-${LANG:-}}}" in
    zh*) LANG_CODE=zh ;;
    *)   LANG_CODE=en ;;
esac
msg() { # msg "<中文>" "<English>"
    if [ "$LANG_CODE" = zh ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi
}

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

# starship.toml is two files in one: the layout is NyxDeck's and the palette
# block between the markers belongs to DMS's matugen, which rewrites it on every
# theme change. Deploying therefore merges — repo layout, live palette — instead
# of treating the whole file as seed-if-absent, so a machine that still carries
# a Noctalia-era file gets the layout corrected while keeping its colours.
starship_wanted() {
    local src="$REPO_DIR/configs/starship.toml" dst="$CONFIG_HOME/starship.toml"
    local layout palette
    layout="$(awk '/PALETTE >>>/{skip=1} /PALETTE <<</{skip=0; next} !skip' "$src")"
    if [ -f "$dst" ]; then
        # Keep the live block, normalised to the DMS markers and table name so
        # future matugen splices find it.
        palette="$(awk '/PALETTE >>>/{keep=1} keep{print} /PALETTE <<</{keep=0}' "$dst" \
            | sed -e 's|^\[palettes\..*\]|[palettes.dms]|' \
                  -e 's|^# >>> .*PALETTE >>>$|# >>> DMS STARSHIP PALETTE >>>|' \
                  -e 's|^# <<< .*PALETTE <<<$|# <<< DMS STARSHIP PALETTE <<<|')"
    fi
    [ -n "$palette" ] || palette="$(awk '/PALETTE >>>/{keep=1} keep{print} /PALETTE <<</{keep=0}' "$src")"
    # Command substitution eats the blank line the layout ends with, so put it
    # back: the palette block is separated from the layout by one empty line.
    printf '%s\n\n%s\n' "$layout" "$palette"
}

# What a managed file should contain.
desired_content() {
    local key="$1" f="$2"
    if [ "$key" = "starship.toml" ]; then
        starship_wanted
    else
        sed "s|/home/user|$HOME|g" "$f"
    fi
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
        elif ! desired_content "$key" "$f" | cmp -s - "$dst"; then
            say "  ~ $dst"
            changed=1
        fi
    done < <(collect)
    [ "$changed" -eq 1 ]
}

do_deploy() {
    say "NyxDeck → $CONFIG_HOME"

    # Command link, independent of whether the configs have drifted.
    if [ -f "$REPO_DIR/nyxdeck" ]; then
        mkdir -p "$HOME/.local/bin"
        ln -sfn "$REPO_DIR/nyxdeck" "$HOME/.local/bin/nyxdeck"
    fi

    if ! plan_changes; then
        msg "已是最新，无改动。" "Already up to date."
        return 0
    fi

    local key f dst backup
    while IFS=$'\t' read -r key f dst; do
        wants_write "$key" "$dst" || continue
        mkdir -p "$(dirname "$dst")"
        if [ -e "$dst" ] && ! desired_content "$key" "$f" | cmp -s - "$dst"; then
            backup="$BACKUP_ROOT/$STAMP/$key"
            mkdir -p "$(dirname "$backup")"
            cp -p "$dst" "$backup"
        fi
        if [ "$key" = "starship.toml" ]; then
            # Written from the merge, through a temp file so an existing symlink
            # is replaced rather than written through.
            desired_content "$key" "$f" > "$dst.tmp.$$" \
                && chmod 644 "$dst.tmp.$$" && mv -f "$dst.tmp.$$" "$dst"
            continue
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
    # clean-cache.py is executed directly by the `clean` alias.
    [ -f "$CONFIG_HOME/fish/clean-cache.py" ] && chmod +x "$CONFIG_HOME/fish/clean-cache.py"

    # Non-fish shells: source our hook from their rc files. Appended once,
    # marked, and only when the file exists, so a bash/zsh login gets the same
    # PATH, prompt and welcome panel as fish.
    local rc
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [ -f "$rc" ] || continue
        grep -q "nyxdeck/nyxdeck.sh" "$rc" 2>/dev/null && continue
        mkdir -p "$BACKUP_ROOT/$STAMP/$(dirname "${rc#"$HOME/"}")"
        cp -p "$rc" "$BACKUP_ROOT/$STAMP/${rc#"$HOME/"}" 2>/dev/null || true
        {
            printf '\n# NyxDeck shell layer (PATH, prompt, welcome panel)\n'
            printf '[ -f "$HOME/.config/nyxdeck/nyxdeck.sh" ] && . "$HOME/.config/nyxdeck/nyxdeck.sh"\n'
        } >> "$rc"
        say "  + $rc (NyxDeck hook)"
    done

    # One-off: a stale hook from an earlier setup.
    local stale="$CONFIG_HOME/fish/conf.d/nyxdeck-path.fish"
    if [ -e "$stale" ]; then
        mkdir -p "$BACKUP_ROOT/$STAMP/fish/conf.d"
        cp -p "$stale" "$BACKUP_ROOT/$STAMP/fish/conf.d/" 2>/dev/null || true
        rm -f "$stale"
        say "  - $stale (legacy leftover, replaced by nyxdeck-path.fish)"
    fi

    msg "完成。改动前的旧文件备份在 $BACKUP_ROOT/$STAMP/" "Done. Previous files backed up to $BACKUP_ROOT/$STAMP/"
}

do_status() {
    msg "NyxDeck 部署状态：" "NyxDeck deployment status:"
    if plan_changes; then
        say ""
        msg "上面是待同步的差异。运行 ./install.sh 应用。" \
            "The differences above are not deployed yet. Run ./install.sh to apply."
    else
        msg "  全部已同步。" "  Everything is in sync."
    fi
}

do_uninstall() {
    msg "移除 NyxDeck 部署的文件（机器状态与 DMS 运行时文件保留）：" \
        "Removing files deployed by NyxDeck (machine state and DMS runtime files are kept):"
    local key f dst
    while IFS=$'\t' read -r key f dst; do
        is_preserved "$key" && continue
        if [ -e "$dst" ]; then
            say "  - $dst"
            rm -f "$dst"
        fi
    done < <(collect)
    local link="$HOME/.local/bin/nyxdeck"
    if [ -L "$link" ] && [ "$(readlink -f "$link")" = "$REPO_DIR/nyxdeck" ]; then
        rm -f "$link"
        say "  - $link"
    fi
    msg "完成。" "Done."
}

case "${1:-install}" in
    install)   do_deploy ;;
    status)    do_status ;;
    uninstall) do_uninstall ;;
    *)         die "$(msg "用法: $0 [install|status|uninstall]" "usage: $0 [install|status|uninstall]")" ;;
esac
