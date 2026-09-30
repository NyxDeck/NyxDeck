# NyxDeck

NyxDeck is an independent, self-contained desktop configuration for Wayland.
It combines the [niri](https://github.com/YaLTeR/niri) compositor with
[DankMaterialShell](https://github.com/AvengeMedia/DankMaterialShell) (DMS)
and a matugen-based theming pipeline, and it deploys as a single unit without
depending on any other configuration project.

## Scope

NyxDeck is responsible for:

- **niri configuration** (`~/.config/niri/`): key bindings, window and layer
  rules, layout, animations, and utility scripts (wallpaper picker, Orbit
  launcher, scratchpad, eye-care, brightness, and media control).
- **DankMaterialShell**: configuration and session startup
  (`~/.config/DankMaterialShell/`).
- **Theming**: DMS generates Material You color schemes for GTK, niri,
  fcitx5, kitty, qt6ct, and Firefox. NyxDeck supplies the templates that DMS
  does not provide (currently starship) and the application entry points that
  import the generated output.
- **starship configuration** (`~/.config/starship.toml`).

NyxDeck intentionally does not manage:

- **Machine- and user-specific state**: `monitor.kdl`, `input__custom__.kdl`,
  `__custom__.kdl`, `orbit-items__custom__.toml`, `effects.kdl`, and
  `starship.toml`. These files are created only when absent and are never
  overwritten.
- **Any desktop shell other than DMS.**

## Repository layout

```
configs/
  niri/                  → ~/.config/niri/
    config.kdl           main configuration; includes fragments and starts DMS
    binds.kdl            key bindings (dispatch through the dms CLI)
    rules.kdl            window and layer rules
    layout.kdl           layout, animations.kdl, monitor.kdl, effects_*.kdl
    __custom__.kdl       user/machine state (not overwritten on deploy)
    input__custom__.kdl
    scripts/             wallpaper picker, Orbit, scratchpad, eye-care,
                         brightness, media control
  DankMaterialShell/     → ~/.config/DankMaterialShell/
    start.sh             session entry point that launches DMS
  matugen/               → ~/.config/matugen/
    config.toml          registers the user templates below
    templates/           starship palette template
    splice-starship.sh   post-hook that splices the palette into starship.toml
  gtk-3.0/               → ~/.config/gtk-3.0/     (imports dank-colors.css)
  gtk-4.0/               → ~/.config/gtk-4.0/     (imports dank-colors.css)
  kitty/                 → ~/.config/kitty/       (kitty.conf pulls in
                                                  current-theme.conf and
                                                  dank-tabs.conf)
  qt6ct/                 → ~/.config/qt6ct/       (selects the matugen scheme)
  starship.toml          → ~/.config/starship.toml
themes/                  custom DMS theme JSON files
docs/                    design documentation
```

## Installation

```bash
git clone https://github.com/NyxDeck/NyxDeck.git ~/NyxDeck
cd ~/NyxDeck
./install.sh            # deploy and list changes
./install.sh status     # show whether the deployment is up to date
./install.sh uninstall  # remove deployed files (machine state is retained)
```

The installer assumes a working niri session with DankMaterialShell, matugen,
and a terminal (kitty by default) available. Before writing, it prints the
list of changes. Any file it overwrites is backed up to
`~/.config/.nyxdeck-backup/<timestamp>/`.

## Command line

`install.sh` links a `nyxdeck` command into `~/.local/bin`. Run it with no
arguments for an interactive control panel (ASCII banner + menu); the first
run asks for the language. Every command also works non-interactively:

```bash
nyxdeck                  # help
nyxdeck install          # deploy the configuration (runs install.sh)
nyxdeck status           # is the deployment up to date? (non-zero when it is not)
nyxdeck uninstall        # remove deployed files (machine state is kept)
nyxdeck doctor           # check dependencies, the session, and plugins
nyxdeck verify           # every check in one pass: non-zero when one of them failed
                         #   --no-deps / --no-plugins for a machine without either
nyxdeck deps [--check]   # install the core packages (cava, matugen, qt6ct, wtype)
nyxdeck widget list      # desktop widgets
nyxdeck plugin list            # grouped by category, with install/enable state
nyxdeck plugin install <id> [--force]
nyxdeck plugin enable <id> | disable <id>
nyxdeck plugin update [id]     # git pull for repository plugins
nyxdeck visualizer on|off|status   # the NyxRings desktop widget
nyxdeck setup                  # one-shot install: deps → config → plugins → Mihomo
nyxdeck setup --dry-run        # just list the steps
nyxdeck update                 # git pull, redeploy, refresh the declared plugins
nyxdeck backup list            # snapshots of every managed file
nyxdeck backup create "note"   # take one
nyxdeck backup restore 2       # roll back (the previous state is snapshotted first)
nyxdeck shell doctor           # shell layer: what is deployed, what is left over
nyxdeck shell edit             # open the preserved __custom__.fish
nyxdeck clean                  # cache cleaner (the `clean` alias runs the same)
nyxdeck help                   # cheatsheet: commands, keybindings, shell helpers
nyxdeck logo pick              # one screen: choices, live preview, type to filter
nyxdeck logo [show]            # the panel mark: show | list [filter] | preview [name]
nyxdeck logo set arch_small    # a built-in fastfetch logo, or a path to an ASCII file
nyxdeck logo --reset           # back to the system default
nyxdeck tagline pick           # type a tagline, watch the header update
nyxdeck tagline [text]         # the NYX DECK tagline: text | --reset | --blank | show
nyxdeck fetch                  # terminal welcome panel (colours follow the wallpaper)
nyxdeck fetch --compact        # no mark
nyxdeck fetch --native         # hand off to fastfetch with a generated config
nyxdeck fetch --install        # write that config for a bare `fastfetch`
nyxdeck mihomo status          # core, service, controller, dashboard, plugin
nyxdeck mihomo install         # whole chain: core → config → dashboard → unit → plugin
nyxdeck mihomo dashboard       # install / update the local dashboard at /ui/
nyxdeck mihomo plugin          # install / update the DMS plugin only
nyxdeck mihomo secret          # show the controller secret (and copy it)
nyxdeck mihomo on|off          # start / stop mihomo.service
nyxdeck mihomo uninstall [--purge]
```

`install`, `status`, and `uninstall` are `install.sh`. The rest wrap DMS: the
plugin manager, and the desktop-widget instances stored in
`~/.config/DankMaterialShell/settings.json`. `nyxdeck visualizer on` installs
the NyxRings plugin from its repository if needed, then adds a widget instance.

### Plugins and categories

`nyxdeck plugin list` (and `doctor`) group plugins by what they do — *visual /
desktop look* (NyxRings), *network / proxy* (mihomoTun) and *built-in / other* —
and report what is actually true rather than just whether a directory exists:
the `plugin.json` manifest has to parse and name the plugin, the checkout has to
be a git repository to be updatable, and DMS itself is asked through
`dms ipc call plugins status <id>` whether the plugin is `loaded` or `disabled`.
Reinstall a broken directory with `nyxdeck plugin install <id> --force`.

### Terminal panel

`nyxdeck fetch` replaces the ad-hoc fastfetch configuration that came before it. It draws a
Material 3 Expressive panel — accent-coloured section labels, the
distribution's own logo art, and a tonal swatch row — from the palette DMS
generated for the current wallpaper, with `fastfetch --format json` supplying
the machine data.
Nothing is hard-coded, so the panel changes with the wallpaper like the bar,
the terminal and starship do.

A `rice  NyxDeck` row credits the desktop. Section
labels carry no background block, which would read as a halo on a translucent
terminal.

The mark defaults to fastfetch's built-in logo for the detected distribution
(official distro art, so it looks as deliberate as the distro's own),
recoloured from the palette — fastfetch drops colour when stdout is a pipe, so
it is captured through a pty and merged into the canvas. A hand-drawn crescent
is used only when fastfetch is missing.

`nyxdeck logo` swaps it. `pick` opens one screen holding the choices, the
current value, a live preview of the highlighted logo and type-to-filter (fzf
underneath, so `esc` cancels; the plain menu is the fallback without fzf).
`list` prints the names — CachyOS is Arch underneath, so `arch_small` and
friends are right there — `preview` draws one on its own, `set <name|file>`
stores it in `~/.config/nyxdeck/logo` and `--reset` returns to the auto-detected
default. A path to an ASCII file of your own works the same way.

Wide art is kept beside the text rather than pushed underneath it: the panel
uses up to the full terminal width (capped at 100 columns) and elides the
longest values with `…` so the columns still fit. Only when that would leave the
text column narrower than 26 cells — `CachyOS` (54 wide) on an 84-column
terminal — does it stack the logo above, centred, and only a logo wider than the
terminal itself is dropped.

The tagline has the same shape: `nyxdeck tagline pick` is a prompt whose preview
redraws the header as you type, with a few suggestions listed.

The header reads `◆ NYX DECK · <tagline>`. The tagline defaults to the
localised "a self-contained desktop" / 自足的桌面 and is overridable with
`nyxdeck tagline <text>` (also in the interactive panel), `--reset` restores
the default and `--blank` drops the tagline so only `NYX DECK` remains. It is
stored in `~/.config/nyxdeck/tagline`.

The panel is English; `NYXDECK_LANG=zh` switches it. Terminal and shell are
read from the process tree rather than from fastfetch, which would otherwise
report the renderer's own `python3` process. `NO_COLOR` prints it plain, a
terminal narrower than 64 columns drops the mark, and a missing palette falls
back to a built-in dark M3 set.

`install.sh` deploys it to `~/.config/fastfetch/fetch.py` and drops a
`~/.config/fish/conf.d/nyxdeck-fetch.fish` hook so interactive shells show it
(never in tmux/ssh nesting, never with `NYXDECK_NO_FETCH`, never without a
terminal).

A `fish_greeting` function defined by the distribution runs in addition to that
hook — CachyOS ships one that calls bare `fastfetch`, which draws a second,
unthemed panel. Remove it with `functions -e fish_greeting` (the hook, sourced
from `conf.d`, runs before `config.fish` and cannot cancel a later definition,
so NyxDeck taking over `~/.config/fish` is what would make this automatic). `--native` falls back to fastfetch itself with a generated config,
and `--install` writes that config into `~/.config/fastfetch` (backing the old
one up first) for anyone who runs bare `fastfetch`.

### Shell prompt

The prompt is starship and its layout lives in `configs/starship.toml` — the
`╭╴ … ╰─❯` shape. That file is two things at once: the
layout is NyxDeck's, and the `# >>> DMS STARSHIP PALETTE >>>` block inside it
belongs to DMS's matugen, which rewrites it on every theme change. Deployment
therefore **merges** rather than seeding: it takes the layout from this
repository and keeps the palette block from the machine (normalising its markers
and table name to `dms`), so a box that still carries a file from an earlier
`starship.toml` gets the layout corrected while keeping its colours. Deploying
is idempotent once the two agree.

`configs/fish/conf.d/nyxdeck-starship.fish` makes a shell actually use it.
`conf.d` is sourced before `config.fish`, so it cannot know whether the user's
own configuration is about to initialise starship; it defers to the first
`fish_prompt` event and checks `STARSHIP_SHELL` there, which means it initialises
starship on a box that has none and does nothing on a box that already does
(initialising twice would duplicate key bindings).

### One-shot install, updates and snapshots

`nyxdeck setup` is the whole pipeline in one command: it installs the runtime
dependencies, deploys the configuration, clones the plugins declared in
`PLUGIN_REPOS`, runs the Mihomo TUN pipeline and restarts DMS. It takes a
snapshot first, so a setup that goes wrong is one `nyxdeck backup restore` away
from undone; `--dry-run` lists the steps, `--no-mihomo` / `--no-plugins` /
`--no-deps` narrow them down. `CORE_DEPS` includes fastfetch and starship,
because the panel and the prompt are built on them.

`nyxdeck update` pulls this repository (`--ff-only`), redeploys and refreshes
every declared plugin checkout.

`nyxdeck backup` keeps snapshots — a copy of the current state of every managed
file — in `~/.config/.nyxdeck-snapshots`, newest ten kept. `rollback` snapshots
the state it is about to replace, so a rollback can itself be rolled back.
Tighter than that, each deploy still records only the files it changed under
`~/.config/.nyxdeck-backup`.

### What is not covered here

The lifecycle is complete — install, update, verify, snapshot, roll back,
uninstall — and the list of what this repository deliberately leaves to
something else is short:

- **theming**: DMS's matugen generates the palette and the per-app templates;
- **the display manager and the input method**: installing those is a system
  decision rather than a configuration one;
- **an app store, per-app configuration presets, diagnostic report bundles and
  self-tests**: useful tools, but not part of deploying this desktop.

Beyond configuration this repository owns: categorised DMS plugin management,
the Mihomo TUN chain with its local dashboard, the terminal welcome panel, the
logo and tagline theming, the desktop-widget toggles, and a shell layer that
covers bash and zsh as well as fish.

### Shell layer

NyxDeck owns the shell configuration:

| file | note |
|---|---|
| `configs/fish/config.fish` | aliases, proxy helpers, package helpers — **refreshed on deploy** |
| `configs/fish/clean-cache.py` | the cache cleaner behind `nyxdeck clean` and the `clean` alias |
| `configs/fish/conf.d/__custom__.fish` | the entry point for private tweaks — **preserved on deploy** |
| `configs/fish/conf.d/nyxdeck-*.fish` | PATH, welcome panel, prompt hooks |
| `configs/nyxdeck/nyxdeck.sh` | the same PATH, prompt and panel for bash and zsh, sourced from their rc files |
| `configs/starship.toml` | the prompt layout (merged at deploy time, see below) |

Anything personal belongs in `conf.d/__custom__.fish` or a `__custom__/` directory
next to it; `config.fish` itself is refreshed so the shell layer can actually
evolve. Fisher plugins stay user-managed and are never touched.

`nyxdeck shell status` reports each file, `nyxdeck shell doctor` also checks what the layer needs (starship, the hooks,
the fisher plugins), `shell install` re-deploys and `shell edit` opens the private file.

`nyxdeck help` is generated rather than hand-written: the command list comes
from the argument parser and the keybindings are parsed from the niri
configuration in use, so the cheatsheet cannot go stale. The `nyxhelp` and
`clean` aliases still work.

### Mihomo TUN pipeline

`nyxdeck mihomo install` owns the whole chain and is idempotent:

1. the `mihomo` core (pacman / AUR),
2. `/etc/mihomo/config.yaml` + controller secret + the DIRECT rule provider,
3. **metacubexd** into `/etc/mihomo/ui` plus `external-ui` in the config, so the
   controller serves a local dashboard at `http://127.0.0.1:9090/ui/`,
4. `mihomo.service`, enabled and started,
5. the `mihomoTun` DMS plugin, enabled and restarted.

The root-side steps live in the plugin checkout (`install.sh`,
`scripts/install-dashboard.sh`) and are invoked through `sudo`; the GUI panel
uses `pkexec` for the same edits. Mihomo only exposes `/ui/` when `external-ui`
is configured, so the plugin's *Web panel* button probes the endpoint first and
falls back to the hosted dashboard with the secret on the clipboard.

Output is bilingual (zh / en), chosen from the locale (`LC_ALL`,
`LC_MESSAGES`, `LANG`); set `NYXDECK_LANG=zh` or `en` to override. `install.sh`
follows the same rule.

### Wallpapers

`nyxdeck wallpaper` is the one backend for wallpaper work: the GTK picker on
`Mod+W` and (eventually) the bar plugin are front ends for it, so they cannot
disagree about what a wallpaper is or how it is applied.

```bash
nyxdeck wallpaper status          # roots, counts, thumbnail cache, sources
nyxdeck wallpaper list --json     # categories and items, for a UI front end
nyxdeck wallpaper sources         # list | add <name> <url> [--mirror <url>] | remove <name>
nyxdeck wallpaper download        # fetch a source; nothing is downloaded by default
nyxdeck wallpaper set <file|#>    # static through DMS, video through mpvpaper
nyxdeck wallpaper next            # a random one (--static / --video)
nyxdeck wallpaper cache --clean   # drop the thumbnail cache
```

Wallpapers live where the picker already looks — `~/图片/Wallpapers` and
`~/图片/Wallpapers/video` (or `~/Pictures/...`, `${NYXDECK_WALLPAPERS_DIR}`).
The directory layout *is* the second level of the categories the panel shows:
`All` / `Static` / `Live` on top, the subfolders underneath.

Nothing is downloaded until you ask. The shipped source list
(`configs/nyxdeck/wallpaper-sources.json`, copied once and then preserved) names
one community collection plus a mirror for networks that need it; it declares no
licence, which is exactly why it is a source you opt into rather than something
we bundle. Add your own with `nyxdeck wallpaper sources add`.

## Verifying an installation

Three levels of checking, none of which needs a graphical session.

**On a live machine.** One command covers everything, and it is the same check
`setup` runs as its last step:

```bash
nyxdeck verify            # configuration, deployment, dependencies, shell layer,
                          # plugins, session, Mihomo — non-zero if one failed
```

**Deploy into a throwaway HOME.** The cheapest way to prove the deploy path works
from scratch:

```bash
rm -rf /tmp/freshhome && mkdir -p /tmp/freshhome
HOME=/tmp/freshhome XDG_CONFIG_HOME=/tmp/freshhome/.config ./install.sh install
niri validate -c /tmp/freshhome/.config/niri/config.kdl
```

`install.sh` validates the deployed niri configuration itself before it finishes,
so a missing include is reported immediately instead of when the session starts.
This is worth running after touching `configs/niri/`: a stale check catches
exactly the class of fault that only appears at login.

**The whole pipeline on a clean system.** Packages, deployment and tooling, in a
container built from the host's own repositories and package cache:

```bash
sudo pacman -S --needed arch-install-scripts
ROOT=/tmp/nyxdeck-test && mkdir -p "$ROOT"
sudo pacstrap -C /etc/pacman.conf -K "$ROOT" \
    base niri dms-shell kitty fish starship fastfetch fzf matugen cava \
    qt6ct wtype wlsunset mpvpaper ffmpeg jq eza python-gobject gtk-layer-shell \
    ttf-jetbrains-mono-nerd noto-fonts-cjk
sudo systemd-nspawn -q -D "$ROOT" useradd -m tester
sudo systemd-nspawn -q -D "$ROOT" --bind="$PWD:/src" --uid=tester \
    /bin/bash -lc 'cd /src && ./install.sh install \
        && niri validate -c ~/.config/niri/config.kdl \
        && export PATH=$HOME/.local/bin:$PATH \
        && nyxdeck deps --check && nyxdeck shell doctor'
sudo rm -rf "$ROOT"
```

Using `pacstrap` rather than a container image keeps the repository configuration
identical to the target machine — `dms-shell` and `mpvpaper` come from the
CachyOS repositories, and a plain Arch image would need them from the AUR instead.

Last run: 388 packages installed, the deploy finished with `niri configuration
validates`, `deps --check` reported everything present, and the shell layer came
out clean. The panel rendered inside the container too — picking that
distribution's own logo (the Arch art there, the CachyOS one here) and falling
back to `? · dark` where no palette exists yet.

What a container cannot prove is the session itself: niri starting, DMS running,
the display manager, font and emoji rendering. Those need a real GPU and
compositor.

## Optional: audio visualizer

DMS's built-in visualizer lives in the bar media widget and Dank Island and
only requires `cava`:

```bash
sudo pacman -S cava
```

**NyxRings** is a separate plugin, open-sourced at
[github.com/NyxDeck/nyxRings](https://github.com/NyxDeck/nyxRings); this
repository does not vendor it. It is a fully transparent desktop widget
rendering the *wave_rings* effect (the shader is a port; its upstream
notice lives in the plugin's `LICENSE`): concentric rings and a
polar spectrum around an empty centre, driven by cava. Install it into DMS's
plugin directory and restart:

```bash
git clone https://github.com/NyxDeck/nyxRings.git \
    ~/.config/DankMaterialShell/plugins/nyxRings
dms restart
```

Then add one instance under **Settings → Desktop Widgets**. Its appearance is
set by the widget's properties (`sensitivity`, `rotationSpeed`, `ringOpacity`,
`bloomIntensity`, `waveThickness`, `innerDiameter`, `fadeWhenIdle`); the
colours follow the theme's primary and secondary. See the plugin's README.

Registry alternatives, also added under Settings → Desktop Widgets:

- **EnderPulse** — braille, spectrum, mirrored pulse, radial orbit.
- **Cava Visualizer** — bars, curve outline, curve filled.

AudioFX offers a screen-edge spectrum, a wallpaper glow, and a player disc.
The edge spectrum and the glow are full-screen background layers (on niri the
wallpaper is drawn over them); using them needs these layer rules in
`configs/niri/rules.kdl`:

```kdl
layer-rule { match namespace="^audiofx$"      place-within-backdrop true }
layer-rule { match namespace="^audiofx-glow$" place-within-backdrop true }
```

DMS never adds plugin desktop widgets automatically: create one instance per
widget under **Settings → Desktop Widgets**. Instance position and size are
part of DMS's own state, not this repository.

## License

Licensed under GPL-3.0. See [LICENSE](LICENSE).

## Operational notes

- DMS writes compositor colors into `~/.config/niri/dms/colors.kdl` at a
  fixed path, which niri then includes. Because that directory is owned by
  this project, DMS output and the compositor configuration are always
  managed together.
- DMS rewrites `~/.config/starship.toml` at runtime (through its matugen
  post-hook). The copy in this repository is an initial value only; it is
  written when the target is absent and is otherwise left untouched.

## Troubleshooting

**Icons render as blank or checkered placeholders.** DMS selects and indexes
its own icon theme, and it cannot resolve every system theme (the Breeze
family, for example). Choose a resolvable theme in DMS Settings -> Icon
Theming, or from a shell:

```bash
dms ipc call settings set iconThemeDark Adwaita
dms ipc call settings set iconThemeLight Adwaita
dms restart
```

See `docs/architecture.md` for the deploy model and `docs/matugen.md` for the
theming pipeline.
