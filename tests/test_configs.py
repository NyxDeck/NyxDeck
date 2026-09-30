"""What the deployment ships has to be reachable.

Two bugs came out of this gap. configs/kitty shipped a theme file that no
kitty.conf included — kitty reads exactly one file — so the terminal ran on
kitty's defaults. And configs/fish never shipped the fish_plugins that
install.sh, verify and doctor all look for, so the fisher step was dead code.

Both deployed cleanly, passed `niri validate`, passed `verify`, and passed the
fresh-install job. Every existing check asks whether the files we write are
correct; none asked whether anything reads them.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIGS = REPO / "configs"

# The single file each program reads, and the suffix it loads configuration
# from. Every other *configuration* file this repository ships under that
# directory has to be reachable from the entry point, by an include or through a
# rule stated in LOADED_ELSEWHERE. Scripts are not configuration: niri spawns
# them from binds.kdl, which is a bind, not an include.
ENTRY_POINT = {
    "kitty": ("kitty.conf", (".conf",)),
    "niri": ("config.kdl", (".kdl",)),
    "gtk-3.0": ("gtk.css", (".css",)),
    "gtk-4.0": ("gtk.css", (".css",)),
}

# Shipped files deliberately not reachable from the entry point, and what loads
# them instead. An entry here is a claim about the runtime, so it says who.
LOADED_ELSEWHERE = {
    "niri/effects_normal.kdl": "the effects.kdl symlink toggle-eyecare.sh maintains",
    "niri/effects_eyecare.kdl": "the effects.kdl symlink toggle-eyecare.sh maintains",
    "niri/orbit-items__custom__.toml": "orbit-launcher.py, not niri",
}

# Files a shipped config may include that this repository does not ship, and who
# writes them. A deploy into an empty HOME leaves all of these missing, so an
# include of one has to be tolerated by the program that reads it.
GENERATED = {
    "niri/effects.kdl": "install.sh, and toggle-eyecare.sh from then on",
    "niri/dms/colors.kdl": "DMS, on every theme change",
    "niri/dms/input.kdl": "DMS",
    "niri/dms/layout.kdl": "DMS",
    "niri/dms/binds.kdl": "DMS",
    "niri/dms/cursor.kdl": "DMS",
    "niri/dms/outputs.kdl": "DMS",
    "niri/dms/windowrules.kdl": "DMS",
    "kitty/dank-theme.conf": "DMS's matugen (colours)",
    "kitty/dank-tabs.conf": "DMS's matugen (tab bar)",
    "gtk-3.0/dank-colors.css": "DMS's matugen",
    "gtk-4.0/dank-colors.css": "DMS's matugen",
}

# install.sh's PRESERVE list promises "seed it when it is absent", so a key with
# no file in configs/ promises a seed that can never happen. These are the two
# that the user's own machine or the deploy creates instead.
SELF_CREATED = {
    "fish/fish_variables": "fish",
    "niri/effects.kdl": "install.sh, and toggle-eyecare.sh from then on",
}

INCLUDE_PATTERNS = {
    ".kdl": r'include\s+(?:optional=true\s+)?"([^"]+)"',
    ".css": r'@import\s+url\("([^"]+)"\)',
    ".fish": r"^\s*source\s+(\S+)",
    ".conf": r"^\s*(?:include|globinclude)\s+(\S+)",
}


def shipped():
    """Every file this repository deploys, as configs-relative posix paths."""
    for path in sorted(CONFIGS.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            yield path.relative_to(CONFIGS).as_posix(), path


def includes_of(path: pathlib.Path) -> list[str]:
    pattern = INCLUDE_PATTERNS.get(path.suffix)
    if pattern is None:
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    targets = []
    for raw in re.findall(pattern, text, re.M):
        target = raw.strip("\"'")
        # Shell loops and globs are not file references we can resolve.
        if not target or target.startswith(("$", "*")) or "*" in target:
            continue
        targets.append(target)
    return targets


def reachable(root: pathlib.Path, entry: str) -> set[str]:
    """configs-relative paths reachable from an entry point by following includes."""
    seen: set[str] = set()
    stack = [entry]
    while stack:
        relative = stack.pop()
        if relative in seen:
            continue
        seen.add(relative)
        current = root / relative
        if not current.is_file():
            continue
        for target in includes_of(current):
            # Both niri and kitty resolve an include relative to the file that
            # names it.
            joined = pathlib.PurePosixPath(relative).parent / target
            stack.append(str(joined))
    return seen


def preserve_list() -> list[str]:
    text = (REPO / "install.sh").read_text(encoding="utf-8")
    body = re.search(r"^PRESERVE=\((.*?)^\)", text, re.M | re.S)
    assert body, "install.sh has no PRESERVE list"
    # bash allows newline-separated array elements, with or without a comma.
    return re.findall(r'^\s*"([^"]+)"\s*,?\s*$', body.group(1), re.M)


@pytest.mark.parametrize("app", sorted(ENTRY_POINT))
def test_every_shipped_config_is_read_by_something(app):
    root = CONFIGS / app
    entry, suffixes = ENTRY_POINT[app]
    loaded = reachable(root, entry)
    orphans = []
    for relative, _ in shipped():
        inside = relative[len(app) + 1:]
        if not relative.startswith(app + "/") or relative in LOADED_ELSEWHERE:
            continue
        if not inside.endswith(suffixes) or inside.startswith("scripts/"):
            continue
        if relative == f"{app}/{entry}" or inside in loaded:
            continue
        orphans.append(relative)
    assert not orphans, (
        f"{app} reads {entry} and nothing else; these are deployed but never read: "
        + ", ".join(orphans)
    )


def dangling_includes(root: pathlib.Path, generated: set[str]) -> list[str]:
    """Includes under `root` that neither the repository ships nor anything creates.

    An absolute path is a system file: this repository cannot ship one, and
    whether it is present is the reading program's business — configs/fish/conf
    .fish guards its CachyOS include with `test -f`. Judging those by the running
    machine is what made an earlier version of this test green on CachyOS and red
    in CI's Arch container.
    """
    dangling = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        for target in includes_of(path):
            if target.startswith("/"):
                continue
            normalised = str(pathlib.PurePosixPath(relative).parent / target)
            if (root / normalised).is_file() or normalised in generated:
                continue
            dangling.append(f"{relative} -> {target}")
    return dangling


def test_every_include_resolves_to_a_shipped_or_generated_file():
    dangling = dangling_includes(CONFIGS, GENERATED)
    assert not dangling, "a shipped config includes a file nothing creates: " + "; ".join(dangling)


def test_an_include_is_not_judged_by_the_machine_it_runs_on(tmp_path):
    """The absolute-path rule, as a behaviour rather than a comment."""
    (tmp_path / "configs" / "fish").mkdir(parents=True)
    (tmp_path / "configs" / "fish" / "config.fish").write_text(
        "source /definitely/not/on/this/machine.fish\n", encoding="utf-8")
    assert dangling_includes(tmp_path / "configs", set()) == []

    # …while a relative include that nothing ships is still reported.
    (tmp_path / "configs" / "fish" / "config.fish").write_text(
        "source ../nowhere.fish\n", encoding="utf-8")
    assert dangling_includes(tmp_path / "configs", set()) == [
        "fish/config.fish -> ../nowhere.fish"]


def test_every_preserved_path_is_seeded_or_self_created():
    unseeded = [
        key for key in preserve_list()
        if not (CONFIGS / key).is_file() and key not in SELF_CREATED
    ]
    assert not unseeded, (
        "PRESERVE promises to seed these, but the repository does not ship them "
        "and nothing else creates them: " + ", ".join(unseeded)
    )


def test_the_preserve_list_is_not_empty():
    """The parser above is load-bearing; a silent empty list would pass the tests."""
    assert len(preserve_list()) > 5
