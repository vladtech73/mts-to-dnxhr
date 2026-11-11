# Simple drop-and-convert GUI for MTS → DNxHR

*Author: claude · 2026-11-07*

## Goal

A small Windows desktop app, `MTS-to-DNxHR.exe`, that the user double-clicks instead of opening Shutter Encoder. It does three things:

1. Accepts `.MTS` / `.M2TS` files and folders by drag-and-drop or Browse.
2. Lets the user choose one export folder.
3. Converts everything with one **Convert** button. Progress is visible per file and for the whole batch, and each file ends as converted, skipped, failed, or cancelled.

Success looks like:

- The GUI calls `convert_one`, so it produces byte-for-byte the same encode argv (`force=True`, writing `*.mov.part`) as `python mts_to_dnxhr.py <clip>` with default flags: DNxHR HQX `yuv422p10le`, `.mov`, `pcm_s16le` 48 kHz, source resolution and frame rate, no deinterlace. The only GUI option is a **Deinterlace** checkbox, off by default. When ticked it adds the CLI's `--deinterlace` behavior.
- Encoding logic is reused from `mts_to_dnxhr.py` (`discover_inputs`, `output_path_for`, `find_collisions`, `convert_one`, `build_command`, `run_ffmpeg`, `probe`). The GUI does not duplicate any FFmpeg flags.
- Stop and window-close both kill ffmpeg and leave no `.part` files.
- The packaged exe runs from Explorer with no console window and no console flashes when ffmpeg runs.
- The exe has a **custom app icon** (`assets/app.ico`), not the default PyInstaller icon. The same icon shows on the exe in Explorer, on any shortcut or taskbar pin made from it, and in the running window's title bar, taskbar button, and Alt-Tab. The user starts the app by clicking that icon.
- The existing CLI behavior and the `tests/test_mts_to_dnxhr.py` suite are unchanged and still pass.

## Constraints

- **Wrap, don't fork.** `mts_to_dnxhr.py` stays the single source of truth for discovery, output mapping, collision checks, the ffmpeg argv, `.part` handling, and cleanup. Changes to it are limited to **optional, backward-compatible hooks** (step 1). With default arguments the CLI must behave exactly as it does now.
- **Python 3.9+ syntax** in both modules, matching the existing code: `from __future__ import annotations`, `Optional[...]`, no `match`, no runtime `X | Y`.
- **No `shell=True`, no string-built commands.** Dropped paths are untrusted input. They are only used as `Path` objects and argv items, through the existing `build_command`.
- **Never touch source media.** The GUI only reads inputs. It writes only under the chosen export folder. It never overwrites existing outputs: they are skipped, as in the CLI default.
- **Tk is single-threaded.** Only the main thread touches widgets. The encode runs on one worker thread, which sends events through a `queue.Queue`. The main thread polls that queue with `after(100, …)`.
- **Windowed exe realities.** In a PyInstaller `--windowed` build, `sys.stdout` and `sys.stderr` are `None`, so the GUI path must never call `tqdm`, `tqdm.write`, or `print`. Child processes need `CREATE_NO_WINDOW` and `stdin=DEVNULL`; otherwise consoles flash, or the inherited handles are invalid.
- **FFmpeg is not bundled.** This matches the CLI (README: "No installer … or bundled FFmpeg"), and it avoids GPL redistribution and a 100+ MB exe. The GUI must detect a missing FFmpeg and say so clearly.
- **Minimal UI.** The UI has no function menu, profile, container, or bit-depth pickers, GPU toggle, prefix/suffix, subfolder, delete-source, overwrite, or preset options. Settings chrome is limited to a single checkbox.
- **Icon artwork is original.** It is drawn by a script in this repo (step 7), not downloaded from an icon site or copied from Shutter Encoder, DaVinci Resolve, Avid, or FFmpeg branding. This avoids licensing and trademark questions. A missing or unreadable icon file must never stop the GUI from starting.
- **The repo is not a git repo.** Do not `git init`, commit, or publish without asking.
- The existing `.venv` is Python 3.11.9 with Tk 8.6 available. FFmpeg 8.0.1 (Gyan, WinGet) is on PATH on the dev machine.

## Existing data / APIs

Everything below is in `mts_to_dnxhr.py` and gets reused as is unless step 1 says otherwise:

| Symbol | Used by the GUI for |
|---|---|
| `INPUT_EXTENSIONS`, `is_input_file` | Filtering dropped and browsed paths |
| `discover_inputs(path, recursive=True)` | Expanding a dropped folder into clips, plus a count of ignored files |
| `default_output_dir(path)` | Prefilling the export folder from the first item added |
| `output_path_for(src, root, out_dir, container)` | Mapping each clip to its `.mov` path (loose file → `out/stem.mov`; folder → mirrored subfolders) |
| `find_collisions(pairs)` | Blocking a run when two clips map to one output (for example, `00000.MTS` from two cards) |
| `Options`, `build_parser()` defaults | GUI defaults are **derived from the CLI parser**, so they cannot drift |
| `find_tool`, `INSTALL_HINT` | FFmpeg/ffprobe detection |
| `convert_one(src, dst, opts, ffmpeg, ffprobe)` | Per-file probe, `.part` encode, rename, and cleanup. Returns `("ok" \| "skipped" \| "failed", err)` |
| `run_ffmpeg`, `probe` | Called through `convert_one`. Need hooks (step 1) |

Facts that matter for the GUI wrapper:

- `run_ffmpeg` (line 429) draws a `tqdm` bar and reads `-progress pipe:1` line by line. `parse_progress_line` turns each line into seconds. `_bar_total(info, opts)` gives the total.
- `convert_one` (line 517) reports through `tqdm.write`. It handles `KeyboardInterrupt` by re-raising, after `run_ffmpeg` has already stopped ffmpeg and unlinked the `.part`.
- `probe` (line 215) calls `subprocess.run` without `stdin` or `creationflags`. `run_ffmpeg` calls `Popen` with `stdin=DEVNULL` but no `creationflags`.
- Encoding the 168 s sample at HQX gives about 4.7 GB, roughly 14× the 335 MB source (README).

## Approach

**Stack: Python + Tkinter/ttk + `tkinterdnd2`, packaged with PyInstaller `--onefile --windowed`.**

- **Tkinter** is in the stdlib and already works in `.venv` (Tk 8.6). It adds almost nothing to the exe size, and it imports the conversion module directly, so there is no IPC and no re-parsing of CLI output.
- **`tkinterdnd2`** adds OS file drop (Explorer → window), which plain Tk lacks. It ships tkdnd binaries for Windows, macOS, and Linux. The import is guarded: without it, the app still runs with Browse buttons, and the drop-zone text changes to say drag-and-drop is unavailable.
- **PyInstaller `--onefile --windowed`** produces one double-clickable exe, which is what the user asked for. The tradeoffs are a 1–2 s startup while it unpacks and occasional antivirus or SmartScreen warnings on an unsigned exe (see Risks). `--onedir` is the fallback if AV becomes a problem. Swapping it is a one-flag change in the build script.
- **In-process wrapping with small hooks** instead of running the CLI as a subprocess and scraping tqdm output. Hooks give exact per-file status and fractional progress, and they allow a clean cancel. Scraping a TTY progress bar would be fragile.
- **Custom icon: a committed multi-size `assets/app.ico`, generated by `scripts/make_icon.py` (Pillow, build-time only).** The icon has two jobs on Windows, and each needs its own wiring:
  - *Exe file icon* (Explorer, desktop shortcut, Start/taskbar pin): embedded into the exe resources with PyInstaller `--icon`.
  - *Running-window icon* (title bar, taskbar button, Alt-Tab): Tk shows its feather icon unless told otherwise, so the app calls `root.iconbitmap(default=…)` on the same `.ico`, which is bundled with `--add-data`.

  The `.ico` is committed, so a normal build needs no Pillow and no regeneration. The script exists so the art is reproducible and easy to tweak. Users who prefer their own art can replace `assets/app.ico` with any multi-size `.ico` and rebuild.

  Alternatives considered: hand-drawing in an icon editor (not reproducible, and nothing to review in the repo); passing a PNG to `--icon` and letting PyInstaller convert it (one downscaled image, blurry at 16 px, and Tk's `iconbitmap` still needs a real `.ico`); a downloaded icon pack (licensing).

Alternatives considered and rejected:

- **PySide6/Qt**: native drop and nicer widgets, but the exe is ~60–100 MB, and the toolkit is heavy for three controls.
- **`windnd`**: tiny, but Windows-only and less maintained.
- **Electron/Tauri**: a second language and runtime for a three-control window.
- **Nuitka**: smaller and faster exe, but it needs a C toolchain. PyInstaller is the simpler default.

**Product decisions (fixed for the implementer):**

- **Deinterlace checkbox:** the only option. Off by default. 1080i AVCHD is common, and the README tells users to either set Field Dominance in Resolve or deinterlace, so a single checkbox earns its place. Everything else uses the CLI defaults.
- **Existing outputs are skipped**, as in the CLI without `--overwrite`. The row shows "Skipped (already exists)". There is no overwrite option.
- **Dropped folders are scanned recursively** (`discover_inputs(folder, recursive=True)`), so dropping an AVCHD card or its `PRIVATE` folder finds the `STREAM` clips. Outputs mirror subfolders under the export folder, using the same `output_path_for` semantics as `--recursive`.
- **Loose files** go to `<export>/<stem>.mov`.
- **Collisions block the run** with a dialog. This is the CLI's preflight rule.
- **The export folder is prefilled** with `default_output_dir(first item)`, but only while the field is empty. A user's choice is never overwritten. Nothing is persisted between sessions.
- **Disk-space warning (warn only):** if the estimated output (source bytes × 14, counting only outputs that don't exist yet) exceeds the free space on the export drive, ask before starting. The default answer is No.

## UI specification

Window title `MTS to DNxHR`. Default size 720×540; minimum 560×440; resizable. On Windows, call `ctypes.windll.shcore.SetProcessDpiAwareness(1)` (in a try/except) before creating the root so text is not blurry. Use the default ttk theme (`vista` on Windows). The only colors used are the drop-zone highlight and red text for the FFmpeg banner. The window icon is `assets/app.ico` (see **App icon** below); if it cannot be loaded, the app keeps Tk's default icon and starts normally.

### App icon

Fixed design, so the implementer does not have to make art decisions:

- **Canvas:** square, transparent outside a rounded-square tile (corner radius ≈ 18% of the side).
- **Tile:** a vertical gradient from `#2B3A55` (top) to `#16202F` (bottom).
- **Glyph:** a white film frame (a rectangle outline with three sprocket holes along the top and bottom edges) on the left 55% of the tile. An amber (`#F5A524`) right-pointing chevron on the right overlaps the frame's right edge. The chevron reads as "convert".
- **No text** at any size. Letters such as "DNx" are unreadable at 16–32 px.
- **Small sizes:** at 16 and 24 px, drop the sprocket holes and thicken the strokes to at least 2 px, so the frame and chevron stay distinct.
- **Sizes in the `.ico`:** 16, 20, 24, 32, 40, 48, 64, 128, 256. These cover 100–250% display scaling for small icons, the taskbar, and Explorer's large icons. The 256 entry is stored PNG-compressed, which is the Pillow default.

```
┌ MTS to DNxHR ─────────────────────────────────────────────────┐
│ ┌───────────────────────────────────────────────────────────┐ │
│ │                                                           │ │
│ │      Drop .MTS / .M2TS files or folders here              │ │  ← drop zone (~110 px tall)
│ │            [ Add files… ]   [ Add folder… ]               │ │
│ │                                                           │ │
│ └───────────────────────────────────────────────────────────┘ │
│ Clips: 3                                  [ Remove ] [ Clear ] │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ File                    │ Source folder        │ Status   │ │  ← ttk.Treeview, expands
│ │ 01 American Landscape…  │ D:\…\samples         │ Waiting  │ │
│ │ 00000.MTS               │ E:\PRIVATE\…\STREAM  │ 42%      │ │
│ └───────────────────────────────────────────────────────────┘ │
│ Export to: [ D:\Footage\dnxhr                     ] [Browse…] │
│ ☐ Deinterlace interlaced (1080i) clips                        │
│ Output: DNxHR HQX · MOV · PCM 16-bit 48 kHz · source size/fps │  ← grey, read-only
│ ⚠ FFmpeg was not found. … [Check again]                       │  ← only when missing
│ ─────────────────────────────────────────────────────────────  │
│ Converting 2 of 3: 00000.MTS (42%)                             │  ← status label
│ [██████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░]              │  ← overall progress bar
│                                               [  Convert  ]   │  ← primary button, wide
└───────────────────────────────────────────────────────────────┘
```

### Controls and behavior

| Control | Behavior |
|---|---|
| **Drop zone** (`tk.Label` or `Frame`, `relief="groove"`, light grey background) | Accepts file and folder drops. On `<<DropEnter>>` the background turns light blue; on `<<DropLeave>>` and `<<Drop>>` it reverts. Clicking the empty area opens **Add files…**. Without `tkinterdnd2` the text reads: "Drag-and-drop unavailable. Use Add files… or Add folder…". |
| **Add files…** | `filedialog.askopenfilenames`, with filetypes `[("AVCHD clips", "*.mts *.m2ts"), ("All files", "*.*")]`. |
| **Add folder…** | `filedialog.askdirectory`. The folder is scanned recursively. |
| **File list** (Treeview, `selectmode="extended"`) | Columns: File (name), Source folder (parent path), Status. Also a drop target. Rows are deduped by `os.path.normcase(abs path)`. The **Delete** key removes the selected rows, except while a batch is running, when it is ignored (row updates use list indexes). **Double-click** on a Failed row shows the full error (`messagebox.showerror`, title "Conversion failed", body = clip path + blank line + ffmpeg stderr tail). |
| **Clips: N** label | Count of rows. |
| **Remove** / **Clear** | Remove the selected rows, or all rows. Disabled while running. |
| **Export to** (`ttk.Entry`, editable) + **Browse…** | Browse uses `askdirectory(initialdir=current or first source folder)`. Prefilled with `default_output_dir(first added item)` only while the field is empty. |
| **Deinterlace** checkbox | Off by default. Maps to `Options.deinterlace`. |
| **Output summary** label | Static grey text built from the derived default `Options`, so it always matches the CLI defaults. |
| **FFmpeg banner** | Shown only when `locate_tools()` fails. Text: "FFmpeg was not found. Install it with `winget install Gyan.FFmpeg` (then sign out and back in), or put ffmpeg.exe and ffprobe.exe next to this program." The **Check again** button re-runs detection. |
| **Status label** | Idle: "Add clips, choose an export folder, then click Convert." Running: "Converting {i} of {n}: {name} ({pct}%)", where the displayed `{i}` is 1-based (event index + 1). On `file_started`, set the row to `0%`, or to `Converting…` if the total is unknown. If the duration is unknown, use "Converting {i} of {n}: {name}…". Done: "Finished: {ok} converted, {skipped} skipped, {failed} failed." Stopped: "Stopped: {ok} converted, {skipped} skipped, {failed} failed, {cancelled} not converted." |
| **Overall progress bar** | `ttk.Progressbar`, determinate, `value = (finished_files + current_fraction) / n × 100`. When the current file's duration is unknown, its fraction counts as 0 until it finishes. |
| **Convert** button | Enabled only when there is at least one row, the Export field is non-empty, FFmpeg was found, and nothing is running. While running, its text becomes **Stop** and it stays enabled. |

### Row status strings

| State | Text |
|---|---|
| Queued | Waiting |
| Running | `{pct}%`, or `Converting…` if the total is unknown |
| Done | Done |
| Skipped | Skipped (already exists) |
| Failed | Failed (double-click for details) |
| Cancelled / never started after Stop | Cancelled |

### Flows

- **Add:** each dropped or browsed path is handled as follows. A file with an MTS/M2TS extension adds one row with `root = file`. A folder goes through `discover_inputs(folder, True)` and adds one row per clip with `root = folder`. Anything else is ignored. After an add, the status label briefly reports: "Added {k} clips." If anything was ignored, it appends " Ignored {x} other files." If the add found nothing: "No .MTS/.M2TS files found in what you added." Discovery runs on the main thread with a busy cursor (`root.config(cursor="watch")`). Cards and folders are small; see Risks for huge folders.
- **Convert click:**
  1. Validation. The export path must be absolute; otherwise show "Choose a full folder path for Export to (use Browse…)." Then `mkdir(parents=True, exist_ok=True)`; on `OSError` show "Could not create the export folder:\n{path}\n\n{error}".
  2. Build the pairs with `plan_outputs`. If there are collisions, show `messagebox.showerror("Name clash", …)` with each destination followed by its sources, and the line "Remove one of these clips, or convert them in separate runs." Nothing is encoded.
  3. The disk-space warning is skipped when `free_bytes` returns `None`. If it is triggered, it uses `askyesno(..., default="no")` titled "Low disk space". Sizes are decimal GB (`bytes / 1e9`), so the 335 MB sample estimates about 4.7 GB. The body is: "This batch may need about {est:.1f} GB, but only {free:.1f} GB is free on {drive}. DNxHR HQX files are roughly 14× larger than camera files. Convert anyway?"
  4. Reset all rows to Waiting, disable the inputs (drop zone, Add, Remove, Clear, Export, Browse, checkbox), and start the worker.
- **Stop click:** `askyesno("Stop converting?", "The file being converted now will be deleted. Finished files are kept.")`. On yes, set the cancel event, disable the button, and show "Stopping…". The worker ends; the remaining rows become Cancelled.
- **Finish:** re-enable the controls and update the status label. Show a dialog: `showinfo` if nothing failed, `showwarning` if any did. It contains the summary line and up to 5 failed file names (with "…and N more" after that). **Only when `out_dir.is_dir()`** (Stop may have removed an empty export folder), it then asks "Open the export folder?" (`askyesno`). On yes, call `os.startfile(out_dir)` inside `try/except OSError`, guarded to `sys.platform == "win32"`. If the folder is gone, show only the summary dialog.
- **Close window while running:** `askyesno("Quit?", "A conversion is running. Stop it and quit?")`. On yes, set cancel, then poll every 100 ms until the worker thread is no longer alive, giving up after a 15 s cap. Then call `root.destroy()`. On no, do nothing.

## Implementation

### 1. Backward-compatible hooks in `mts_to_dnxhr.py`

All new parameters are keyword-only, with defaults that keep today's behavior.

- **Child-process flags.** Add `_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0`.
  - In `probe`, pass `creationflags=_CREATE_NO_WINDOW` and `stdin=subprocess.DEVNULL`.
  - In `run_ffmpeg`'s `Popen`, pass `creationflags=_CREATE_NO_WINDOW`.
  - In a console this changes nothing visible, because ffmpeg's stderr already goes to a temp file and its progress to a pipe.
- **Cancellation.** Add `class ConversionCancelled(Exception): """The caller asked to stop; ffmpeg was stopped and the .part removed."""`.
- **`run_ffmpeg(..., *, on_progress: Optional[Callable[[float, Optional[float]], None]] = None, cancel: Optional[threading.Event] = None)`**
  - When `on_progress` is `None`, keep the existing `tqdm` code path unchanged.
  - When it is provided, **do not construct a `tqdm` bar**: read the same lines and call `on_progress(seconds, total)` for each parsed line. After `proc.wait()` returns 0, call `on_progress(total, total)` **only when `total` is not `None`** (this mirrors lines 473–475).
  - Hoist `returncode = proc.wait()` out of the `with tqdm` block so both branches set it and fall through to the existing `.part` size check and `os.replace` (lines 476–483). The tqdm branch is otherwise unchanged.
  - Cancellation applies only to the `on_progress` branch. Write the check as `cancel is not None and cancel.is_set()`, once per line and once more just before `proc.wait()`. If it is true, `raise ConversionCancelled()`. The existing `except Exception` branch (lines 494–497) already stops ffmpeg and unlinks the `.part`. With `cancel=None` the check is a no-op, so it can never turn into an `AttributeError` that fails the encode.
- **`convert_one(..., *, log: Optional[Callable[[str], None]] = None, on_progress=None, cancel=None)`**
  - Use `emit = log or tqdm.write` for every current `tqdm.write` call.
  - Forward `on_progress` and `cancel` to `run_ffmpeg`.
  - **Order of the cancel checks.** If `cancel` is already set, raise `ConversionCancelled` after the existing exists-check (line 525) and **before `mkdir`** (line 529), so a cancelled file never creates `final_dst.parent`. A cancel that arrives later, during `run_ffmpeg`, is handled by `except ConversionCancelled: _remove_dir_if_empty(final_dst.parent); raise` on the `run_ffmpeg` try (lines 550–561). That clause goes after `except KeyboardInterrupt` and **before** `except OSError` / `except Exception`, so a cancel is never reported as `"failed"`.
  - A cancel set while `probe` runs is not seen until `run_ffmpeg` reads its first progress line. That is acceptable, because `probe` is short (see Risks).
- Add `import threading` and `Callable` to the `typing` import.

**Done when:** `.\.venv\Scripts\python.exe -m unittest -v` passes with no edits to the existing tests, `python mts_to_dnxhr.py "samples/01 American Landscape.MTS" --dry-run` prints the same command as before, and a CLI encode still shows the tqdm bars.

### 2. Tests for the hooks: `tests/test_mts_to_dnxhr.py` (new class `HookTests`)

No FFmpeg is needed. Mock `subprocess.Popen` with a fake whose `stdout` iterates `["out_time_us=500000\n", "out_time_us=1000000\n", "progress=end\n"]` and that has `poll`/`wait`/`terminate`/`kill`. The fake should create a non-empty `.part` file so the success path renames it. Its `poll()` must return `None` until `terminate` or `kill` is called (a `Mock` return value is not `None`, and `_stop_process` at line 390 would then skip `terminate`).

- With `on_progress` given and `cancel=None`: `on_progress` receives `(0.5, total)`, `(1.0, total)`, then `(total, total)`. `run_ffmpeg` returns `(True, "")`, the `.part` is gone, and the final file exists. `tqdm` is never constructed (patch `mts_to_dnxhr.tqdm` to raise if called). With `duration=None`, the final `(total, total)` call is not made.
- With `cancel` set after the first line, `run_ffmpeg` raises `ConversionCancelled`, `terminate` was called, and the `.part` file does not exist.
- `convert_one(..., cancel=<already set>)`, with a destination that does not exist, raises `ConversionCancelled`, does not return `"failed"`, and does not create the output dir.
- `convert_one` with `cancel` set during `run_ffmpeg` raises `ConversionCancelled` and leaves no empty output dir.
- `convert_one(..., log=list.append)` collects "wrote …" on success, and "skipped (exists): …" when the destination exists. Nothing is printed (`contextlib.redirect_stdout`/`stderr` capture is empty).
- On `win32`, `Popen` and `subprocess.run` receive `creationflags=subprocess.CREATE_NO_WINDOW`, and `probe` receives `stdin=subprocess.DEVNULL`. Patch both and inspect the kwargs.

**Done when:** the new tests pass and fail if the hook code is reverted.

### 3. GUI core (no Tk widgets): new file `mts_to_dnxhr_gui.py` at the repo root

The new module sits next to the CLI, matching the single-file style. This step writes the pure, testable part:

- **Imports.** `from __future__ import annotations` and `import dataclasses`. At the top of the module, **before** importing `mts_to_dnxhr` (which imports `tqdm`) or `tkinter`: if `sys.stdout` or `sys.stderr` is `None`, point it at `open(os.devnull, "w")`. This is the windowed-exe guard. Then `import mts_to_dnxhr as core`. Import `tkinterdnd2` inside `try/except ImportError` and set `DND_AVAILABLE`.
- **`DEFAULT_OPTIONS: core.Options`** is built from `core.build_parser().parse_args(["_"])`, using that result's `profile`, `container`, and `audio_bit_depth`, with `deinterlace=False`, `overwrite=False`, and `duration=None`. A helper `options_for(deinterlace: bool) -> core.Options` returns it via `dataclasses.replace`.
- **`OUTPUT_SUMMARY`** is the summary text built from `DEFAULT_OPTIONS`: profile `dnxhr_hqx` displays as "DNxHR HQX", plus the container in upper case and "PCM {bits}-bit 48 kHz", followed by the static tail "source size/fps".
- **`@dataclass(frozen=True) class ClipItem: src: Path; root: Path`**.
- **`collect_items(paths: Iterable[Path], existing: Sequence[ClipItem]) -> tuple[list[ClipItem], int]`** returns the new items and the count of ignored entries. Files use `core.is_input_file`; folders use `core.discover_inputs(p, recursive=True)`, which returns `(clips, skipped)`. The ignored count is the sum of the top-level non-MTS files, the nonexistent paths, and **`skipped` from every folder** (`ignored += skipped`). Folder-internal files such as `.CPI`, `README.md`, or an old `.mov` are counted only through `skipped`. Dedupe against `existing` and within the batch by `os.path.normcase(str(src))`. Catch `ValueError`/`OSError` per path (for example, permission denied while walking) and count those as ignored, without raising.
- **`plan_outputs(items, out_dir: Path, container: str) -> tuple[list[tuple[Path, Path]], dict[Path, list[Path]]]`** returns the pairs from `core.output_path_for(item.src, item.root, out_dir, container)` and the result of `core.find_collisions(pairs)`.
- **`estimate_needed_bytes(pairs) -> int`** returns the sum of `src.stat().st_size * 14` over pairs whose `dst` does not exist. Missing sources count as 0. Define `SIZE_RATIO = 14` and comment it with the README source.
- **`free_bytes(out_dir) -> Optional[int]`** calls `shutil.disk_usage` on the nearest existing ancestor and returns `None` on `OSError`. When it returns `None`, the GUI skips the disk warning.
- **`resource_path(rel: str) -> Path`** returns `Path(sys._MEIPASS) / rel` when `getattr(sys, "frozen", False)` and `_MEIPASS` exists (the onefile unpack dir), otherwise `Path(__file__).resolve().parent / rel`. **`ICON_PATH = resource_path("assets/app.ico")`**. This is used only for bundled read-only assets. FFmpeg lookup stays in `locate_tools`, which looks next to the exe, **not** in `_MEIPASS`.
- **`locate_tools() -> tuple[Optional[str], Optional[str]]`** checks first for `ffmpeg.exe` and `ffprobe.exe` next to `sys.executable` when `getattr(sys, "frozen", False)`, otherwise next to this file, then falls back to `core.find_tool`. Both must be found; otherwise return `(None, None)`.
- **`run_batch(pairs, opts, ffmpeg, ffprobe, post: Callable[[tuple], None], cancel: threading.Event) -> None`** is the worker body and has no Tk dependency. It posts these events:
  - `("file_started", i)`
  - `("file_progress", i, fraction_or_None)`: `seconds / total`, clamped to 0–1, or `None` if the total is unknown. Throttle so at most one event is posted per 1% change.
  - `("file_finished", i, status, err)`: `status` is one of `ok`, `skipped`, `failed`, `cancelled`.
  - `("batch_finished", ok, skipped, failed, cancelled)`: always posted, from a `finally` block.

  Before each file, if `cancel` is set, mark that file and every later file `cancelled`. Call `core.convert_one(src, dst, opts, ffmpeg, ffprobe, log=lambda s: None, on_progress=…, cancel=cancel)`. Catch `core.ConversionCancelled` **before** `Exception`: mark the current file and the rest as cancelled and stop. Any other unexpected exception becomes `failed` with `str(exc)`, and the loop continues. The thread must never die silently.

**Done when:** the module imports without a display or `tkinterdnd2`, and step 4's tests pass.

### 4. GUI core tests: new file `tests/test_mts_to_dnxhr_gui.py`

Each test uses temp dirs with empty `.MTS` files, as `tests/test_mts_to_dnxhr.py` already does.

- **Defaults parity.** `DEFAULT_OPTIONS` equals the `Options` that `core.main` would build from parser defaults. `core.build_command("ffmpeg", src, dst, DEFAULT_OPTIONS, info, force=True)` equals the argv the CLI builds for the same inputs, for interlaced and progressive `ProbeInfo`. This proves the GUI introduces no new flags. Also, `options_for(True)` adds yadif for an interlaced `ProbeInfo` and no yadif for a progressive one, matching the CLI with `--deinterlace`.
- **`collect_items`.** Covers a mixed drop: a clip, a `.txt`, a folder with `A/00000.MTS` and `B/00000.MTS` plus a `.CPI`, and a missing path. It yields 3 items and an ignored count of exactly 3 (the loose `.txt`, the missing path, and the `.CPI` from the folder's `skipped`). Adding the same paths again yields 0 new items. Case-variant duplicates are deduped on Windows.
- **`plan_outputs`.** A loose file maps to `out/clip.mov`. Folder items mirror to `out/A/00000.mov` and `out/B/00000.mov`. Two loose `00000.MTS` from different folders produce one collision group with both sources.
- **`estimate_needed_bytes`.** Skips pairs whose `dst` exists. `free_bytes` handles a not-yet-created out dir.
- **`run_batch`.** With `core.convert_one` mocked:
  - The event order is correct for ok, skipped, and failed results.
  - A `cancel` set during file 2 of 3 yields `cancelled` for files 2–3, and `batch_finished` reports `cancelled == 2`.
  - An exception from the mock becomes `failed`, and the batch continues.
  - `batch_finished` is always the last event.
- **`locate_tools`.** With `find_tool` patched to `None` and no exe-dir binaries, it returns `(None, None)`.
- **`resource_path`.** Unfrozen, it resolves under the module's directory. With `sys.frozen = True` and `sys._MEIPASS = <tmp>` patched (via `mock.patch.object(sys, …, create=True)`), it resolves under `<tmp>`.
- **Icon file** (stdlib only, no Pillow): `assets/app.ico` exists. Parse the ICONDIR header with `struct`: reserved `0`, type `1`, and the entry count. In each 16-byte entry, a width/height byte of `0` means 256. Assert that the set of sizes includes `{16, 24, 32, 48, 256}`, that every entry is square, and that every entry's offset + size lies within the file length.

The icon-file test lives in this module, but it does not import Tk. It runs in plain CI.

**Done when:** `.\.venv\Scripts\python.exe -m unittest -v` passes with FFmpeg off PATH and without `tkinterdnd2` installed (simulate by patching `sys.modules["tkinterdnd2"] = None` in one test that re-imports the module).

### 5. Tk UI: `App` class and `main()` in `mts_to_dnxhr_gui.py`

Build the UI exactly as specified in **UI specification** above.

- **Root window.** Use `tkinterdnd2.TkinterDnD.Tk()` when `DND_AVAILABLE`, else `tk.Tk()`.
- **Window icon.** Right after creating the root, on `sys.platform == "win32"`, call `root.iconbitmap(default=str(ICON_PATH))` inside `try/except tk.TclError`. The `default=` form also applies the icon to every `messagebox`/`filedialog` and Toplevel. On other platforms, skip this step: Tk's `iconbitmap` there does not take `.ico`, and non-Windows packaging is out of scope.
- **Taskbar identity.** In `main()`, before creating the root, on `win32` call `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MTSToDNxHR.App")` in a try/except. Without it, a run from source (`pythonw`) groups under Python's taskbar button and shows Python's icon. It is harmless in the exe.
- **Drop targets.** Register the drop zone and the Treeview with `drop_target_register(DND_FILES)` and `dnd_bind("<<Drop>>", …)`. Parse `event.data` with `self.root.tk.splitlist(event.data)`, which handles brace-quoted paths with spaces. Return `event.action` from the handler.
- **Worker.** A `threading.Thread(daemon=True)` runs `run_batch(..., post=self.events.put, cancel=self.cancel)`. `self._poll()` drains `self.events` with `get_nowait()` in a loop and reschedules itself with `after(100)` while running. Store failure text per row for the double-click dialog.
- **`main()`:**
  1. Set DPI awareness and the AppUserModelID, build `App` (which sets the window icon), run `mainloop()`. The `sys.stdout`/`sys.stderr` guard has already run at import time (step 3).
  2. Use the `if __name__ == "__main__": main()` guard. Nothing runs at import time.
- **Launch.** It can be started with `.\.venv\Scripts\pythonw.exe mts_to_dnxhr_gui.py` (no console) or with `python.exe` (console, for debugging).

**Done when:** the manual GUI checklist in **Verification** passes when run from source.

### 6. Dependencies

- **`requirements.txt`**: add `tkinterdnd2>=0.4,<0.5` next to `tqdm>=4.60`. Confirm the newest 0.4.x installs a cp311 win_amd64-compatible wheel in `.venv`. If the major/minor has moved on, pin to the verified one and note it here.
- **New `requirements-build.txt`**: `-r requirements.txt` plus `pyinstaller>=6,<7` and `pillow` (pinned to the major version that installs in `.venv`, for example `pillow>=11,<12`). Pillow is used only by `scripts/make_icon.py`. This file is for building only; the runtime does not need it.

**Done when:** `.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt` succeeds and `python -c "import tkinterdnd2, PyInstaller, PIL"` works.

### 7. App icon: new `scripts/make_icon.py` and committed `assets/app.ico`

- **`scripts/make_icon.py`.** Python 3.9+ syntax, with `from __future__ import annotations`. No CLI arguments beyond an optional `--out` (default: `<repo>/assets/app.ico`, resolved from `Path(__file__).resolve().parent.parent`). It draws the design in **UI specification → App icon**:
  - For each target size, render on a 4× supersampled RGBA canvas with `ImageDraw` (`rounded_rectangle`, `rectangle`, `polygon`; the gradient is drawn line by line). Downscale with `Image.LANCZOS`. Each size is rendered separately, not shrunk from the 256 image, so the 16/24 px variants can use the simplified glyph.
  - Save with `largest.save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=others)`. Pillow uses an appended image whose size matches exactly, instead of resizing.
  - Also write `assets/app-256.png` for the README and for review. This is optional for the build.
  - Print the written path and the sizes. Output is deterministic: no timestamps or randomness.
- **Run it once and commit the outputs** `assets/app.ico` and `assets/app-256.png`. Confirm that `.gitignore` does not exclude `assets/`. The current patterns (`*.mov`, `dnxhr/`, …) do not match it.
- **Self-check in the script.** After saving, reopen with `Image.open(out)` and assert that `img.info["sizes"]` contains every size in `SIZES`. Exit non-zero if it does not.

**Done when:**

- `.\.venv\Scripts\python.exe scripts\make_icon.py` writes both files, and its self-check passes.
- Opening `assets\app.ico` in Explorer (Large icons) and viewing `assets\app-256.png` shows the tile, frame, and chevron. The 16 px variant is legible. Check this by opening the `.ico` in Windows Photos or by temporarily viewing the folder in Small icons.
- Step 4's icon-file test passes.

### 8. Packaging: new `scripts/build_exe.ps1` and `.gitignore`

`scripts/build_exe.ps1` resolves the repo root from `$PSScriptRoot\..` and sets `$py` to `.\.venv\Scripts\python.exe` under that root, stopping with a clear message if it is missing. It sets `$ico = Join-Path $root 'assets\app.ico'` and stops with "Missing assets\app.ico. Run scripts\make_icon.py first." if that file does not exist. Then it runs this from the repo root (`Push-Location $root` / `Pop-Location`):

```powershell
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name "MTS-to-DNxHR" `
  --icon $ico `
  --add-data "$ico;assets" `
  --collect-all tkinterdnd2 `
  --specpath build --workpath build --distpath dist `
  mts_to_dnxhr_gui.py
```

The `--icon` and `--add-data` paths are **absolute**. With `--specpath build`, PyInstaller resolves relative data and icon paths against the spec directory (`build\`), not against the current directory, so `assets\app.ico` would not be found. `--icon` embeds the icon in the exe resources. `--add-data` places a copy at `_MEIPASS\assets\app.ico` for `iconbitmap`.

The script ends by printing the path to `dist\MTS-to-DNxHR.exe`. Add `build/` and `dist/` to `.gitignore`. With `--specpath build`, the generated spec stays out of the repo root.

**Done when:**

- `powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1` produces `dist\MTS-to-DNxHR.exe`.
- In Explorer, `dist\MTS-to-DNxHR.exe` shows the custom icon, not the PyInstaller snake. Check both the Large icons and Details views.
- Double-clicking it opens the window with no console. The title bar, taskbar button, and Alt-Tab all show the custom icon.
- Dragging the sample from Explorer onto the drop zone adds a row, which proves the tkdnd binaries were bundled.

### 9. README: `README.md`

- Add a **"Desktop app (Windows)"** section after **Usage** and before **Output layout**. It covers:
  - What the app does (drop clips, choose a folder, Convert), with the defaults it uses.
  - How to run it from source (`pythonw mts_to_dnxhr_gui.py`).
  - How to build (`scripts\build_exe.ps1` → `dist\MTS-to-DNxHR.exe`).
  - **Launching by icon.** The exe is self-contained. Copy it anywhere, such as `C:\Tools\MTS-to-DNxHR\`. Then right-click it and choose **Pin to Start** or **Pin to taskbar**, or **Show more options → Send to → Desktop (create shortcut)**. If you rely on the next-to-exe FFmpeg lookup, put `ffmpeg.exe` and `ffprobe.exe` in the folder where the **exe** lives, not where the shortcut is.
  - **Changing the icon.** Replace `assets\app.ico` (multi-size `.ico`), or edit and re-run `scripts\make_icon.py`, then rebuild. If Explorer still shows the old icon, run `ie4uinit.exe -show` or sign out and back in. This clears the icon cache.
  - That FFmpeg must be on PATH or next to the exe.
  - The SmartScreen "More info → Run anyway" note for an unsigned exe.
  - That existing outputs are skipped.
  - The folder-mirroring rule.
- In **Requirements**, replace "`tqdm` is the only Python dependency" with `tqdm` (CLI) and `tkinterdnd2` (GUI drag-and-drop).
- In **Profiles**, update "There is no free-space check before encoding." to say that the CLI has none and the GUI warns.
- In **Limitations**, change "No installer, `pyproject.toml`, or bundled FFmpeg. No GUI." to state that there is a minimal GUI (HQX/MOV/16-bit only; use the CLI for other profiles), and no installer, code signing, or bundled FFmpeg.

**Done when:** every command in the new section runs as written from the repo root.

## Verification

**Automated** (no FFmpeg or keys needed):

```powershell
.\.venv\Scripts\python.exe -m unittest -v
# FFmpeg hidden from PATH for this shell only:
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'ffmpeg' }) -join ';'; .\.venv\Scripts\python.exe -m unittest -v
```

**Opt-in smoke test** (real FFmpeg; unchanged CLI encode): `$env:MTS_SMOKE='1'; .\.venv\Scripts\python.exe -m unittest -v`

**CLI regression:** `.\.venv\Scripts\python.exe mts_to_dnxhr.py "samples/01 American Landscape.MTS" --dry-run` prints the same argv as before step 1.

**Manual GUI checklist.** Run once from source (`.\.venv\Scripts\pythonw.exe mts_to_dnxhr_gui.py`), then again from `dist\MTS-to-DNxHR.exe`:

1. Drop `samples\01 American Landscape.MTS` from Explorer. One row appears, and Export is prefilled with `…\samples\dnxhr`.
2. Drop the `samples` folder. No duplicate row is added; the status shows "Ignored N other files": 1 for `README.md`, plus 1 if a gitignored `samples\dnxhr\*.mov` from an earlier run exists.
3. Convert with the default settings.
   - Per-row % and the overall bar advance, and the status label follows the spec strings.
   - The finish dialog offers to open the folder.
   - The finished file in `samples\dnxhr\` is checked with: `ffprobe -v error -show_entries stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,sample_rate,channels -of compact "samples\dnxhr\01 American Landscape.mov"`. Expected: `dnxhd`, `DNXHR HQX`, `yuv422p10le`, 1920×1080, `30000/1001`, `pcm_s16le`, 48000, 2 channels. These match the README's verified CLI output.
4. Click Convert again. The row shows "Skipped (already exists)", and the dialog reports "0 converted, 1 skipped, 0 failed".
5. Delete the output, Convert, then **Stop** within 5 s and confirm.
   - The row shows Cancelled.
   - `Get-ChildItem samples\dnxhr -Filter *.part` returns nothing, and `Get-Process ffmpeg -ErrorAction SilentlyContinue` returns nothing.
   - The empty `dnxhr` folder is removed.
6. Start again, close the window mid-encode, and confirm Quit. Check the same: no `.part` file and no ffmpeg process.
7. Tick Deinterlace and convert. The resulting `.mov` keeps `avg_frame_rate=30000/1001` and has the same frame count as the CLI `--deinterlace` run (per README).
8. Add two `00000.MTS` copies from different folders as loose files. Convert shows "Name clash", and nothing is written.
9. Add a `.txt` and a `.mov`. Neither is added, and the status reports them as ignored.
10. Start the app with FFmpeg hidden from PATH (`$env:PATH=…` as above, then `pythonw`). The banner shows and Convert is disabled. After restoring PATH in that shell, **Check again** does not help (the process env is fixed), which is documented as expected. Separately, put `ffmpeg.exe` and `ffprobe.exe` next to the built exe; that copy works with FFmpeg off PATH.
11. In the exe build, no console window flashes during probe or encode.
12. Type a relative path such as `out` in Export. Convert shows the "full folder path" error.
13. **Icon.**
    - From source (`pythonw`), the title bar and taskbar button show the custom icon, not the Tk feather or the Python icon. The taskbar button is separate from any other Python window.
    - From the exe, `dist\MTS-to-DNxHR.exe` shows the custom icon in Explorer.
    - Create a desktop shortcut and pin the exe to the taskbar. Both show the custom icon, and clicking either one launches the app.
    - A `messagebox` (for example, the Name clash dialog) shows the custom icon in its title bar.
    - At 150% display scaling, the taskbar icon is crisp, not blurry.
14. **Icon fallback.** Temporarily rename `assets\app.ico` and run from source. The app starts with Tk's default icon, and no error dialog or traceback appears.

Clean up after verification: delete `samples\dnxhr\` (gitignored, about 4.7 GB).

## Risks

- **tkdnd not bundled.** If `--collect-all tkinterdnd2` misses the native tkdnd DLLs, the exe falls back to Browse-only (the guarded import keeps it working). Mitigation: step 8's done-when tests a real Explorer drop on the built exe. If it fails, add `--add-data` for the package's `tkdnd` folder explicitly.
- **AV and SmartScreen.** An unsigned `--onefile` exe can trigger a SmartScreen warning or an AV false positive. This is documented in the README. If it is persistent, switch to `--onedir`; code signing is out of scope.
- **Cancel latency.** Cancel is checked once per ffmpeg progress line (about every 0.5 s by default). If ffmpeg stalls without emitting progress (for example, on a hung network drive), Stop waits until the next line arrives. The 15 s close cap then destroys the window anyway. In that case the daemon thread dies with the process, but a stray `ffmpeg.exe` could survive. This is acceptable for v1 and noted for follow-up (a watcher thread that terminates `proc` directly). Likewise, `probe`'s `subprocess.run` (60 s timeout) does not see `cancel`, so a Stop during a probe waits for the probe to finish.
- **PATH not refreshed.** A process started from Explorer inherits Explorer's PATH, so FFmpeg installed after login may be invisible until the user signs out and back in. The banner text says so, and the exe-dir lookup is the escape hatch.
- **Huge folder drops.** Dropping a large tree (for example, a whole drive) scans recursively on the UI thread and can freeze the window. This is acceptable for cards and footage folders. Moving discovery to the worker is a follow-up if it bites.
- **Card-root mirroring.** Dropping a card root produces `export\PRIVATE\AVCHD\BDMV\STREAM\00000.mov`. That is correct and collision-safe, but deep. Users can drop the `STREAM` folder instead; the README mentions this.
- **Disk estimate is crude.** The 14× ratio comes from the one 1080i sample. Low-bitrate sources need more than 14×, so the estimate is a warning, not a guarantee. A disk-full failure mid-batch is already handled per file by `convert_one`.
- **Stale icon cache.** After a rebuild, Explorer may keep showing the old (or default) icon for `dist\MTS-to-DNxHR.exe` because Windows caches icons by path. This can look like `--icon` failed. Before debugging the build, run `ie4uinit.exe -show`, or copy the exe to a new path and check there. This is documented in the README.
- **Icon path resolution.** There are two places this can go wrong. First, a relative `--icon`/`--add-data` path with `--specpath build` silently resolves under `build\`; the build script uses absolute paths and fails fast if the `.ico` is missing. Second, at runtime the bundled copy lives in `_MEIPASS`, not next to the exe; `resource_path` handles that, the step 4 test covers it, and a load failure only falls back to the Tk icon.
- **Blurry small sizes.** If the `.ico` lacks a native size for the current DPI, Windows scales the nearest one, which looks soft. Mitigation: the nine-size set in **App icon**, per-size rendering, and verification item 13's 150% check.
- **Hook regressions.** Step 1 touches the CLI's hot path. The existing tests, the smoke test, and the dry-run argv comparison guard against this.

## Out of scope

- Profile, container, audio-bit-depth, or overwrite selectors in the GUI; presets; an "Advanced" panel. The CLI remains the tool for those.
- GPU decode or encode, parallel encodes, trimming or `--duration`, scaling, frame-rate conversion, LUTs, and a 59.94p field-rate deinterlace.
- Prefix or suffix naming, custom subfolder rules, deleting sources, and joining spanned clips.
- Bundling FFmpeg, an installer or MSI, code signing, and auto-update.
- Scripted creation of Start menu or desktop shortcuts. The README explains the manual Pin / Send to steps. Also out: a professionally designed or brand-matched icon, and `.icns`/Linux icon variants.
- Persisting settings or window state between sessions.
- macOS and Linux packaging. The code should stay cross-platform, but only Windows is built and verified.
- `git init`, commits, or publishing.

**Ready for implementation whenever you are.**
