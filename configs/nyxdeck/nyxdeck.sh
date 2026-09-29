# NyxDeck shell layer for non-fish shells.
#
# NyxDeck owns the fish configuration outright; bash and zsh get this file so
# they are not second-class: the same PATH, the same starship prompt driven by
# ~/.config/starship.toml, and the same welcome panel (the panel is Python, so
# only the hook differs per shell).

# PATH: ~/.local/bin holds the nyxdeck command.
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) PATH="$HOME/.local/bin:$PATH" ;;
esac
export PATH

# Prompt: starship, once, and only if something else has not already claimed it.
if [ -z "${STARSHIP_SHELL:-}" ] && command -v starship >/dev/null 2>&1; then
    # $SHELL is the *login* shell, which is often not the one running this
    # file, so ask the shell itself which it is.
    if [ -n "${BASH_VERSION:-}" ]; then
        eval "$(starship init bash)"
    elif [ -n "${ZSH_VERSION:-}" ]; then
        eval "$(starship init zsh)"
    fi
fi

# Welcome panel: interactive terminal only, never nested, never when silenced.
nyxdeck_skip_fetch() {
    [ -n "${NYXDECK_NO_FETCH:-}" ] && return 0
    [ -t 1 ] || return 0
    [ -n "${SSH_TTY:-}" ] && return 0
    case "${TERM:-}" in
        screen*|tmux*|linux) return 0 ;;
    esac
    return 1
}

if ! nyxdeck_skip_fetch && command -v nyxdeck >/dev/null 2>&1; then
    nyxdeck fetch
fi
unset -f nyxdeck_skip_fetch 2>/dev/null || true
