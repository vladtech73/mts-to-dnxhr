# Feedback: Desktop UI polish, sortable columns, resizable columns, higher contrast

*Loop signal: satisfied*

*Plan: [ui-polish-sort-resize-claude-2026-11-10.md](ui-polish-sort-resize-claude-2026-11-10.md) · Reviewer: grok · 2026-11-10*

## Verdict
solid-with-nits — The round-2 crash formulas are fixed in the steps, the checks that used to throw now pass, and the plan is safe to implement as written.

## Summary
Required sections are all present. The iid snapshot, the five-cell insert, the contrast list, and the `hwaccel-gpu-decode` core-file gate still match the tree. Tagged `natural_key` pairs produce the mixed-name order step 8 names, `None` sizes stay last in both directions without a `TypeError`, and the separator helper names the column to the left of every heading divider, including while the tree is scrolled.

## Blocking
None.

## Non-blocking
- **Make the new drop labels `tk.Label`s, and hook them up like `drop_label`.** Step 7 adds a title and a secondary line and puts both in `_drop_fill`. `_set_drop_bg` calls `configure(bg=...)` (`mts_to_dnxhr_gui.py:548-550`). On Tk 8.6.12 a `ttk.Label` raises `unknown option "-bg"`. The approach already says the drop zone is plain tk, so the new labels should be `tk.Label`s (secondary foreground from the palette). Bind `<Button-1>` to `_on_drop_zone_click` and call `_register_drop` on them, the same as `drop_label` at `:406-409`. Otherwise the title and the "or click to browse" line do not take a click or a drop.

## Nits
- Step 8 lists the Tk cases as 1, 2, 3, 4, 6, 5. Renumber so 5 is the row-values check and 6 is the stripe check.
- State the descending mixed-name result next to the ascending one. `sort_iids(..., "file", True)` on `00000.MTS`, `01 American Landscape.MTS`, `clip1.mts`, `Clip2.MTS` (added in that order, distinct keys) returns `Clip2.MTS`, `clip1.mts`, `01 American Landscape.MTS`, `00000.MTS`.
- Compare `displaycolumns` with `==`. The Tk 8.6.12 read-back is a fresh tuple `('#all',)`; `== ("#all",)` matches it. Identity comparison against a new `("#all",)` literal does not, and the helper would then call `tree.column("#all", "width")` and raise `TclError` again.

## Spot-checks
- Round-2 blockers, re-run and not re-opened: tagged `natural_key` on `["clip1.mts", "01 American Landscape.MTS", "Clip2.MTS", "00000.MTS"]` sorts to `00000.MTS`, `01 American Landscape.MTS`, `clip1.mts`, `Clip2.MTS` and does not raise. `_Reversed` descending file order is the list in Nits. Two `None` sizes sort last in both directions and keep add order (`seq` 0 before `seq` 1). `displaycolumns` is `('#all',)` and `tree.column("#all", "width")` raises `Invalid column index #all`. The plan's `#all` guard plus `tree["columns"]` is the path that works.
- Separator math on a mapped tree with the planned widths: every separator band (about 9 px) resolved to the left column, unscrolled and after `xview_moveto(0.25)` (actual fraction `(0.102, 1.0)`, offset 102 px). `identify_column` on those bands also named the left column (`#1` at the file/status divider). Setting the file width to 400 during a separator press survived `ButtonRelease` and `ttk::treeview::resize.release` / `drop`. Cursor from `ttk::cursor hresize` is `size_we`. Class `<Motion>` is still `treeview.tcl:104-118`.
- Required contrast pairs still clear 4.5:1. Weakest required pair is `ACTIVE_FG` `#0a5fb4` on `SELECT_BG` `#cce4f7` at 4.84. `TEXT_DISABLED` `#6b6b6b` on `SURFACE` is 4.84 (the 3.0 floor). The same gray on `DISABLED_BG` `#c8ccd1` is 3.30 and stays outside the test list, matching the disabled-control exemption already in step 8.
- Branch is `hwaccel-gpu-decode`. Uncommitted diff is still those four files, one jobs-default line each (`2 +-` per file). `git diff --stat main -- mts_to_dnxhr.py` is still `240 insertions, 57 deletions`. Cited sites still match: insert `641-645`, `_drop_fill` `401`, `SetProcessDpiAwareness` `1154` before `Tk()` at `1161`, `_poll` started only from `_start_batch` `869`, `jobs_var` `475`, `#666666` at `488` and `494`, `fg="red"` at `504`, minsize `350`, low-disk `/1e9` at `824`. `DefaultsTests.test_defaults_match_cli_encode_argv` is `tests/test_mts_to_dnxhr_gui.py:49`. README "A grey hint shows…" is line 125. `tests/test_mts_to_dnxhr.py:573` still asserts `args.jobs == 2`.
- Dev interpreter is Python 3.11.9, Tk 8.6.12, themes include `clam`. `requirements.txt` is tqdm and tkinterdnd2. `scripts/build_exe.ps1` still collects only `tkinterdnd2`. `samples/01 American Landscape.MTS` is on disk at 335,646,720 bytes. Zero-byte `.MTS` files still pass `is_input_file` (suffix plus `is_file()`). Vista-versus-clam was not re-rendered.

## Suggested steals / strengtheners
- In step 7: the new drop labels are `tk.Label`s, added to `_drop_fill`, bound to `_on_drop_zone_click`, and passed to `_register_drop`.
- In step 8, next to the mixed ascending order: descending file order is `Clip2.MTS`, `clip1.mts`, `01 American Landscape.MTS`, `00000.MTS`.
- In step 5: `if cols == "#all" or cols == ("#all",): cols = tree["columns"]`.

## Confidence
high — The new sort key, the `#all` read-back, contrast, separator hit-testing, the resize-release width, and the cited line numbers were executed or read in this tree. The vista theme was not given a fresh screenshot.
