#!/usr/bin/env python3
"""PULSE // SYSTEM MONITOR — neon pixel-style process monitor for Arch Linux."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import ttk

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:  # Pillow optional: fallback to pixel-art logo
    PIL_AVAILABLE = False


# -----------------------------------------------------------------------------
# PULSE configuration
# -----------------------------------------------------------------------------

APP_TITLE = "PULSE // SYSTEM MONITOR"
REFRESH_MS = 2000

# XDG-compliant paths: work both from a git checkout and from /usr/bin
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "pulse"
JSON_PATH = CONFIG_DIR / "processes.json"

LOGO_CANDIDATES = (
    Path(__file__).resolve().with_name("pulse.png"),           # dev checkout
    Path("/usr/share/icons/hicolor/256x256/apps/pulse.png"),   # pacman install
    Path.home() / ".local" / "share" / "icons" / "pulse.png",  # user install
    Path.cwd() / "pulse.png",                                  # cwd fallback
)

BG = "#0b0f17"
PANEL = "#121a27"
PANEL_ALT = "#172233"
EDGE = "#29394d"
GRID = "#1b2939"
TEXT = "#dce8f5"
MUTED = "#8193a8"
CYAN = "#50e3c2"
BLUE = "#63a8ff"
PURPLE = "#b58cff"
YELLOW = "#ffd166"
RED = "#ff6b7a"


# -----------------------------------------------------------------------------
# Process collection and JSON layer
# -----------------------------------------------------------------------------

def find_logo_path() -> Path | None:
    """Return the first existing pulse.png candidate."""
    for candidate in LOGO_CANDIDATES:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def get_ps_output() -> str:
    result = subprocess.run(
        ["ps", "auxww"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def to_seconds(value: str) -> int:
    try:
        days = 0
        if "-" in value:
            day_text, value = value.split("-", 1)
            days = int(day_text)

        parts = value.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        else:
            return days * 86400 + int(float(value))

        return (
            days * 86400
            + int(hours) * 3600
            + int(minutes) * 60
            + int(float(seconds))
        )
    except (TypeError, ValueError):
        return 0


def ps_aux_to_records(raw: str) -> list[dict]:
    lines = raw.strip().splitlines()
    if len(lines) < 2:
        return []

    header = lines[0].split()
    fixed_columns = len(header) - 1
    records: list[dict] = []

    for line in lines[1:]:
        parts = line.split(None, fixed_columns)
        if len(parts) < fixed_columns + 1:
            continue

        source = dict(zip(header, parts))
        try:
            records.append({
                "user": source["USER"],
                "pid": int(source["PID"]),
                "cpu_pct": float(source["%CPU"]),
                "mem_pct": float(source["%MEM"]),
                "vsz_kb": int(source["VSZ"]),
                "rss_kb": int(source["RSS"]),
                "tty": source["TTY"],
                "stat": source["STAT"],
                "start": source["START"],
                "time_seconds": to_seconds(source["TIME"]),
                "command": source["COMMAND"],
            })
        except (KeyError, TypeError, ValueError):
            continue

    return records


def save_processes(records: list[dict], path: Path = JSON_PATH) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": len(records),
        "processes": records,
    }

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    temporary_path.replace(path)
    return data


def load_processes(path: str | Path = JSON_PATH) -> list[dict]:
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    return data["processes"] if isinstance(data, dict) else data


# -----------------------------------------------------------------------------
# Analysis layer
# -----------------------------------------------------------------------------

def top_consumers(processes: list[dict], key: str = "cpu_pct", top: int = 10) -> list[dict]:
    allowed_keys = {"cpu_pct", "mem_pct", "rss_kb", "vsz_kb", "time_seconds"}
    if key not in allowed_keys:
        raise ValueError(f"Unknown sort key: {key!r}")
    return sorted(processes, key=lambda process: process.get(key, 0), reverse=True)[:top]


def summarize(processes: list[dict], top: int = 10) -> dict:
    return {
        "total_processes": len(processes),
        "sum_cpu_pct": round(sum(p.get("cpu_pct", 0) for p in processes), 2),
        "sum_rss_mb": round(sum(p.get("rss_kb", 0) for p in processes) / 1024, 1),
        "top_by_cpu": top_consumers(processes, "cpu_pct", top),
        "top_by_memory": top_consumers(processes, "rss_kb", top),
    }


# -----------------------------------------------------------------------------
# Pixel-style Tkinter interface
# -----------------------------------------------------------------------------

class PulseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.geometry("1280x800")
        self.minsize(980, 680)

        self.font_name = self._choose_font()
        self.font = (self.font_name, 10)
        self.font_small = (self.font_name, 9)
        self.font_bold = (self.font_name, 11, "bold")
        self.font_title = (self.font_name, 19, "bold")

        self.current_processes: list[dict] = []
        self.refresh_count = 0
        self.data_queue: queue.Queue = queue.Queue()

        # Keep references so Tk images are not garbage-collected
        self.logo_image = None
        self.icon_images: list = []

        self._configure_styles()
        self._apply_window_icon()
        self._build_interface()

        self.after(100, self._poll_queue)
        self._start_collection()

    # -------------------------------------------------------------------------
    # Fonts & styles
    # -------------------------------------------------------------------------

    def _choose_font(self) -> str:
        available = set(tkfont.families(self))
        for candidate in ("Press Start 2P", "Pixel Operator", "Terminus", "Consolas"):
            if candidate in available:
                return candidate
        return str(self.tk.call("font", "actual", "TkFixedFont", "-family"))

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        # Notebook (navigation tabs)
        style.configure("Pulse.TNotebook", background=BG, borderwidth=0)
        style.configure(
            "Pulse.TNotebook.Tab",
            background=PANEL_ALT,
            foreground=MUTED,
            padding=[18, 12],
            font=self.font_bold,
            borderwidth=0,
            width=12,
        )
        style.map(
            "Pulse.TNotebook.Tab",
            background=[("selected", PANEL)],
            foreground=[("selected", CYAN)],
            expand=[("selected", [0, 0, 0, 4])],
        )

        # Treeview (process table)
        style.configure(
            "Pulse.Treeview",
            background=PANEL,
            foreground=TEXT,
            fieldbackground=PANEL,
            borderwidth=0,
            rowheight=28,
            font=self.font,
        )
        style.configure(
            "Pulse.Treeview.Heading",
            background=PANEL_ALT,
            foreground=CYAN,
            relief="flat",
            borderwidth=0,
            font=self.font_bold,
        )
        style.map(
            "Pulse.Treeview",
            background=[("selected", "#25465a")],
            foreground=[("selected", "#ffffff")],
        )

    # -------------------------------------------------------------------------
    # Logo handling
    # -------------------------------------------------------------------------

    def _apply_window_icon(self) -> None:
        """Set the window manager icon from pulse.png (all common sizes)."""
        logo_path = find_logo_path()
        if not (PIL_AVAILABLE and logo_path):
            return
        try:
            with Image.open(logo_path) as image:
                image = image.convert("RGBA")
                images = []
                for side in (16, 32, 48, 64, 128, 256):
                    copy = image.copy()
                    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
                    images.append(ImageTk.PhotoImage(copy))
            self.icon_images = images
            self.iconphoto(True, *images)
        except Exception:
            self.icon_images = []

    def _load_logo(self, parent: tk.Widget, size: tuple[int, int] = (56, 56)) -> tk.Widget:
        """Load pulse.png into the header; fall back to pixel-art canvas."""
        logo_path = find_logo_path()
        if PIL_AVAILABLE and logo_path:
            try:
                with Image.open(logo_path) as image:
                    image = image.convert("RGBA")
                    image.thumbnail(size, Image.Resampling.LANCZOS)
                    self.logo_image = ImageTk.PhotoImage(image)
                return tk.Label(parent, image=self.logo_image, bg=PANEL,
                                bd=0, highlightthickness=0)
            except Exception:
                pass
        return self._pixel_logo(parent)

    def _pixel_logo(self, parent: tk.Widget) -> tk.Canvas:
        logo = tk.Canvas(parent, width=38, height=38, bg=PANEL, highlightthickness=0)
        pixels = [
            (1, 0), (2, 0), (0, 1), (3, 1), (0, 2), (2, 2), (3, 2),
            (0, 3), (3, 3), (1, 4), (2, 4),
        ]
        for x, y in pixels:
            logo.create_rectangle(x * 7 + 2, y * 7 + 2, x * 7 + 7, y * 7 + 7,
                                  fill=CYAN, outline=CYAN)
        return logo

    # -------------------------------------------------------------------------
    # Interface construction
    # -------------------------------------------------------------------------

    def _build_interface(self) -> None:
        # --- Header ---
        header = tk.Frame(self, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        header.pack(fill="x", padx=18, pady=(18, 12))

        self._load_logo(header, size=(56, 56)).pack(side="left", padx=(14, 10), pady=8)

        title_box = tk.Frame(header, bg=PANEL)
        title_box.pack(side="left", pady=10)
        tk.Label(title_box, text="PULSE", bg=PANEL, fg=TEXT,
                 font=self.font_title).pack(anchor="w")
        tk.Label(title_box, text="PROCESS INTELLIGENCE  /  ARCH LINUX",
                 bg=PANEL, fg=MUTED, font=self.font_small).pack(anchor="w")

        self.status_label = tk.Label(
            header, text="■ INITIALIZING", bg=PANEL, fg=YELLOW, font=self.font_bold
        )
        self.status_label.pack(side="right", padx=(8, 18))

        refresh_button = tk.Button(
            header, text="[ REFRESH ]", command=self.refresh_now,
            bg=PANEL_ALT, fg=CYAN, activebackground=CYAN, activeforeground=BG,
            relief="flat", bd=0, padx=14, pady=9, font=self.font_bold, cursor="hand2",
        )
        refresh_button.pack(side="right", padx=8, pady=12)

        # --- Navigation (Notebook) ---
        self.notebook = ttk.Notebook(self, style="Pulse.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        self.tab_dashboard = tk.Frame(self.notebook, bg=BG)
        self.tab_processes = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_dashboard, text=" DASHBOARD ")
        self.notebook.add(self.tab_processes, text=" PROCESSES ")

        self._build_dashboard()
        self._build_processes_tab()

        # --- Footer ---
        self.footer_label = tk.Label(
            self, text=f"DATA FILE: {JSON_PATH}   |   AUTO REFRESH: {REFRESH_MS // 1000}s",
            bg=BG, fg=MUTED, font=self.font_small, anchor="w",
        )
        self.footer_label.pack(fill="x", padx=20, pady=(0, 10))

    def _build_dashboard(self) -> None:
        # Metric cards
        metrics = tk.Frame(self.tab_dashboard, bg=BG)
        metrics.pack(fill="x", padx=0, pady=(0, 12))
        for column in range(4):
            metrics.grid_columnconfigure(column, weight=1, uniform="metric")

        self.metric_values: dict[str, tk.Label] = {}
        metric_specs = [
            ("PROCESSES", "—", CYAN, "◆"),
            ("CPU TOTAL", "—", BLUE, "▲"),
            ("RAM / RSS", "—", PURPLE, "●"),
            ("LAST UPDATE", "—", YELLOW, "◷"),
        ]

        for column, (label, initial, accent, icon) in enumerate(metric_specs):
            card = tk.Frame(metrics, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
            card.grid(row=0, column=column, sticky="nsew",
                      padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
            tk.Frame(card, bg=accent, height=4).pack(fill="x")
            tk.Label(card, text=f"{icon}  {label}", bg=PANEL, fg=MUTED,
                     font=self.font_small).pack(anchor="w", padx=14, pady=(12, 3))
            value = tk.Label(card, text=initial, bg=PANEL, fg=TEXT,
                             font=(self.font_name, 17, "bold"))
            value.pack(anchor="w", padx=14, pady=(0, 13))
            self.metric_values[label] = value

        # Charts
        charts = tk.Frame(self.tab_dashboard, bg=BG)
        charts.pack(fill="both", expand=True, padx=0, pady=0)
        charts.grid_columnconfigure(0, weight=1, uniform="chart")
        charts.grid_columnconfigure(1, weight=1, uniform="chart")
        charts.grid_rowconfigure(0, weight=1)

        cpu_panel = self._make_panel(charts, "CPU HOTSPOTS", CYAN)
        cpu_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        mem_panel = self._make_panel(charts, "MEMORY HOTSPOTS", PURPLE)
        mem_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.cpu_canvas = tk.Canvas(cpu_panel, height=260, bg=PANEL,
                                    highlightthickness=0, bd=0)
        self.cpu_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.mem_canvas = tk.Canvas(mem_panel, height=260, bg=PANEL,
                                    highlightthickness=0, bd=0)
        self.mem_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.cpu_canvas.bind("<Configure>", lambda _e: self._draw_charts())
        self.mem_canvas.bind("<Configure>", lambda _e: self._draw_charts())

    def _build_processes_tab(self) -> None:
        table_panel = self._make_panel(
            self.tab_processes, "LIVE PROCESS LIST  /  SORTED BY CPU", BLUE
        )
        table_panel.pack(fill="both", expand=True, padx=0, pady=0)

        table_frame = tk.Frame(table_panel, bg=PANEL)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        columns = ("pid", "user", "cpu", "mem", "rss", "stat", "command")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Pulse.Treeview", height=20,
        )

        headings = {
            "pid": ("PID", 80, "center"),
            "user": ("USER", 110, "w"),
            "cpu": ("CPU %", 90, "e"),
            "mem": ("MEM %", 90, "e"),
            "rss": ("RSS MB", 100, "e"),
            "stat": ("STATE", 80, "center"),
            "command": ("COMMAND", 600, "w"),
        }
        for column, (heading, width, anchor) in headings.items():
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, minwidth=60, anchor=anchor,
                             stretch=(column == "command"))

        # Zebra striping
        self.tree.tag_configure("oddrow", background=PANEL_ALT, foreground=TEXT)
        self.tree.tag_configure("evenrow", background=PANEL, foreground=TEXT)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _make_panel(self, parent: tk.Widget, title: str, accent: str) -> tk.Frame:
        panel = tk.Frame(parent, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        heading = tk.Frame(panel, bg=PANEL)
        heading.pack(fill="x", padx=12, pady=(10, 8))
        tk.Label(heading, text="■", bg=PANEL, fg=accent,
                 font=self.font_bold).pack(side="left", padx=(0, 8))
        tk.Label(heading, text=title, bg=PANEL, fg=TEXT,
                 font=self.font_bold).pack(side="left")
        return panel

    # -------------------------------------------------------------------------
    # Charts & table rendering
    # -------------------------------------------------------------------------

    def _draw_pixel_chart(self, canvas: tk.Canvas, processes: list[dict], key: str,
                          accent: str, suffix: str, use_mb: bool = False) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 200)

        # Blueprint grid
        for x in range(0, width, 20):
            canvas.create_line(x, 0, x, height, fill=GRID, width=1, dash=(2, 4))
        for y in range(0, height, 20):
            canvas.create_line(0, y, width, y, fill=GRID, width=1, dash=(2, 4))

        rows = top_consumers(processes, key, 6)
        if not rows:
            canvas.create_text(width // 2, height // 2, text="NO PROCESS DATA",
                               fill=MUTED, font=self.font_bold)
            return

        values = [float(row.get(key, 0) or 0) for row in rows]
        maximum = max(values) if max(values) > 0 else 1.0

        left, right, top, bottom = 160, 80, 30, 20
        available_w = width - left - right
        available_h = height - top - bottom

        bar_height = 22
        num_rows = len(rows)
        row_gap = max(12, (available_h - (num_rows * bar_height)) / (num_rows + 1))

        # Scale markers
        for pct in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = left + int(pct * available_w)
            canvas.create_line(x, top - 5, x, height - bottom + 5, fill=EDGE, dash=(2, 4))
            val = pct * maximum
            display_val = val / 1024 if use_mb else val
            label = f"{display_val:.0f}{suffix}" if pct > 0 else "0"
            canvas.create_text(x, top - 12, text=label, fill=MUTED, font=self.font_small)

        block_w, block_gap = 8, 2
        step = block_w + block_gap
        num_blocks = max(1, available_w // step)

        for index, row in enumerate(rows):
            y = top + row_gap + index * (bar_height + row_gap)

            command = str(row.get("command", "?"))
            cmd_name = command.split()[0].split("/")[-1] if command.split() else "?"
            if len(cmd_name) > 20:
                cmd_name = "…" + cmd_name[-19:]

            canvas.create_text(left - 12, y + bar_height // 2, text=cmd_name,
                               anchor="e", fill=TEXT, font=self.font_small)

            value = float(row.get(key, 0) or 0)
            filled_blocks = int(round((value / maximum) * num_blocks))

            for b in range(num_blocks):
                x1 = left + b * step
                color = accent if b < filled_blocks else PANEL_ALT
                outline = accent if b < filled_blocks else EDGE
                canvas.create_rectangle(x1, y, x1 + block_w, y + bar_height,
                                        fill=color, outline=outline, width=1)

            display_value = value / 1024 if use_mb else value
            canvas.create_text(width - 10, y + bar_height // 2,
                               text=f"{display_value:.1f}{suffix}",
                               anchor="e", fill=accent, font=(self.font_name, 11, "bold"))

    def _draw_charts(self) -> None:
        if not hasattr(self, "cpu_canvas"):
            return
        self._draw_pixel_chart(self.cpu_canvas, self.current_processes, "cpu_pct", CYAN, "%")
        self._draw_pixel_chart(self.mem_canvas, self.current_processes, "rss_kb",
                               PURPLE, " MB", use_mb=True)

    def _update_table(self, processes: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, process in enumerate(top_consumers(processes, "cpu_pct", 150)):
            rss_mb = process.get("rss_kb", 0) / 1024
            tag = "oddrow" if i % 2 else "evenrow"
            self.tree.insert("", "end", values=(
                process.get("pid", ""),
                process.get("user", ""),
                f"{process.get('cpu_pct', 0):.1f}",
                f"{process.get('mem_pct', 0):.1f}",
                f"{rss_mb:.1f}",
                process.get("stat", ""),
                process.get("command", ""),
            ), tags=(tag,))

    # -------------------------------------------------------------------------
    # Threading & refresh loop
    # -------------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                if isinstance(data, Exception):
                    self._handle_error(data)
                else:
                    self._process_data(data)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _start_collection(self) -> None:
        self.status_label.configure(text="■ SCANNING...", fg=YELLOW)
        threading.Thread(target=self._collect_data, daemon=True).start()

    def _collect_data(self) -> None:
        try:
            raw_output = get_ps_output()
            records = ps_aux_to_records(raw_output)
            save_processes(records)
            self.data_queue.put(records)
        except Exception as error:  # noqa: BLE001 - forwarded to the UI thread
            self.data_queue.put(error)

    def _process_data(self, records: list[dict]) -> None:
        self.current_processes = records
        result = summarize(records, top=6)

        self.metric_values["PROCESSES"].configure(text=f"{result['total_processes']:,}")
        self.metric_values["CPU TOTAL"].configure(text=f"{result['sum_cpu_pct']:.1f}%")
        self.metric_values["RAM / RSS"].configure(text=f"{result['sum_rss_mb']:.0f} MB")
        self.metric_values["LAST UPDATE"].configure(text=datetime.now().strftime("%H:%M:%S"))

        self._update_table(records)
        self._draw_charts()

        self.status_label.configure(text="■ LIVE", fg=CYAN)
        self.footer_label.configure(
            text=f"DATA FILE: {JSON_PATH}   |   AUTO REFRESH: {REFRESH_MS // 1000}s"
                 f"   |   SNAPSHOT: #{self.refresh_count + 1}"
        )
        self.refresh_count += 1

        self.after(REFRESH_MS, self._start_collection)

    def _handle_error(self, error: Exception) -> None:
        self.status_label.configure(text="■ SYSTEM ERROR", fg=RED)
        self.footer_label.configure(text=f"ERROR: {error}")
        self.after(REFRESH_MS, self._start_collection)

    def refresh_now(self) -> None:
        self._start_collection()


def main() -> None:
    app = PulseApp()
    app.mainloop()


if __name__ == "__main__":
    main()