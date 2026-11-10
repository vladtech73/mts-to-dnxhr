# Feedback: Desktop UI polish, sortable columns, resizable columns, higher contrast

*Loop signal: revise*

*Plan: [ui-polish-sort-resize-claude-2026-11-10.md](ui-polish-sort-resize-claude-2026-11-10.md) · Reviewer: grok · 2026-11-10*

## Verdict
ship-after-fixes — The iid model, clam palette, and column plan match the code; three local edits are required before this is safe to implement as written.

## Summary
The plan is grounded. Positional `self.items` / `self.errors` / `values[2]` coupling is real, the cited line numbers match the working tree, Tk 8.6.12 has `clam`, and every contrast pair the test lists clears 4.5:1 (weakest required pair is 4.84:1). The encode path, stdlib limit, and the uncommitted jobs-default diff are described correctly.

Three defects would still produce the wrong result if the steps were followed literally. Step 4 never rewrites the tree insert tuple, so the new column order displays the folder path in Status and leaves Size and Modified empty. The core-file gate diffs against `main`, which already differs by hundreds of lines on the required base branch. `AppTableTests` builds one shared `App` in `setUpClass` and then sorts, fails, and deletes rows on it.

## Blocking
- **Step 4 does not update the row values, so the new columns show the wrong cells.** `tree.insert` at `mts_to_dnxhr_gui.py:641-645` writes `(item.src.name, str(item.src.parent), "Waiting")` for columns `file`, `folder`, `status` (`:427`). Step 4 changes the column order to `file`, `status`, `size`, `mtime`, `folder` and never mentions that tuple. After the change, Status shows the folder path, Size shows `Waiting`, and Modified and Source folder stay empty. `tree.set(iid, "status", text)` only replaces the status cell, so progress updates do not repair the others. In step 4, set all five values on insert, in that order, with `format_size`, `format_mtime`, and the initial text `Waiting`. Keep later status updates on `tree.set`, so nothing rebuilds the values tuple by position.
- **The core-file gate compares against `main`, which is already a large diff on the required base.** The plan says to branch from current `hwaccel-gpu-decode` HEAD, then run `git diff --stat main -- mts_to_dnxhr.py` and treat a hit as this work touching the encode path. On this tree that command is already `240 insertions, 57 deletions` before any UI edit. `git diff --stat HEAD -- mts_to_dnxhr.py` is only the uncommitted jobs-default line. After that line is committed or stashed, the gate has to be empty against the branch point (`HEAD` or `hwaccel-gpu-decode`), not against `main`.
- **`AppTableTests` mutates one shared app, so the cases interfere.** `setUpClass` creates the root, builds one `App`, and adds the clips. Case 2 then writes a failed status onto a row, and case 3 deletes rows. A later case sees the leftover sort, the failed row, or a shorter list. Create the withdrawn `Tk` once in `setUpClass`. Build a new `App`, or clear and re-add a named fixture, in `setUp`. Stop the `locate_tools` and `messagebox` patches when the class ends if they were started for the whole class. Name the fixture files so case 1 has a determined natural order (`clip10.MTS`, `Clip2.MTS`, `clip1.mts` at minimum).

## Non-blocking
- **The extra `<Motion>` binding does not win the cursor, and `return "break"` would drop heading hover.** `ttk::treeview::Motion` (`tcl/tk8.6/ttk/treeview.tcl:104-118`) already switches the cursor to `hresize` (`size_we` on Windows) over a separator, and the class binding runs after a widget binding. A widget-level `sb_h_double_arrow` is overwritten on the next class call. Returning `"break"` keeps that cursor and also skips `ActivateHeading`, so `HEADING_ACTIVE` never applies. The class `<Leave>` binding only clears the heading state. Keep the built-in cursor, or set the cursor from a binding that runs after the class binding and still lets `ActivateHeading` run.
- **Step 1's read list misses live `self.items` / `self.errors` sites.** `_items()` is specified for `:627`, `:715`, `:801`, `:926`, and `:1052`. These still read the lists: `_update_count` (`:654`), `_update_buttons` (`:751`), and `_start_batch` (`:789`, `:842-843`). Failed-row text is a separate path: `_on_double_click` (`:703-706`) must show `_rows[iid].error` and that row's path, `_handle_event` (`:1023-1024`) must store `err` on the row, and the Waiting reset (`:843`) must clear `row.error`. `_failed_names` (`:1071`) must take the name from the row.
- **Heading marks need a full rewrite from `_HEADINGS` on every click.** "Append `▲`/`▼` to the active heading" stacks marks on the second click if it concatenates onto the current text (`File ▲` then `File ▲ ▼`). Set every heading from `_HEADINGS` each time, and add the mark only on the active column.
- **The hex gate rejects two colors step 6 tells you to write.** `#c8ccd1` (disabled accent) and `#dfe3e8` (progress trough) sit in `apply_theme`, while the done-when grep allows six-digit hex only inside the palette block. Add them to the palette under fixed names and reference those names.
- **Separator and heading handling has to run before the empty-row return.** `_on_double_click` returns immediately when `identify_row` is empty (`:692-694`). A separator or heading hit has no row, so a check placed after that return never autofits and never suppresses anything. Put the region branch first. Extract the boundary math as a named helper the step 8 case can call.
- **Descending sort needs a key recipe that can express "flip the primary only."** The contract is right: `None` last both ways, `seq` ascending both ways, tests cover ties. A two-part tuple cannot negate a `natural_key` tuple. For numbers use `(is_none, -value if descending else value, seq)`. For file and folder, wrap only the primary in a reverse-compare object. `reverse=True` on the whole key flips `None` and `seq` too.
- **Hard-coded padding fights the font-metrics constraint at 200%.** Column widths correctly scale by `winfo_fpixels("1i") / 96`. Outer padding 12, the 8 px gaps, button padding `(10, 4)`, heading padding `(8, 4)`, and `rowheight = linespace + 8` leave the added pixels unscaled. `linespace` is already in device pixels. Scale the added pixel padding the same way as the column widths.
- **`TLabelframe.Label` is a separate style.** Configuring `TLabelframe` leaves the group title on clam's default label colors. Set `TLabelframe.Label` background to `SURFACE` and foreground to `TEXT`.
- **Apply the 10 pt body font to the widgets that should grow.** Step 6 names the font sizes and then assigns the bold font to headings only. Set the body font on `TLabel`, `TButton`, `TCheckbutton`, `Treeview`, `TEntry`, and `TSpinbox`, or the window stays at Segoe UI 9 except the headings.
- **The real-clip check writes a full HQX file.** `samples/01 American Landscape.MTS` is 335,646,720 bytes. The GUI has no duration limit, and the README's own ratio is about 4.7 GB for this clip. The Done/green check needs a finished file. State that, and keep Stop / Cancelled as a separate pass on the same clip so verification can stop without waiting for the full file.

## Nits
- The two Open questions already pick defaults in the same bullets (problems-first rank, and Size and Modified are in scope). Move them into Approach so implementation does not pause for an answer.
- "Problems sort near the top" does not match the rank tuple `active < waiting < failed < cancelled < skipped < ok`. Waiting sorts above Failed. The tuple is the spec; align the sentence with it.
- `grep` for `get_children()\[` does not match the current bug. The code binds `children = self.tree.get_children()` and then indexes `children[index]` (`:772-775`, `:947-952`). Case 2 is the real gate. Widen the grep, or drop the claim that an empty grep proves there is no positional read.
- A heading double-click ends on the previous direction only when that column was already the sort column. A double-click on a different column leaves it descending. The risk note can say the double toggle is accepted; "ends in the original order" is stronger than ttk does.
- Status width 230 fits the required `Failed (double-click for details) (1:23)` string (215 px at Segoe UI 10 on this machine). The hour form `(1:02:03)` measures 232 px and can ellipsize. Per-clip elapsed for the sample is a few minutes, so this is only the long-file case.

## Spot-checks
- Working tree is branch `hwaccel-gpu-decode`. Uncommitted diff is four files, no line shift: GUI change is `jobs_var` `1` → `2` at `mts_to_dnxhr_gui.py:475`. `tests/test_mts_to_dnxhr.py:573` asserts `args.jobs == 2`. CLI `default=2` is `mts_to_dnxhr.py:839`. Stashing does not move the cited GUI lines.
- `git diff --stat main -- mts_to_dnxhr.py` → 240 insertions, 57 deletions. `git diff --stat HEAD -- mts_to_dnxhr.py` → the one jobs-default line.
- Line map checked against `mts_to_dnxhr_gui.py`: `_build` 381–536, tree 425–443 (`file`/`folder` stretch, `status` stretch false, vertical scrollbar only), `items`/`errors` 358–359, `events` 365, insert 641–645, `remove_selected` 656, `clear_all` 676, `_on_double_click` 691, `_set_status_cell` 771, `_start_batch` 788, `_refresh_running_status` 943, `_handle_event` display map 1013–1021, `_failed_names` 1065, `SetProcessDpiAwareness` 1154 (before `Tk()` at 1161), spinbox `state="readonly"` 482, `#666666` at 488 and 494, `fg="red"` at 504, minsize 560×440 at 350, icon `TclError` swallow 351–355, low-disk `/1e9` at 824. `format_elapsed` is line 53. `run_batch` posts `file_started` / `file_progress` / `file_finished` / `batch_finished` by batch index and calls `core.convert_one` (248–333).
- `tests/test_mts_to_dnxhr_gui.py:1` says no Tk window is required. `DefaultsTests.test_defaults_match_cli_encode_argv` is line 49. No current GUI test reads tree values.
- README "A grey hint shows…" is in the Desktop app section, line 125.
- Dev interpreter is Python 3.11.9, Tk 8.6.12, themes include `clam`. `scripts/build_exe.ps1` collects only `tkinterdnd2`. `requirements.txt` is tqdm and tkinterdnd2.
- `samples/01 American Landscape.MTS` is on disk (335,646,720 bytes) plus `samples/README.md`. Media is gitignored.
- Contrast for the published palette, WCAG relative luminance: every pair step 8 lists at 4.5 is at least 4.84 (`#0a5fb4` on `#cce4f7`). `TEXT_DISABLED` `#6b6b6b` on `SURFACE` is 4.84. The same gray on disabled-button `#c8ccd1` is 3.30 and is not in the test list.
- Body 10 pt Segoe UI measure: `Failed (double-click for details) (1:23)` = 215 px; `(1:02:03)` = 232 px. Default font on this process is Segoe UI 9. `winfo_fpixels("1i")` was 96 in a process that had not called `SetProcessDpiAwareness`; the app sets that before `Tk()`.
- Treeview class bindings: separator press resizes and does not invoke the heading command (`treeview.tcl:170-175`, `247-251`). A double-click is two heading releases, then `<Double-1>`. `identify_row` is empty on the heading, which is why the region check has to come first.
- Vista-versus-clam drawing was not re-rendered. `clam` is installed. The "vista ignores `background`/`foreground`" claim is the usual vsapi behavior and was not given a fresh screenshot.

## Suggested steals / strengtheners
- One sentence in step 4: insert `(name, "Waiting", format_size(size), format_mtime(mtime), folder)` and do not write the other cells by index.
- Replace the `main` diff with `git diff --stat <branch-point> -- mts_to_dnxhr.py` after the jobs-default commit or stash.
- `setUp` rebuilds the app from a fixed three-file fixture; `setUpClass` only owns the withdrawn root and the skip.
- Descending key: `(missing, inverted_primary, seq)` with a reverse-compare wrapper for `natural_key`.
- Name `_column_left_of(event_x)` and call it before the `identify_row` return.
- Palette entries `DISABLED_BG` and `TROUGH`. Style `TLabelframe.Label` and the 10 pt body font on the text widgets.
- Scale the extra pixel padding with the same DPI factor as the column widths.

## Confidence
high — Line numbers, the jobs diff, the `main` diff, Tk 8.6.12 bindings, the sample file, and the contrast ratios were checked in the tree; the vista theme was not re-rendered.
