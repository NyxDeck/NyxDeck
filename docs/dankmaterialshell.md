# DankMaterialShell configuration

DMS stores its settings in `~/.config/DankMaterialShell/settings.json`. The
file is normally edited through the settings panel (`Mod+,`) rather than by
hand.

## Contents of this directory

- `start.sh` — session entry point invoked by niri's `config.kdl`.
- `settings.json` — not pre-seeded.

## Why settings.json is not pre-seeded

The DMS settings schema is large and changes between releases. Maintaining a
hand-written copy duplicates the defaults and becomes stale after every
version change. The recommended procedure is:

1. Log into DMS and configure it through the settings panel.
2. Import the machine's copy into the repository:

   ```bash
   cp ~/.config/DankMaterialShell/settings.json \
      ~/NyxDeck/configs/DankMaterialShell/settings.json
   ```

3. Subsequent `./install.sh` runs deploy it like any other file, with backup.

Once the repository contains `settings.json`, it overwrites the machine's
copy. Local experimental settings should therefore be imported promptly or
kept out of this directory.
