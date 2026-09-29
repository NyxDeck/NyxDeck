"""Import the nyxdeck script itself, rooted at a throwaway HOME.

nyxdeck is one file without a .py extension and it computes its paths (HOME,
CONFIG_HOME, the niri config, the plugin directory) at import time. Redirecting
HOME before the module runs therefore gives every test a private desktop, and
keeps the suite away from the real ~/.config.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "nyxdeck"


@pytest.fixture
def nx(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    for name in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))

    loader = importlib.machinery.SourceFileLoader("nyxdeck_under_test", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module
