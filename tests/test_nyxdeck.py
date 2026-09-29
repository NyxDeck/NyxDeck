"""Unit tests for the parts of nyxdeck that are worth pinning down.

The bugs that reached a machine were all in logic like this — the prompt merge
that read an unset variable, a helper called with the wrong signature — so these
tests exist to keep that class of change honest.
"""

from __future__ import annotations

import json
import subprocess
import types

import pytest


def _result(returncode: int):
    return types.SimpleNamespace(returncode=returncode, stdout="", stderr="")


# ── text and language ────────────────────────────────────────────────────────

def test_pad_counts_cjk_as_two_columns(nx):
    assert nx._pad("中文", 6) == "中文  "
    assert nx._pad("ab", 4) == "ab  "
    assert nx._pad("toolong", 4) == "toolong "      # never truncates, keeps a space


def test_language_switches_both_ways(nx):
    nx.set_lang("en")
    assert nx.t("中文", "English") == "English"
    nx.set_lang("zh")
    assert nx.t("中文", "English") == "中文"


# ── packages ─────────────────────────────────────────────────────────────────

def test_pkg_source_splits_repo_from_aur(nx, monkeypatch):
    monkeypatch.setattr(nx, "have", lambda cmd: True)
    monkeypatch.setattr(nx.subprocess, "run", lambda *a, **k: _result(0))
    assert nx._pkg_source("niri") == "repo"
    monkeypatch.setattr(nx.subprocess, "run", lambda *a, **k: _result(1))
    assert nx._pkg_source("mihomo-bin") == "aur"


def test_pkg_installed_asks_pacman(nx, monkeypatch):
    monkeypatch.setattr(nx, "have", lambda cmd: cmd == "pacman")
    monkeypatch.setattr(nx.subprocess, "run", lambda *a, **k: _result(0))
    assert nx._pkg_installed("niri")
    monkeypatch.setattr(nx.subprocess, "run", lambda *a, **k: _result(1))
    assert not nx._pkg_installed("niri")


# ── fisher plugins ───────────────────────────────────────────────────────────

def test_fisher_state_reports_what_is_missing(nx, monkeypatch):
    plugins = nx.CONFIG_HOME / "fish" / "fish_plugins"
    plugins.parent.mkdir(parents=True, exist_ok=True)
    plugins.write_text("jorgebucaran/fisher\n"
                       "jorgebucaran/autopair.fish\n"
                       "PatrickF1/fzf.fish\n")
    present = {"fisher", "fzf_configure_bindings"}       # autopair is missing
    monkeypatch.setattr(nx.subprocess, "run",
                        lambda cmd, **kw: _result(0 if cmd[-1].split()[-1] in present else 1))
    assert nx._fisher_state() == (3, 2, ["jorgebucaran/autopair.fish"])


def test_fisher_state_without_a_declaration(nx):
    assert nx._fisher_state() == (0, 0, [])


# ── niri configuration ───────────────────────────────────────────────────────

def test_niri_binds_reads_the_configuration_in_use(nx):
    nx.BINDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    nx.BINDS_FILE.write_text(
        '// Mod+Comma { spawn "nope"; }\n'
        'Mod+Return { spawn "kitty"; }\n'
        'Mod+Space { spawn "nyxdeck" "fetch"; }\n'
    )
    assert nx._niri_binds() == [
        ("Mod+Return", "kitty"),
        ("Mod+Space", "nyxdeck"),
    ]


def test_niri_binds_without_a_config(nx):
    assert nx._niri_binds() == []


def test_shell_state_notices_a_missing_deployment(nx):
    state, _ = nx._shell_state("fish/config.fish")       # exists in the repository
    assert state == "missing"
    state, _ = nx._shell_state("fish/nothing-here.fish")
    assert state == "unknown"


# ── plugins ──────────────────────────────────────────────────────────────────

def _plugin(nx, plugin_id: str, manifest: dict | None):
    directory = nx.PLUGIN_DIR / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (directory / "plugin.json").write_text(json.dumps(manifest))
    return directory


def test_plugin_state_compares_the_manifest_id_with_the_directory(nx, monkeypatch):
    monkeypatch.setattr(nx, "_dms_plugin_status", lambda pid: "loaded")
    _plugin(nx, "mihomoTun", {"id": "mihomoTun", "name": "Mihomo TUN"})
    state = nx.plugin_state("mihomoTun")
    assert state["dir"] and state["manifest_ok"] and state["dms"] == "loaded"

    _plugin(nx, "nyxRings", {"id": "somethingElse", "name": "x"})
    assert not nx.plugin_state("nyxRings")["manifest_ok"]


def test_git_state_reads_head_and_dirt(nx, tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    (repo / "file.txt").write_text("one")
    git("add", "file.txt")
    git("commit", "-q", "-m", "init")

    state = nx._git_state(repo)
    assert state["head"] and not state["dirty"]
    assert (state["ahead"], state["behind"]) == (0, 0)    # no upstream configured

    (repo / "file.txt").write_text("two")
    assert nx._git_state(repo)["dirty"] is True


def test_git_state_is_empty_outside_a_checkout(nx, tmp_path):
    assert nx._git_state(tmp_path) == {}


def test_verify_plugins_flags_a_manifest_mismatch(nx, monkeypatch):
    monkeypatch.setattr(nx, "have", lambda cmd: True)
    monkeypatch.setattr(nx, "_dms_plugin_status", lambda pid: "loaded")
    _plugin(nx, "broken", {"id": "other", "name": "Other"})
    rows = nx._verify_plugins()
    levels = {label: level for level, label, _ in rows}
    assert levels["broken"] == "fail"


# ── verify ───────────────────────────────────────────────────────────────────

def test_verify_section_counts_only_failures(nx, capsys):
    failed = nx._verify_section("sect", [
        ("ok", "a", ""),
        ("warn", "b", "detail"),
        ("skip", "c", ""),
        ("fail", "d", "boom"),
    ])
    assert failed == 1
    out = capsys.readouterr().out
    assert "sect" in out and "d  —  boom" in out


def test_verify_deps_names_what_is_missing(nx, monkeypatch):
    monkeypatch.setattr(nx, "_pkg_installed", lambda pkg: pkg != "niri")
    rows = nx._verify_deps()
    assert rows[0][0] == "fail" and "niri" in rows[0][2]


def _ok_sections(nx, monkeypatch):
    for name in ("_verify_config", "_verify_deployment", "_verify_deps",
                 "_verify_shell", "_verify_plugins", "_verify_session", "_verify_mihomo"):
        monkeypatch.setattr(nx, name, lambda name=name: [("ok", name, "")])


def test_verify_exit_code_follows_failures(nx, monkeypatch, capsys):
    _ok_sections(nx, monkeypatch)
    assert nx.cmd_verify([]) == 0

    monkeypatch.setattr(nx, "_verify_deployment", lambda: [("warn", "deployment", "pending")])
    assert nx.cmd_verify([]) == 0                      # a warning is not a failure

    monkeypatch.setattr(nx, "_verify_session", lambda: [("fail", "session", "dead")])
    assert nx.cmd_verify([]) == 1


def test_verify_flags_skip_sections(nx, monkeypatch, capsys):
    _ok_sections(nx, monkeypatch)
    monkeypatch.setattr(nx, "_verify_deps",
                        lambda: pytest.fail("--no-deps must skip the dependency check"))
    monkeypatch.setattr(nx, "_verify_plugins",
                        lambda: pytest.fail("--no-plugins must skip the plugin check"))
    assert nx.cmd_verify(["--no-deps", "--no-plugins"]) == 0


# ── command line ─────────────────────────────────────────────────────────────

def test_parser_offers_verify(nx):
    subparsers = [action for action in nx.build_parser()._actions
                  if getattr(action, "choices", None)]
    assert "verify" in subparsers[0].choices


def test_help_runs_without_a_deployment(nx, capsys):
    assert nx.main(["help"]) == 0
    assert capsys.readouterr().out


def test_unknown_command_exits_two(nx, capsys):
    assert nx.main(["definitely-not-a-command"]) == 2
