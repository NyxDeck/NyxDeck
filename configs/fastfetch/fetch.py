#!/usr/bin/env python3
"""nyxdeck fetch — the terminal welcome panel.

Draws a Material 3 Expressive panel from the palette DMS generated for the
current wallpaper, with fastfetch supplying the machine data. Everything lands
on a cell canvas first, so the labels and the mark follow the desktop theme
instead of a fixed ANSI colour set.

    nyxdeck fetch                 # the panel
    nyxdeck fetch --compact       # no mark
    nyxdeck fetch --native        # hand off to fastfetch with a generated config
    nyxdeck fetch --install       # write that config for a bare `fastfetch`
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache"))
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state"))

DMS_SETTINGS = CONFIG_HOME / "DankMaterialShell" / "settings.json"
DMS_SESSION = STATE_HOME / "DankMaterialShell" / "session.json"
DMS_COLORS = CACHE_HOME / "DankMaterialShell" / "dms-colors.json"

RESET = "\033[0m"
BOLD = "\033[1m"

# Terminal output is English; NYXDECK_LANG=zh opts into Chinese.
_LANG = os.environ.get("NYXDECK_LANG", "en").lower()[:2]


def t(zh: str, en: str) -> str:
    return zh if _LANG == "zh" else en


# Used only when DMS has not written a palette yet, so the panel still looks
# deliberate instead of collapsing to eight-colour ANSI.
FALLBACK_PALETTE = {
    "primary": "#a3c9fe",
    "on_primary_container": "#d3e4ff",
    "primary_container": "#1e4876",
    "secondary": "#bcc7db",
    "tertiary": "#d8bde3",
    "error": "#ffb4ab",
    "on_surface": "#e1e2e8",
    "on_surface_variant": "#c3c6cf",
    "outline_variant": "#43474e",
    "surface_container_high": "#1d2024",
}


# ── palette ──────────────────────────────────────────────────────────────────


def load_palette() -> dict:
    """DMS's generated palette, completed with fallbacks for missing roles."""
    try:
        data = json.loads(DMS_COLORS.read_text(encoding="utf-8"))
        palette = data.get("colors", {}).get(data.get("mode", "dark")) or {}
    except (OSError, ValueError):
        palette = {}
    merged = dict(FALLBACK_PALETTE)
    merged.update({k: v for k, v in palette.items() if isinstance(v, str) and v.startswith("#")})
    return merged


def rgb(value: str) -> tuple[int, int, int]:
    value = str(value or "").lstrip("#")
    if len(value) != 6:
        return (225, 226, 232)
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (225, 226, 232)


def mix(a, b, ratio: float):
    return tuple(round(x + (y - x) * ratio) for x, y in zip(a, b))


def swidth(string: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in string)


def pad_left(string: str, width: int) -> str:
    return " " * max(0, width - swidth(string)) + string


# ── the mark ─────────────────────────────────────────────────────────────────
# fastfetch ships hand-drawn per-distribution ASCII art and picks it from
# /etc/os-release. We use that art — it looks as deliberate as the distro's own —
# looks as deliberate as the distro's own) and colour it from the DMS palette
# instead of a hard-coded ANSI colour. fastfetch drops colour when stdout is a
# pipe, hence the pty capture.

_ANSI = re.compile(r"\033\[([0-9;]*)m")
_OTHER_ESC = re.compile(r"\033\[[0-9;]*[A-Za-z]")

# fastfetch's colour groups in the built-in logos, mapped to palette roles.
LOGO_ROLES = {1: "primary", 2: "tertiary", 3: "secondary", 4: "error"}


def capture_ansi(cmd: list[str], timeout: float = 5.0) -> str:
    """Run a command attached to a pty so it keeps its ANSI colours."""
    master, slave = pty.openpty()
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=slave,
                                stderr=subprocess.DEVNULL)
    finally:
        os.close(slave)
    chunks: list[bytes] = []
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(master)
        proc.wait(timeout=2)
    return b"".join(chunks).decode("utf-8", "replace")


def parse_ansi(text: str) -> list[list[tuple[str, tuple | None]]]:
    """-> rows of (character, foreground) with the SGR state applied."""
    rows: list[list[tuple[str, tuple | None]]] = []
    row: list[tuple[str, tuple | None]] = []
    colour: tuple | None = None
    for token in re.split(r"(\033\[[0-9;]*[A-Za-z])", text):
        if not token:
            continue
        match = _ANSI.fullmatch(token)
        if match:
            params = [int(p) if p else 0 for p in match.group(1).split(";")] or [0]
            index = 0
            while index < len(params):
                value = params[index]
                if value == 0:
                    colour = None
                elif value == 38 and params[index + 1:index + 2] == [2]:
                    rgbv = params[index + 2:index + 5]
                    if len(rgbv) == 3:
                        colour = tuple(rgbv)
                    index += 4
                index += 1
            continue
        if _OTHER_ESC.fullmatch(token):
            continue
        for char in token.replace("\r", ""):
            if char == "\n":
                rows.append(row)
                row = []
            else:
                row.append((char, colour))
    if row:
        rows.append(row)
    return rows


def distro_logo(palette: dict) -> list[list[tuple[str, tuple | None]]]:
    """fastfetch's built-in logo for this distribution, in our palette."""
    exe = shutil.which("fastfetch")
    if not exe:
        return []
    config = {
        "logo": {
            "type": "small",
            "color": {str(k): "38;2;%d;%d;%d" % rgb(palette[v]) for k, v in LOGO_ROLES.items()},
            "padding": {"left": 0, "right": 0},
        },
        "modules": [],
    }
    scratch = Path("/tmp") / f"nyxdeck-logo-{os.getpid()}.jsonc"
    try:
        scratch.write_text(json.dumps(config), encoding="utf-8")
        rows = parse_ansi(capture_ansi([exe, "-c", str(scratch)]))
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    finally:
        scratch.unlink(missing_ok=True)
    return [r for r in rows if any(c.strip() for c, _ in r)]


# ── canvas ───────────────────────────────────────────────────────────────────


class Canvas:
    """Cell grid; a wide character claims two columns, later writes win."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.rows: list[list] = []

    def _row(self, index: int) -> list:
        while len(self.rows) <= index:
            self.rows.append([None] * self.width)
        return self.rows[index]

    def put(self, row: int, col: int, char: str, fg=None, bg=None, bold=False) -> int:
        if not (0 <= col < self.width):
            return col + 1
        self._row(row)[col] = (char, fg, bg, bold)
        if unicodedata.east_asian_width(char) in ("W", "F") and col + 1 < self.width:
            self._row(row)[col + 1] = ("", fg, bg, bold)
        return col + swidth(char)

    def text(self, row: int, col: int, string: str, fg=None, bg=None, bold=False) -> int:
        for char in string:
            col = self.put(row, col, char, fg, bg, bold)
        return col

    def render(self) -> str:
        if os.environ.get("NO_COLOR"):
            return "\n".join(
                "".join((cell[0] if cell else " ") for cell in cells).rstrip()
                for cells in self.rows
            )
        lines = []
        for cells in self.rows:
            out, last = [], object()
            for cell in cells:
                char, fg, bg, bold = cell if cell else (" ", None, None, False)
                style = (fg, bg, bold)
                if style != last:
                    codes = ["1"] if bold else []
                    if fg:
                        codes.append("38;2;%d;%d;%d" % fg)
                    if bg:
                        codes.append("48;2;%d;%d;%d" % bg)
                    out.append("\033[" + (";".join(codes) or "0") + "m")
                    last = style
                out.append(char)
            lines.append("".join(out).rstrip() + RESET)
        return "\n".join(lines)


# ── who is running us ────────────────────────────────────────────────────────

TERMINALS = {
    "kitty": "kitty", "alacritty": "alacritty", "wezterm": "wezterm",
    "wezterm-gui": "wezterm", "ghostty": "ghostty", "foot": "foot",
    "footclient": "foot", "konsole": "konsole", "gnome-terminal": "gnome-terminal",
    "kgx": "gnome console", "xterm": "xterm", "alacritty-msg": "alacritty",
    "contour": "contour", "rio": "rio", "termux": "termux",
}
SHELLS = {
    "fish": "fish", "bash": "bash", "zsh": "zsh", "nu": "nushell",
    "elvish": "elvish", "dash": "dash", "ksh": "ksh", "tcsh": "tcsh",
}


def ancestors() -> list[str]:
    """Process names from us upwards; fastfetch would report *us* otherwise."""
    names, pid, guard = [], os.getpid(), 0
    while pid > 1 and guard < 24:
        guard += 1
        try:
            name = Path(f"/proc/{pid}/comm").read_text().strip()
            status = Path(f"/proc/{pid}/status").read_text()
        except OSError:
            break
        names.append(name)
        parent = 0
        for line in status.splitlines():
            if line.startswith("PPid:"):
                parent = int(line.split()[1])
                break
        if parent == pid:
            break
        pid = parent
    return names


def detect_running() -> tuple[str, str]:
    """(terminal, shell) as names, from the process tree then the environment."""
    chain = ancestors()
    terminal = next((TERMINALS[p] for p in chain if p in TERMINALS), "")
    shell = next((SHELLS[p] for p in chain if p in SHELLS), "")

    if not terminal:
        term = os.environ.get("TERM", "")
        if "kitty" in term:
            terminal = "kitty"
        elif "alacritty" in term:
            terminal = "alacritty"
        elif "ghostty" in term:
            terminal = "ghostty"
        elif os.environ.get("WEZTERM_PANE"):
            terminal = "wezterm"
        elif os.environ.get("VTE_VERSION"):
            terminal = "vte"
        elif term and term != "linux":
            terminal = term
    if not shell:
        shell = Path(os.environ.get("SHELL", "")).name or "?"
    return terminal or "terminal", shell or "?"


# ── system data ──────────────────────────────────────────────────────────────

STRUCTURE = "OS:Kernel:WM:CPU:GPU:Display:Memory:Disk:Uptime"


def fastfetch_data() -> dict:
    exe = shutil.which("fastfetch")
    if not exe:
        return {}
    try:
        raw = subprocess.run(
            [exe, "--format", "json", "--logo", "none", "--structure", STRUCTURE],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
        modules = json.loads(raw)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    return {
        m["type"]: m["result"]
        for m in modules
        if m.get("type") and isinstance(m.get("result"), (dict, list))
    }


def human_gib(value) -> str:
    try:
        return "%.1f GiB" % (float(value) / 1024 ** 3)
    except (TypeError, ValueError):
        return "?"


def human_duration(seconds) -> str:
    try:
        seconds = int(float(seconds) / 1000)
    except (TypeError, ValueError):
        return "?"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    parts = [f"{days}d"] if days else []
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{rest // 60}m")
    return " ".join(parts)


def os_pretty_name() -> str:
    """Used only when fastfetch is unavailable."""
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def collect() -> list[tuple[str, list[tuple[str, str, str]]]]:
    data = fastfetch_data()
    terminal, shell = detect_running()

    system: list[tuple[str, str, str]] = []
    osinfo = data.get("OS") or {}
    pretty = osinfo.get("prettyName") or osinfo.get("name") or os_pretty_name()
    system.append(("os", f"{pretty} ({osinfo.get('architecture') or os.uname().machine})", "value"))
    if (data.get("Kernel") or {}).get("release"):
        system.append(("kern", data["Kernel"]["release"], "value"))
    wm = data.get("WM") or {}
    if wm.get("prettyName"):
        protocol = wm.get("protocolName")
        system.append(("wm", f"{wm['prettyName']}{f' ({protocol})' if protocol else ''}", "value"))
    # Which desktop this is.
    system.append(("rice", "NyxDeck", "accent"))
    system.append(("term", terminal, "value"))
    system.append(("sh", shell, "value"))

    desktop: list[tuple[str, str, str]] = []
    settings = read_json(DMS_SETTINGS)
    colours = read_json(DMS_COLORS)
    theme = settings.get("currentThemeName") or "?"
    desktop.append(("theme", f"{theme} · {colours.get('mode') or 'dark'}", "accent"))
    wallpaper = read_json(DMS_SESSION).get("wallpaperPath") or ""
    if wallpaper:
        desktop.append(("wall", Path(wallpaper).name, "value"))
    state = service_state("mihomo.service")
    if state:
        desktop.append(("proxy", state, "accent" if state == "active" else "muted"))

    hardware: list[tuple[str, str, str]] = []
    cpu = data.get("CPU") or {}
    if cpu.get("cpu"):
        cores = (cpu.get("cores") or {}).get("logical")
        hardware.append(("cpu", cpu["cpu"] + (f" · {cores}c" if cores else ""), "value"))
    gpus = data.get("GPU") or []
    if gpus and gpus[0].get("name"):
        hardware.append(("gpu", gpus[0]["name"], "value"))
    displays = data.get("Display") or []
    if displays and (displays[0].get("output") or {}).get("width"):
        out = displays[0]["output"]
        hardware.append(("disp", f"{out['width']}x{out['height']} @{round(out.get('refreshRate') or 0)}Hz", "value"))
    memory = data.get("Memory") or {}
    if memory.get("total"):
        used, total = memory.get("used", 0), memory["total"]
        hardware.append(("mem", f"{human_gib(used)} / {human_gib(total)} ({round(used / total * 100)}%)", "accent"))
    for disk in data.get("Disk") or []:
        sizes = disk.get("bytes") or {}
        if sizes.get("total") and (disk.get("mountpoint") == "/" or not any(k == "disk" for k, _, _ in hardware)):
            used = sizes.get("used", 0)
            hardware.append(("disk", f"{human_gib(used)} / {human_gib(sizes['total'])} ({round(used / sizes['total'] * 100)}%)", "value"))
            break
    if (data.get("Uptime") or {}).get("uptime") is not None:
        hardware.append(("up", human_duration(data["Uptime"]["uptime"]), "value"))

    return [
        (t("系统", "system"), system),
        ("nyxdeck", desktop),
        (t("硬件", "hardware"), hardware),
    ]


def service_state(unit: str) -> str:
    if not shutil.which("systemctl"):
        return ""
    try:
        return subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True, text=True,
            timeout=3, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# ── drawing ──────────────────────────────────────────────────────────────────

# Fallback mark, used only when fastfetch is unavailable.
MARK = [
    "   ▄▄▄▄▄",
    " ▄██▀▀▀",
    "▄██",
    "███",
    "███",
    "▀██▄",
    " ▀██▄▄▄",
    "   ▀▀▀▀▀",
]


def ramp(palette: dict) -> list[tuple[int, int, int]]:
    stops = [rgb(palette["primary"]), rgb(palette["secondary"]), rgb(palette["tertiary"])]
    out = []
    for start, end in zip(stops, stops[1:]):
        out.extend(mix(start, end, step / 4) for step in range(4))
    out.append(stops[-1])
    return out


class Panel:
    def __init__(self, palette: dict, width: int, mark: bool) -> None:
        self.p = palette
        self.c = Canvas(width)
        self.width = width
        self.mark = mark
        self.logo = distro_logo(palette) if mark else []

    def heading(self, row: int, col: int, label: str) -> None:
        """Section label: the accent colour and weight only. A filled block
        behind it reads as a halo on a translucent terminal."""
        self.c.text(row, col, label, fg=rgb(self.p["primary"]), bold=True)

    def draw(self, sections) -> None:
        """Lay the block out the way the rice it replaces did: one column of
        sections, the mark beside it, the whole thing centred instead of glued
        to the left edge."""
        p = self.p
        entries = [(title, rows) for title, rows in sections if rows]
        key_w = min(max((len(key) for _, rows in entries for key, _, _ in rows), default=6), 8)
        value_w = max((swidth(value) for _, rows in entries for _, value, _ in rows), default=12)
        label_w = max((swidth(title) for title, _ in entries), default=6)
        info_w = max(key_w + 2 + value_w, label_w) + 1

        logo_w = 0
        if self.logo:
            logo_w = max(swidth("".join(char for char, _ in row)) for row in self.logo)
        elif self.mark:
            logo_w = max(swidth(line) for line in MARK)
        gap = 3 if logo_w else 0
        if logo_w and logo_w + gap + info_w + 2 > self.width:
            logo_w = gap = 0        # no room for the mark beside the text
            self.logo = []

        content = logo_w + gap + info_w
        pad = max(1, min(6, (self.width - content - 1) // 2))
        info_col = pad + logo_w + gap

        top = 2
        # Header sits with the text column, not out on its own.
        self.c.put(top, info_col, "◆", fg=rgb(p["primary"]), bold=True)
        self.c.text(top, info_col + 2, "NYX DECK", fg=rgb(p["primary"]), bold=True)
        self.c.text(top, info_col + 11, f"· {t('自足的桌面', 'a self-contained desktop')}",
                    fg=rgb(p["on_surface_variant"]))

        body = top + 2
        if self.logo:
            # Top-aligned with the text, the way a fetch normally reads; centring
            # it left equal blanks above and below, which looked accidental.
            for index, row in enumerate(self.logo):
                for column, (char, colour) in enumerate(row):
                    if char != " ":
                        self.c.put(body + index, pad + column, char,
                                   fg=colour or rgb(p["primary"]))
        elif self.mark:
            colours = ramp(p)
            for index, line in enumerate(MARK):
                self.c.text(body + index, pad, line.rstrip(), fg=colours[min(index, len(colours) - 1)])

        value_col = info_col + key_w + 2
        row = body
        for title, rows in entries:
            self.heading(row, info_col, title)
            row += 1
            for key, value, style in rows:
                self.c.text(row, info_col, pad_left(key, key_w), fg=rgb(p["on_surface_variant"]))
                colour = {
                    "accent": rgb(p["tertiary"]),
                    "muted": rgb(p["on_surface_variant"]),
                }.get(style, rgb(p["on_surface"]))
                while swidth(value) > info_w - (value_col - info_col) - 1 and value:
                    value = value[:-1]
                self.c.text(row, value_col, value, fg=colour)
                row += 1
            row += 1

# ── native fastfetch fallback ────────────────────────────────────────────────


def native_config(palette: dict) -> str:
    def fg(role: str) -> str:
        return "38;2;%d;%d;%d" % rgb(palette[role])

    return json.dumps(
        {
            "logo": {
                "type": "small",
                "color": {str(k): fg(v) for k, v in LOGO_ROLES.items()},
                "padding": {"top": 1, "left": 2, "right": 4},
            },
            "display": {"separator": "  ", "color": {"keys": fg("on_surface_variant"), "title": fg("primary")}},
            "modules": [
                {"type": "custom", "format": ""},
                {"type": "custom", "format": f"{{#{fg('primary')}}}NYX DECK{{#}}"},
                {"type": "custom", "format": ""},
                {"type": "custom", "format": f"{{#{fg('primary')}}}system{{#}}"},
                {"type": "os", "key": "  os   ", "format": "{3} ({12})"},
                {"type": "kernel", "key": "  kern ", "format": "{2}"},
                {"type": "wm", "key": "  wm   ", "format": "{1} ({3})"},
                {"type": "custom", "format": ""},
                {"type": "custom", "format": f"{{#{fg('primary')}}}hardware{{#}}"},
                {"type": "cpu", "key": "  cpu  ", "format": "{1}"},
                {"type": "gpu", "key": "  gpu  ", "format": "{2}"},
                {"type": "display", "key": "  disp ", "format": "{width}x{height} @{refresh-rate}Hz"},
                {"type": "memory", "key": "  mem  ", "format": "{1} / {2} ({3})"},
                {"type": "disk", "key": "  disk ", "folders": "/", "format": "{1} / {2} ({3})"},
                {"type": "uptime", "key": "  up   ", "format": "{?days}{days}d {?}{hours}h {minutes}m"},
            ],
        },
        indent=4,
        ensure_ascii=False,
    )


def run_native(palette: dict, install: bool) -> int:
    exe = shutil.which("fastfetch")
    if not exe:
        print("fastfetch not found", file=sys.stderr)
        return 1
    if install:
        target = CONFIG_HOME / "fastfetch"
        target.mkdir(parents=True, exist_ok=True)
        existing = target / "config.jsonc"
        if existing.is_file():
            shutil.copy2(existing, existing.with_suffix(f".jsonc.bak.{time.strftime('%Y%m%d_%H%M%S')}"))
        (target / "config.jsonc").write_text(native_config(palette, target) + "\n", encoding="utf-8")
        print(f"wrote {target / 'config.jsonc'}")
        return 0
    scratch = Path("/tmp") / f"nyxdeck-fetch-{os.getpid()}"
    try:
        config = scratch / "config.jsonc"
        scratch.mkdir(parents=True, exist_ok=True)
        config.write_text(native_config(palette, scratch), encoding="utf-8")
        return subprocess.run([exe, "-c", str(config)]).returncode
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="nyxdeck fetch",
                                     description="terminal welcome panel")
    parser.add_argument("--compact", action="store_true", help="no mark")
    parser.add_argument("--no-logo", action="store_true", help="same as --compact")
    parser.add_argument("--native", action="store_true", help="render with fastfetch instead")
    parser.add_argument("--install", action="store_true", help="write the fastfetch config")
    parser.add_argument("--width", type=int, default=0, help="override the column count")
    args = parser.parse_args()

    palette = load_palette()
    if args.native or args.install:
        return run_native(palette, args.install)

    width = max(args.width or min(shutil.get_terminal_size((90, 24)).columns, 84), 40)
    mark = not (args.compact or args.no_logo) and width >= 64
    panel = Panel(palette, width, mark)
    panel.draw(collect())
    sys.stdout.write(panel.c.render() + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # a shell greeting must never break the shell
        sys.exit(0)
