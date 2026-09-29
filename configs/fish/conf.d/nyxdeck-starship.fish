# NyxDeck prompt: starship, driven by ~/.config/starship.toml.
#
# conf.d is sourced before config.fish, so at this point we cannot know whether
# the user's own config is about to initialise starship. Defer to the first
# prompt instead: by then config.fish has run, and STARSHIP_SHELL tells us
# whether starship already drives the prompt. Initialising twice would duplicate
# key bindings.

if not status is-interactive
    return
end

set -q STARSHIP_SHELL; and return

function __nyxdeck_starship --on-event fish_prompt --description "initialise starship once"
    if not set -q STARSHIP_SHELL; and command -q starship
        starship init fish | source
    end
    functions -e __nyxdeck_starship
end
