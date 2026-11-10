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
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

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
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

# README: a 168 s HQX encode is about 4.7 GB, roughly 14× a 335 MB source.
SIZE_RATIO = 14


class _Palette:
    """Night theme: charcoal surfaces, muted gray-teal accent. Every UI color lives here so contrast can be checked in one place."""

    SURFACE = "#14171a"
    FIELD = "#0d0f11"
    STRIPE = "#171b1e"
    CONTROL_BG = "#20272b"
    CONTROL_HOVER = "#2c363b"
    TEXT = "#e6eaec"
    TEXT_SECONDARY = "#a3adb3"
    TEXT_DISABLED = "#7b858b"
    BORDER = "#3a444a"
    HEADING_BG = "#20272b"
    HEADING_FG = "#e6eaec"
    HEADING_ACTIVE = "#2c363b"
    # Desaturated teal, tuned for dark surfaces.
    ACCENT = "#3f6b66"
    ACCENT_ACTIVE = "#4b7d77"
    ACCENT_FG = "#ffffff"
    # Keep Convert recognizably teal-gray while disabled (idle window still shows the scheme).
    ACCENT_DISABLED = "#2c3a38"
    ACCENT_DISABLED_FG = "#8fa8a4"
    SELECT_BG = "#24413e"
    SELECT_FG = "#ffffff"
    OK_FG = "#6fcf97"
    FAILED_FG = "#ff8a80"
    ACTIVE_FG = "#7fd0c6"
    MUTED_FG = "#aab4ba"
    ERROR_BG = "#3a1a1a"
    ERROR_FG = "#ffb4ab"
    ERROR_BORDER = "#7a3333"
    DROP_BG = "#101316"
    DROP_HOT_BG = "#16302d"
    DROP_PAUSED_BG = "#1a1e21"
    DROP_BORDER = "#44505a"
    DROP_HOT_BORDER = "#5f9a92"
    DISABLED_BG = "#20272b"
    TROUGH = "#232b2f"


class _DropdownSelect(tk.Frame):
    """Flat dropdown for a fixed list of integers (readonly; styled for the night palette)."""

    def __init__(
        self,
        master: tk.Misc,
        variable: tk.IntVar,
        choices: Sequence[int],
        font: tkfont.Font,
        px: Callable[[int], int],
    ) -> None:
        super().__init__(
            master,
            bg=_Palette.CONTROL_BG,
            highlightthickness=1,
            highlightbackground=_Palette.BORDER,
            highlightcolor=_Palette.ACCENT_ACTIVE,
            bd=0,
            takefocus=True,
        )
        self._var = variable
        self._choices = tuple(choices)
        self._font = font
        self._px = px
        self._enabled = True
        self._popup: Optional[tk.Toplevel] = None
        self._outside_id: Optional[str] = None
        # Single-digit values: keep the closed control as tight as a spinbox digit.
        self._label = tk.Label(
            self,
            font=font,
            width=1,
            anchor="center",
            bg=_Palette.CONTROL_BG,
            fg=_Palette.TEXT,
        )
        self._label.pack(side="left", padx=(px(3), 0), pady=px(1))
        self._arrow = tk.Label(
            self, text="▾", font=font, bg=_Palette.CONTROL_BG, fg=_Palette.TEXT_SECONDARY
        )
        self._arrow.pack(side="left", padx=(0, px(2)))
        for widget in (self, self._label, self._arrow):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", lambda _e: self._paint(hover=True))
            widget.bind("<Leave>", lambda _e: self._paint(hover=False))
        self.bind("<Key-space>", self._on_click)
        self.bind("<Return>", self._on_click)
        self.bind("<Down>", self._on_click)
        self._var.trace_add("write", lambda *_a: self._refresh())
        self._refresh()

    def _value(self) -> int:
        try:
            value = int(self._var.get())
        except (tk.TclError, ValueError):
            return self._choices[0]
        return value if value in self._choices else self._choices[0]

    def _refresh(self) -> None:
        self._label.configure(text=str(self._value()))

    def _paint(self, hover: bool) -> None:
        if not self._enabled:
            bg, fg, arrow = _Palette.SURFACE, _Palette.TEXT_DISABLED, _Palette.TEXT_DISABLED
        else:
            bg = _Palette.CONTROL_HOVER if hover else _Palette.CONTROL_BG
            fg, arrow = _Palette.TEXT, _Palette.TEXT_SECONDARY
        tk.Frame.configure(self, bg=bg)
        self._label.configure(bg=bg, fg=fg)
        self._arrow.configure(bg=bg, fg=arrow)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._close()
        tk.Frame.configure(self, takefocus=enabled)
        self._paint(hover=False)

    def _on_click(self, _event: object = None) -> str:
        if self._enabled:
            if self._popup is None:
                self._open()
            else:
                self._close()
            self.focus_set()
        return "break"

    def _open(self) -> None:
        popup = tk.Toplevel(self)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=_Palette.BORDER)
        body = tk.Frame(popup, bg=_Palette.CONTROL_BG)
        body.pack(padx=1, pady=1)
        current = self._value()
        for n in self._choices:
            selected = n == current
            row = tk.Label(
                body,
                text=str(n),
                font=self._font,
                anchor="center",
                bg=_Palette.SELECT_BG if selected else _Palette.CONTROL_BG,
                fg=_Palette.SELECT_FG if selected else _Palette.TEXT,
                padx=self._px(8),
                pady=self._px(2),
            )
            row.pack(fill="x")
            row.bind(
                "<Enter>",
                lambda _e, w=row: w.configure(bg=_Palette.ACCENT, fg=_Palette.ACCENT_FG),
            )
            row.bind(
                "<Leave>",
                lambda _e, w=row, sel=selected: w.configure(
                    bg=_Palette.SELECT_BG if sel else _Palette.CONTROL_BG,
                    fg=_Palette.SELECT_FG if sel else _Palette.TEXT,
                ),
            )
            row.bind("<Button-1>", lambda _e, v=n: self._choose(v))
        popup.bind("<Escape>", lambda _e: self._close())
        self.update_idletasks()
        popup.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        width = max(self.winfo_width(), popup.winfo_reqwidth())
        popup.geometry("{0}x{1}+{2}+{3}".format(width, popup.winfo_reqheight(), x, y))
        popup.deiconify()
        popup.lift()
        self._popup = popup
        # A click anywhere else in the app closes the list.
        self._outside_id = self.winfo_toplevel().bind("<Button-1>", self._on_outside, add="+")

    def _on_outside(self, event: tk.Event) -> None:
        widget = str(event.widget)
        if widget == str(self) or widget.startswith(str(self) + "."):
            return
        self._close()

    def _choose(self, value: int) -> None:
        self._var.set(value)
        self._close()

    def _close(self) -> None:
        popup, self._popup = self._popup, None
        if popup is not None:
            popup.destroy()
        if self._outside_id is not None:
            try:
                self.winfo_toplevel().unbind("<Button-1>", self._outside_id)
            except tk.TclError:
                pass
            self._outside_id = None


_DROP_PAUSED = "Converting… drops are paused"
_IDLE_STATUS = "Add clips, choose an export folder, then click Convert."
_HEADINGS = {
    "file": "File",
    "status": "Status",
    "size": "Size",
    "mtime": "Modified",
    "folder": "Source folder",
}
_STATUS_RANK = {
    "active": 0,
    "waiting": 1,
    "failed": 2,
    "cancelled": 3,
    "skipped": 4,
    "ok": 5,
}
_STATUS_TAG = {kind: kind for kind in _STATUS_RANK}
_COLUMN_LAYOUT = (
    ("file", 220, 120, False, "w"),
    ("status", 230, 140, False, "w"),
    ("size", 90, 70, False, "e"),
    ("mtime", 140, 110, False, "w"),
    ("folder", 290, 160, True, "w"),
)


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


@dataclasses.dataclass
class _Row:
    """One clip list row, keyed by its Treeview iid."""

    item: ClipItem
    seq: int
    size: Optional[int]
    mtime: Optional[float]
    status: str
    error: str


def natural_key(text: str) -> tuple:
    """Sort key that orders ``clip2`` before ``clip10`` and keeps comparisons typed."""
    pieces = []
    for part in re.split(r"(\d+)", text.casefold()):
        if part == "":
            continue
        if part.isdigit():
            pieces.append((0, int(part)))
        else:
            pieces.append((1, part))
    return tuple(pieces)


def format_size(n: Optional[int]) -> str:
    """Decimal size (``335 MB``, ``4.7 GB``), or an em dash when unknown."""
    if n is None:
        return "—"
    value = float(n if n > 0 else 0)
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    for unit in units:
        if value < 1000.0 or unit == units[-1]:
            break
        value /= 1000.0
    if unit == "B" or abs(value - round(value)) < 1e-6:
        return "{0:.0f} {1}".format(value, unit)
    return "{0:.1f} {1}".format(value, unit)


def format_mtime(ts: Optional[float]) -> str:
    """Local ``YYYY-MM-DD HH:MM``, or an em dash when unknown."""
    if ts is None:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


class _Reversed:
    """Reverse a ``natural_key`` tuple without flipping the other sort fields."""

    def __init__(self, value: tuple) -> None:
        self.value = value

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, _Reversed):
            return NotImplemented
        return other.value < self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Reversed):
            return NotImplemented
        return self.value == other.value


def sort_iids(
    rows: Mapping[str, _Row],
    column: str,
    descending: bool,
) -> list[str]:
    """Stable iid order. Missing sizes and mtimes stay last in both directions."""

    def key(iid: str) -> tuple:
        row = rows[iid]
        missing = False
        primary: object
        if column == "file":
            names = natural_key(row.item.src.name)
            primary = _Reversed(names) if descending else names
        elif column == "folder":
            folders = natural_key(str(row.item.src.parent))
            primary = _Reversed(folders) if descending else folders
        elif column == "size":
            if row.size is None:
                missing = True
                primary = 0
            else:
                primary = -row.size if descending else row.size
        elif column == "mtime":
            if row.mtime is None:
                missing = True
                primary = 0
            else:
                primary = -row.mtime if descending else row.mtime
        elif column == "status":
            rank = _STATUS_RANK[row.status]
            primary = -rank if descending else rank
        else:
            primary = row.seq
        return (missing, primary, row.seq)

    return sorted(rows, key=key)


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
        deinterlace=args.deinterlace,
        overwrite=args.overwrite,
        duration=args.duration,
        hwaccel=args.hwaccel,
    )


DEFAULT_OPTIONS: core.Options = _parser_defaults()
OUTPUT_SUMMARY = (
    f"{_profile_label(DEFAULT_OPTIONS.profile)} · {DEFAULT_OPTIONS.container.upper()} · "
    f"PCM {DEFAULT_OPTIONS.audio_bit_depth}-bit 48 kHz · source size/fps"
)


def options_for(deinterlace: bool, *, gpu_decode: bool = True) -> core.Options:
    return dataclasses.replace(
        DEFAULT_OPTIONS,
        deinterlace=deinterlace,
        hwaccel="cuda" if gpu_decode else "off",
    )


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


@dataclasses.dataclass
class _Fonts:
    body: tkfont.Font
    heading: tkfont.Font
    drop: tkfont.Font
    count: tkfont.Font


# Keep PhotoImage refs alive; ttk styles do not hold strong references.
_CHECK_IMAGES: list[tk.PhotoImage] = []
_CHECKBOX_STYLE = "Big.TCheckbutton"
_CHECKBOX_SIZE = 18


def _dpi_scale(root: tk.Misc) -> float:
    return root.winfo_fpixels("1i") / 96.0


def _photo_fill(img: tk.PhotoImage, x0: int, y0: int, x1: int, y1: int, color: str) -> None:
    if x1 <= x0 or y1 <= y0:
        return
    img.put(color, to=(x0, y0, x1, y1))


def _photo_dot(img: tk.PhotoImage, x: int, y: int, color: str, radius: int) -> None:
    w = int(img["width"])
    h = int(img["height"])
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            xx = x + dx
            yy = y + dy
            if 0 <= xx < w and 0 <= yy < h:
                img.put(color, to=(xx, yy, xx + 1, yy + 1))


def _photo_line(
    img: tk.PhotoImage,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: str,
    radius: int,
) -> None:
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(steps + 1):
        t = i / steps
        _photo_dot(
            img,
            int(round(x0 + (x1 - x0) * t)),
            int(round(y0 + (y1 - y0) * t)),
            color,
            radius,
        )


def _make_checkbox_image(
    root: tk.Misc,
    size: int,
    *,
    checked: bool,
    disabled: bool,
    label_gap: int = 0,
) -> tk.PhotoImage:
    """Draw a square indicator with an optional checkmark (not an X).

    ``label_gap`` adds empty pixels to the right of the box so the label is not
    cramped against the indicator (ttk has no reliable indicator-to-label gap).
    """
    width = size + max(0, label_gap)
    img = tk.PhotoImage(master=root, width=width, height=size)
    # Match the checkbutton background so the gap reads as spacing, not a second box.
    _photo_fill(img, 0, 0, width, size, _Palette.SURFACE)
    fill = _Palette.SURFACE if disabled else _Palette.CONTROL_BG
    border = _Palette.TEXT_DISABLED if disabled else _Palette.BORDER
    mark = _Palette.TEXT_DISABLED if disabled else _Palette.ACCENT_ACTIVE
    _photo_fill(img, 0, 0, size, size, fill)
    border_w = max(2, size // 9)
    for i in range(border_w):
        _photo_fill(img, i, i, size - i, i + 1, border)
        _photo_fill(img, i, size - i - 1, size - i, size - i, border)
        _photo_fill(img, i, i, i + 1, size - i, border)
        _photo_fill(img, size - i - 1, i, size - i, size - i, border)
    if checked:
        thick = max(1, size // 10)
        x0 = int(round(size * 0.22))
        y0 = int(round(size * 0.52))
        x1 = int(round(size * 0.42))
        y1 = int(round(size * 0.72))
        x2 = int(round(size * 0.78))
        y2 = int(round(size * 0.28))
        _photo_line(img, x0, y0, x1, y1, mark, thick)
        _photo_line(img, x1, y1, x2, y2, mark, thick)
    return img


def _check_images_alive() -> bool:
    if not _CHECK_IMAGES:
        return False
    try:
        _CHECK_IMAGES[0].width()
    except tk.TclError:
        _CHECK_IMAGES.clear()
        return False
    return True


def _install_big_checkbuttons(
    style: ttk.Style,
    root: tk.Misc,
    px: Callable[[int], int],
    body: tkfont.Font,
) -> None:
    """Replace the clam indicator with larger checkmark images."""
    linespace = int(body.metrics("linespace"))
    # Match the body text height so the box sits on the same visual centerline.
    size = max(14, min(px(_CHECKBOX_SIZE), linespace))
    label_gap = max(6, px(8))
    vpad = max(0, (linespace - size + 1) // 2)
    if not _check_images_alive():
        unchecked = _make_checkbox_image(
            root, size, checked=False, disabled=False, label_gap=label_gap
        )
        checked = _make_checkbox_image(
            root, size, checked=True, disabled=False, label_gap=label_gap
        )
        unchecked_dis = _make_checkbox_image(
            root, size, checked=False, disabled=True, label_gap=label_gap
        )
        checked_dis = _make_checkbox_image(
            root, size, checked=True, disabled=True, label_gap=label_gap
        )
        _CHECK_IMAGES[:] = [unchecked, checked, unchecked_dis, checked_dis]
        try:
            style.element_create(
                "Big.Checkbutton.indicator",
                "image",
                unchecked,
                ("disabled", "selected", checked_dis),
                ("disabled", unchecked_dis),
                ("selected", checked),
                border=0,
                sticky="",
            )
        except tk.TclError:
            # Element already exists from an earlier root; layout/configure below still apply.
            pass
    style.layout(
        _CHECKBOX_STYLE,
        [
            (
                "Checkbutton.padding",
                {
                    "sticky": "nswe",
                    "children": [
                        # Empty sticky keeps the indicator vertically centered with the label.
                        ("Big.Checkbutton.indicator", {"side": "left", "sticky": ""}),
                        (
                            "Checkbutton.focus",
                            {
                                "side": "left",
                                "sticky": "",
                                "children": [("Checkbutton.label", {"sticky": ""})],
                            },
                        ),
                    ],
                },
            )
        ],
    )
    style.configure(
        _CHECKBOX_STYLE,
        background=_Palette.SURFACE,
        foreground=_Palette.TEXT,
        padding=(0, vpad, 0, vpad),
    )
    style.map(
        _CHECKBOX_STYLE,
        foreground=[("disabled", _Palette.TEXT_DISABLED)],
        background=[("active", _Palette.SURFACE), ("disabled", _Palette.SURFACE)],
    )


def _configure_tree_tags(tree: ttk.Treeview) -> None:
    tree.tag_configure("odd", background=_Palette.STRIPE)
    tree.tag_configure("even", background=_Palette.FIELD)
    tree.tag_configure("waiting", foreground=_Palette.MUTED_FG)
    tree.tag_configure("active", foreground=_Palette.ACTIVE_FG)
    tree.tag_configure("ok", foreground=_Palette.OK_FG)
    tree.tag_configure("skipped", foreground=_Palette.MUTED_FG)
    tree.tag_configure("failed", foreground=_Palette.FAILED_FG)
    tree.tag_configure("cancelled", foreground=_Palette.MUTED_FG)


def apply_theme(root: tk.Misc) -> _Fonts:
    """Apply the clam night theme. A styling failure must not stop startup."""
    scale = _dpi_scale(root)

    def px(n: int) -> int:
        return round(n * scale)

    family = tkfont.nametofont("TkDefaultFont").cget("family")
    fonts = _Fonts(
        body=tkfont.Font(root, family=family, size=10),
        heading=tkfont.Font(root, family=family, size=10, weight="bold"),
        drop=tkfont.Font(root, family=family, size=11),
        count=tkfont.Font(root, family=family, size=10, weight="bold"),
    )
    try:
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        _apply_clam_styles(style, fonts, px)
        _install_big_checkbuttons(style, root, px, fonts.body)
        style.configure(_CHECKBOX_STYLE, font=fonts.body)
        root.configure(bg=_Palette.SURFACE)
    except tk.TclError:
        pass
    return fonts


def _apply_windows_dark_titlebar(root: tk.Misc) -> None:
    """Ask Windows to paint a dark caption (Tk cannot theme the title bar itself)."""
    if sys.platform != "win32":
        return
    try:
        root.update_idletasks()
        hwnd = int(root.winfo_id())
        parent = ctypes.windll.user32.GetParent(hwnd)
        if parent:
            hwnd = parent
        value = ctypes.c_int(1)
        # 20 = Win10 20H1+; 19 = earlier builds. Try both.
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attr,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        pass


def _apply_clam_styles(
    style: ttk.Style,
    fonts: _Fonts,
    px: Callable[[int], int],
) -> None:
    body = fonts.body
    style.configure("TFrame", background=_Palette.SURFACE)
    style.configure(
        "TLabel",
        background=_Palette.SURFACE,
        foreground=_Palette.TEXT,
        font=body,
    )
    style.configure(
        "TCheckbutton",
        background=_Palette.SURFACE,
        foreground=_Palette.TEXT,
        font=body,
    )
    style.configure(
        "TLabelframe",
        background=_Palette.SURFACE,
        foreground=_Palette.TEXT,
        bordercolor=_Palette.BORDER,
        lightcolor=_Palette.BORDER,
        darkcolor=_Palette.BORDER,
    )
    style.configure(
        "TLabelframe.Label",
        background=_Palette.SURFACE,
        foreground=_Palette.TEXT,
        font=body,
    )
    style.configure("TSeparator", background=_Palette.BORDER)
    style.configure(
        "Secondary.TLabel",
        background=_Palette.SURFACE,
        foreground=_Palette.TEXT_SECONDARY,
        font=body,
    )
    style.configure(
        "TButton",
        padding=(px(10), px(4)),
        background=_Palette.CONTROL_BG,
        foreground=_Palette.TEXT,
        bordercolor=_Palette.BORDER,
        lightcolor=_Palette.CONTROL_BG,
        darkcolor=_Palette.CONTROL_BG,
        focuscolor=_Palette.CONTROL_BG,
        relief="flat",
        borderwidth=1,
        font=body,
    )
    style.map(
        "TButton",
        background=[
            ("disabled", _Palette.SURFACE),
            ("pressed", _Palette.HEADING_ACTIVE),
            ("active", _Palette.CONTROL_HOVER),
        ],
        lightcolor=[
            ("disabled", _Palette.SURFACE),
            ("pressed", _Palette.HEADING_ACTIVE),
            ("active", _Palette.CONTROL_HOVER),
        ],
        darkcolor=[
            ("disabled", _Palette.SURFACE),
            ("pressed", _Palette.HEADING_ACTIVE),
            ("active", _Palette.CONTROL_HOVER),
        ],
        foreground=[("disabled", _Palette.TEXT_DISABLED)],
        bordercolor=[("focus", _Palette.ACCENT)],
    )
    style.configure(
        "Accent.TButton",
        padding=(px(10), px(4)),
        background=_Palette.ACCENT,
        foreground=_Palette.ACCENT_FG,
        bordercolor=_Palette.ACCENT,
        lightcolor=_Palette.ACCENT,
        darkcolor=_Palette.ACCENT,
        focuscolor=_Palette.ACCENT,
        relief="flat",
        font=body,
    )
    style.map(
        "Accent.TButton",
        background=[
            ("disabled", _Palette.ACCENT_DISABLED),
            ("pressed", _Palette.ACCENT_ACTIVE),
            ("active", _Palette.ACCENT_ACTIVE),
        ],
        foreground=[
            ("disabled", _Palette.ACCENT_DISABLED_FG),
            ("!disabled", _Palette.ACCENT_FG),
        ],
        bordercolor=[
            ("disabled", _Palette.ACCENT_DISABLED),
            ("pressed", _Palette.ACCENT_ACTIVE),
            ("active", _Palette.ACCENT_ACTIVE),
        ],
        lightcolor=[
            ("disabled", _Palette.ACCENT_DISABLED),
            ("pressed", _Palette.ACCENT_ACTIVE),
            ("active", _Palette.ACCENT_ACTIVE),
        ],
        darkcolor=[
            ("disabled", _Palette.ACCENT_DISABLED),
            ("pressed", _Palette.ACCENT_ACTIVE),
            ("active", _Palette.ACCENT_ACTIVE),
        ],
    )
    style.configure(
        "TEntry",
        fieldbackground=_Palette.FIELD,
        foreground=_Palette.TEXT,
        insertcolor=_Palette.TEXT,
        bordercolor=_Palette.BORDER,
        lightcolor=_Palette.BORDER,
        darkcolor=_Palette.BORDER,
    )
    style.map(
        "TEntry",
        fieldbackground=[
            ("readonly", _Palette.FIELD),
            ("disabled", _Palette.SURFACE),
        ],
        foreground=[("disabled", _Palette.TEXT_DISABLED)],
        bordercolor=[("focus", _Palette.ACCENT)],
        lightcolor=[("focus", _Palette.ACCENT)],
        darkcolor=[("focus", _Palette.ACCENT)],
    )
    style.configure(
        "Treeview",
        background=_Palette.FIELD,
        fieldbackground=_Palette.FIELD,
        foreground=_Palette.TEXT,
        rowheight=body.metrics("linespace") + px(8),
        bordercolor=_Palette.BORDER,
        lightcolor=_Palette.FIELD,
        darkcolor=_Palette.FIELD,
        relief="flat",
        borderwidth=0,
        font=body,
    )
    style.map(
        "Treeview",
        background=[("selected", _Palette.SELECT_BG)],
        foreground=[("selected", _Palette.SELECT_FG)],
    )
    style.configure(
        "Treeview.Heading",
        background=_Palette.HEADING_BG,
        foreground=_Palette.HEADING_FG,
        font=fonts.heading,
        padding=(px(8), px(5)),
        bordercolor=_Palette.BORDER,
        lightcolor=_Palette.HEADING_BG,
        darkcolor=_Palette.HEADING_BG,
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", _Palette.HEADING_ACTIVE)],
        lightcolor=[("active", _Palette.HEADING_ACTIVE)],
        darkcolor=[("active", _Palette.HEADING_ACTIVE)],
        foreground=[("active", _Palette.HEADING_FG)],
    )
    bar = body.metrics("linespace")
    style.configure(
        "Horizontal.TProgressbar",
        background=_Palette.ACCENT,
        troughcolor=_Palette.TROUGH,
        bordercolor=_Palette.TROUGH,
        lightcolor=_Palette.ACCENT,
        darkcolor=_Palette.ACCENT,
        thickness=bar,
    )
    for name in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            name,
            background=_Palette.CONTROL_HOVER,
            troughcolor=_Palette.SURFACE,
            bordercolor=_Palette.SURFACE,
            lightcolor=_Palette.CONTROL_HOVER,
            darkcolor=_Palette.CONTROL_HOVER,
            arrowcolor=_Palette.TEXT_SECONDARY,
            relief="flat",
        )
        style.map(name, background=[("active", _Palette.BORDER)])


class App:
    """Single-window exporter. Widgets are touched only on the Tk thread."""

    def __init__(self, root: tk.Tk, dnd: Optional[bool] = None) -> None:
        self.root = root
        self.root.title("MTS to DNxHR")
        self._scale = _dpi_scale(root)
        self._fonts = apply_theme(root)
        self.root.geometry(
            "{0}x{1}".format(
                min(self._px(1024), root.winfo_screenwidth() - self._px(40)),
                min(self._px(660), root.winfo_screenheight() - self._px(80)),
            )
        )
        # 800×580 is the smallest 100% size that keeps the options row and the
        # FFmpeg banner intact, with two clip rows still visible.
        min_w = min(self._px(800), root.winfo_screenwidth() - self._px(40))
        min_h = min(self._px(580), root.winfo_screenheight() - self._px(80))
        self.root.minsize(min_w, min_h)
        if sys.platform == "win32":
            try:
                self.root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        self.dnd = DND_AVAILABLE if dnd is None else dnd
        self._rows: dict[str, _Row] = {}
        self._iids: list[str] = []
        self._seq = 0
        self._sort_col: Optional[str] = None
        self._sort_desc = False
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
        _apply_windows_dark_titlebar(self.root)
        # Re-apply after the HWND exists; first call can race window creation.
        self.root.after_idle(lambda: _apply_windows_dark_titlebar(self.root))

    def _px(self, n: int) -> int:
        return round(n * self._scale)

    def _build(self) -> None:
        gap = self._px(8)
        outer = ttk.Frame(self.root, padding=self._px(12))
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        self.drop = tk.Frame(
            outer,
            relief="flat",
            bd=0,
            highlightthickness=2,
            highlightbackground=_Palette.DROP_BORDER,
            highlightcolor=_Palette.DROP_BORDER,
            bg=_Palette.DROP_BG,
        )
        self.drop.grid(row=0, column=0, sticky="ew", pady=(0, gap))
        # No fixed height: the frame sizes from the labels + button row so
        # buttons are never clipped at high DPI.
        self.drop_title = tk.Label(
            self.drop,
            text=_DROP_TEXT if self.dnd else _DROP_TEXT_NO_DND,
            bg=_Palette.DROP_BG,
            fg=_Palette.TEXT,
            font=self._fonts.drop,
        )
        self.drop_title.pack(pady=(self._px(12), self._px(2)))
        self.drop_secondary = tk.Label(
            self.drop,
            text="or click to browse",
            bg=_Palette.DROP_BG,
            fg=_Palette.TEXT_SECONDARY,
            font=self._fonts.body,
        )
        self.drop_secondary.pack(pady=(0, self._px(4)))
        button_row = tk.Frame(self.drop, bg=_Palette.DROP_BG)
        button_row.pack(pady=(0, self._px(12)))
        self._drop_fill = (self.drop, self.drop_title, self.drop_secondary, button_row)
        self.add_files_btn = ttk.Button(button_row, text="Add files…", command=self.add_files)
        self.add_files_btn.pack(side="left", padx=self._px(4))
        self.add_folder_btn = ttk.Button(button_row, text="Add folder…", command=self.add_folder)
        self.add_folder_btn.pack(side="left", padx=self._px(4))
        self.drop.bind("<Button-1>", self._on_drop_zone_click)
        for label in (self.drop_title, self.drop_secondary):
            label.bind("<Button-1>", self._on_drop_zone_click)
            self._register_drop(label)
        self._register_drop(self.drop)
        self._register_drop(button_row)

        clips = ttk.Frame(outer)
        clips.grid(row=1, column=0, sticky="ew", pady=(0, gap))
        self.count_var = tk.StringVar(value="Clips: 0")
        ttk.Label(clips, textvariable=self.count_var, font=self._fonts.count).pack(side="left")
        self.clear_btn = ttk.Button(clips, text="Clear", command=self.clear_all)
        self.clear_btn.pack(side="right")
        self.remove_btn = ttk.Button(clips, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(side="right", padx=(0, self._px(6)))

        tree_frame = ttk.Frame(outer)
        tree_frame.grid(row=2, column=0, sticky="nsew", pady=(0, gap))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=tuple(spec[0] for spec in _COLUMN_LAYOUT),
            show="headings",
            selectmode="extended",
        )
        for name, width, minwidth, stretch, anchor in _COLUMN_LAYOUT:
            self.tree.heading(
                name,
                text=_HEADINGS[name],
                command=lambda col=name: self._on_heading_click(col),
            )
            self.tree.column(
                name,
                width=self._px(width),
                minwidth=self._px(minwidth),
                stretch=stretch,
                anchor=anchor,
            )
        _configure_tree_tags(self.tree)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.tree.bind("<Delete>", self._on_delete_key)
        self.tree.bind("<Double-1>", self._on_double_click)
        self._register_drop(self.tree)

        settings = ttk.Labelframe(outer, text="Export settings", padding=self._px(8))
        settings.grid(row=3, column=0, sticky="ew", pady=(0, gap))
        settings.columnconfigure(0, weight=1)

        export = ttk.Frame(settings)
        export.grid(row=0, column=0, sticky="ew", pady=(0, gap))
        export.columnconfigure(1, weight=1)
        ttk.Label(export, text="Export to:").grid(row=0, column=0, padx=(0, self._px(6)))
        self.export_var = tk.StringVar()
        self.export_entry = ttk.Entry(
            export, textvariable=self.export_var, font=self._fonts.body
        )
        self.export_entry.grid(row=0, column=1, sticky="ew")
        self.browse_btn = ttk.Button(export, text="Browse…", command=self.browse_export)
        self.browse_btn.grid(row=0, column=2, padx=(self._px(6), 0))
        self.export_var.trace_add("write", self._on_export_changed)

        options = ttk.Frame(settings)
        options.grid(row=1, column=0, sticky="ew")
        self.deinterlace_var = tk.BooleanVar(value=False)
        self.deinterlace_chk = ttk.Checkbutton(
            options,
            text="Deinterlace interlaced (1080i) clips",
            variable=self.deinterlace_var,
            style=_CHECKBOX_STYLE,
        )
        self.deinterlace_chk.pack(side="left", padx=(0, self._px(12)))
        self.gpu_decode_var = tk.BooleanVar(value=DEFAULT_OPTIONS.hwaccel != "off")
        self.gpu_decode_chk = ttk.Checkbutton(
            options,
            text="GPU decode (hardware)",
            variable=self.gpu_decode_var,
            style=_CHECKBOX_STYLE,
        )
        self.gpu_decode_chk.pack(side="left", padx=(0, self._px(12)))
        # Concurrent convert jobs (each job already includes decode + DNxHR encode).
        ttk.Label(options, text="Parallel streams:").pack(side="left")
        self.jobs_var = tk.IntVar(value=2)
        self.jobs_combo = _DropdownSelect(
            options,
            self.jobs_var,
            range(1, core.MAX_JOBS + 1),
            self._fonts.body,
            self._px,
        )
        self.jobs_combo.pack(side="left", padx=(self._px(6), self._px(6)))
        ttk.Label(
            options,
            text="(suggested max {0} for this PC)".format(core.suggested_jobs()),
            style="Secondary.TLabel",
        ).pack(side="left")

        self.summary = ttk.Label(
            outer,
            text="Output: {0}".format(OUTPUT_SUMMARY),
            style="Secondary.TLabel",
        )
        self.summary.grid(row=4, column=0, sticky="w", pady=(0, gap))

        self.banner = tk.Frame(
            outer,
            bg=_Palette.ERROR_BG,
            highlightthickness=1,
            highlightbackground=_Palette.ERROR_BORDER,
            highlightcolor=_Palette.ERROR_BORDER,
            bd=0,
        )
        self.banner.grid(row=5, column=0, sticky="ew", pady=(0, gap))
        self.banner.columnconfigure(0, weight=1)
        self.banner_label = tk.Label(
            self.banner,
            text=_FFMPEG_MISSING,
            fg=_Palette.ERROR_FG,
            bg=_Palette.ERROR_BG,
            justify="left",
            anchor="w",
            wraplength=self._px(640),
            font=self._fonts.body,
        )
        self.banner_label.grid(
            row=0, column=0, sticky="ew", padx=self._px(8), pady=self._px(6)
        )
        self.check_btn = ttk.Button(self.banner, text="Check again", command=self.check_tools)
        self.check_btn.grid(row=0, column=1, padx=(0, self._px(8)), pady=self._px(6))

        ttk.Separator(outer, orient="horizontal").grid(
            row=6, column=0, sticky="ew", pady=gap
        )
        self.status_var = tk.StringVar(value=_IDLE_STATUS)
        ttk.Label(outer, textvariable=self.status_var).grid(row=7, column=0, sticky="w")
        progress_row = ttk.Frame(outer)
        progress_row.grid(row=8, column=0, sticky="ew", pady=(gap, 0))
        progress_row.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.overall_pct_var = tk.StringVar(value="")
        ttk.Label(progress_row, textvariable=self.overall_pct_var, width=5).grid(
            row=0, column=1, sticky="e", padx=(gap, 0)
        )
        actions = ttk.Frame(outer)
        actions.grid(row=9, column=0, sticky="ew", pady=(gap, 0))
        self.convert_btn = ttk.Button(
            actions,
            text="Convert",
            command=self.on_convert,
            style="Accent.TButton",
            width=16,
        )
        self.convert_btn.pack(side="right")

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

    def _resting_drop_kind(self) -> str:
        return "paused" if self.running else "resting"

    def _set_drop_state(self, kind: str) -> None:
        if kind == "hot":
            bg = _Palette.DROP_HOT_BG
            border = _Palette.DROP_HOT_BORDER
        elif kind == "paused":
            bg = _Palette.DROP_PAUSED_BG
            border = _Palette.DROP_BORDER
        else:
            bg = _Palette.DROP_BG
            border = _Palette.DROP_BORDER
        for widget in self._drop_fill:
            widget.configure(bg=bg)
        self.drop.configure(highlightbackground=border, highlightcolor=border)

    def _apply_drop_chrome(self) -> None:
        self._set_drop_state(self._resting_drop_kind())
        if self.running:
            self.drop_title.configure(text=_DROP_PAUSED)
        else:
            self.drop_title.configure(text=_DROP_TEXT if self.dnd else _DROP_TEXT_NO_DND)

    def _on_drop_enter(self, event: tk.Event) -> object:
        if not self.running and self._event_on_drop_zone(event):
            self._set_drop_state("hot")
        return event.action

    def _on_drop_leave(self, event: tk.Event) -> object:
        self._set_drop_state(self._resting_drop_kind())
        return event.action

    def _on_drop(self, event: tk.Event) -> object:
        self._set_drop_state(self._resting_drop_kind())
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
            self.banner_label.configure(wraplength=max(self._px(240), event.width - self._px(160)))

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

    def _items(self) -> list[ClipItem]:
        return [self._rows[iid].item for iid in self._iids]

    def _add_paths(self, paths: Sequence[Path]) -> None:
        if self.running:
            return
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            items, ignored = collect_items(paths, self._items())
            staged: list[tuple[ClipItem, Optional[int], Optional[float]]] = []
            for item in items:
                size: Optional[int] = None
                mtime: Optional[float] = None
                try:
                    info = item.src.stat()
                except OSError:
                    info = None
                if info is not None:
                    size = info.st_size
                    mtime = info.st_mtime
                staged.append((item, size, mtime))
        finally:
            self.root.configure(cursor="")
        if not staged:
            message = "No .MTS/.M2TS files found in what you added."
            if ignored:
                message += " Ignored {0} other files.".format(ignored)
            self.status_var.set(message)
            return
        if not self.export_var.get().strip():
            self.export_var.set(str(core.default_output_dir(staged[0][0].root)))
        for item, size, mtime in staged:
            self._seq += 1
            iid = self.tree.insert(
                "",
                "end",
                values=(
                    item.src.name,
                    "Waiting",
                    format_size(size),
                    format_mtime(mtime),
                    str(item.src.parent),
                ),
            )
            self._rows[iid] = _Row(
                item=item,
                seq=self._seq,
                size=size,
                mtime=mtime,
                status="waiting",
                error="",
            )
            self._iids.append(iid)
        self._apply_sort()
        self._update_count()
        message = "Added {0} clips.".format(len(staged))
        if ignored:
            message += " Ignored {0} other files.".format(ignored)
        self.status_var.set(message)
        self._update_buttons()

    def _update_count(self) -> None:
        self.count_var.set("Clips: {0}".format(len(self._rows)))

    def remove_selected(self) -> None:
        if self.running:
            return
        selected = self.tree.selection()
        if not selected:
            return
        selected_set = set(selected)
        for iid in selected:
            self.tree.delete(iid)
            self._rows.pop(iid, None)
        self._iids = [iid for iid in self._iids if iid not in selected_set]
        self._restripe()
        self._update_count()
        self._update_buttons()

    def clear_all(self) -> None:
        if self.running:
            return
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self._rows.clear()
        self._iids.clear()
        self._restripe()
        self._update_count()
        self._update_buttons()

    def _on_delete_key(self, _event: tk.Event) -> str:
        if self.running:
            return "break"
        self.remove_selected()
        return "break"

    def _on_double_click(self, event: tk.Event) -> Optional[str]:
        region = self.tree.identify_region(event.x, event.y)
        if region == "separator":
            self._autofit(self._column_left_of(event.x))
            return "break"
        if region == "heading":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        row = self._rows.get(iid)
        if row is None or row.status != "failed":
            return None
        messagebox.showerror(
            "Conversion failed",
            "{0}\n\n{1}".format(row.item.src, row.error),
            parent=self.root,
        )
        return None

    def browse_export(self) -> None:
        if self.running:
            return
        current = self.export_var.get().strip()
        initial = current
        items = self._items()
        if not initial and items:
            initial = str(items[0].src.parent)
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
        self.gpu_decode_chk.configure(state="normal")
        self.jobs_combo.set_enabled(True)
        ready = bool(self._rows) and bool(self.export_var.get().strip()) and self._tools_ready()
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
        self.gpu_decode_chk.configure(state=state)
        self.jobs_combo.set_enabled(not running)
        if running:
            self.convert_btn.configure(text="Stop", state="normal")
        else:
            self._update_buttons()
        self._apply_drop_chrome()

    def _set_status(self, index: int, kind: str, text: str) -> None:
        if index < 0 or index >= len(self._iids):
            return
        iid = self._iids[index]
        row = self._rows.get(iid)
        if row is None:
            return
        self.tree.set(iid, "status", text)
        row.status = kind
        tags = self.tree.item(iid, "tags") or ()
        self._retag(iid, "odd" in tags)

    def _retag(self, iid: str, stripe: bool) -> None:
        row = self._rows[iid]
        stripe_tag = "odd" if stripe else "even"
        self.tree.item(iid, tags=(_STATUS_TAG[row.status], stripe_tag))

    def _restripe(self) -> None:
        for index, iid in enumerate(self.tree.get_children()):
            self._retag(iid, index % 2 == 1)

    def _snapshot_batch_order(self) -> None:
        self._iids = list(self.tree.get_children())

    def _on_heading_click(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = False
        self._apply_sort()
        self._update_heading_marks()

    def _update_heading_marks(self) -> None:
        for col, label in _HEADINGS.items():
            text = label
            if col == self._sort_col:
                mark = "▼" if self._sort_desc else "▲"
                text = "{0} {1}".format(label, mark)
            self.tree.heading(col, text=text)

    def _apply_sort(self) -> None:
        if self._sort_col is not None:
            ordered = sort_iids(self._rows, self._sort_col, self._sort_desc)
            for position, iid in enumerate(ordered):
                self.tree.move(iid, "", position)
        self._restripe()

    def _display_columns(self) -> tuple:
        raw = self.tree["displaycolumns"]
        if isinstance(raw, str):
            columns: tuple = (raw,)
        else:
            columns = tuple(raw)
        if columns == ("#all",):
            listed = self.tree["columns"]
            if isinstance(listed, str):
                return (listed,)
            return tuple(listed)
        return columns

    def _column_left_of(self, event_x: int) -> Optional[str]:
        cols = self._display_columns()
        if not cols:
            return None
        widths = []
        total = 0
        for col in cols:
            width = int(self.tree.column(col, "width"))
            widths.append(width)
            total += width
        if total <= 0:
            return None
        x = float(event_x) + float(self.tree.xview()[0]) * total
        best_col: Optional[str] = None
        best_dist: Optional[float] = None
        edge = 0.0
        for col, width in zip(cols, widths):
            edge += width
            dist = abs(x - edge)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_col = col
        return best_col

    def _autofit(self, col: Optional[str]) -> None:
        if col is None or col not in self._display_columns():
            return
        width = self._fonts.heading.measure(str(self.tree.heading(col, "text")))
        for iid in self.tree.get_children():
            measured = self._fonts.body.measure(str(self.tree.set(iid, col)))
            if measured > width:
                width = measured
        width += self._px(2 * 8)
        minimum = int(self.tree.column(col, "minwidth"))
        maximum = self._px(600)
        if width < minimum:
            width = minimum
        if width > maximum:
            width = maximum
        self.tree.column(col, width=width)

    def on_convert(self) -> None:
        if self.running:
            self._confirm_stop()
            return
        self._start_batch()

    def _start_batch(self) -> None:
        self._snapshot_batch_order()
        items = self._items()
        if not items or not self._tools_ready() or not self.ffmpeg or not self.ffprobe:
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
                items, out_dir, DEFAULT_OPTIONS.container
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
        for index, iid in enumerate(self._iids):
            self._rows[iid].error = ""
            self._set_status(index, "waiting", "Waiting")
        try:
            jobs = max(1, min(core.MAX_JOBS, int(self.jobs_var.get())))
        except (tk.TclError, ValueError):
            jobs = 1
        self._finished_files = 0
        self._active = {}
        self._batch_jobs = jobs
        self._batch_t0 = time.monotonic()
        self.progress["value"] = 0
        self.overall_pct_var.set("0%")
        self.cancel = threading.Event()
        self.running = True
        self._set_running_ui(True)
        opts = options_for(
            bool(self.deinterlace_var.get()),
            gpu_decode=bool(self.gpu_decode_var.get()),
        )
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
        count = len(self._iids)
        active: list[tuple[int, str, Optional[int]]] = []
        for index, entry in self._active.items():
            if index < 0 or index >= count:
                continue
            name = self._rows[self._iids[index]].item.src.name
            active.append((index, name, entry.pct))
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
            for index, entry in list(self._active.items()):
                if index < 0 or index >= len(self._iids):
                    continue
                text = self._active_row_text(entry)
                iid = self._iids[index]
                if self.tree.set(iid, "status") == text:
                    continue
                self._set_status(index, "active", text)
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
            self._set_status(index, "active", self._active_row_text(entry))
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
                self._set_status(index, "active", self._active_row_text(entry))
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
            status_kind = {
                "ok": "ok",
                "skipped": "skipped",
                "failed": "failed",
                "cancelled": "cancelled",
            }.get(status, "failed")
            if 0 <= index < len(self._iids):
                self._rows[self._iids[index]].error = err if status == "failed" else ""
            self._set_status(index, status_kind, text)
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
        count = len(self._iids)
        if count <= 0:
            self.progress["value"] = 0
            self.overall_pct_var.set("")
            return
        current = 0.0
        for entry in self._active.values():
            if entry.pct is not None:
                current += entry.fraction
        pct = (self._finished_files + current) / count * 100.0
        self.progress["value"] = pct
        self.overall_pct_var.set("{0}%".format(int(round(pct))))

    def _failed_names(self) -> list[str]:
        names = []
        for iid in self.tree.get_children():
            row = self._rows.get(iid)
            if row is not None and row.status == "failed":
                names.append(row.item.src.name)
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
