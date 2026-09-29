#!/usr/bin/env bash
# matugen post_hook: splice the rendered palette into ~/.config/starship.toml.
#
# starship has no include mechanism, so the palette table has to live inside
# its single config file. We replace everything between the two markers,
# leaving the rest of starship.toml (hand-written) untouched.
set -u

rendered="${XDG_CACHE_HOME:-$HOME/.cache}/nyxdeck/starship-palette.toml"
target="${XDG_CONFIG_HOME:-$HOME/.config}/starship.toml"
start='# >>> DMS STARSHIP PALETTE >>>'
end='# <<< DMS STARSHIP PALETTE <<<'

[ -f "$rendered" ] || exit 0
[ -f "$target" ] || exit 0

tmp="$(mktemp)" || exit 1
trap 'rm -f "$tmp"' EXIT

awk -v start="$start" -v end="$end" -v block="$rendered" '
    $0 == start {
        print start
        while ((getline line < block) > 0) print line
        close(block)
        skip = 1
        next
    }
    skip && $0 == end { print end; skip = 0; next }
    skip { next }
    { print }
' "$target" > "$tmp" || exit 1

cat "$tmp" > "$target"
