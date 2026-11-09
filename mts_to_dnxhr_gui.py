"""Desktop window for converting AVCHD clips to DNxHR.

The encode path is ``mts_to_dnxhr``. This module only collects files, checks
the export folder, and draws progress. A windowed PyInstaller build has no
console, so stdout and stderr are pointed at the null device before tqdm is
imported.
"""

from __future__ import annotations

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import ctypes
import dataclasses
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

import mts_to_dnxhr as core

try:
    import tkinterdnd2
    from tkinterdnd2 import DND_FILES

    DND_AVAILABLE = True
except ImportError:
    tkinterdnd2 = None
    DND_FILES = None
    DND_AVAILABLE = False

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# README: a 168 s HQX encode is about 4.7 GB, roughly 14× a 335 MB source.
SIZE_RATIO = 14

_DROP_BG = "#ededed"
_DROP_HOT = "#d6e8ff"
_DROP_PAUSED_BG = "#d0d0d0"
_DROP_PAUSED = "Converting… drops are paused"
_IDLE_STATUS = "Add clips, choose an export folder, then click Convert."


def format_elapsed(seconds: float) -> str:
    """Format a duration for the status line (``M:SS`` or ``H:MM:SS``)."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "{0}:{1:02d}:{2:02d}".format(hours, minutes, secs)
    return "{0}:{1:02d}".format(minutes, secs)


def running_prefix(
    count: int,
    active: Sequence[tuple[int, str, Optional[int]]],
) -> str:
    """Status-line prefix for the clips encoding right now."""
    if not active:
        return "Converting…"
    if len(active) == 1:
        index, name, pct = active[0]
        if pct is None:
            return "Converting {0} of {1}: {2}…".format(index + 1, count, name)
        return "Converting {0} of {1}: {2} ({3}%)".format(index + 1, count, name, pct)
    ids = ", ".join(str(index + 1) for index in sorted(item[0] for item in active))
    return "Converting {0} at once ({1} of {2})".format(len(active), ids, count)


_FFMPEG_MISSING = (
    "FFmpeg was not found. Install it with `winget install Gyan.FFmpeg` "
    "(then sign out and back in), or put ffmpeg.exe and ffprobe.exe next to this program."
)
_DROP_TEXT = "Drop .MTS / .M2TS files or folders here"
_DROP_TEXT_NO_DND = "Drag-and-drop unavailable. Use Add files… or Add folder…"


def _profile_label(profile: str) -> str:
    prefix = "dnxhr_"
    if profile.startswith(prefix):
        return "DNxHR " + profile[len(prefix) :].upper()
    return profile


def _parser_defaults() -> core.Options:
    args = core.build_parser().parse_args(["_"])
    return core.Options(
        profile=args.profile,
        container=args.container,
        audio_bit_depth=args.audio_bit_depth,
        deinterlace=False,
        overwrite=False,
        duration=None,
    )


DEFAULT_OPTIONS: core.Options = _parser_defaults()
OUTPUT_SUMMARY = (
    f"{_profile_label(DEFAULT_OPTIONS.profile)} · {DEFAULT_OPTIONS.container.upper()} · "
    f"PCM {DEFAULT_OPTIONS.audio_bit_depth}-bit 48 kHz · source size/fps"
)


def options_for(deinterlace: bool) -> core.Options:
    return dataclasses.replace(DEFAULT_OPTIONS, deinterlace=deinterlace)


@dataclasses.dataclass(frozen=True)
class ClipItem:
    src: Path
    root: Path


def _item_key(src: Path) -> str:
    return os.path.normcase(str(src))


def collect_items(
    paths: Iterable[Path],
    existing: Sequence[ClipItem],
) -> tuple[list[ClipItem], int]:
    """Return new clips and how many dropped entries were ignored.

    Folders are scanned recursively. Folder sidecars are counted only through
    ``discover_inputs``'s skipped total. Paths are deduped case-insensitively
    on Windows via ``os.path.normcase``.
    """
    seen = {_item_key(item.src) for item in existing}
    new_items: list[ClipItem] = []
    ignored = 0
    for raw in paths:
        try:
            path = Path(raw)
            if path.is_file():
                if not core.is_input_file(path):
                    ignored += 1
                    continue
                src = path.absolute()
                key = _item_key(src)
                if key in seen:
                    continue
                seen.add(key)
                new_items.append(ClipItem(src=src, root=src))
                continue
            if path.is_dir():
                clips, skipped = core.discover_inputs(path, recursive=True)
                ignored += skipped
                root = path.absolute()
                for src in clips:
                    key = _item_key(src)
                    if key in seen:
                        continue
                    seen.add(key)
                    new_items.append(ClipItem(src=src, root=root))
                continue
            ignored += 1
        except (ValueError, OSError):
            ignored += 1
    return new_items, ignored


def plan_outputs(
    items: Sequence[ClipItem],
    out_dir: Path,
    container: str,
) -> tuple[list[tuple[Path, Path]], dict[Path, list[Path]]]:
    pairs = [
        (item.src, core.output_path_for(item.src, item.root, out_dir, container))
        for item in items
    ]
    return pairs, core.find_collisions(pairs)


def estimate_needed_bytes(pairs: Sequence[tuple[Path, Path]]) -> int:
    """Sum ``source size × 14`` for outputs that do not exist yet."""
    total = 0
    for src, dst in pairs:
        if dst.exists():
            continue
        try:
            total += src.stat().st_size * SIZE_RATIO
        except OSError:
            continue
    return total


def free_bytes(out_dir: Path) -> Optional[int]:
    """Free bytes on the export drive, or ``None`` if that cannot be read."""
    current = out_dir
    try:
        while not current.exists():
            parent = current.parent
            if parent == current:
                return None
            current = parent
        return shutil.disk_usage(current).free
    except OSError:
        return None


def resource_path(rel: str) -> Path:
    """Locate a bundled read-only file, in the PyInstaller unpack dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parent / rel


ICON_PATH = resource_path("assets/app.ico")


def locate_tools() -> tuple[Optional[str], Optional[str]]:
    """Find ffmpeg and ffprobe beside the exe (or this file), then on PATH.

    Both must be found. A windowed build looks next to ``sys.executable``,
    not in the onefile unpack directory.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    ffmpeg = base / "ffmpeg.exe"
    ffprobe = base / "ffprobe.exe"
    if ffmpeg.is_file() and ffprobe.is_file():
        return str(ffmpeg), str(ffprobe)
    ffmpeg_path = core.find_tool("ffmpeg")
    ffprobe_path = core.find_tool("ffprobe")
    if ffmpeg_path and ffprobe_path:
        return ffmpeg_path, ffprobe_path
    return None, None


def run_batch(
    pairs: Sequence[tuple[Path, Path]],
    opts: core.Options,
    ffmpeg: str,
    ffprobe: str,
    post: Callable[[tuple], None],
    cancel: threading.Event,
    jobs: int = 1,
) -> None:
    """Encode ``pairs`` and post progress events. Never exits without ``batch_finished``."""
    ok = 0
    skipped = 0
    failed = 0
    cancelled = 0
    tally = threading.Lock()

    def work(index: int) -> None:
        nonlocal ok, skipped, failed, cancelled
        src, dst = pairs[index]
        post(("file_started", index))
        last_bucket = -2

        def on_progress(
            seconds: float,
            total: Optional[float],
            file_index: int = index,
        ) -> None:
            nonlocal last_bucket
            if total is None or total <= 0:
                fraction: Optional[float] = None
                bucket = -1
            else:
                fraction = seconds / total
                if fraction < 0.0:
                    fraction = 0.0
                elif fraction > 1.0:
                    fraction = 1.0
                bucket = int(fraction * 100)
                if bucket > 100:
                    bucket = 100
            if bucket == last_bucket:
                return
            last_bucket = bucket
            post(("file_progress", file_index, fraction))

        try:
            status, err = core.convert_one(
                src,
                dst,
                opts,
                ffmpeg,
                ffprobe,
                log=lambda _line: None,
                on_progress=on_progress,
                cancel=cancel,
            )
        except core.ConversionCancelled:
            post(("file_finished", index, "cancelled", ""))
            with tally:
                cancelled += 1
            cancel.set()
            return
        except Exception as exc:
            post(("file_finished", index, "failed", str(exc)))
            with tally:
                failed += 1
            return
        if status not in ("ok", "skipped", "failed"):
            err = err or "unexpected status {0}".format(status)
            status = "failed"
        with tally:
            if status == "ok":
                ok += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
        post(("file_finished", index, status, err))

    try:
        unstarted = core.run_indexed(len(pairs), jobs, work, cancel)
        for index in unstarted:
            post(("file_finished", index, "cancelled", ""))
            cancelled += 1
    finally:
        post(("batch_finished", ok, skipped, failed, cancelled))


@dataclasses.dataclass
class _ActiveFile:
    t0: float
    pct: Optional[int]
    fraction: float


class App:
    """Single-window exporter. Widgets are touched only on the Tk thread."""

    def __init__(self, root: tk.Tk, dnd: Optional[bool] = None) -> None:
        self.root = root
        self.root.title("MTS to DNxHR")
        self.root.geometry("720x540")
        self.root.minsize(560, 440)
        if sys.platform == "win32":
            try:
                self.root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        self.dnd = DND_AVAILABLE if dnd is None else dnd
        self.items: list[ClipItem] = []
        self.errors: list[str] = []
        self.running = False
        self._quitting = False
        self._modal_open = False
        self._pending_finish: Optional[tuple] = None
        self.cancel = threading.Event()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.ffmpeg, self.ffprobe = locate_tools()
        self._finished_files = 0
        self._quit_deadline = 0.0
        self._batch_t0: Optional[float] = None
        self._active: dict[int, _ActiveFile] = {}
        self._batch_jobs = 1

        self._build()
        self._apply_tools_banner()
        self.status_var.set(_IDLE_STATUS)
        self._update_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_configure)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        self.drop = tk.Frame(outer, relief="groove", bd=2, bg=_DROP_BG)
        self.drop.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        # No fixed height: the frame sizes from label + button row so buttons
        # are never clipped at high DPI.
        self.drop_label = tk.Label(
            self.drop,
            text=_DROP_TEXT if self.dnd else _DROP_TEXT_NO_DND,
            bg=_DROP_BG,
        )
        self.drop_label.pack(pady=(8, 6))
        button_row = tk.Frame(self.drop, bg=_DROP_BG)
        button_row.pack()
        self._drop_fill = (self.drop, self.drop_label, button_row)
        self.add_files_btn = ttk.Button(button_row, text="Add files…", command=self.add_files)
        self.add_files_btn.pack(side="left", padx=4)
        self.add_folder_btn = ttk.Button(button_row, text="Add folder…", command=self.add_folder)
        self.add_folder_btn.pack(side="left", padx=4)
        self.drop.bind("<Button-1>", self._on_drop_zone_click)
        self.drop_label.bind("<Button-1>", self._on_drop_zone_click)
        self._register_drop(self.drop)
        self._register_drop(self.drop_label)
        self._register_drop(button_row)

        clips = ttk.Frame(outer)
        clips.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.count_var = tk.StringVar(value="Clips: 0")
        ttk.Label(clips, textvariable=self.count_var).pack(side="left")
        self.clear_btn = ttk.Button(clips, text="Clear", command=self.clear_all)
        self.clear_btn.pack(side="right")
        self.remove_btn = ttk.Button(clips, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(side="right", padx=(0, 6))

        tree_frame = ttk.Frame(outer)
        tree_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("file", "folder", "status"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("file", text="File")
        self.tree.heading("folder", text="Source folder")
        self.tree.heading("status", text="Status")
        self.tree.column("file", width=220, stretch=True)
        self.tree.column("folder", width=280, stretch=True)
        self.tree.column("status", width=180, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Delete>", self._on_delete_key)
        self.tree.bind("<Double-1>", self._on_double_click)
        self._register_drop(self.tree)

        export = ttk.Frame(outer)
        export.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        export.columnconfigure(1, weight=1)
        ttk.Label(export, text="Export to:").grid(row=0, column=0, padx=(0, 6))
        self.export_var = tk.StringVar()
        self.export_entry = ttk.Entry(export, textvariable=self.export_var)
        self.export_entry.grid(row=0, column=1, sticky="ew")
        self.browse_btn = ttk.Button(export, text="Browse…", command=self.browse_export)
        self.browse_btn.grid(row=0, column=2, padx=(6, 0))
        self.export_var.trace_add("write", self._on_export_changed)

        self.deinterlace_var = tk.BooleanVar(value=False)
        self.deinterlace_chk = ttk.Checkbutton(
            outer,
            text="Deinterlace interlaced (1080i) clips",
            variable=self.deinterlace_var,
        )
        self.deinterlace_chk.grid(row=4, column=0, sticky="w", pady=(0, 4))

        jobs_row = ttk.Frame(outer)
        jobs_row.grid(row=5, column=0, sticky="w", pady=(0, 4))
        ttk.Label(jobs_row, text="Parallel encodes:").pack(side="left")
        self.jobs_var = tk.IntVar(value=1)
        self.jobs_spin = ttk.Spinbox(
            jobs_row,
            from_=1,
            to=core.MAX_JOBS,
            width=3,
            textvariable=self.jobs_var,
            state="readonly",
        )
        self.jobs_spin.pack(side="left", padx=(6, 6))
        ttk.Label(
            jobs_row,
            text="(suggested max {0} for this PC)".format(core.suggested_jobs()),
            foreground="#666666",
        ).pack(side="left")

        self.summary = ttk.Label(
            outer,
            text="Output: {0}".format(OUTPUT_SUMMARY),
            foreground="#666666",
        )
        self.summary.grid(row=6, column=0, sticky="w", pady=(0, 4))

        self.banner = tk.Frame(outer)
        self.banner.grid(row=7, column=0, sticky="ew", pady=(0, 4))
        self.banner.columnconfigure(0, weight=1)
        self.banner_label = tk.Label(
            self.banner,
            text=_FFMPEG_MISSING,
            fg="red",
            justify="left",
            anchor="w",
            wraplength=640,
        )
        self.banner_label.grid(row=0, column=0, sticky="ew")
        self.check_btn = ttk.Button(self.banner, text="Check again", command=self.check_tools)
        self.check_btn.grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(outer, orient="horizontal").grid(
            row=8, column=0, sticky="ew", pady=8
        )
        self.status_var = tk.StringVar(value=_IDLE_STATUS)
        ttk.Label(outer, textvariable=self.status_var).grid(row=9, column=0, sticky="w")
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        actions = ttk.Frame(outer)
        actions.grid(row=11, column=0, sticky="ew", pady=(8, 0))
        self.convert_btn = ttk.Button(
            actions,
            text="Convert",
            command=self.on_convert,
            width=16,
        )
        self.convert_btn.pack(side="right", ipadx=18)

    def _register_drop(self, widget: tk.Widget) -> None:
        if not self.dnd or DND_FILES is None:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        except tk.TclError:
            pass

    def _set_drop_bg(self, color: str) -> None:
        for widget in self._drop_fill:
            widget.configure(bg=color)

    def _resting_drop_bg(self) -> str:
        return _DROP_PAUSED_BG if self.running else _DROP_BG

    def _apply_drop_chrome(self) -> None:
        self._set_drop_bg(self._resting_drop_bg())
        if self.running:
            self.drop_label.configure(text=_DROP_PAUSED)
        else:
            self.drop_label.configure(text=_DROP_TEXT if self.dnd else _DROP_TEXT_NO_DND)

    def _on_drop_enter(self, event: tk.Event) -> object:
        if not self.running and self._event_on_drop_zone(event):
            self._set_drop_bg(_DROP_HOT)
        return event.action

    def _on_drop_leave(self, event: tk.Event) -> object:
        self._set_drop_bg(self._resting_drop_bg())
        return event.action

    def _on_drop(self, event: tk.Event) -> object:
        self._set_drop_bg(self._resting_drop_bg())
        if not self.running:
            try:
                raw = self.root.tk.splitlist(event.data)
            except tk.TclError:
                raw = ()
            self._add_paths([Path(item) for item in raw])
        return event.action

    def _event_on_drop_zone(self, event: tk.Event) -> bool:
        widget = event.widget
        while widget is not None:
            if widget is self.drop:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _on_drop_zone_click(self, event: tk.Event) -> None:
        if self.running:
            return
        if event.widget in (self.add_files_btn, self.add_folder_btn):
            return
        self.add_files()

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is self.root:
            self.banner_label.configure(wraplength=max(240, event.width - 160))

    def _on_export_changed(self, *_args: object) -> None:
        if not self.running:
            self._update_buttons()

    def add_files(self) -> None:
        if self.running:
            return
        selected = filedialog.askopenfilenames(
            parent=self.root,
            filetypes=[("AVCHD clips", "*.mts *.m2ts"), ("All files", "*.*")],
        )
        if selected:
            self._add_paths([Path(item) for item in selected])

    def add_folder(self) -> None:
        if self.running:
            return
        selected = filedialog.askdirectory(parent=self.root)
        if selected:
            self._add_paths([Path(selected)])

    def _add_paths(self, paths: Sequence[Path]) -> None:
        if self.running:
            return
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            items, ignored = collect_items(paths, self.items)
        finally:
            self.root.configure(cursor="")
        if not items:
            message = "No .MTS/.M2TS files found in what you added."
            if ignored:
                message += " Ignored {0} other files.".format(ignored)
            self.status_var.set(message)
            return
        if not self.export_var.get().strip():
            self.export_var.set(str(core.default_output_dir(items[0].root)))
        for item in items:
            self.items.append(item)
            self.errors.append("")
            self.tree.insert(
                "",
                "end",
                values=(item.src.name, str(item.src.parent), "Waiting"),
            )
        self._update_count()
        message = "Added {0} clips.".format(len(items))
        if ignored:
            message += " Ignored {0} other files.".format(ignored)
        self.status_var.set(message)
        self._update_buttons()

    def _update_count(self) -> None:
        self.count_var.set("Clips: {0}".format(len(self.items)))

    def remove_selected(self) -> None:
        if self.running:
            return
        selected = set(self.tree.selection())
        if not selected:
            return
        children = list(self.tree.get_children())
        kept_items: list[ClipItem] = []
        kept_errors: list[str] = []
        for index, iid in enumerate(children):
            if iid in selected:
                self.tree.delete(iid)
            else:
                kept_items.append(self.items[index])
                kept_errors.append(self.errors[index])
        self.items = kept_items
        self.errors = kept_errors
        self._update_count()
        self._update_buttons()

    def clear_all(self) -> None:
        if self.running:
            return
        self.tree.delete(*self.tree.get_children())
        self.items = []
        self.errors = []
        self._update_count()
        self._update_buttons()

    def _on_delete_key(self, _event: tk.Event) -> str:
        if self.running:
            return "break"
        self.remove_selected()
        return "break"

    def _on_double_click(self, event: tk.Event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        children = list(self.tree.get_children())
        try:
            index = children.index(iid)
        except ValueError:
            return
        values = self.tree.item(iid, "values")
        if len(values) < 3 or not str(values[2]).startswith("Failed"):
            return
        detail = self.errors[index] if index < len(self.errors) else ""
        messagebox.showerror(
            "Conversion failed",
            "{0}\n\n{1}".format(self.items[index].src, detail),
            parent=self.root,
        )

    def browse_export(self) -> None:
        if self.running:
            return
        current = self.export_var.get().strip()
        initial = current
        if not initial and self.items:
            initial = str(self.items[0].src.parent)
        kwargs = {"parent": self.root}
        if initial:
            kwargs["initialdir"] = initial
        selected = filedialog.askdirectory(**kwargs)
        if selected:
            self.export_var.set(selected)

    def check_tools(self) -> None:
        self.ffmpeg, self.ffprobe = locate_tools()
        self._apply_tools_banner()
        self._update_buttons()

    def _apply_tools_banner(self) -> None:
        if self.ffmpeg and self.ffprobe:
            self.banner.grid_remove()
        else:
            self.banner.grid()

    def _tools_ready(self) -> bool:
        return bool(self.ffmpeg) and bool(self.ffprobe)

    def _update_buttons(self) -> None:
        if self.running:
            return
        busy = "normal"
        self.add_files_btn.configure(state=busy)
        self.add_folder_btn.configure(state=busy)
        self.remove_btn.configure(state=busy)
        self.clear_btn.configure(state=busy)
        self.browse_btn.configure(state=busy)
        self.export_entry.configure(state="normal")
        self.deinterlace_chk.configure(state="normal")
        self.jobs_spin.configure(state="readonly")
        ready = bool(self.items) and bool(self.export_var.get().strip()) and self._tools_ready()
        self.convert_btn.configure(text="Convert", state="normal" if ready else "disabled")

    def _set_running_ui(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.add_files_btn.configure(state=state)
        self.add_folder_btn.configure(state=state)
        self.remove_btn.configure(state=state)
        self.clear_btn.configure(state=state)
        self.browse_btn.configure(state=state)
        self.export_entry.configure(state=state)
        self.deinterlace_chk.configure(state=state)
        self.jobs_spin.configure(state="disabled" if running else "readonly")
        if running:
            self.convert_btn.configure(text="Stop", state="normal")
        else:
            self._update_buttons()
        self._apply_drop_chrome()

    def _set_status_cell(self, index: int, text: str) -> None:
        children = self.tree.get_children()
        if index < 0 or index >= len(children):
            return
        iid = children[index]
        values = list(self.tree.item(iid, "values"))
        if len(values) < 3:
            return
        values[2] = text
        self.tree.item(iid, values=values)

    def on_convert(self) -> None:
        if self.running:
            self._confirm_stop()
            return
        self._start_batch()

    def _start_batch(self) -> None:
        if not self.items or not self._tools_ready() or not self.ffmpeg or not self.ffprobe:
            return
        out_text = self.export_var.get().strip()
        out_dir = Path(out_text)
        if not out_dir.is_absolute():
            messagebox.showerror(
                "MTS to DNxHR",
                "Choose a full folder path for Export to (use Browse…).",
                parent=self.root,
            )
            return
        try:
            pairs, collisions = plan_outputs(
                self.items, out_dir, DEFAULT_OPTIONS.container
            )
        except ValueError as exc:
            messagebox.showerror("MTS to DNxHR", str(exc), parent=self.root)
            return
        if collisions:
            lines = []
            for dst, sources in collisions.items():
                lines.append(str(dst))
                for src in sources:
                    lines.append("  {0}".format(src))
            lines.append("Remove one of these clips, or convert them in separate runs.")
            messagebox.showerror("Name clash", "\n".join(lines), parent=self.root)
            return
        needed = estimate_needed_bytes(pairs)
        free = free_bytes(out_dir)
        if free is not None and needed > free:
            drive = out_dir.drive or str(out_dir.anchor)
            proceed = messagebox.askyesno(
                "Low disk space",
                "This batch may need about {0:.1f} GB, but only {1:.1f} GB is free on {2}. "
                "DNxHR HQX files are roughly 14× larger than camera files. Convert anyway?".format(
                    needed / 1e9,
                    free / 1e9,
                    drive,
                ),
                default="no",
                parent=self.root,
            )
            if not proceed:
                return
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "MTS to DNxHR",
                "Could not create the export folder:\n{0}\n\n{1}".format(out_dir, exc),
                parent=self.root,
            )
            return
        for index in range(len(self.items)):
            self.errors[index] = ""
            self._set_status_cell(index, "Waiting")
        try:
            jobs = max(1, min(core.MAX_JOBS, int(self.jobs_var.get())))
        except (tk.TclError, ValueError):
            jobs = 1
        self._finished_files = 0
        self._active = {}
        self._batch_jobs = jobs
        self._batch_t0 = time.monotonic()
        self.progress["value"] = 0
        self.cancel = threading.Event()
        self.running = True
        self._set_running_ui(True)
        opts = options_for(bool(self.deinterlace_var.get()))
        self.worker = threading.Thread(
            target=run_batch,
            args=(pairs, opts, self.ffmpeg, self.ffprobe, self.events.put, self.cancel),
            kwargs={"jobs": jobs},
            daemon=True,
        )
        self.worker.start()
        self._poll()

    def _ask_yes_no(self, title: str, message: str) -> bool:
        """Show a yes/no prompt. Finish dialogs wait until it closes."""
        self._modal_open = True
        try:
            return bool(messagebox.askyesno(title, message, parent=self.root))
        finally:
            self._modal_open = False

    def _show_pending_finish(self) -> None:
        pending = self._pending_finish
        self._pending_finish = None
        if pending is None or self._quitting:
            return
        self._handle_event(pending)

    def _confirm_stop(self) -> None:
        if self._batch_jobs > 1:
            message = "Files being converted now will be deleted. Finished files are kept."
        else:
            message = "The file being converted now will be deleted. Finished files are kept."
        yes = self._ask_yes_no("Stop converting?", message)
        if self._pending_finish is not None:
            self._show_pending_finish()
            return
        if not yes or not self.running:
            return
        self.cancel.set()
        self.convert_btn.configure(state="disabled")
        self.status_var.set(self._with_times("Stopping…", include_file=False))

    def _poll(self) -> None:
        self._drain_events()
        if self.running:
            self._refresh_running_status()
            self.root.after(100, self._poll)

    def _elapsed_batch(self) -> Optional[float]:
        if self._batch_t0 is None:
            return None
        return time.monotonic() - self._batch_t0

    def _with_times(self, prefix: str, *, include_file: bool = True) -> str:
        """Append `` · file M:SS · total M:SS`` when timers are running."""
        parts = [prefix]
        if include_file and len(self._active) == 1:
            entry = next(iter(self._active.values()))
            parts.append("file {0}".format(format_elapsed(time.monotonic() - entry.t0)))
        batch_secs = self._elapsed_batch()
        if batch_secs is not None:
            parts.append("total {0}".format(format_elapsed(batch_secs)))
        if len(parts) == 1:
            return prefix
        return " · ".join(parts)

    def _running_prefix(self) -> str:
        count = len(self.items)
        active: list[tuple[int, str, Optional[int]]] = []
        for index, entry in self._active.items():
            if index < 0 or index >= count:
                continue
            active.append((index, self.items[index].src.name, entry.pct))
        return running_prefix(count, active)

    def _active_row_text(self, entry: _ActiveFile) -> str:
        if entry.pct is None:
            label = "Converting…"
        else:
            label = "{0}%".format(entry.pct)
        if self._batch_jobs <= 1:
            return label
        return "{0} · {1}".format(label, format_elapsed(time.monotonic() - entry.t0))

    def _refresh_running_status(self) -> None:
        if not self.running or self._quitting:
            return
        if self._batch_jobs > 1:
            children = self.tree.get_children()
            for index, entry in list(self._active.items()):
                if index < 0 or index >= len(children):
                    continue
                text = self._active_row_text(entry)
                values = self.tree.item(children[index], "values")
                if len(values) >= 3 and values[2] == text:
                    continue
                self._set_status_cell(index, text)
        text = self.status_var.get()
        if text.startswith("Stopping"):
            self.status_var.set(self._with_times("Stopping…", include_file=False))
            return
        if not self._active:
            return
        self.status_var.set(self._with_times(self._running_prefix()))

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

    def _handle_event(self, event: tuple) -> None:
        if self._quitting:
            if event[0] == "batch_finished":
                self.running = False
                self._pending_finish = None
            return
        if event[0] == "batch_finished" and self._modal_open:
            self._pending_finish = event
            self.running = False
            return
        kind = event[0]
        if kind == "file_started":
            index = event[1]
            entry = _ActiveFile(time.monotonic(), 0, 0.0)
            self._active[index] = entry
            self._set_status_cell(index, self._active_row_text(entry))
            self.status_var.set(self._with_times(self._running_prefix()))
            self._update_overall()
        elif kind == "file_progress":
            index = event[1]
            fraction = event[2]
            entry = self._active.get(index)
            if entry is not None:
                if fraction is None:
                    entry.pct = None
                    entry.fraction = 0.0
                else:
                    pct = int(fraction * 100)
                    if pct < 0:
                        pct = 0
                    elif pct > 100:
                        pct = 100
                    entry.pct = pct
                    entry.fraction = fraction
                self._set_status_cell(index, self._active_row_text(entry))
            self.status_var.set(self._with_times(self._running_prefix()))
            self._update_overall()
        elif kind == "file_finished":
            index = event[1]
            status = event[2]
            err = event[3]
            text = {
                "ok": "Done",
                "skipped": "Skipped (already exists)",
                "failed": "Failed (double-click for details)",
                "cancelled": "Cancelled",
            }.get(status, "Failed (double-click for details)")
            entry = self._active.pop(index, None)
            if entry is not None and status in ("ok", "failed", "cancelled", "skipped"):
                text = "{0} ({1})".format(text, format_elapsed(time.monotonic() - entry.t0))
            self._set_status_cell(index, text)
            if index < len(self.errors):
                self.errors[index] = err if status == "failed" else ""
            self._finished_files += 1
            self._update_overall()
        elif kind == "batch_finished":
            _ok, _skipped, failed, cancelled = event[1], event[2], event[3], event[4]
            summary = self._summary_line(event[1], event[2], failed, cancelled)
            self.running = False
            self._active.clear()
            self._batch_jobs = 1
            self._set_running_ui(False)
            self.status_var.set(summary)
            self._show_finished(summary, failed)

    def _summary_line(self, ok: int, skipped: int, failed: int, cancelled: int) -> str:
        if cancelled:
            line = (
                "Stopped: {0} converted, {1} skipped, {2} failed, {3} not converted."
            ).format(ok, skipped, failed, cancelled)
        else:
            line = "Finished: {0} converted, {1} skipped, {2} failed.".format(
                ok, skipped, failed
            )
        batch_secs = self._elapsed_batch()
        if batch_secs is not None:
            line = "{0} · Total {1}".format(line, format_elapsed(batch_secs))
        return line

    def _update_overall(self) -> None:
        count = len(self.items)
        if count <= 0:
            self.progress["value"] = 0
            return
        current = 0.0
        for entry in self._active.values():
            if entry.pct is not None:
                current += entry.fraction
        self.progress["value"] = (self._finished_files + current) / count * 100.0

    def _failed_names(self) -> list[str]:
        names = []
        children = list(self.tree.get_children())
        for index, iid in enumerate(children):
            values = self.tree.item(iid, "values")
            if len(values) >= 3 and str(values[2]).startswith("Failed"):
                names.append(self.items[index].src.name)
        return names

    def _show_finished(self, summary: str, failed: int) -> None:
        names = self._failed_names()
        lines = [summary]
        if names:
            lines.append("")
            lines.extend(names[:5])
            extra = len(names) - 5
            if extra > 0:
                lines.append("…and {0} more".format(extra))
        body = "\n".join(lines)
        if failed:
            messagebox.showwarning("MTS to DNxHR", body, parent=self.root)
        else:
            messagebox.showinfo("MTS to DNxHR", body, parent=self.root)
        out_dir = Path(self.export_var.get().strip())
        if not out_dir.is_dir():
            return
        if not messagebox.askyesno("MTS to DNxHR", "Open the export folder?", parent=self.root):
            return
        if sys.platform != "win32":
            return
        try:
            os.startfile(str(out_dir))
        except OSError:
            pass

    def _on_close(self) -> None:
        if self._quitting:
            return
        worker_alive = self.worker is not None and self.worker.is_alive()
        if self.running and worker_alive:
            yes = self._ask_yes_no(
                "Quit?",
                "A conversion is running. Stop it and quit?",
            )
            if yes:
                self._quitting = True
                self._pending_finish = None
                self.cancel.set()
                self._quit_deadline = time.monotonic() + 15.0
                self._wait_to_quit()
                return
            self._show_pending_finish()
            return
        self.root.destroy()

    def _wait_to_quit(self) -> None:
        alive = self.worker is not None and self.worker.is_alive()
        if alive and time.monotonic() < self._quit_deadline:
            self.root.after(100, self._wait_to_quit)
            return
        self.root.destroy()


def _discard_failed_root() -> None:
    """Drop a Tk that ``TkinterDnD.Tk`` created before tkdnd failed to load."""
    dangling = getattr(tk, "_default_root", None)
    if dangling is None:
        return
    try:
        dangling.destroy()
    except tk.TclError:
        pass
    if getattr(tk, "_default_root", None) is dangling:
        tk._default_root = None


def _create_root() -> tuple[tk.Tk, bool]:
    """Return the main window and whether drag-and-drop is actually available."""
    if DND_AVAILABLE and tkinterdnd2 is not None:
        try:
            return tkinterdnd2.TkinterDnD.Tk(), True
        except (RuntimeError, tk.TclError):
            _discard_failed_root()
    return tk.Tk(), False


def main() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MTSToDNxHR.App")
        except Exception:
            pass
    root, dnd = _create_root()
    App(root, dnd=dnd)
    root.mainloop()


if __name__ == "__main__":
    main()
