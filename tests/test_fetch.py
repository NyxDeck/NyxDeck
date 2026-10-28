from __future__ import annotations

import importlib.util
import json
import pathlib
import re

import pytest


@pytest.fixture
def fetch():
    path = pathlib.Path(__file__).resolve().parent.parent / "configs/fastfetch/fetch.py"
    spec = importlib.util.spec_from_file_location("fetch_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collect_groups_data_and_prefers_root_disk(fetch, monkeypatch):
    gib = 1024 ** 3
    monkeypatch.setattr(fetch, "fastfetch_data", lambda: {
        "OS": {"prettyName": "Linux"},
        "Packages": {"all": 12, "pacman": 12},
        "WM": {"prettyName": "niri", "protocolName": "Wayland"},
        "GPU": [{"name": "Discrete"}, {"name": "Integrated"}],
        "Disk": [
            {"mountpoint": "/data", "bytes": {"total": 200 * gib, "used": 10 * gib}},
            {"mountpoint": "/", "filesystem": "btrfs", "bytes": {"total": 100 * gib, "free": 40 * gib}},
        ],
        "Battery": [{"capacity": 75, "status": "Charging"}],
    })
    monkeypatch.setattr(fetch, "detect_running", lambda: ("kitty", "fish"))
    sections = fetch.collect()
    assert [title for title, _ in sections] == ["Distro", "DE/WM", "System"]
    assert ("pkg", "12 (pacman)", "value") in sections[0][1]
    hardware = sections[2][1]
    assert [value for key, value, _ in hardware if key == "gpu"] == ["Discrete", "Integrated"]
    assert ("disk", "60.0 GiB / 100.0 GiB (60%) - btrfs", "value") in hardware
    assert ("bat", "75% [Charging]", "accent") in hardware


@pytest.mark.parametrize("width,logo_width", [(40, 0), (64, 8), (84, 54), (100, 38), (140, 38)])
def test_panel_keeps_logo_and_bounds_long_values(fetch, monkeypatch, width, logo_width):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(fetch, "distro_logo", lambda _: [[("L", None)] * logo_width])
    monkeypatch.setattr(fetch, "tagline", lambda: "")
    panel = fetch.Panel(fetch.FALLBACK_PALETTE, width, bool(logo_width))
    panel.draw([
        ("Distro", [("os", "发行版" * 40, "value"), ("sh", "fish", "value")]),
        ("DE/WM", [("wm", "niri", "value")]),
        ("System", [("host", "desktop", "value")]),
    ])
    text = panel.c.render()
    assert "Distro" in text and "DE/WM" in text and "System" in text
    assert "└─" in text and "…" in text
    assert all(fetch.swidth(line) <= width for line in text.splitlines())
    if logo_width:
        assert "L" * logo_width in text
    backgrounds = {cell[2] for row in panel.c.rows for cell in row if cell and cell[2]}
    assert len(backgrounds) == 16


def test_nerd_icons_are_one_cell_and_style_resets(fetch, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert fetch.swidth("󰏖中") == 4
    canvas = fetch.Canvas(4)
    canvas.text(0, 0, "ab", bg=(1, 2, 3), bold=True)
    canvas.text(0, 2, "c", fg=(4, 5, 6))
    output = canvas.render()
    assert "\033[0;38;2;4;5;6mc" in output
    assert re.sub(r"\033\[[0-9;]*m", "", output).strip() == "abc"


def test_header_uses_os_name_in_panel_and_native_config(fetch, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(fetch, "os_pretty_name", lambda: "Test Linux")
    canvas = fetch.Canvas(60)
    fetch.draw_header(canvas, fetch.FALLBACK_PALETTE, 0, 0, 60, "")
    assert canvas.render().splitlines() == ["NyxDeck · Test Linux", "─" * 20]
    config = json.loads(fetch.native_config(fetch.FALLBACK_PALETTE))
    assert "NyxDeck · Test Linux" in config["modules"][1]["format"]
