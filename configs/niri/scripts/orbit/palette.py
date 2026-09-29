"""
Orbit Launcher Palette Engine
Reads DMS's Material You palette cache (dms-colors.json), falling back to
default Material You tokens when it is missing.
"""

import json
import os

DMS_COLORS_PATH = "~/.cache/DankMaterialShell/dms-colors.json"

# dms-colors.json M3 token → orbit's internal role.
_ROLE_MAP = {
    "primary": "primary",
    "secondary": "secondary",
    "tertiary": "tertiary",
    "background": "surface",
    "surface_dim": "surface_dim",
    "on_background": "on_surface",
    "on_surface_variant": "on_surface_var",
    "outline": "outline",
}


def hex_to_rgb(hex_str: str, default=(0.5, 0.5, 0.5)):
    """Convert hex color string (#RRGGBB) to normalized float RGB tuple (0.0 - 1.0)."""
    try:
        hex_str = hex_str.strip().lstrip("#")
        if len(hex_str) == 6:
            return tuple(int(hex_str[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except Exception:
        pass
    return default


def load_material_palette() -> dict:
    """Load the DMS palette with a graceful Material You fallback."""
    palette = {
        "primary": (0.42, 0.70, 1.00),
        "secondary": (0.38, 0.85, 0.65),
        "tertiary": (1.00, 0.75, 0.35),
        "surface": (0.12, 0.13, 0.18),
        "surface_dim": (0.05, 0.06, 0.09),
        "on_surface": (0.95, 0.96, 0.99),
        "on_surface_var": (0.68, 0.72, 0.78),
        "outline": (0.80, 0.84, 0.90),
        "is_dark": True,
    }

    path = os.path.expanduser(DMS_COLORS_PATH)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            colors = data.get("colors", {})
            mode = data.get("mode", "dark")
            m3 = colors.get(mode) or colors.get("dark") or {}
            for m3_name, role in _ROLE_MAP.items():
                if m3_name in m3:
                    palette[role] = hex_to_rgb(m3[m3_name])
            palette["is_dark"] = (mode != "light")
        except Exception:
            pass

    return palette
