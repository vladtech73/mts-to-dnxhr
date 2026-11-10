# Desktop UI polish, sortable columns, resizable columns, higher contrast

*Author: claude · 2026-11-10*

## Goal

Make the desktop app (`mts_to_dnxhr_gui.py`) look like a deliberate, professional tool instead of default Tk, and add two table features:

- **Sort by column.** Clicking a clip-list heading sorts by that column, and clicking again reverses it. A ▲/▼ mark shows the active column and direction. File names sort naturally (`clip2` before `clip10`), sizes and dates sort numerically, and Status sorts by a fixed rank.
- **Resize column width.** Dragging a heading separator resizes the column, and the cursor changes over the separator so users can find it. Double-clicking a separator auto-fits the column to its content. A horizontal scrollbar appears when the columns are wider than the window.
- **More contrast, within reason.** One light palette defined in one place. Body text, secondary text, status colors, the accent button, headings, and the error banner all reach a WCAG 2.x contrast ratio of at least 4.5:1 against their backgrounds, and a unit test enforces it. No pure-black-on-pure-white glare and no dark mode.
- A clearer layout: grouped settings, a styled drop zone, an accent **Convert** button, colored per-row status, striped rows, and row heights that scale with DPI.

Success means every existing behavior still works: drop, add, remove, clear, convert, stop, quit-while-running, failed-row details, parallel progress, and the low-disk and name-clash dialogs. The encode argv stays byte-for-byte unchanged.

## Constraints

- **Encode path untouched.** `mts_to_dnxhr.py` does not change for this work. The GUI keeps calling `core.convert_one` through `run_batch` (`mts_to_dnxhr_gui.py:248`). `DefaultsTests.test_defaults_match_cli_encode_argv` (`tests/test_mts_to_dnxhr_gui.py:49`) must still pass.
- **Stdlib only.** Use `tkinter`/`ttk` and the built-in `clam` theme. Add nothing to `requirements.txt` or `requirements-build.txt`, and do not change the `--collect-*` flags in `scripts/build_exe.ps1`.
- **Tk is single-threaded.** Sorting, resizing, and styling all run on the Tk thread. The worker still talks only through `self.events` (`mts_to_dnxhr_gui.py:365`).
- **Python 3.9+ syntax**, matching the module: `from __future__ import annotations`, `Optional[...]`, no `match`. The dev venv is Python 3.11.9 with Tk 8.6.12.
- **Windows first.** The app calls `SetProcessDpiAwareness(1)` (`mts_to_dnxhr_gui.py:1154`), so the layout must hold at 100%, 150%, and 200% scaling. Row height comes from font metrics. Every other pixel value in this plan (column widths, padding, gaps, borders added to `linespace`) is a 100%-scaling value that goes through one `_px(n)` helper: `round(n * root.winfo_fpixels("1i") / 96)`.
- **Light theme only.** Keep the existing Segoe UI system font family; only size and weight change.
- **Keep the module's style.** Use `"{0}".format(...)` in user strings, private `_UPPER` constants near the top of the module, and pure helpers at module level so tests can import them without Tk.
- **Unrelated uncommitted work exists.** `git status` shows the `--jobs`/Parallel-encodes default change from 1 to 2 in `README.md`, `mts_to_dnxhr.py`, `mts_to_dnxhr_gui.py:475`, and `tests/test_mts_to_dnxhr.py:573`. Commit it on `hwaccel-gpu-decode` or stash it on its own before starting. Do not mix it into these commits. Stashing does not shift any GUI line cited below.
- Work on a new branch off the current `hwaccel-gpu-decode` HEAD, for example `ui-polish-sort-resize`. That HEAD is the **branch point** for the core-file gate in Verification; do not diff against `main`, which already differs in `mts_to_dnxhr.py` by about 240/57 lines. Do not commit or push without the user asking.

## Existing data / APIs

| Where | What it does today | Why it matters |
|---|---|---|
| `App._build` (`mts_to_dnxhr_gui.py:381-535`) | Builds every widget in one `outer` grid, rows 0-12 | Layout and theme changes go here |
| `self.tree` (`:425-443`) | `ttk.Treeview` with columns `file`, `folder`, `status`; `file` and `folder` use `stretch=True`; vertical scrollbar only | Sorting, resizing, and the new columns live here |
| `self.items` / `self.errors` (`:358-359`) | Parallel lists that must match `tree.get_children()` order **by position** | **Sorting breaks this.** It must change to stable iid-keyed rows first (step 1) |
| `_set_status_cell` (`:771`), `_on_double_click` (`:691`), `_failed_names` (`:1065`), `_refresh_running_status` (`:943`), `remove_selected` (`:656`) | Map a batch index to a row through `children = get_children()` then `children[index]`, and read status as `values[2]` | All of these must use the iid map and `tree.set(iid, "status")` |
| `tree.insert(..., values=(name, folder, "Waiting"))` (`:641-645`) | Writes all cells **by position** in column order | Must be rewritten whenever the column order changes (step 4) |
| `run_batch` events (`:248-333`) | `file_started` / `file_progress` / `file_finished` / `batch_finished` keyed by batch index into `pairs` | Stays the same. The batch index maps to an iid through a snapshot taken at Convert |
| `_DROP_BG`, `_DROP_HOT`, `_DROP_PAUSED_BG` (`:46-48`); `foreground="#666666"` (`:488`, `:494`); banner `fg="red"` (`:504`) | Colors scattered through the module | They move into one palette block |
| `tests/test_mts_to_dnxhr_gui.py` | Docstring says "No Tk window … required"; only pure helpers and `run_batch` are tested | New pure helpers get plain tests. App-level tests go in a skip-guarded Tk class (step 8) |
| `README.md` "Desktop app (Windows)" section | Describes the controls and says "A grey hint shows…" | Update it for sorting, resizing, the new columns, and the hint wording |

## Approach

**Primary path: stdlib `ttk` on the `clam` theme with a small, centralized palette, plus a refactor that keys clip rows by Treeview iid instead of position.**

1. **Data model first.** Sorting reorders rows, so the positional link between `self.items`/`self.errors` and `tree.get_children()` has to go before any sorting lands. Each row gets a `_Row` record stored in `self._rows: dict[str, _Row]` and keyed by its Treeview iid. `self._iids: list[str]` holds the batch order. When Convert is pressed, `self._iids` is rebuilt from the **current displayed order**, so clips encode in the order the user sees and batch indices stay fixed for the whole run. Sorting during a run only moves rows. Status updates find rows through the iid, so they still land on the right row.
2. **Sorting** is a pure function, `sort_iids(rows, column, descending) -> list[str]`. It is a stable sort with add-order as the tie-break. The App applies the result with `tree.move`, then restripes the rows. Heading clicks use `tree.heading(col, command=...)`. When new clips are added, the current sort is applied again. Status changes do **not** trigger a re-sort, so rows don't jump while encoding.
3. **Resizing** uses the native ttk separator drag, which already exists but is hard to find and limited because both text columns stretch to the viewport. The changes are: only the last column stretches, every column gets a `minwidth`, a horizontal scrollbar is added, and double-clicking a separator auto-fits that column. The resize cursor over separators is ttk's built-in class binding and is kept as is.
4. **Look and contrast** come from a `_Palette` constant block and an `apply_theme(root) -> _Fonts` function that configures `clam` styles and named fonts in one place. Plain `tk` widgets (the drop zone and the banner) take the palette explicitly.
5. **New columns: Size and Modified.** These make sorting useful, since sorting three text columns adds little. Both come from one `stat()` per clip, done while clips are added, under the existing watch cursor. No ffprobe is needed.
6. **Status sort order is the integer rank in `_STATUS_RANK` (step 2)**, chosen over lifecycle order (Waiting → Converting → Done). Ascending puts in-progress and pending work first, then problems (Failed, Cancelled), then finished work (Skipped, Done).

**Alternatives rejected:**

- *Keep the native `vista` theme and only tweak it.* On Windows, `vista` draws headings, buttons, and the progress bar with native elements that ignore `background`/`foreground`, so it can't deliver the contrast or the accent button.
- *`sv-ttk` (Sun Valley) or `ttkbootstrap`.* They look more modern but add a dependency and PyInstaller data collection, and image-based elements get slow on large Treeviews. That is too much for a polish pass. They could come back later if `clam` styling isn't enough.
- *Sorting only the display and leaving the positional lists alone.* That is fragile: every index lookup would need a translation layer, and failed-row details would point at the wrong clip.
- *Persisting column widths and sort across launches.* That needs a settings file under `%APPDATA%`. It is left as a follow-up (see Out of scope).

## Implementation

Steps are ordered. Each one should leave `python -m unittest -v` green and the app runnable.

### 1. Key clip rows by iid instead of position

File: `mts_to_dnxhr_gui.py`

- Add a module-level `@dataclasses.dataclass class _Row` with these fields: `item: ClipItem`, `seq: int` (add order), `size: Optional[int]`, `mtime: Optional[float]`, `status: str` (a status *kind*, see step 2), and `error: str`.
- In `App.__init__`, replace `self.items` / `self.errors` with `self._rows: dict[str, _Row]`, `self._iids: list[str]`, and `self._seq = 0`. Add a read-only helper `_items() -> list[ClipItem]` that returns `[self._rows[i].item for i in self._iids]`. Use it (or `self._iids` / `len(self._rows)` where only a count or emptiness check is needed) wherever `self.items` was read: `collect_items(paths, ...)` at `:627`, `_update_count` at `:654`, `browse_export` at `:715`, `_update_buttons` at `:751`, `_start_batch` at `:789`, `plan_outputs` at `:801`, `_running_prefix` at `:926`, and `_update_overall` at `:1052`. Done-check: `grep -n "self\.items\|self\.errors" mts_to_dnxhr_gui.py` returns nothing.
- `_add_paths` (`:621`): inside the existing watch-cursor block, `stat()` each new clip (catch `OSError`, which leaves `None`). Insert the row with the current three-column tuple (step 4 replaces it), keep the iid that `tree.insert` returns, and record a `_Row` and its iid.
- `remove_selected` (`:656`): drop the selected iids from `self._rows` and `self._iids`, then delete those rows from the tree. Don't enumerate `get_children()` by position.
- `clear_all` (`:676`): clear both containers.
- `_set_status_cell(index, text)` becomes `_set_status(index, kind, text)`. It finds the row through `iid = self._iids[index]`, writes the text with `self.tree.set(iid, "status", text)`, stores `kind` on the `_Row`, and applies the tags (step 2) by calling `_retag` with the row's **current** stripe (`"odd" in tree.item(iid, "tags")`), so progress updates never drop zebra striping. Remove every `values[2]` read. That includes `_refresh_running_status` at `:952`, which should read `self.tree.set(iid, "status")` instead.
- `_on_double_click` (`:691`) and `_failed_names` (`:1065`) use `self._rows[iid].status == "failed"` instead of `str(values[2]).startswith("Failed")`. `_on_double_click` shows `self._rows[iid].item.src` and `self._rows[iid].error` (replacing `self.items[index]` / `self.errors[index]` at `:703-706`). `_failed_names` takes the name from `self._rows[iid].item.src.name`.
- `_handle_event` `file_finished` (`:1023-1024`) stores `err` on the row through `self._rows[self._iids[index]].error`.
- The Waiting reset in `_start_batch` (`:842-843`) loops over `self._iids`, clears `row.error`, and calls `_set_status(index, "waiting", "Waiting")`.
- Add `_snapshot_batch_order()`, which sets `self._iids = list(self.tree.get_children())`. Call it at the top of `_start_batch` (`:788`), before `plan_outputs`, so `pairs[i]` and `self._iids[i]` refer to the same clip.

Done when the GUI behaves exactly as before with no sorting yet: add, remove, clear, convert, failed double-click, and the parallel row timers all work. `grep -n "values\[2\]\|self\.items\|self\.errors" mts_to_dnxhr_gui.py` returns nothing. The grep cannot prove there is no positional `children[index]` read (that pattern is too generic to grep); `AppTableTests` case 2 is the real gate.

### 2. Status kinds and row tags

File: `mts_to_dnxhr_gui.py`

- Define the status kinds as constants: `waiting`, `active`, `ok`, `skipped`, `failed`, `cancelled`. Add `_STATUS_RANK`, a dict of kind → **integer** rank (so `-rank` is valid when descending), for sorting (active < waiting < failed < cancelled < skipped < ok; ascending shows in-progress and pending rows first, then problems, then finished rows) and `_STATUS_TAG` to map each kind to a Treeview tag.
- `file_started` / `file_progress` set `active`, and `file_finished` maps `status` to its kind. The display text stays as it is now in `_handle_event` (`:1013-1021`).
- Add `_retag(iid, stripe: bool)`, which sets `tags=(status_tag, "odd"|"even")`, and `_restripe()`, which walks `get_children()` once and alternates the stripe.

Done when every row carries exactly one status tag and one stripe tag, `_restripe()` runs after insert, remove, clear, and sort, and `_set_status` preserves the row's existing stripe tag.

### 3. Pure helpers for sorting and display

File: `mts_to_dnxhr_gui.py`, next to `format_elapsed` (`:53`)

- `natural_key(text: str) -> tuple`: casefold the text, `re.split(r"(\d+)", ...)` it, **skip empty pieces**, and append a tagged pair per run: `(0, int(part))` for a digit run and `(1, part)` for a text run. Tagging keeps every comparison int-vs-int or str-vs-str; an untagged mix (`(0, ".mts")` vs `("clip", 1, ".mts")`) raises `TypeError` in `sorted` when digit-leading names like `00000.MTS` or `01 American Landscape.MTS` meet letter-leading names. `Clip2` sorts before `clip10`, and at the first differing slot a digit run sorts before a text run (so `00000.MTS` before `clip1.mts`).
- `format_size(n: Optional[int]) -> str`: decimal units to match the low-disk dialog's `/1e9` (`:824`). For example `"335 MB"`, `"4.7 GB"`, and `"—"` for `None`.
- `format_mtime(ts: Optional[float]) -> str`: local `YYYY-MM-DD HH:MM`, or `"—"`.
- `sort_iids(rows: Mapping[str, _Row], column: str, descending: bool) -> list[str]`, with these keys:
  - `file`: `natural_key(item.src.name)`
  - `folder`: `natural_key(str(item.src.parent))`
  - `size` and `mtime`: numeric, with `None` always last in both directions
  - `status`: `_STATUS_RANK`

  Every key is `(missing, primary, seq)`, where `missing` is `True` only for a `None` size or mtime. Ties keep add order and `None` stays last in both directions. When descending, flip **only** the primary, never the whole key (`reverse=True` would also flip `missing` and `seq`):
  - `size`, `mtime`: `primary = 0 if value is None else (-value if descending else value)`. Never negate `None`; the `0` stand-in only ties among missing rows (which `missing` already sorts last), so `seq` decides their order.
  - `status`: `-rank` when descending, `rank` otherwise.
  - `file`, `folder`: wrap the `natural_key` tuple in a small module-level `_Reversed` class whose `__lt__` returns `other.value < self.value` and whose `__eq__` compares values.

Done when the helpers are importable without creating a Tk root, and step 8 covers them.

### 4. Columns, heading sort, and sort indicator

File: `mts_to_dnxhr_gui.py`, `_build` tree block (`:425-443`)

- Set the columns, in this order: `file`, `status`, `size`, `mtime`, `folder`. Headings are **File**, **Status**, **Size**, **Modified**, and **Source folder**. Put the long path last so it truncates on the right.
- Rewrite the insert in `_add_paths` (`:641-645`) to write all five values in that order: `(item.src.name, "Waiting", format_size(size), format_mtime(mtime), str(item.src.parent))`. This is the only place that writes cells by position. All later status writes stay on `tree.set(iid, "status", text)`, and nothing rebuilds the values tuple.
- Column settings:

  | Column | width | minwidth | stretch | anchor |
  |---|---|---|---|---|
  | file | 220 | 120 | False | w |
  | status | 230 | 140 | False | w |
  | size | 90 | 70 | False | e |
  | mtime | 140 | 110 | False | w |
  | folder | 320 | 160 | True | w |

  Status must fit `Failed (double-click for details) (1:23)` at default width (≈215 px in Segoe UI 10); the hour form `(1:02:03)` measures ≈232 px and may ellipsize until auto-fit or a drag, which is accepted. Widths are in pixels at 100% scaling and go through `_px(...)` so they scale at higher DPI.
- Add `_HEADINGS = {"file": "File", ...}` and the sort state `self._sort_col: Optional[str] = None` and `self._sort_desc = False`. `tree.heading(col, text=..., command=lambda c=col: self._on_heading_click(c))`.
- `_on_heading_click(col)`: the same column toggles direction; a new column starts ascending. Then call `_apply_sort()` and `_update_heading_marks()`, which resets **every** heading's text from `_HEADINGS` and then adds `" ▲"` or `" ▼"` to the active column only, so marks never stack.
- `_apply_sort()`: if `self._sort_col` is set, call `tree.move(iid, "", pos)` for each iid in `sort_iids(...)`, then `_restripe()`. Also call it at the end of `_add_paths`. Don't call it from status updates.
- Sorting stays enabled while a batch runs, because it only moves rows (see step 1's snapshot).

Done when every column shows its own value after adding clips (Status shows `Waiting`, Size and Modified are filled, Source folder shows the path), clicking each heading sorts both ways with the right mark, newly added clips land in sorted position, and sorting mid-run doesn't misroute status or progress updates.

### 5. Column resizing: discoverability, auto-fit, horizontal scroll

File: `mts_to_dnxhr_gui.py`

- Add `ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)` at `row=1, column=0, sticky="ew"`, and wire it with `self.tree.configure(xscrollcommand=...)`.
- **Cursor:** add no binding. The ttk class binding `ttk::treeview::Motion` (`tcl/tk8.6/ttk/treeview.tcl:104-118`) already switches to the resize cursor (`size_we` on Windows) over a separator, and a widget-level `<Motion>` would be overwritten by it or, with `return "break"`, would also skip `ActivateHeading` and lose the `HEADING_ACTIVE` hover. Separators are hard to find today because both text columns stretch; the fixed widths and `minwidth`s above are what fix that. Verify the built-in cursor in the manual run.
- Add `_column_left_of(event_x) -> Optional[str]`: take `cols = tree["displaycolumns"]`; if it is `"#all"` or `("#all",)` (the Tk 8.6.12 default when `displaycolumns` is never set, which this plan doesn't set), use `tree["columns"]` instead, because `tree.column("#all", "width")` raises `TclError`. Sum `tree.column(c, "width")` over `cols`, offset by `tree.xview()[0]` times the total width, and return the column whose right edge is nearest `event_x`. Don't rely on `identify_column` near edges.
- Extend `_on_double_click` (`:691`). Check `tree.identify_region(event.x, event.y)` **first, before the `identify_row` empty-row return** at `:692-694` (a heading or separator hit has no row). If the region is `"separator"`, call `_autofit(_column_left_of(event.x))` and `return "break"`. If the region is `"heading"`, return without doing anything, so a double-click doesn't open failed details. Otherwise keep the current failed-details behavior.
- `_autofit(col)`: measure the heading text (in the bold heading font) and every cell value (in the body font) with `tkfont.Font.measure`. Add padding of `_px(2 * 8)`, clamp between the column's `minwidth` and `_px(600)`, then `tree.column(col, width=...)`.

Done when dragging any separator resizes the column, the cursor changes over separators, double-clicking a separator fits that column, columns wider than the window can be reached with the horizontal scrollbar, and shrinking the window never squeezes a column below its `minwidth`.

### 6. Palette, theme, and fonts

File: `mts_to_dnxhr_gui.py`. Replace the color constants at `:46-48` with one block.

- Add `_Palette` constants (light theme). Names are fixed; values are starting points that step 8 checks:

  | Name | Value | Used for |
  |---|---|---|
  | `SURFACE` | `#f3f4f6` | window, frames |
  | `FIELD` | `#ffffff` | tree, entry |
  | `STRIPE` | `#f5f7fa` | odd rows |
  | `TEXT` | `#1a1a1a` | body text |
  | `TEXT_SECONDARY` | `#4d4d4d` | hints, output summary (replaces `#666666`) |
  | `TEXT_DISABLED` | `#6b6b6b` | disabled labels and buttons |
  | `BORDER` | `#8a8f98` | field and button borders |
  | `HEADING_BG` / `HEADING_FG` / `HEADING_ACTIVE` | `#e1e4e8` / `#1a1a1a` / `#d0d5db` | Treeview headings |
  | `ACCENT` / `ACCENT_ACTIVE` / `ACCENT_FG` | `#0a5fb4` / `#084c90` / `#ffffff` | Convert, progress bar, focus |
  | `SELECT_BG` / `SELECT_FG` | `#cce4f7` / `#1a1a1a` | selected rows (light, so status colors stay readable on it) |
  | `OK_FG` | `#1e6b2e` | Done |
  | `FAILED_FG` | `#a4262c` | Failed |
  | `ACTIVE_FG` | `#0a5fb4` | Converting / % |
  | `MUTED_FG` | `#4d4d4d` | Skipped, Cancelled, Waiting |
  | `ERROR_BG` / `ERROR_FG` / `ERROR_BORDER` | `#fde7e9` / `#a4262c` / `#e8a3a8` | FFmpeg-missing banner |
  | `DROP_BG` / `DROP_HOT_BG` / `DROP_PAUSED_BG` / `DROP_BORDER` / `DROP_HOT_BORDER` | `#ffffff` / `#e5f1fb` / `#e4e6e9` / `#8a8f98` / `#0a5fb4` | drop zone states |
  | `DISABLED_BG` | `#c8ccd1` | disabled accent button |
  | `TROUGH` | `#dfe3e8` | progress bar trough |

- Add a module-level `_dpi_scale(root) -> float` returning `root.winfo_fpixels("1i") / 96`. `apply_theme` uses it for style padding, and `App._px(n)` returns `round(n * self._scale)` for widths, gaps, and autofit. Step 4's column widths depend on it, so add it with step 4 if step 6 lands later.
- Add `apply_theme(root) -> _Fonts`:
  - `style.theme_use("clam")`, wrapped in `try/except tk.TclError` so it falls back to the current theme. A styling failure must never stop the app from starting, the same rule as the icon at `:351-355`.
  - Named fonts derived from `TkDefaultFont` (Segoe UI 9 on this machine): body at 10 pt, heading at 10 pt bold, drop-zone title at 11 pt, and `Clips: N` at 10 pt bold. Set the body font on `TLabel`, `TButton`, `TCheckbutton`, `Treeview`, `TEntry`, and `TSpinbox` so the whole window grows, not just the headings.
  - Styles (all padding values go through `_px`):
    - `TFrame`, `TLabel`, `TCheckbutton`, and `TLabelframe` use the `SURFACE` background and `TEXT` foreground. `TLabelframe.Label` is a separate style and gets the same `SURFACE`/`TEXT` pair.
    - `Secondary.TLabel` uses `TEXT_SECONDARY`.
    - `TButton` gets padding `(10, 4)`, `BORDER`, and a hover/pressed `map`.
    - `Accent.TButton` uses `ACCENT`/`ACCENT_FG` with an active and disabled map. Disabled is `DISABLED_BG` with `TEXT_DISABLED`.
    - `TEntry` / `TSpinbox` get a `FIELD` background, including `readonly` in the `map` because the spinbox is readonly (`:482`), plus `BORDER` and an `ACCENT` focus border.
    - `Treeview` gets a `FIELD` background, `TEXT` foreground, `rowheight = linespace + _px(8)` (`linespace` is already in device pixels), and selection mapped to `SELECT_BG`/`SELECT_FG`.
    - `Treeview.Heading` uses the `HEADING_*` colors, the bold font, and padding `(8, 4)`.
    - `Horizontal.TProgressbar` uses `ACCENT` on a `TROUGH` trough, with thickness from font metrics.
    - `TScrollbar` uses neutral colors.
  - Tree tags: `odd` gets the `STRIPE` background, and each status tag sets only `foreground`.
  - `root.configure(bg=SURFACE)`.
- Call `apply_theme(self.root)` at the start of `App.__init__`, before `_build`, and keep the returned fonts on `self._fonts` for `_autofit`.

Done when the app starts on `clam` with the palette applied everywhere. The only remaining hex literals are in the palette block, so `grep -n "#[0-9a-fA-F]\{6\}" mts_to_dnxhr_gui.py` returns matches only there.

### 7. Layout refresh

File: `mts_to_dnxhr_gui.py`, `_build` (`:381-535`), `_apply_drop_chrome` (`:555`), `_set_drop_bg` (`:548`), `_on_configure` (`:596`)

- `outer` padding goes to `_px(12)`, with consistent `_px(8)` vertical gaps.
- **Drop zone** (`:389-410`): change `relief="groove", bd=2` to `relief="flat", bd=0, highlightthickness=2` using `DROP_BORDER`. Use a title label in the drop font plus one `Secondary` line, such as "or click to browse". Add both new labels to `self._drop_fill` (`:401`) so the state recolor reaches them. Add-files and Add-folder buttons stay. The hot and paused states change both the background and `highlightbackground`. `_set_drop_bg` becomes `_set_drop_state(kind)` and is used by `_on_drop_enter`, `_on_drop_leave`, `_on_drop`, and `_apply_drop_chrome`. The existing texts `_DROP_TEXT`, `_DROP_TEXT_NO_DND`, and `_DROP_PAUSED` are kept.
- **Clips toolbar** (`:412-419`): `Clips: N` in the bold font on the left; Remove and Clear on the right.
- **Settings group:** one `ttk.Labelframe(text="Export settings")` holds the Export-to row (`:445-454`, unchanged behavior) and **one options row** with the Deinterlace checkbox, GPU decode checkbox, and Parallel encodes spinbox. The hint uses `Secondary.TLabel` (replacing `foreground="#666666"` at `:488`). The Output summary goes below as a `Secondary.TLabel` (`:491-496`). This replaces grid rows 3-7 and frees vertical space for the list.
- **Banner** (`:498-511`): a `tk.Frame` with `ERROR_BG` and a 1 px `ERROR_BORDER` highlight, and a label in `ERROR_FG` on `ERROR_BG` (replacing `fg="red"`). The **Check again** button stays. `_apply_tools_banner` keeps `grid()`/`grid_remove()`.
- **Footer:** separator, then the status label, then the progress bar with its % label, then Convert using `style="Accent.TButton"`, right-aligned. The Stop state keeps the accent style; only the text changes, as it does now at `:766`.
- Raise `self.root.minsize` (`:350`, today `560, 440`) to roughly 640×480 at 100% if the new grouping clips at 150% scaling. Check this in Verification and pick the smallest size that doesn't clip. The value you keep goes through `_px` (`minsize(self._px(w), self._px(h))`) so it scales with the fonts.
- Renumber grid rows. `outer.rowconfigure(<tree row>, weight=1)` must stay on the tree row so only the list grows.

Done when every control from before is still present with the same behavior, nothing clips at 100%, 150%, or 200% scaling, and the list area takes up the extra height when the window is resized.

### 8. Tests

File: `tests/test_mts_to_dnxhr_gui.py`

- **Pure tests** (no Tk):
  - `natural_key` ordering: `["clip10.MTS", "Clip2.MTS", "clip1.mts"]` sorts to `clip1, Clip2, clip10`.
  - `natural_key` mixed shapes: `sorted(["clip1.mts", "01 American Landscape.MTS", "Clip2.MTS", "00000.MTS"], key=natural_key)` does not raise and gives `00000.MTS, 01 American Landscape.MTS, clip1.mts, Clip2.MTS` (digit-leading before letter-leading). Also run it through `sort_iids(..., "file", True)` to cover `_Reversed` on the same mix.
  - `format_size` / `format_mtime`, including `None`.
  - `sort_iids` for each column in both directions, with `None` sizes last both ways (including **two** `None` rows, which must not raise and keep add order), ties in add order both ways, and status rank order.
- **Contrast test:** add a `_contrast_ratio(fg, bg)` WCAG helper in the test file. Assert at least 4.5 for:
  - `TEXT` and `TEXT_SECONDARY` on `SURFACE` and `FIELD`
  - each status foreground on `FIELD`, `STRIPE`, and `SELECT_BG`
  - `ACCENT_FG` on `ACCENT` and `ACCENT_ACTIVE`
  - `HEADING_FG` on `HEADING_BG` and `HEADING_ACTIVE`
  - `ERROR_FG` on `ERROR_BG`
  - `TEXT` on every `DROP_*_BG`

  Assert at least 3.0 for `TEXT_DISABLED` on `SURFACE` (a "within reason" floor; WCAG exempts disabled controls).
- **Tk-backed App tests**, in a new class `AppTableTests`. Each case gets a fresh app so sort state, failed rows, and deletions never leak between cases:
  - `setUpClass` only owns the shared root: try `tk.Tk()` and call `root.withdraw()`; on `tk.TclError`, skip the class. `tearDownClass` destroys the root.
  - `setUp` starts patches for `gui.locate_tools` (returns `("ffmpeg", "ffprobe")`) and `messagebox.*` (no-ops) and registers each with `self.addCleanup(patcher.stop)`. It creates a `TemporaryDirectory` (also cleaned up), writes the fixed fixture `clip10.MTS`, `Clip2.MTS`, `clip1.mts` (zero bytes, added in that order so add-order differs from natural order), builds `App(root, dnd=False)`, and adds the files through `app._add_paths`.
  - `tearDown` destroys every child of the root (`for w in root.winfo_children(): w.destroy()`). The tests inject events into `_handle_event` directly and never start `_poll`, so no `after` callbacks outlive a case.

  Cases:
  1. `_on_heading_click("file")` gives `clip1, Clip2, clip10` and the ▲ mark; a second click gives reverse order and ▼, and no heading text contains two marks.
  2. After sorting, `_snapshot_batch_order()`, then sorting by another column, then injecting `("file_started", 0)` and `("file_finished", 0, "failed", "boom")` into `_handle_event`: the status lands on `app._iids[0]`'s row, and `_failed_names()` returns that clip's name.
  3. `remove_selected` on a sorted view removes the right `_Row`s, and stripes alternate afterwards.
  4. Separator lookup: with `displaycolumns` left at its default (`#all`), `_column_left_of(x)` from step 5 returns the left column for an x on each boundary and does not raise.
  6. Stripe survives status: after `_restripe()`, `_set_status(i, "active", "Converting…")` on an odd row leaves `"odd"` in `tree.item(iid, "tags")`.
  5. Row values: after setup, `tree.set(iid, "status") == "Waiting"`, `tree.set(iid, "folder") == str(app._rows[iid].item.src.parent)`, and `size` / `mtime` are non-empty for every row (guards the step 4 insert tuple).
- Update the module docstring (`:1`) to say that the Tk-backed tests skip themselves when no Tk display is available.

Done when `.\.venv\Scripts\python.exe -m unittest -v` passes and the new tests run (not skip) on the dev machine.

### 9. README

File: `README.md`, "Desktop app (Windows)" section

- Change "A grey hint shows…" to "A hint shows…".
- Add one short paragraph: click a column heading to sort (click again to reverse); drag a heading divider to resize; double-click a divider to fit the column; clips convert in the order shown; and Size and Modified come from the source file.

Done when the README matches the shipped UI and makes no claims about persistence.

## Verification

1. **Unit tests:** `.\.venv\Scripts\python.exe -m unittest -v` passes. `AppTableTests` runs on the dev machine rather than skipping, and the contrast test passes.
2. **Static checks:**
   - `grep -n "values\[2\]\|self\.items\|self\.errors" mts_to_dnxhr_gui.py` returns nothing (step 1). Positional `children[index]` reads are gated by `AppTableTests` case 2, not by grep.
   - `grep -n "#[0-9a-fA-F]\{6\}\|fg=\"red\"" mts_to_dnxhr_gui.py` matches only the palette block (step 6).
   - After the jobs-default change is committed on `hwaccel-gpu-decode` or stashed, `git diff --stat hwaccel-gpu-decode -- mts_to_dnxhr.py` (the branch point) is empty. Do not use `main` here; it already differs by about 240/57 lines.
3. **Manual run from source:** `.\.venv\Scripts\pythonw.exe mts_to_dnxhr_gui.py`. Create test clips in PowerShell:
   ```powershell
   $d = "$env:TEMP\mts-ui"; New-Item -ItemType Directory -Force $d | Out-Null
   'clip1','Clip2','clip10','b','A' | ForEach-Object { Set-Content "$d\$_.MTS" ('x' * (Get-Random -Max 5000)) }
   ```
   Drop or add the folder, then check:
   - Clicking each heading sorts natural, numeric, and by status rank; ▲/▼ toggles.
   - The built-in resize cursor shows over a heading divider and headings still highlight on hover; dragging resizes; double-clicking fits; the horizontal scrollbar appears when columns are too wide.
   - Convert with an export folder: dummy clips fail, so Failed rows show in red. Double-clicking a failed row shows the error. Double-clicking a heading or divider does not.
   - Sort by Status during or after the run. Failed details still match the right file.
   - Also convert the real clip in `samples/01 American Landscape.MTS` (335 MB in; the finished HQX file is about 4.7 GB, so use an export folder with room and expect a full encode). This pass checks that the Done row shows green, the progress bar uses the accent color, and parallel row timers update with Parallel encodes set to 2.
   - In a separate pass on the same clip, press Stop partway: it asks for confirmation and marks rows Cancelled. This pass does not need to wait for the full file.
   - Rename ffmpeg off PATH, or test on a machine without it: the error banner uses the new colors and **Check again** works.
   - Drop-zone hover, paused, and resting states all look different.
4. **DPI:** repeat the layout check at 100%, 150%, and 200% scaling (Settings → Display). Nothing clips, row height fits the text, and the minimum window size holds.
5. **Frozen build:** run `powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1`, then launch `dist\MTS-to-DNxHR.exe`. The theme applies with no console window and no missing-resource errors. `clam` is built into Tk, so nothing new needs bundling.
6. **Screenshot pair:** capture before and after shots of the main window at 100% with the same clips loaded, for the PR description.

## Risks

- **Index/iid regressions (highest).** Status, progress, failed details, and `_failed_names` currently depend on positional order. Any lookup missed in step 1 would send updates to the wrong row once sorting exists. Mitigation: do step 1 alone, run the grep gate, and add `AppTableTests` case 2.
- **`clam` looks less native.** Checkboxes and scrollbars won't match Windows 11 controls exactly. Mitigation: style them with the palette. If the result still looks off, revisit `sv-ttk` in a separate plan.
- **Tag colors vs selection colors.** In some Tk 8.6 patch levels, tag `foreground` wins over the style's selected `map`. With a light `SELECT_BG`, every status color stays at least 4.5:1 either way, and the contrast test checks it.
- **Separator hit-testing.** `identify_region` reports "separator" a few pixels to each side of the boundary, and `identify_column` can name the right-hand column. The step 5 helper computes the boundary explicitly (resolving the default `#all` to `tree["columns"]`); test case 4 covers it.
- **Sort-key type errors.** Mixed digit/text filename runs and `None` sizes can both raise `TypeError` inside `sorted`. Step 3 tags runs and uses a numeric stand-in for `None`; step 8 tests both mixes.
- **Heading double-click toggles the sort twice.** ttk fires the heading command on each click, so a double-click on the current sort column ends in its previous direction, and on a different column ends descending. This double toggle is accepted.
- **DPI layout.** Larger fonts and padding plus the new group frame could clip at 200% or at the old `minsize`. Covered by Verification step 4.
- **Stat cost on add.** One `stat()` per clip on the Tk thread is cheap next to the discovery `collect_items` already does there. Very large card dumps on slow USB readers could add a moment under the watch cursor.
- **Convert order changes meaning.** Clips now encode in the displayed order, not the order they were added. This is intended and documented in the README (step 9).

## Out of scope

- Dark mode, theme switching, or following the Windows accent color.
- Third-party theme packages (`sv-ttk`, `ttkbootstrap`, and similar).
- Saving column widths, column order, or sort state between launches.
- Reordering columns by drag, hiding columns, or filter and search boxes.
- Probing duration, resolution, or frame rate for extra columns, which would need ffprobe at add time.
- Any change to `mts_to_dnxhr.py`, encode options, or the CLI.
- Tooltips, menus, an About dialog, keyboard shortcuts beyond the existing Delete key, and localization.
- Changing the status wording in `_handle_event` beyond what the new layout needs.

## PR split

Use one branch, with commits following steps 1-9. If review size matters, split it in two:

1. **Table PR:** steps 1-5 and the pure and App tests from step 8, plus the README sort/resize paragraph. This is the functional, testable work.
2. **Look PR:** steps 6-7, the contrast test, and the README hint wording. This one is visual only and goes on top.

**Ready for implementation whenever you are.**
