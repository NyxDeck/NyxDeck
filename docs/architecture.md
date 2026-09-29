# Architecture

NyxDeck is a self-contained DMS desktop. It owns the entire `~/.config/niri/`
directory together with the DMS, matugen, and starship configuration.

## Why NyxDeck owns the entire niri configuration directory

DMS writes compositor colors to a fixed path, `$XDG_CONFIG_HOME/niri/dms/colors.kdl`
(present in the binary as `CONFIG_DIR/niri/dms/colors.kdl`); the location is not
configurable. Because that directory is written to unconditionally, it is
managed here as a single unit: the niri configuration, key bindings, rules,
and scripts all reside in NyxDeck rather than being distributed across
projects and synchronized afterwards.

## Deploy model

`install.sh` performs an incremental copy:

- It writes only the files present under `configs/` and never deletes
  unknown files in the destination. DMS runtime output under
  `~/.config/niri/dms/` is therefore unaffected.
- Machine- and user-specific state follows a "create if absent, never
  overwrite" policy, declared in the `PRESERVE` list in `install.sh`:
  `niri/monitor.kdl`, `niri/input__custom__.kdl`, `niri/__custom__.kdl`,
  `niri/orbit-items__custom__.toml`, `niri/effects.kdl`, and `starship.toml`.
- `effects.kdl` is a runtime symlink (to `effects_normal.kdl` or
  `effects_eyecare.kdl`). It is created when missing and preserved otherwise,
  because it encodes the eye-care toggle state.
- `starship.toml` is preserved because DMS's matugen rewrites its palette at
  runtime; the repository copy serves as an initial value only.

## Components

- **niri**: `config.kdl` includes the fragments (`layout`, `animations`,
  `rules`, `binds`, `dms/colors.kdl`, `__custom__.kdl`) and starts `start.sh`.
- **DMS**: `~/.config/DankMaterialShell/start.sh` runs `dms run`.
- **matugen**: DMS's built-in templates produce GTK, niri, fcitx5, kitty,
  qt6ct, and Firefox color schemes; the NyxDeck user template adds starship.

## starship

starship has no include mechanism, so its palette must reside inside its
single configuration file. DMS merges and executes the user's
`matugen/config.toml` template declarations on every theme generation. The
pipeline is:

```
DMS wallpaper or theme change
  → matugen renders templates/starship-palette.toml
  → output written to ~/.cache/nyxdeck/starship-palette.toml
  → post-hook splice-starship.sh replaces the marked block in starship.toml
```

A static palette is retained in `starship.toml` as a fallback. DMS locates the
user sections of `matugen/config.toml` by string search rather than TOML
parsing; the resulting constraints are documented in `docs/matugen.md`.
