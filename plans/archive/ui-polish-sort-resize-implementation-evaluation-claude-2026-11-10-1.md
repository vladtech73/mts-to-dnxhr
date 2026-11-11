# Desktop UI Polish, Sortable and Resizable Columns — Implementation Evaluation

*Claude Code turns used: 16 / max 100*

*Evaluator: claude · 2026-11-10 · Reviews the implemented `ui-polish-sort-resize-claude-2026-11-10.md` against the working tree (uncommitted changes on `ui-polish-sort-resize`, which has no commits ahead of `hwaccel-gpu-decode` @ `265794e`).*

## Verdict: All nine steps landed and every automated gate passes; only cheap Low polish gaps and unrun manual checks remain.

The iid-keyed row model, pure sort helpers, five-column table, heading sort with marks, separator auto-fit, horizontal scroll, centralized palette, `clam` theme, layout refresh, tests, and README all match the plan. The encode path, `mts_to_dnxhr.py`, requirements, and the build script have no changes. The unrelated jobs-default work sits in its own stash and did not leak in. No Critical or High issues turned up. The open items are a style `font` that does nothing on Entry/Spinbox, a default window that's 18 px too narrow for the default column widths, a large scaled `minsize`, and the plan's manual, DPI, and frozen-build checks, which have no recorded results.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 4 | Steps 1–9 are done. The TEntry/TSpinbox body font in step 6 has no effect, and the step 7 minsize differs from the plan's suggested size |
| Contract fidelity | 5 | Argv test passes. Core, requirements, and build script are unchanged. Batch order follows the displayed order, as the plan says |
| Verification honesty | 4 | Unit tests and grep gates pass, and `AppTableTests` runs instead of skipping. Manual, DPI, frozen-build, and screenshot checks (Verification 3–6) have no results |
| Finding severity | 4 | Low findings only |
| Merge readiness | 4 | Safe to merge after a short polish pass and the manual DPI check |

**Overall completeness:** 21/25 · **percent:** 84%
**Band:** nearly-done
**Open findings:** Critical 0 · High 0 · Low 4 · Trivial/Noted 7

## Loop signal

**Loop signal:** one-more-fix
**Signal rationale:** Each Low fix is a one- to three-line change (widget font, default geometry or column width, minsize clamp), plus one manual DPI and frozen-build pass, so one remediation round closes everything.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. iid-keyed rows** | Complete | `_Row` at `mts_to_dnxhr_gui.py:122-131`. `_rows`/`_iids`/`_seq` at `:743-745`. `_items()` at `:1071`. `_set_status` uses `tree.set(iid, "status")` and keeps the stripe (`:1251-1261`). `_snapshot_batch_order()` is the first line of `_start_batch` (`:1360`). The Waiting reset clears `row.error` (`:1415-1417`). `file_finished` stores the error by iid (`:1601-1602`). `_failed_names` and `_on_double_click` use `row.status == "failed"`. Grep gate is empty, and there are no `children[` reads |
| **2. Status kinds & tags** | Complete | `_STATUS_RANK` uses integer ranks in plan order (`:92-99`). `_STATUS_TAG` at `:100`. `_retag`/`_restripe` at `:1263-1270`, run after insert (via `_apply_sort`), remove, clear, and sort |
| **3. Pure helpers** | Complete | `natural_key` uses tagged pairs and skips empty pieces (`:134-144`). `format_size` uses decimal units (`:147-160`). `format_mtime` at `:163`. `_Reversed` at `:170`. `sort_iids` keys on `(missing, primary, seq)` and flips only the primary (`:187-223`). All are importable without Tk |
| **4. Columns, heading sort, marks** | Complete | `_COLUMN_LAYOUT` matches the plan's table, scaled through `_px` (`:101-107`, `:847-859`). The five-value insert matches the column order (`:1105-1115`). `_on_heading_click` and `_update_heading_marks` reset every heading's text (`:1275-1290`). `_apply_sort` runs at the end of `_add_paths` and not from status updates |
| **5. Resize / autofit / h-scroll** | Complete | Horizontal scrollbar at `:864-866`. No `<Motion>` binding was added (matches the plan). `_display_columns` resolves `#all` (`:1299-1310`). `_column_left_of` includes the xview offset (`:1312-1334`). `_on_double_click` checks the region before the row (`:1169-1175`). `_autofit` measures the heading and body fonts, adds `_px(16)`, and clamps to minwidth and `_px(600)` |
| **6. Palette / theme / fonts** | Partial (minor) | `_Palette` uses the plan's exact values (`:49-80`). `apply_theme` falls back on `TclError` (`:527-551`). Styles cover every listed widget, and the hex grep matches only the palette block. **But** `font=` on the `TEntry`/`TSpinbox` styles does nothing in ttk, so both stay at TkTextFont 9 pt (finding 1) |
| **7. Layout refresh** | Complete, with minsize deviation | Flat drop zone with a 2 px highlight and a title plus secondary line, both included in `_drop_fill` (`:781-812`). `_set_drop_state` handles hot/paused/resting (`:991-1003`). Bold `Clips: N` toolbar. `Labelframe("Export settings")` with a single options row. Banner uses `ERROR_*` colors with a 1 px border. Footer with an Accent Convert button. `rowconfigure(2, weight=1)` stays on the tree row. `minsize(_px(800), _px(620))` against the plan's "roughly 640×480" (finding 3) |
| **8. Tests** | Complete | `SortHelperTests` (6), `PaletteContrastTests`, and all six `AppTableTests` cases are present. The module docstring is updated. Fresh app per case, patches cleaned up through `addCleanup`, root children destroyed in `tearDown` |
| **9. README** | Complete | "A grey hint" became "A hint". The sort/resize/order paragraph is added and makes no claims about persistence (`README.md:125-127`) |

## Findings (ranked)

### 1. The `font=` option on the `TEntry` / `TSpinbox` styles does nothing, so the Export-to field and the Parallel spinbox stay at 9 pt. *(Low)*

Step 6 says to set the body font on `TEntry` and `TSpinbox` "so the whole window grows". `_apply_clam_styles` passes `font=body` to `style.configure("TEntry", …)` and `("TSpinbox", …)` (`mts_to_dnxhr_gui.py:643`, `:664`). ttk entries take their font from the **widget** option, not the style. A live probe confirmed this: `export_entry.cget("font")` and `jobs_spin.cget("font")` both return `TkTextFont`, which is Segoe UI **9**. The labels and buttons next to them are Segoe UI 10. The difference is small, but this plan's goal is a consistent, deliberate look.

**Remediation:** Pass `font=self._fonts.body` to `ttk.Entry(...)` (`:880`) and `ttk.Spinbox(...)` (`:904`), or call `tkfont.nametofont("TkTextFont").configure(size=10)` in `apply_theme`. Remove the two dead `font=` style keys.

### 2. The default window is narrower than the default columns, so the horizontal scrollbar is active at first launch. *(Low)*

The column widths add up to 220+230+90+140+320 = 1000 px. With outer padding and the vertical scrollbar, the root needs **1042** px of width (`winfo_reqwidth`), but `root.geometry("1024x680")` (`:732`, a new value, not scaled) opens it at 1024. Probe: tree width 986, `xview()` = `(0.018, 1.0)`, and `folder` stays at 320. Tk 8.6 doesn't shrink the stretch column to fit, so a fresh window always has 14 px of horizontal overflow and a live scrollbar. It looks unfinished at exactly the moment the plan's screenshot is taken (Verification 6).

**Remediation:** Either set `folder` width to 300 (total 980), or derive the geometry from the layout (`self._px(1060)` × `self._px(700)`, or open without geometry and let `reqwidth` decide). Add an `AppTableTests` assertion that `tree.xview() == (0.0, 1.0)` after `update()` at default size.

### 3. The scaled `minsize(800, 620)` can exceed the work area on 1080p screens above 150%. *(Low)*

The plan said to raise the old `560×440` to "roughly 640×480" if needed and to pick "the smallest size that doesn't clip". The implementation picks 800×620 and runs it through `_px`. The width is justified: the single options row alone measures 739 px (`reqwidth`), and the settings group measures 759. But at 175% scaling, the minimum becomes 1400×1085 device px, taller than a 1920×1080 panel's ~1032 px work area. The footer and **Convert** could end up below the taskbar with no way to shrink the window. At 150% (1200×930) it fits. There are no recorded results from the plan's DPI pass (Verification 4).

**Remediation:** Clamp to the screen with `minsize(min(px(800), sw - margin), min(px(620), sh - margin))` using `winfo_screenwidth`/`winfo_screenheight`. Consider lowering the height to about 560, since the tree row absorbs the shrink. Record the 100/150/200% results.

### 4. The plan's manual, DPI, frozen-build, and screenshot checks have no recorded results. *(Low)*

Verification 3–6 cover the manual run with dummy clips and the real 335 MB sample (green Done, accent bar, parallel timers), Stop leading to Cancelled, the ffmpeg-missing banner, drop-zone states, DPI at 100/150/200%, `scripts\build_exe.ps1` plus launching the exe, and a before/after screenshot pair. No notes or screenshots exist under `plans/draft/` or anywhere else. Automated coverage is strong, but the theme, DPI, and frozen-build risks the plan flags can only be checked by hand.

**Remediation:** Run Verification 3–6 before merge and write a short results note (or attach the screenshots to the PR).

### 5. A few pixel literals still skip `_px`. *(Trivial)*

`padx=4` on the Add buttons (`:814`, `:816`), `wraplength=640` (`:943`), and `max(240, event.width - 160)` (`:1048`). These are older than this change, but the plan's constraint says "every other pixel value … goes through one `_px(n)` helper". At 200% the banner wraps early, and the gap between the drop buttons halves relative to the text.

**Remediation:** Wrap them in `self._px(...)`.

### 6. Leftover scaffolding in the drop-zone code. *(Trivial)*

`self.drop_label = self.drop_title` (`:800`) is an alias, and the `registered_labels` loop that skips duplicates (`:818-824`) exists only because the alias puts the same label in the tuple twice. Iterating `(self.drop_title, self.drop_secondary)` once would do the same thing.

**Remediation:** Keep `drop_label` only if something outside the module uses it (nothing in the repo does), and replace the loop with a plain two-label loop.

### 7. Separator and double-click behavior is spot-checked but not tested. *(Trivial)*

Case 4 checks `_column_left_of` only with `xview()[0] == 0`, because the hidden root never scrolls. There's no test for the `separator`/`heading` branches of `_on_double_click` or for `_autofit`. A manual probe showed they work: after `xview_moveto(0.2)`, the separator at x=200 resolved to `file`. A double-click on the separator auto-fit `file` from 220 to 120 (clamped to minwidth). A heading double-click on a failed row left `showerror` uncalled.

**Remediation:** Optionally add two short `AppTableTests` cases: a double-click on a heading calls no messagebox, and `_autofit` clamps to minwidth and `_px(600)`.

### 8. Status tags color the whole row, not just the Status cell. *(Noted)*

ttk tag `foreground` applies to every cell, so Waiting rows show their file name, size, and folder in `#4d4d4d`, Failed rows in red, and so on. This follows from the plan's "each status tag sets only `foreground`", and every pair passes 4.5:1, so it is not a defect. Call it out in the screenshots so reviewers expect it.

**Remediation:** No action.

### 9. Disabled Convert text on `DISABLED_BG` isn't covered by the contrast test. *(Noted)*

`TEXT_DISABLED` on `DISABLED_BG` measures **3.3:1**. That passes the plan's 3.0 "within reason" floor, but the test checks `TEXT_DISABLED` only against `SURFACE`. Secondary text on `DROP_HOT_BG`/`DROP_PAUSED_BG` (7.37 / 6.76) is fine but also untested.

**Remediation:** Optionally add these pairs to `PaletteContrastTests`.

### 10. The Output summary sits below the Export-settings group, not inside it. *(Noted)*

Grid row 4 (`:919-924`) is outside the `Labelframe`. The plan's wording ("The Output summary goes below") allows either reading.

**Remediation:** No action.

### 11. The repo hygiene constraints were followed. *(Noted)*

The jobs-default change is in `stash@{0}` ("jobs-default-2 unrelated; stash before ui-polish-sort-resize"). The working tree keeps `IntVar(value=1)` (`:903`) and README "defaults to 1". `git diff --stat hwaccel-gpu-decode -- mts_to_dnxhr.py requirements*.txt scripts/build_exe.ps1` is empty. Nothing is committed yet, which matches "do not commit … without the user asking". The plan's "commits following steps 1–9" split will need to happen at commit time.

**Remediation:** No action.

## Net assessment

Merge-ready in substance. The risky part, re-keying rows from position to iid, is done thoroughly: no `values[2]`, `self.items`, `self.errors`, or `children[index]` remain, and case 2 shows that status and failed details follow the batch snapshot after a re-sort. Sort keys handle mixed digit and letter names and `None` values in both directions without `TypeError`. Before merge, fix the Entry/Spinbox font (finding 1) and the first-launch overflow (finding 2). Both are a few minutes of work. Then run the DPI and frozen-build pass (findings 3 and 4), since that's the only real way to catch theme and layout regressions. Findings 5–7 can wait or go in the same pass.

## Verification performed

- `.\.venv\Scripts\python.exe -m unittest -v` → **Ran 82 tests, OK (skipped=2)**. All six `AppTableTests`, the six `SortHelperTests`, and `PaletteContrastTests` ran and passed. `DefaultsTests.test_defaults_match_cli_encode_argv` passed.
- Grep gate 1, `grep -n 'values\[2\]\|self\.items\|self\.errors' mts_to_dnxhr_gui.py` → no matches. `grep -n 'children\['` → no matches.
- Grep gate 2, `grep -n '#[0-9a-fA-F]\{6\}\|fg="red"' mts_to_dnxhr_gui.py` → matches only lines 52–80 (the `_Palette` block).
- Core gate, `git diff --stat hwaccel-gpu-decode -- mts_to_dnxhr.py requirements.txt requirements-build.txt scripts/build_exe.ps1` → empty. `git log hwaccel-gpu-decode..HEAD` → no commits, so the branch point is `265794e`.
- `git stash show -p stash@{0}` → contains only the jobs 1→2 change, kept out of this work.
- Live Tk probe (temporary script under `D:\tmp\pwtest`, deleted afterwards):
  - Theme is `clam`, scale is 1.0, and the minsize is (800, 620).
  - Entry and spinbox font is `TkTextFont` (Segoe UI 9) against a body font of Segoe UI 10.
  - Root `reqsize` is 1042×738 (1042×800 with the banner) against a geometry of 1024×680. The tree is 986 px wide with `xview` (0.018, 1.0).
  - `identify_region` reports `separator` at ±3 px around each boundary, and `_column_left_of` named the correct left column every time, both unscrolled and scrolled.
  - Separator double-click auto-fit `file` from 220 to 120. A heading double-click didn't call `showerror`.
  - Rowheight is 25 (linespace 17 + 8). Tags alternate even/odd with a status tag on each row.
- Text measurements in the body font: `Failed (double-click for details) (1:23)` = 215 px, which fits the 230 px Status column. The hour form is 232 px and ellipsizes, which the plan accepts. The options row `reqwidth` is 739 px, which accounts for the 800 px minimum width.
- Extra contrast pairs: TEXT_SECONDARY on DROP_HOT_BG 7.37, on DROP_PAUSED_BG 6.76, on STRIPE 7.88. TEXT_DISABLED on DISABLED_BG 3.30.
- Not run: manual GUI pass with real or dummy clips, DPI 150/200%, `scripts\build_exe.ps1` and launching the frozen exe, screenshots (Verification 3–6).
