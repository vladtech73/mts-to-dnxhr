# Feedback: Desktop UI polish, sortable columns, resizable columns, higher contrast

*Loop signal: revise*

*Plan: [ui-polish-sort-resize-claude-2026-11-10.md](ui-polish-sort-resize-claude-2026-11-10.md) · Reviewer: grok · 2026-11-10*

## Verdict
ship-after-fixes — Round 1's three blockers are fixed in the code's terms; two steps still crash if an implementer follows them literally.

## Summary
The iid snapshot, the five-value insert, the `hwaccel-gpu-decode` core-file gate, and a fresh `App` per test now match the tree. Contrast pairs in step 8 still clear 4.5:1 (weakest required pair is 4.84:1). The encode path, stdlib limit, and jobs-default diff are unchanged and still described correctly.

Two new spot-checks fail on this machine. `natural_key`, as specified, raises `TypeError` when a digit-leading name is sorted with a letter-leading name, and the planned tests never mix those shapes. `_column_left_of` sums `displaycolumns`, which Tk 8.6.12 returns as `('#all',)`, and `tree.column("#all", "width")` throws.

## Blocking
- **`natural_key` crashes on mixed filename shapes.** Step 3 casefolds the name and splits it into digit and non-digit runs, then compares digit runs as ints in the same tuple as the text runs. On Python 3.11.9 that key is `(0, '.mts')` for `00000.MTS` and `('clip', 1, '.mts')` for `clip1.mts`. `sorted` raises `TypeError: '<' not supported between instances of 'str' and 'int'`. The same mix is the verification sample `01 American Landscape.MTS`, key `(1, ' american landscape.mts')`, against the letter-named manual clips (`clip1.mts`, `b.MTS`). A folder of only `00000.MTS`-style names does not crash, and the step 8 list is only `clip10.MTS`, `Clip2.MTS`, `clip1.mts`, so unittest stays green. Tag each run before it is compared: `(0, int)` for a digit run and `(1, text)` for a text run, and drop empty runs from `re.split`. Digit-leading before letter-leading at the first differing slot is the default that encoding gives; write that into the test. Extend the `natural_key` test with one digit-leading name and one letter-leading name in the same list (`00000.MTS` with `clip1.mts`, or the sample name with `clip1.mts`). `_Reversed` can keep wrapping that tuple.
- **`_column_left_of` iterates `displaycolumns`, which is `('#all',)`.** A `ttk.Treeview` given `columns=(...)` and no `displaycolumns` setting reads back `('#all',)` on Tk 8.6.12. `tree.column("#all", "width")` raises `TclError: Invalid column index #all`. Step 5 never reaches the real widths, so separator double-click throws and case 4 cannot pass as written. When the value is `#all`, sum `tree["columns"]` instead. The plan does not set `displaycolumns`, so this is the default the helper will see.

## Non-blocking
- **Do not negate `None`.** The descending recipe says the size and mtime primary is `-value`. `-None` raises `TypeError`, and a primary left as `None` then throws `None < None` when two sizes are missing. The `missing` flag already sorts those rows last in both directions. Use a numeric stand-in (`0`) as the primary when `missing` is true, and apply `-value` only to a real number. Step 8 already requires `None` last both ways; put the stand-in in the recipe so it matches the test.
- **`_set_status` has to keep the stripe.** `_restripe` runs after insert, remove, clear, and sort, not after progress updates. `_set_status` should call `_retag` with the stripe already on that row. Replacing `tags` with only the status tag drops zebra striping as soon as a batch starts, and nothing puts it back until the next sort.
- **The new drop labels have to join the recolor set.** `_set_drop_bg` walks `_drop_fill` only (`mts_to_dnxhr_gui.py:401`: the frame, the one label, and the button row). A title plus an "or click to browse" line that is not in that tuple stays on the resting color when the frame goes hot or paused.
- **Put the minimum window size through `_px`.** Column widths and padding scale with `winfo_fpixels("1i") / 96`, and step 7 still starts `minsize` at a raw 640×480. `SetProcessDpiAwareness(1)` is set before `Tk()` (`:1154`), so at 200% that floor is half as large relative to the fonts. Verification step 4 already says to pick the smallest size that does not clip; state that the value you keep goes through `_px`.

## Nits
- Status width 230 still fits `Failed (double-click for details) (1:23)` (215 px in Segoe UI 10 here). The hour form `(1:02:03)` measures 232 px and can ellipsize. Per-clip elapsed for the sample is a few minutes, so this is only the long-file case.
- Approach calls the status order a "rank tuple", and step 3 then uses `-value` as the primary. Store integer ranks so that negation is valid. The order itself (`active < waiting < failed < cancelled < skipped < ok`) is already the spec.

## Spot-checks
- Round 1 blockers, re-read against the tree and not re-opened: step 4 insert is `(name, "Waiting", format_size(size), format_mtime(mtime), parent)` for columns `file`, `status`, `size`, `mtime`, `folder`; the core-file gate is `git diff --stat hwaccel-gpu-decode -- mts_to_dnxhr.py` after the jobs change is committed or stashed; `AppTableTests` builds a new `App` in `setUp` from `clip10.MTS`, `Clip2.MTS`, `clip1.mts`, and `setUpClass` only owns the withdrawn root. Zero-byte `.MTS` files pass `is_input_file` (suffix only), so that fixture is accepted by `collect_items`.
- Branch is `hwaccel-gpu-decode`. Uncommitted diff is still those four files, one jobs-default line each. `git diff --stat main -- mts_to_dnxhr.py` is still `240 insertions, 57 deletions`. GUI `jobs_var` is still line 475. Cited sites still match: insert `641-645`, `_drop_fill` `401`, `SetProcessDpiAwareness` `1154`, `_poll` started only from `_start_batch` `869` (not from `__init__`). `tests/test_mts_to_dnxhr.py:573` still asserts `args.jobs == 2`. README "A grey hint shows…" is still line 125.
- `natural_key` crash executed as above. Required contrast pairs recomputed; none fail 4.5. Weakest required pair is `#0a5fb4` on `#cce4f7` at 4.84. `TEXT_DISABLED` `#6b6b6b` on `DISABLED_BG` `#c8ccd1` is 3.30 and is still outside the test list.
- Tk 8.6.12, Python 3.11.9. `displaycolumns` and `column("#all")` executed as above. A second `tkinter.font.Font(name="AppBody", ...)` on the same root did not raise. Withdrawn-tree `xview()` was `(0.0, 1.0)`.
- Class cursor binding is present: `bind Treeview <Motion>` calls `ttk::treeview::Motion` (`treeview.tcl:28` and `:104-118`), which sets `hresize` over a separator and still calls `ActivateHeading`. The plan's "add no binding" choice matches that. `requirements.txt` is tqdm and tkinterdnd2. `scripts/build_exe.ps1` still collects only `tkinterdnd2`.
- Vista-versus-clam was not re-rendered.

## Suggested steals / strengtheners
- In step 3, one key recipe: skip empty pieces; append `(0, int(part))` or `(1, part)`; test `sorted(natural_key of ["00000.MTS", "clip1.mts", "Clip2.MTS"])` and keep the existing `clip1`, `Clip2`, `clip10` order.
- In step 5: `cols = tree["displaycolumns"]`; if `cols` is `"#all"` or `("#all",)`, use `tree["columns"]`.
- In the descending key: `primary = 0 if value is None else (-value if descending else value)`.
- One clause on `_set_status`: call `_retag` with the row's current odd/even tag. Add the new drop labels to `_drop_fill`.

## Confidence
high — The sort crash, `#all` column error, contrast ratios, jobs diff, and cited line numbers were executed or read in this tree. The vista theme was not given a fresh screenshot.
