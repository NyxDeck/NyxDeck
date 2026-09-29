# matugen user templates

DMS generates color schemes for GTK, niri, fcitx5, kitty, qt6ct, and Firefox
through matugen; `dms matugen check` lists the detected targets. This
directory holds the templates that DMS does not provide but the desktop
requires — currently starship.

## starship

starship has no include mechanism: its palette must be defined inside its
single configuration file. DMS does not ship a starship template, so NyxDeck
renders one and splices it into `~/.config/starship.toml` by way of a matugen
post-hook.

## How DMS consumes user templates

At run time, DMS builds a merged matugen configuration. It locates the user's
sections by **string search rather than TOML parsing**: it extracts a config
section and a templates section using their bracketed names as literal
markers. Two constraints follow, and both are mandatory:

- Comments must not contain those section names inside brackets. A bracketed
  name in a comment is treated as the start of a section, which causes the
  merged configuration to fail to parse and prevents matugen from running at
  all.
- The templates section must be preceded by a bare section header (the name
  alone, with no subtable). A `[templates.<name>]` line on its own does not
  match the marker and is ignored.

Both requirements are documented inline in `config.toml`.

## Template syntax and layout

matugen templates use `{{ colors.<role>.default.hex }}` expressions.
`config.toml` declares each template's `input_path`, `output_path`, and
`post_hook`; `templates/` holds the template bodies. DMS invokes matugen with
user templates enabled, so every declaration here is rendered on each theme
change.

The post-hook, `splice-starship.sh`, replaces the marked palette block in
`starship.toml` with the rendered output and leaves the remainder of the file
intact.
