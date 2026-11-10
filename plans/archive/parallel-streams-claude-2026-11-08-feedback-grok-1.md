# Feedback: Parallel encodes ("streams") for the GUI and CLI

*Loop signal: revise*

*Plan: [parallel-streams-claude-2026-11-08.md](parallel-streams-claude-2026-11-08.md) · Reviewer: grok · 2026-11-08*

## Verdict
ship-after-fixes — the scheduler, jobs=1 compatibility, and test list are implementable, but the specified options row does not fit the window and unchanged `convert_one` cleanup can delete a shared export folder under a parallel batch.

## Summary
The plan matches the repo: `convert_one` / `run_ffmpeg` cancel behavior, the five `RunBatchTests` sequences, the uncommitted timer diff, `MAX` vs suggestion math, and the "wrap, don't fork" argv constraint are all real. `run_indexed` with an inline `jobs == 1` path is a sound way to keep those tests. Two steps, followed literally, still ship a broken UI on this machine and a cross-file cleanup race. Both are plan edits, not product decisions.

## Blocking
Must fix or resolve before implementation (missing gates, wrong paths, unsafe approach, scope bombs, contradicted repo facts).

- **The one-row options layout does not fit the 560px window on this PC.** The app calls `SetProcessDpiAwareness(1)` before creating the window (`mts_to_dnxhr_gui.py` `main`). On this display that is 144 DPI. Measured `winfo_reqwidth`: the deinterlace checkbutton is 297px, "Parallel encodes:" is 134px, a width-3 spinbox is 49px, and `(suggested max 3 for this PC)` is 237px. Packed on one row that is about 717–745px. Content width at `minsize(560, 440)` with `outer` padding 10 is about 540px. Verification item 6 requires the hint to be visible at that size, and step 5 only says to check the fit. Specify a layout that already fits: leave the checkbox on grid row 4, put the label, spinbox, and hint on a new row beneath it (about 420px, which fits), and shift the summary and later rows down by one. Keep the 560×440 minimum.

- **`convert_one` empty-directory cleanup is not safe for siblings that share `final_dst.parent`.** `_remove_dir_if_empty` is `directory.rmdir()` (`mts_to_dnxhr.py`). `convert_one` calls it after a probe error, a cancel, and other failures. `rmdir` succeeds when the directory is empty. A normal batch writes every output into one folder, and the GUI creates that folder before the batch (`_start_batch`). Two workers can both be between `mkdir` and the first `.part` (ffprobe is that window). If one then fails or cancels and removes its `.part`, `rmdir` deletes the export directory while the other worker still needs it, and the sibling encode fails. `test_probe_error_strips_duplicate_path_and_empty_dir` locks in the single-file behavior: after a probe error the parent must be gone. Step 3 and step 6 say to call `convert_one` as it works today, which keeps this race. Add an in-flight count (or equivalent lock) per output parent around `mkdir` and `_remove_dir_if_empty`: `rmdir` only when the count for that directory is 0. Keep the existing single-file test passing. Add a regression with two threads sharing one parent: one raises `ProbeError` while the other is still inside `probe`, and the parent still exists until the second call finishes.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

- CLI `jobs > 1` should keep today's failure report. `_encode_all` appends `(src, err)` and, after `converted …, skipped …, failed …`, prints `failed: {src}` plus the multi-line tail. Step 6 only says the summary count line stays the same. `convert_one` also `tqdm.write`s a one-line `failed:` during the file; the post-loop reprint is the readable copy. Tally `ok` / `skipped` / `failed` the same way as the current loop, including that reprint.
- Catch `ConversionCancelled` inside the CLI `work` closure and count it as not converted. `run_indexed` re-raises the first exception from a worker after join. If that exception is `ConversionCancelled`, it can surface instead of the `KeyboardInterrupt` handler (`print("\ninterrupted", file=sys.stderr)` and return 130). The current handler writes to stderr.
- For three or four active rows, build the status line from every 1-based index, sorted: `Converting 3 at once (1, 2, 4 of 10)`. The written template only shows two placeholders. The manual check uses 2, so it will not catch a dropped index.
- The `file_finished` elapsed suffix applies to `ok`, `skipped`, `failed`, and `cancelled`, using each status's existing label (`Done`, `Skipped (already exists)`, `Failed (double-click for details)`, `Cancelled`). The step 5 wording names only `Done (M:SS)`.
- Keep `_refresh_running_status` from rewriting the status line when `_active` is empty. Today it returns early when `_active_index is None`, so the previous line stays up between files. A refresh that calls `running_prefix` in that gap would flash `Converting…` on the `jobs == 1` path.
- Narrow the "byte-for-byte" sentence. `--jobs 1` keeps the current encode loop and the inner tqdm bar. `_print_header` still gains a `jobs: N` line on every run, including the default and `--dry-run`. No current test snapshots the whole header, so this will not fail `unittest`; the goal sentence overclaims.

## Nits
Wording, structure, minor clarity.

- The suggestion prose puts "6c/12t has 12 → 2" inside the "up to 11 logical processors → 1" bullet. The formula and the unit-test table agree: 11 → 1, 12–17 → 2, 18+ → 3. Fix the sentence so it matches the table.
- The RAM paragraph says step 6 checks the 0.3–0.6 GB estimate. The peak-RAM measurement is step 9.
- "README: ~1.66 GB/min" is arithmetic on the verified note (about 4.7 GB for 168 s), not a line in the README.
- The plan's `print("\ninterrupted")` sketch omits `file=sys.stderr`. The live handler uses stderr. Keep that when the parallel path shares the handler.
- The Status column is `width=180, stretch=False`. After the timer diff, `Failed (double-click for details) (1:23)` is already wider than 180px at 96 DPI (measured label about 199px) and wider still at 144 DPI. The new `42% · M:SS` text fits. The manual GUI check should look at a failed row as well.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- Required sections are present: Goal, Constraints, Approach, Implementation, Verification, Risks, Out of scope, plus Existing data / APIs, Open questions, and PR split.
- `YADIF` is at `mts_to_dnxhr.py:36`. `Options` has no jobs field. `convert_one` is at line 550 and returns `(status, error)` or raises `ConversionCancelled`. `run_ffmpeg` (line 441) builds an inner tqdm only when `on_progress` is omitted, and checks `cancel` only on the callback path. A no-op callback matches the CLI parallel plan. Children use `_CREATE_NO_WINDOW`.
- `_stop_process` waits 10s after terminate and 10s after kill. `_wait_to_quit` uses a 15s deadline. Both match the risk note.
- `run_batch` is at `mts_to_dnxhr_gui.py:225`. Event tuples match the plan. The five `RunBatchTests` cover ok/skipped/failed order, cancel on the second call, an unexpected exception that continues, throttling (≤101 known fractions), and cancel-already-set with no `file_started`. An inline `jobs == 1` loop that posts the current row from `work` and the unstarted rows after `run_indexed` can satisfy those assertions.
- `threading`, `dataclasses`, and `Sequence` are already imported in the GUI. Both modules have `from __future__ import annotations`.
- Grid row 4 of `outer` is the deinterlace checkbutton. `minsize` is 560×440. `_update_buttons` returns immediately while `self.running` is true, so a spinbox state set there will not re-enable the control mid-batch.
- Width measurement on this PC (DPI awareness on, 144 DPI, client width 560): one combined options row is about 745px versus about 540px of content width. A parallel-only row is about 420px and fits.
- `os.cpu_count()` is 20, so `suggested_jobs()` is 3 and `MAX_JOBS` 4 matches the manual checks. The formula table (None/0/4/8/11 → 1, 12/16 → 2, 18/20/128 → 3, cap 3) matches `max(1, min(3, n // 6))`.
- Uncommitted diff is the timer work only: `format_elapsed`, `_with_times`, `_elapsed_file`, `_elapsed_batch`, `_summary_line`, and `FormatElapsedTests` in `mts_to_dnxhr_gui.py` and `tests/test_mts_to_dnxhr_gui.py` (+107/−15). Step 0 names the right files. `git status` also has untracked plan files; they are outside those two paths.
- `samples/01 American Landscape.MTS` is present (335,646,720 bytes) even though it is gitignored. README Usage, Desktop app, and the "one at a time" limitation are at the lines the plan cites.
- `DefaultsTests.test_defaults_match_cli_encode_argv` rebuilds `Options` from parser fields and compares `build_command`. A new `--jobs` default stays compatible as long as `jobs` stays out of `Options`.
- `_print_header` is called only from `main`. CLI help assertions look for flag substrings, not a full snapshot, so adding `--jobs` to that tuple matches the test style.
- Not executed: `python -m unittest`, the GUI, or the step 9 benchmark. FFmpeg throughput and peak RAM remain unverified.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- Step 5 layout: checkbox stays on row 4. New row: `Parallel encodes:` label, readonly spinbox `from_=1` `to=core.MAX_JOBS`, grey hint `(suggested max {core.suggested_jobs()} for this PC)`. Bump the summary from row 5 to row 6 and every later row by one. Done-when stays "hint fully visible at 560×440" on this 144 DPI display.
- In `convert_one`, refcount output parents. Sketch the regression next to `test_probe_error_strips_duplicate_path_and_empty_dir`: two threads, one shared parent, one `ProbeError`, the other blocked in `probe`, parent remains until both calls return.
- CLI `work` for `jobs > 1` should be a short copy of the current per-file tally (`ok` / `skipped` / `failed` plus `failures`), with `except ConversionCancelled` updating the bar and not counting a failure. `KeyboardInterrupt` remains the only path to exit 130.
- `running_prefix` many-active arm: `", ".join` of all sorted 1-based indices. Add a pure test for k=3.
- State that default CLI stdout gains exactly one header line, `jobs: 1`, and that this is the intended difference from today's transcript.

## Confidence
high — the layout numbers were measured with the app's DPI setting, and the `rmdir` race follows from `convert_one` plus the shared export directory the GUI creates before `run_batch`.
