"""install.sh against a throwaway HOME.

Two of the three bugs that a fresh machine hit lived here: a deploy that aborted
before creating an include niri needs, and a prompt merge that only worked when
the target file already existed. These tests run the real script.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".bashrc").write_text("# bashrc\n")
    return home


def deploy(home, *args, lang="en"):
    """Run install.sh with a HOME of its own and nothing else inherited."""
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "NYXDECK_LANG": lang}
    return subprocess.run([str(INSTALL), *args], capture_output=True, text=True, env=env)


def fingerprint(home):
    """Hash what is deployed, ignoring the bookkeeping directories."""
    skip = {".nyxdeck-backup", ".nyxdeck-snapshots", "__pycache__"}
    digests = {}
    for path in sorted((home / ".config").rglob("*")):
        if skip & set(path.parts) or not path.is_file():
            continue
        digests[str(path.relative_to(home))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


# ── a machine that has never been set up ─────────────────────────────────────

def test_fresh_home_deploys(home):
    res = deploy(home, "install")
    assert res.returncode == 0, res.stderr

    config = home / ".config"
    for relative in ("niri/config.kdl", "niri/effects_normal.kdl", "niri/binds.kdl",
                     "fish/config.fish", "nyxdeck/nyxdeck.sh", "starship.toml",
                     "DankMaterialShell/start.sh", "matugen/config.toml"):
        assert (config / relative).is_file(), relative

    # effects.kdl is a symlink so the eye-care toggle can repoint it.
    assert (config / "niri/effects.kdl").is_symlink()

    # The command link lives outside the config directory.
    assert (home / ".local/bin/nyxdeck").resolve() == REPO / "nyxdeck"

    # A bash login gets the shell layer too.
    assert "nyxdeck/nyxdeck.sh" in (home / ".bashrc").read_text()


def test_deploy_keeps_the_includes_dms_manages(home):
    """DMS writes into niri/dms/ and adds its own include lines; a deploy must not
    drop them, or the display/window-rule/input/layout/binds settings stop being
    read until DMS happens to run again."""
    assert deploy(home, "install").returncode == 0
    config = (home / ".config/niri/config.kdl").read_text()
    for name in ("outputs", "windowrules", "input", "layout", "binds", "cursor"):
        assert f'include optional=true "dms/{name}.kdl"' in config, name


# ── the prompt merge ─────────────────────────────────────────────────────────

def test_prompt_merge_without_a_live_file(home):
    assert not (home / ".config/starship.toml").exists()
    res = deploy(home, "install")
    assert res.returncode == 0, res.stderr
    text = (home / ".config/starship.toml").read_text()
    assert 'palette = "dms"' in text
    assert "DMS STARSHIP PALETTE" in text


def test_prompt_merge_keeps_the_live_palette(home):
    live = home / ".config/starship.toml"
    live.write_text(
        'format = "a layout from an older install"\n'
        "\n"
        "# >>> SOMETHING STARSHIP PALETTE >>>\n"
        "[palettes.something]\n"
        'primary = "#abcdef"\n'
        "# <<< SOMETHING STARSHIP PALETTE <<<\n"
    )
    res = deploy(home, "install")
    assert res.returncode == 0, res.stderr
    text = live.read_text()
    assert "#abcdef" in text                     # colours from matugen survive
    assert "[palettes.dms]" in text              # normalised so matugen keeps splicing
    assert "a layout from an older install" not in text   # layout comes from the repository


# ── repeating it ─────────────────────────────────────────────────────────────

def test_deploy_is_idempotent_and_status_agrees(home):
    assert deploy(home, "install").returncode == 0
    first = fingerprint(home)

    assert deploy(home, "install").returncode == 0
    assert fingerprint(home) == first

    # `status` doubles as a check: zero when the deployment still matches.
    assert deploy(home, "status").returncode == 0

    # ...and non-zero once something drifts.
    (home / ".config/niri/monitor.kdl").unlink()
    assert deploy(home, "status").returncode == 1


def test_status_is_quiet_about_a_missing_deployment(tmp_path):
    empty = tmp_path / "empty"
    (empty / ".config").mkdir(parents=True)
    res = deploy(empty, "status")
    assert res.returncode == 1
    assert "  + " in res.stdout
