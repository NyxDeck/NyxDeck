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
DMS_COLORS = CACHE_HOME / "DankMaterialShell" / "dms-colors.json"
TAGLINE_FILE = CONFIG_HOME / "nyxdeck" / "tagline"
LOGO_FILE = CONFIG_HOME / "nyxdeck" / "logo"

RESET = "\033[0m"

# Terminal output is English; NYXDECK_LANG=zh opts into Chinese.
_LANG = os.environ.get("NYXDECK_LANG", "en").lower()[:2]


def t(zh: str, en: str) -> str:
    return zh if _LANG == "zh" else en


def tagline() -> str:
    """The header's tagline. `nyxdeck tagline` writes the file; a missing file
    means the built-in default and an empty file hides the tagline entirely."""
    try:
        return TAGLINE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return t("自足的桌面", "a self-contained desktop")


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
    return sum(2 if unicodedata.category(c) != "Co" and unicodedata.east_asian_width(c) in ("W", "F")
               else 1 for c in string)


def elide(string: str, width: int) -> str:
    if swidth(string) <= width:
        return string
    while string and swidth(string) > width - 1:
        string = string[:-1]
    return string + "…" if width > 0 else ""


# ── the mark ─────────────────────────────────────────────────────────────────
# fastfetch ships hand-drawn per-distribution ASCII art and picks it from
# /etc/os-release. We use that art — it looks as deliberate as the distro's own —
# and colour it from the DMS palette
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


def known_logos() -> list[str]:
    """Names fastfetch accepts for --logo (its built-in set)."""
    exe = shutil.which("fastfetch")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--list-logos"], capture_output=True,
                             text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({name.strip() for name in re.findall(r'"([^"]+)"', out)})


def print_logo_list(filter_text: str = "") -> int:
    names = known_logos()
    if filter_text:
        needle = filter_text.lower()
        names = [n for n in names if needle in n.lower()]
    if not names:
        print(f"no logo matches {filter_text!r}" if filter_text else "no logos found")
        return 1
    width = max(len(n) for n in names) + 2
    per_row = max(1, 78 // width)
    for index in range(0, len(names), per_row):
        print("".join(n.ljust(width) for n in names[index:index + per_row]).rstrip())
    print(f"\n{len(names)} logos")
    return 0


def logo_spec() -> dict:
    """What fastfetch should draw for us.

    Default is the distribution's own logo, auto-detected from /etc/os-release —
    CachyOS resolves to its own art, but since it *is* Arch underneath, swapping
    in another built-in (`arch_small`, say) or an ASCII file of your own is one
    `nyxdeck logo` away.
    """
    try:
        value = LOGO_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if not value or value == "default":
        return {"type": "small"}
    path = Path(value).expanduser()
    if path.is_file():
        return {"type": "file", "source": str(path)}
    return {"type": "builtin", "source": value}


def spec_for(name: str) -> dict:
    """Resolve a name/path the way logo_spec() would, for --logo-preview."""
    if not name:
        return logo_spec()
    if name == "default":
        return {"type": "small"}
    path = Path(name).expanduser()
    if path.is_file():
        return {"type": "file", "source": str(path)}
    return {"type": "builtin", "source": name}


def fetch_logo(spec: dict, palette: dict) -> list[list[tuple[str, tuple | None]]]:
    """Render a fastfetch logo in our palette and return its cells."""
    exe = shutil.which("fastfetch")
    if not exe:
        return []
    config = {
        "logo": {
            **spec,
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


def distro_logo(palette: dict) -> list[list[tuple[str, tuple | None]]]:
    return fetch_logo(logo_spec(), palette)


def preview_header(text: str) -> int:
    """One header line with `text` as the tagline — the tagline picker's preview."""
    palette = load_palette()
    canvas = Canvas(min(shutil.get_terminal_size((84, 24)).columns, 84))
    draw_header(canvas, palette, 0, 0, canvas.width, text)
    sys.stdout.write(canvas.render() + "\n")
    return 0


def preview_logo(name: str) -> int:
    """`nyxdeck logo preview`: draw one logo on its own."""
    palette = load_palette()
    if name and name != "default" and not Path(name).expanduser().is_file():
        names = known_logos()
        if names and name not in names:
            near = [n for n in names if name.lower() in n.lower()][:5]
            print(f"unknown logo {name!r}" + (f"; try: {', '.join(near)}" if near else ""),
                  file=sys.stderr)
            return 1
    rows = fetch_logo(spec_for(name), palette)
    if not rows:
        print("fastfetch could not render that logo", file=sys.stderr)
        return 1
    canvas = Canvas(max(swidth("".join(c for c, _ in row)) for row in rows))
    for y, row in enumerate(rows):
        for x, (char, colour) in enumerate(row):
            if char != " ":
                canvas.put(y, x, char, fg=colour or rgb(palette["primary"]))
    sys.stdout.write(canvas.render() + "\n")
    return 0


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
        if swidth(char) == 2 and col + 1 < self.width:
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
                    codes = ["0", "1"] if bold else ["0"]
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

STRUCTURE = "OS:Kernel:Packages:WM:Theme:Icons:Cursor:Font:Host:CPU:GPU:Display:Memory:Disk:Battery:Uptime"


def fastfetch_data() -> dict:
    exe = shutil.which("fastfetch")
    if not exe:
        return {}
    try:
        raw = subprocess.run(
            [exe, "--config", "none", "--format", "json", "--logo", "none", "--structure", STRUCTURE],
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


def collect() -> list[tuple[str, list[tuple[str, str, str]]]]:
    data = fastfetch_data()
    terminal, shell = detect_running()

    system: list[tuple[str, str, str]] = []
    osinfo = data.get("OS") or {}
    pretty = osinfo.get("prettyName") or osinfo.get("name") or os_pretty_name()
    system.append(("os", f"{pretty} {osinfo.get('architecture') or os.uname().machine}", "value"))
    if (data.get("Kernel") or {}).get("release"):
        system.append(("kern", f"{data['Kernel'].get('name') or 'Linux'} {data['Kernel']['release']}", "value"))
    packages = data.get("Packages") or {}
    counts = [f"{count} ({name})" for name, count in packages.items()
              if name != "all" and isinstance(count, int) and count > 0]
    if counts:
        system.append(("pkg", ", ".join(counts), "value"))
    system.append(("sh", shell, "value"))

    desktop: list[tuple[str, str, str]] = []
    wm = data.get("WM") or {}
    if wm.get("prettyName"):
        protocol = wm.get("protocolName")
        name = " ".join(filter(None, (wm["prettyName"], wm.get("version"))))
        desktop.append(("wm", f"{name}{f' ({protocol})' if protocol else ''}", "value"))
    else:
        desktop.append(("wm", "NyxDeck", "value"))
    for module, key, fields in (
        ("Theme", "theme", ("theme1", "theme2")),
        ("Icons", "icons", ("icons1", "icons2")),
        ("Cursor", "cursor", ("theme",)),
        ("Font", "font", ("display",)),
    ):
        result = data.get(module) or {}
        value = ", ".join(result[field] for field in fields if result.get(field))
        if key == "cursor" and result.get("size"):
            value += f" ({result['size']}px)"
        if value:
            desktop.append((key, value, "value"))
    desktop.append(("term", terminal, "value"))

    hardware: list[tuple[str, str, str]] = []
    host = data.get("Host") or {}
    host_name = host.get("name") or os.uname().nodename
    if host.get("version"):
        host_name += f" ({host['version']})"
    hardware.append(("host", host_name, "value"))
    for display in data.get("Display") or []:
        out = display.get("output") or {}
        if out.get("width"):
            hardware.append(("disp", f"{out['width']}×{out['height']} @ {round(out.get('refreshRate') or 0)}Hz", "value"))
    cpu = data.get("CPU") or {}
    if cpu.get("cpu"):
        cores = (cpu.get("cores") or {}).get("logical")
        frequency = (cpu.get("frequency") or {}).get("max")
        value = cpu["cpu"] + (f" ({cores})" if cores else "")
        if frequency:
            value += f" @ {frequency / 1000:.2f} GHz"
        hardware.append(("cpu", value, "value"))
    for gpu in data.get("GPU") or []:
        if gpu.get("name"):
            hardware.append(("gpu", gpu["name"], "value"))
    memory = data.get("Memory") or {}
    if memory.get("total"):
        used, total = memory.get("used", 0), memory["total"]
        hardware.append(("mem", f"{human_gib(used)} / {human_gib(total)} ({round(used / total * 100)}%)", "accent"))
    disks = data.get("Disk") or []
    disks = sorted(disks, key=lambda disk: disk.get("mountpoint") != "/")
    for disk in disks:
        sizes = disk.get("bytes") or {}
        if sizes.get("total") and (disk.get("mountpoint") == "/" or not any(k == "disk" for k, _, _ in hardware)):
            used = sizes.get("used")
            if used is None:
                if sizes.get("free") is None:
                    continue
                used = sizes["total"] - sizes["free"]
            filesystem = f" - {disk['filesystem']}" if disk.get("filesystem") else ""
            hardware.append(("disk", f"{human_gib(used)} / {human_gib(sizes['total'])} ({round(used / sizes['total'] * 100)}%){filesystem}", "value"))
            break
    for battery in data.get("Battery") or []:
        if battery.get("capacity") is not None:
            status = f" [{battery['status']}]" if battery.get("status") else ""
            hardware.append(("bat", f"{battery['capacity']:g}%{status}", "accent"))
    if (data.get("Uptime") or {}).get("uptime") is not None:
        hardware.append(("up", human_duration(data["Uptime"]["uptime"]), "value"))

    return [
        (t("发行版", "Distro"), system),
        ("DE/WM", desktop),
        (t("设备", "System"), hardware),
    ]


# ── drawing ──────────────────────────────────────────────────────────────────

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


ICONS = {
    "os": "", "kern": "", "pkg": "󰏖", "sh": "", "wm": "",
    "theme": "󰉼", "icons": "", "cursor": "󰇀", "font": "", "term": "",
    "host": "", "disp": "󰍹", "cpu": "", "gpu": "󰢮", "mem": "",
    "disk": "󰋊", "bat": "󰁹", "up": "󰔟",
}


def draw_header(canvas: Canvas, palette: dict, row: int, col: int, width: int, slogan: str) -> None:
    title = elide(f"NyxDeck · {os_pretty_name()}", width)
    split = min(len("NyxDeck"), len(title))
    end = canvas.text(row, col, title[:split], fg=rgb(palette["tertiary"]), bold=True)
    canvas.text(row, end, title[split:], fg=rgb(palette["primary"]), bold=True)
    canvas.text(row + 1, col, "─" * swidth(title), fg=rgb(palette["on_surface_variant"]))
    room = width - swidth(title) - 3
    if slogan and room >= 12:
        canvas.text(row, col + swidth(title) + 3, elide(slogan, room),
                    fg=rgb(palette["on_surface_variant"]))


class Panel:
    def __init__(self, palette: dict, width: int, mark: bool) -> None:
        self.p = palette
        self.c = Canvas(width)
        self.width = width
        self.mark = mark
        self.logo = distro_logo(palette) if mark else []

    def mark_rows(self) -> list:
        if self.logo:
            return self.logo
        if not self.mark:
            return []
        colours = ramp(self.p)
        return [[(char, colours[min(index, len(colours) - 1)]) for char in line.rstrip()]
                for index, line in enumerate(MARK)]

    def draw(self, sections) -> None:
        p = self.p
        entries = [(title, rows) for title, rows in sections if rows]
        value_w = max((swidth(value) for _, rows in entries for _, value, _ in rows), default=12)
        key_w = max((swidth(title) for title, _ in entries), default=6) + 3
        value_offset = key_w + 3
        info_w = max(value_offset + value_w + 1, 40)
        rows = self.mark_rows()
        logo_w = max((swidth("".join(char for char, _ in row)) for row in rows), default=0)
        gap = 3 if logo_w else 0
        stacked = False
        if logo_w:
            room = self.width - logo_w - gap - 2
            if room < info_w:
                if room >= 26:
                    info_w = room
                elif logo_w + 2 <= self.width:
                    stacked = True
                    gap = 0
                else:
                    rows, logo_w, gap = [], 0, 0
        info_w = min(info_w, self.width - 2)
        content = info_w if stacked else logo_w + gap + info_w
        pad = max(1, min(6, (self.width - content - 1) // 2))
        info_col = pad if stacked else pad + logo_w + gap
        top, body = 2, 5
        if stacked:
            for index, logo_row in enumerate(rows):
                offset = pad + max(0, (info_w - swidth("".join(c for c, _ in logo_row))) // 2)
                column = offset
                for char, colour in logo_row:
                    column = self.c.put(top + index, column, char, fg=colour or rgb(p["primary"]))
            top += len(rows) + 1
            body = top + 3
        elif rows:
            for index, logo_row in enumerate(rows):
                column = pad
                for char, colour in logo_row:
                    column = self.c.put(body + index, column, char, fg=colour or rgb(p["primary"]))

        draw_header(self.c, p, top, info_col, info_w, tagline())

        value_col = info_col + value_offset
        row = body
        for (title, section), role in zip(entries, ("tertiary", "secondary", "primary")):
            accent = rgb(p[role])
            for index, (key, value, _) in enumerate(section):
                if index == 0:
                    label = f"{ICONS.get(key, '•')}  {title}"
                else:
                    label = f"  {'└' if index == len(section) - 1 else '├'}─{ICONS.get(key, '•')}"
                self.c.text(row, info_col, label, fg=accent, bold=index == 0)
                self.c.text(row, info_col + key_w, " ↔ ", fg=rgb(p["on_surface_variant"]))
                self.c.text(row, value_col, elide(value, info_w - value_offset - 1),
                            fg=rgb(p["on_surface"]))
                row += 1
            row += 1
        swatches = [rgb(p.get(role, FALLBACK_PALETTE[role])) for role in (
            "surface_container_high", "error", "tertiary", "primary", "secondary",
            "on_surface_variant", "on_surface", "primary_container",
        )]
        swatch_w = min(5, max(1, (info_w - 2) // len(swatches)))
        swatch_col = info_col + max(0, (info_w - swatch_w * len(swatches)) // 2)
        for level in range(2):
            for index, colour in enumerate(swatches):
                colour = mix(colour, (255, 255, 255), 0.2) if level else colour
                self.c.text(row + level, swatch_col + index * swatch_w, " " * swatch_w, bg=colour)

# ── native fastfetch fallback ────────────────────────────────────────────────


def native_config(palette: dict) -> str:
    def fg(role: str) -> str:
        return "38;2;%d;%d;%d" % rgb(palette[role])

    terminal, shell = detect_running()
    title = f"NyxDeck · {os_pretty_name()}"
    return json.dumps(
        {
            "logo": {
                **logo_spec(),
                "color": {str(k): fg(v) for k, v in LOGO_ROLES.items()},
                "padding": {"top": 1, "left": 2, "right": 4},
            },
            "display": {"separator": " ↔ ", "key": {"width": 12},
                        "color": {"keys": fg("primary"), "title": fg("primary"), "output": fg("on_surface")}},
            "modules": [
                "break",
                {"type": "custom", "format": f"{{#{fg('primary')}}}{title}{{#}}"},
                {"type": "custom", "format": "─" * swidth(title)},
                "break",
                {"type": "os", "key": "  Distro", "keyColor": fg("tertiary")},
                {"type": "kernel", "key": "  ├─", "keyColor": fg("tertiary")},
                {"type": "packages", "key": "  ├─󰏖", "keyColor": fg("tertiary")},
                {"type": "custom", "key": "  └─", "keyColor": fg("tertiary"), "format": shell},
                "break",
                {"type": "wm", "key": "  DE/WM", "keyColor": fg("secondary")},
                {"type": "theme", "key": "  ├─󰉼", "keyColor": fg("secondary")},
                {"type": "icons", "key": "  ├─", "keyColor": fg("secondary")},
                {"type": "cursor", "key": "  ├─󰇀", "keyColor": fg("secondary")},
                {"type": "font", "key": "  ├─", "keyColor": fg("secondary")},
                {"type": "custom", "key": "  └─", "keyColor": fg("secondary"), "format": terminal},
                "break",
                {"type": "custom", "key": "  System", "format": os.uname().nodename},
                {"type": "display", "key": "  ├─󰍹"},
                {"type": "cpu", "key": "  ├─"},
                {"type": "gpu", "key": "  ├─󰢮"},
                {"type": "memory", "key": "  ├─"},
                {"type": "disk", "key": "  ├─󰋊", "folders": "/"},
                {"type": "battery", "key": "  ├─󰁹"},
                {"type": "uptime", "key": "  └─󰔟"},
                "break", {"type": "colors", "symbol": "block"},
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
        (target / "config.jsonc").write_text(native_config(palette) + "\n", encoding="utf-8")
        print(f"wrote {target / 'config.jsonc'}")
        return 0
    scratch = Path("/tmp") / f"nyxdeck-fetch-{os.getpid()}"
    try:
        config = scratch / "config.jsonc"
        scratch.mkdir(parents=True, exist_ok=True)
        config.write_text(native_config(palette), encoding="utf-8")
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
    parser.add_argument("--logo-preview", nargs="?", const="", default=None, metavar="NAME",
                        help="draw one logo (default: the configured one)")
    parser.add_argument("--logo-list", nargs="?", const="", default=None, metavar="FILTER",
                        help="list the built-in logo names")
    parser.add_argument("--header-preview", default=None, metavar="TEXT",
                        help="draw the header with TEXT as the tagline")
    args = parser.parse_args()

    if args.header_preview is not None:
        return preview_header(args.header_preview)
    if args.logo_list is not None:
        return print_logo_list(args.logo_list)
    if args.logo_preview is not None:
        return preview_logo(args.logo_preview)

    palette = load_palette()
    if args.native or args.install:
        return run_native(palette, args.install)

    width = max(args.width or min(shutil.get_terminal_size((90, 24)).columns, 140), 40)
    mark = not (args.compact or args.no_logo) and width >= 64
    panel = Panel(palette, width, mark)
    panel.draw(collect())
    sys.stdout.write(panel.c.render() + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a shell greeting must never break the shell,
        print(f"nyxdeck fetch: {exc}", file=sys.stderr)  # but never silently
        sys.exit(0)
