# NyxDeck terminal welcome panel.
#
# Only in an interactive shell that is attached to a terminal, and never in a
# nested session or when the user asked for silence. NyxDeck owns this file;
# private tweaks belong in conf.d/__custom__.fish.

if not status is-interactive
    return
end

if set -q NYXDECK_NO_FETCH
    return
end

if not test -t 1
    return
end

# Nested sessions already showed it (tmux, screen, ssh, container shells).
switch "$TERM"
    case "screen*" "tmux*" "linux"
        return
end

set -q SSH_TTY; and return

if type -q nyxdeck
    nyxdeck fetch
end
