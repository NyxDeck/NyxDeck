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
SNAP_ROOT="$CONFIG_HOME/.nyxdeck-snapshots"
SNAPSHOT_KEEP=10
BACKUP_KEEP=10
STAMP="$(date +%Y%m%d-%H%M%S)"

# configs/<subdir> is deployed onto ~/.config/<subdir>.
APPS=("DankMaterialShell" "matugen" "niri" "gtk-3.0" "gtk-4.0" "kitty" "qt6ct" "fcitx5" "fastfetch" "fish" "nyxdeck")
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
    # The wallpaper source list: shipped defaults, plus whatever the user adds.
    "nyxdeck/wallpaper-sources.json"
    # The user's own shell additions live here; the rest of config.fish is ours
    # and does get refreshed.
    "fish/conf.d/__custom__.fish"
    # fisher's state: which plugins are wanted, and fish's universal variables.
    "fish/fish_plugins"
    "fish/fish_variables"
    # The user's terminal tweaks: kitty.conf includes it, and the rest of
    # kitty.conf is ours and does get refreshed.
    "kitty/__custom__.conf"
)

# Values a shipped config cannot know, written as placeholders it can carry:
# /home/user for the home directory, and @PICTURES@ for the XDG pictures
# directory — which is locale-dependent (~/Pictures, ~/图片, ~/Bilder, …), so a
# hard-coded name there would file a screenshot somewhere the user never looks.
xdg_pictures_dir() {
    local dir=""
    if command -v xdg-user-dir >/dev/null 2>&1; then
        dir="$(xdg-user-dir PICTURES 2>/dev/null || true)"
    fi
    # xdg-user-dir answers $HOME when the directory is not configured.
    if [ -z "$dir" ] || [ "$dir" = "$HOME" ]; then
        dir="$HOME/Pictures"
    fi
    printf '%s' "$dir"
}

# sed replacement text is not literal: & means the whole match, \ escapes the
# next character, and the delimiter would close the expression. Escape the values
# rather than trusting that $HOME contains none of them.
sed_replacement() { printf '%s' "$1" | sed -e 's/[&\\|]/\\&/g'; }

PICTURES_DIR="$(xdg_pictures_dir)"
PLACEHOLDER_SED=(-e "s|/home/user|$(sed_replacement "$HOME")|g"
                 -e "s|@PICTURES@|$(sed_replacement "$PICTURES_DIR")|g")

say()  { printf '%s\n' "$*"; }
# Warnings carry the marker nyxdeck uses and go to stderr, so a deploy whose
# stdout is captured still shows them. Five call sites already relied on this
# function existing; it did not, and under `set -e` the shell's own "command not
# found" replaced the message and aborted the deploy with it.
warn() { printf '! %s\n' "$*" >&2; }
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

# Remove the line this repository appends to a shell rc file, marker and all.
strip_rc_hook() { # $1 = rc file
    local rc="$1"
    [ -f "$rc" ] || return 0
    grep -q "nyxdeck/nyxdeck.sh" "$rc" 2>/dev/null || return 0
    awk '!/# NyxDeck shell layer/ && !/nyxdeck\/nyxdeck\.sh/' "$rc" > "$rc.tmp.$$" && mv "$rc.tmp.$$" "$rc"
    say "  - $rc（$(msg "NyxDeck 钩子" "NyxDeck hook")）"
}

# Directories that only held files this repository deployed. rmdir refuses
# non-empty ones, so machine state such as fish_variables or DMS' settings stays.
prune_empty_dirs() {
    local app
    for app in "${APPS[@]}"; do
        [ -d "$CONFIG_HOME/$app" ] || continue
        find "$CONFIG_HOME/$app" -mindepth 1 -type d -empty -delete 2>/dev/null || true
        # if/fi rather than `&&`: a non-empty directory is the normal case here,
        # and a failing last command would take the whole script down with -e.
        if rmdir "$CONFIG_HOME/$app" 2>/dev/null; then
            say "  - $CONFIG_HOME/$app"
        fi
    done
    return 0
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
# a file from an earlier setup gets the layout corrected while keeping its colours.
starship_wanted() {
    local src="$REPO_DIR/configs/starship.toml" dst="$CONFIG_HOME/starship.toml"
    # Explicitly empty: `set -u` rejects an unset variable, and on a fresh box
    # there is no live file to take the palette block from.
    local layout="" palette=""
    layout="$(awk '/PALETTE >>>/{skip=1} /PALETTE <<</{skip=0; next} !skip' "$src")"
    if [ -f "$dst" ]; then
        # Keep the live block, normalised to the DMS markers and table name so
        # future matugen splices find it.
        palette="$(awk '/PALETTE >>>/{keep=1} keep{print} /PALETTE <<</{keep=0}' "$dst" \
            | sed -e 's|^\[palettes\..*\]|[palettes.dms]|' \
                  -e 's|^# >>> .*PALETTE >>>$|# >>> DMS STARSHIP PALETTE >>>|' \
                  -e 's|^# <<< .*PALETTE <<<$|# <<< DMS STARSHIP PALETTE <<<|')"
    fi
    [ -n "${palette:-}" ] || palette="$(awk '/PALETTE >>>/{keep=1} keep{print} /PALETTE <<</{keep=0}' "$src")"
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
        sed "${PLACEHOLDER_SED[@]}" "$f"
    fi
}

# Is the deployed file already what we would write?
# Hashed rather than piped through `cmp`: diffutils is not part of a minimal
# system, and a missing `cmp` made every managed file look changed.
same_content() { # same_content <key> <source> <target>
    local key="$1" f="$2" dst="$3"
    [ -f "$dst" ] || return 1
    [ "$(desired_content "$key" "$f" | sha256sum)" = "$(sha256sum < "$dst")" ]
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
        elif ! same_content "$key" "$f" "$dst"; then
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
        if [ -e "$dst" ] && ! same_content "$key" "$f" "$dst"; then
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
        # (e.g. a theme file that is a symlink) is replaced
        # by the file itself, instead of writing through the link.
        cp --remove-destination -p "$f" "$dst"
        # DMS only substitutes SHELL_DIR/CONFIG_DIR in its own templates; the
        # user's [templates.*] section is appended verbatim, and our configs
        # carry the placeholders above, so we expand them ourselves.
        sed -i "${PLACEHOLDER_SED[@]}" "$dst" 2>/dev/null || true
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

    # Fisher plugins: fish_plugins declares what the shell layer needs (autopair,
    # fzf bindings). `fisher list` prints nothing outside a tty, so probe each
    # plugin's marker function and let fisher fill in what is missing.
    if [ -f "$CONFIG_HOME/fish/fish_plugins" ] && command -v fish >/dev/null 2>&1; then
        local need=0 marker line
        while IFS= read -r line; do
            [ -n "$line" ] || continue
            case "${line%%@*}" in
                jorgebucaran/fisher)        marker=fisher ;;
                jorgebucaran/autopair.fish) marker=_autopair_backspace ;;
                PatrickF1/fzf.fish)         marker=fzf_configure_bindings ;;
                *)                          continue ;;
            esac
            fish -c "functions -q $marker" 2>/dev/null || need=1
        done < "$CONFIG_HOME/fish/fish_plugins"
        if [ "$need" -eq 1 ]; then
            if fish -c 'functions -q fisher' 2>/dev/null; then
                say "  ~ fisher 插件不全，运行 fisher update" "  ~ fisher plugins incomplete, running fisher update"
                fish -c 'fisher update' 2>&1 | sed 's/^/      /' || warn "$(msg "fisher update 失败（离线？）" "fisher update failed (offline?)")"
            else
                # fish_plugins names fisher itself, so this is the first run on a
                # machine that has never had it: `fisher install` cannot work
                # before fisher exists, and the bootstrap is the documented one.
                warn "$(msg "声明了 fisher 插件，但这台机器上还没有 fisher。先在 fish 里引导它：
        curl -sL https://raw.githubusercontent.com/jorgebucaran/fisher/main/functions/fisher.fish | source && fisher install jorgebucaran/fisher
      然后重跑本脚本，其余插件会自动补齐。" \
                        "fisher plugins are declared, but this machine has no fisher yet. Bootstrap it in fish:
        curl -sL https://raw.githubusercontent.com/jorgebucaran/fisher/main/functions/fisher.fish | source && fisher install jorgebucaran/fisher
      then re-run this script and the rest are installed.")"
            fi
        fi
    fi

    # Verify the result rather than trusting it: a missing include only shows up
    # when the session starts.
    if command -v niri >/dev/null 2>&1 && [ -f "$CONFIG_HOME/niri/config.kdl" ]; then
        if niri validate -c "$CONFIG_HOME/niri/config.kdl" >/dev/null 2>&1; then
            say "$(msg "  ✓ niri 配置校验通过" "  ✓ niri configuration validates")"
        else
            warn "$(msg "niri 配置校验失败：niri validate -c $CONFIG_HOME/niri/config.kdl" \
                    "niri configuration failed validation: niri validate -c $CONFIG_HOME/niri/config.kdl")"
        fi
    fi

    # A deploy on a machine that is missing the session's own commands succeeds
    # and then hands the user a login that cannot come up. `nyxdeck deps` already
    # owns the list of what those are, so ask it instead of keeping a second one.
    local deps_out=""
    if [ -x "$HOME/.local/bin/nyxdeck" ] && command -v python3 >/dev/null 2>&1 \
            && ! deps_out="$(NO_COLOR=1 "$HOME/.local/bin/nyxdeck" deps --check 2>&1)"; then
        warn "$(msg "依赖不完整：登录后会话起不来，请先装好下面的包。" \
                "dependencies incomplete: the session will not start; install these first.")"
        printf '%s\n' "$deps_out" | sed 's/^/      /'
        say "$(msg "      安装：nyxdeck deps（或 nyxdeck deps --pick 逐项挑）" \
                "      install with: nyxdeck deps (or --pick to choose)")"
    fi

    msg "完成。改动前的旧文件备份在 $BACKUP_ROOT/$STAMP/" \
        "Done. Previous files backed up to $BACKUP_ROOT/$STAMP/"
}

do_status() {
    msg "NyxDeck 部署状态：" "NyxDeck deployment status:"
    if plan_changes; then
        say ""
        msg "上面是待同步的差异。运行 ./install.sh 应用。" \
            "The differences above are not deployed yet. Run ./install.sh to apply."
        # Non-zero so callers can treat `status` as a check; `nyxdeck verify`
        # reads it to decide whether the deployment still matches the repository.
        return 1
    fi
    msg "  全部已同步。" "  Everything is in sync."
}

do_uninstall() {
    local mode="${1:-}"

    case "$mode" in
        --restore|restore)
            # The oldest snapshot is the state before the first deploy.
            local oldest=""
            [ -d "$SNAP_ROOT" ] && oldest="$(find "$SNAP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort | head -1)"
            [ -n "$oldest" ] || { warn "$(msg "没有快照可回滚" "no snapshot to restore from")"; return 0; }
            msg "回到首次部署前的配置状态（快照 $oldest）：" \
                "Restoring the configuration from before the first deploy (snapshot $oldest):"
            do_rollback "$oldest"
            # The snapshot only covers managed files, so the shell layer is
            # judged by what it says: no nyxdeck.sh in it means the hook was
            # not in the rc files yet either.
            if [ ! -e "$SNAP_ROOT/$oldest/nyxdeck/nyxdeck.sh" ]; then
                strip_rc_hook "$HOME/.bashrc"
                strip_rc_hook "$HOME/.zshrc"
            fi
            return 0
            ;;
    esac

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

    if [ "$mode" = "--purge" ] || [ "$mode" = "purge" ]; then
        msg "彻底清除（配置、快照、备份、插件、shell 钩子）：" \
            "Purging (settings, snapshots, backups, plugins, shell hooks):"
        rm -rf "$SNAP_ROOT" "$BACKUP_ROOT"
        say "  - $SNAP_ROOT"
        say "  - $BACKUP_ROOT"
        rm -rf "$CONFIG_HOME/nyxdeck"
        say "  - $CONFIG_HOME/nyxdeck（语言/标语/Logo 等设置）"
        local plugin
        for plugin in nyxRings mihomoTun; do
            if [ -d "$CONFIG_HOME/DankMaterialShell/plugins/$plugin" ]; then
                rm -rf "$CONFIG_HOME/DankMaterialShell/plugins/$plugin"
                say "  - $CONFIG_HOME/DankMaterialShell/plugins/$plugin"
            fi
        done
        # The rc hooks this repository appended.
        strip_rc_hook "$HOME/.bashrc"
        strip_rc_hook "$HOME/.zshrc"
        prune_empty_dirs
        msg "已彻底清除（mihomo 服务/内核请用 nyxdeck mihomo uninstall --purge）" \
            "Purged (use nyxdeck mihomo uninstall --purge for the mihomo unit)"
        return 0
    fi

    msg "完成。（--restore 回到首次部署前，--purge 连设置一起清）" \
        "Done. (--restore returns to the pre-deploy state, --purge also clears settings)"
}

# ── snapshots ────────────────────────────────────────────────────────────────
# A deploy backup only holds what that deploy changed; a snapshot holds the
# current state of every managed file, so a rollback is one command.

prune_snapshots() {
    local roots=("$SNAP_ROOT" "$BACKUP_ROOT") root dirs i
    for root in "${roots[@]}"; do
        [ -d "$root" ] || continue
        mapfile -t dirs < <(find "$root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -r)
        local keep=$SNAPSHOT_KEEP
        [ "$root" = "$BACKUP_ROOT" ] && keep=$BACKUP_KEEP
        for ((i = keep; i < ${#dirs[@]}; i++)); do
            rm -rf "$root/${dirs[$i]}"
        done
    done
}

snapshot_paths() { # $1 = destination directory
    local key f dst
    while IFS=$'\t' read -r key f dst; do
        [ -e "$dst" ] || continue
        mkdir -p "$1/$(dirname "$key")"
        cp -a "$dst" "$1/$key" 2>/dev/null || cp -p "$dst" "$1/$key"
    done < <(collect)
}

do_snapshot() {
    local note="${1:-}"
    local dir="$SNAP_ROOT/$(date +%Y%m%d-%H%M%S)"
    [ -e "$dir" ] && dir="$dir.$$"
    mkdir -p "$dir"
    snapshot_paths "$dir"
    [ -n "$note" ] && printf '%s\n' "$note" > "$dir/NOTE"
    say "  + $dir"
    prune_snapshots
    msg "快照已创建。" "Snapshot created."
}

do_snapshots() {
    [ -d "$SNAP_ROOT" ] || { msg "还没有快照。" "No snapshots yet."; return 0; }
    local dirs i=1 d note count
    mapfile -t dirs < <(find "$SNAP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -r)
    [ ${#dirs[@]} -eq 0 ] && { msg "还没有快照。" "No snapshots yet."; return 0; }
    for d in "${dirs[@]}"; do
        note="$(cat "$SNAP_ROOT/$d/NOTE" 2>/dev/null || true)"
        count="$(find "$SNAP_ROOT/$d" -type f ! -name NOTE 2>/dev/null | wc -l)"
        printf '  %2d  %-16s %4s files  %s\n' "$i" "${d:0:15}" "$count" "$note"
        i=$((i + 1))
    done
}

do_rollback() {
    local arg="${1:-1}" dirs target src key f dst
    [ -d "$SNAP_ROOT" ] || die "$(msg "还没有快照" "no snapshots yet")"
    mapfile -t dirs < <(find "$SNAP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -r)
    [ ${#dirs[@]} -eq 0 ] && die "$(msg "还没有快照" "no snapshots yet")"
    if [[ "$arg" =~ ^[0-9]+$ ]]; then
        target="${dirs[$((arg - 1))]:-}"
        [ -n "$target" ] || die "$(msg "没有第 $arg 个快照" "no snapshot number $arg")"
    else
        target="$arg"
    fi
    src="$SNAP_ROOT/$target"
    [ -d "$src" ] || die "$(msg "找不到快照 $target" "no snapshot named $target")"

    # Snapshot the current state first, so a rollback can be rolled back.
    local undo="$SNAP_ROOT/$(date +%Y%m%d-%H%M%S)-pre-rollback"
    mkdir -p "$undo" && snapshot_paths "$undo"

    while IFS=$'\t' read -r key f dst; do
        [ -e "$src/$key" ] || continue
        mkdir -p "$(dirname "$dst")"
        cp -a "$src/$key" "$dst" 2>/dev/null || cp -p "$src/$key" "$dst"
        say "  ~ $dst"
    done < <(collect)
    # A snapshot only holds what existed when it was taken. Files the deploy
    # added afterwards are not in it, so restoring the contents alone would
    # leave a machine that never existed. Preserved files are the user's.
    while IFS=$'\t' read -r key f dst; do
        is_preserved "$key" && continue
        [ -e "$src/$key" ] && continue
        if [ -e "$dst" ]; then
            say "  - $dst"
            rm -f "$dst"
        fi
    done < <(collect)
    prune_empty_dirs
    prune_snapshots
    msg "已回滚到 $target（回滚前的状态存为 $(basename "$undo")）" \
        "Rolled back to $target (previous state saved as $(basename "$undo"))"
}

case "${1:-install}" in
    install)   do_deploy ;;
    status)    do_status ;;
    uninstall) do_uninstall "${2:-}" ;;
    snapshot)  do_snapshot "${2:-}" ;;
    snapshots) do_snapshots ;;
    rollback)  do_rollback "${2:-1}" ;;
    *)         die "$(msg "用法: $0 [install|status|uninstall [--restore|--purge]|snapshot [备注]|snapshots|rollback [序号]]" \
                    "usage: $0 [install|status|uninstall [--restore|--purge]|snapshot [note]|snapshots|rollback [index]]")" ;;
esac
