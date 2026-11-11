# Feedback: Parallel encodes ("streams") for the GUI and CLI
*Loop signal: satisfied*

*Plan: [parallel-streams-claude-2026-11-08.md](parallel-streams-claude-2026-11-08.md) · Reviewer: grok · 2026-11-08*

## Verdict
solid-with-nits — round 2's `suggested_jobs(None)` clash is resolved, and the scheduler, folder refcount, layout, and jobs=1 paths can be implemented as the steps describe.

## Summary
The plan now uses one meaning for `None`: both `suggested_jobs()` and `suggested_jobs(None)` read `os.cpu_count()`, and a resolved count of `None` or `0` returns 1. The unit table no longer expects `None → 1`; it mocks `os.cpu_count` instead. That matches the step 1 done-when (`3 4` on this 20-processor box) and the hint text. The shared-parent refcount, the parallel-encodes row under deinterlace, and the row-clock rewrite before the Stopping return are still specified against the current line numbers. Remaining notes are wording, not behavior the steps get wrong.

## Blocking
Must fix or resolve before implementation (missing gates, wrong paths, unsafe approach, scope bombs, contradicted repo facts).

None.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

None.

## Nits
Wording, structure, minor clarity.

- The Approach still says the CLI `_encode_all` passes a `work(i)` closure into `run_indexed`, and that `jobs == 1` is that helper's inline path. Step 6 keeps today's CLI loop when `jobs == 1`, so the inner tqdm bar and the `KeyboardInterrupt → 130` handler stay. The steps and the `jobs=1` test are the ones to follow. One sentence in the Approach would stop someone from "unifying" the default CLI path onto `run_indexed` and dropping the inner bar.
- Quote today's unknown-duration status string in the step 5 helper and the step 4 test: `Converting {i+1} of {count}: {name}…` (ellipsis immediately after the name, no parentheses). That is `_running_prefix` at `mts_to_dnxhr_gui.py:859-860`. The percent form is already quoted; the `…` form is not, and the new test is the only lock on it.
- On `file_finished`, pop that index from `_active` before `_update_overall`. Today's handler clears `_current_fraction` and `_active_index` before the bar update (`mts_to_dnxhr_gui.py:947-953`). Updating first counts the finishing file in both `_finished_files` and the active sum for that event, and the next event can move the bar backward.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- Required sections are present: Goal, Constraints, Approach, Implementation, Verification, Risks, Out of scope, plus Existing data / APIs, Open questions, and PR split.
- Round 2 blocker: `suggested_jobs(cpu_count=None)` and a call with no arguments are the same Python call, and the plan now gives them one behavior (read `os.cpu_count()`). The direct table is `0→1`, `4→1`, `8→1`, `11→1`, `12→2`, `16→2`, `18→3`, `20→3`, `128→3`, with `None` excluded. `os.cpu_count()` on this machine is 20, so `max(1, min(3, 20 // 6))` is 3. `mts_to_dnxhr.py` already imports `os`, so patching `mts_to_dnxhr.os.cpu_count` hits `os.cpu_count()` inside the function.
- Round 2 cleanup and layout, re-read: `_remove_dir_if_empty` is `rmdir` and swallows `OSError` (`mts_to_dnxhr.py:377-381`). The six calls are lines 582, 587, 607, 610, 614, and 620, all after `mkdir` at line 573. The skip and already-cancelled returns (lines 567-571) stay outside that region. `probe` is the module function at line 579. `deinterlace_chk` is grid row 4; summary 5, banner 6, separator 7, status 8, progress 9, actions 10. `banner.grid()` / `grid_remove()` pass no row. `outer.rowconfigure(2, weight=1)` is the tree. `minsize` is 560×440.
- Round 2 nits, now in the plan: `_dir_users` is `dict[str, int]` keyed by `os.path.normcase(os.path.abspath(directory))` in both claim and release. `_elapsed_file` is named in the removal list. The per-row rewrite is specified after the running/quitting return and before the Stopping return at `mts_to_dnxhr_gui.py:869`.
- `convert_one` is at line 550 and returns `(status, error)` or raises `ConversionCancelled` / `KeyboardInterrupt`. `run_ffmpeg` (line 441) builds an inner tqdm only when `on_progress` is omitted, and checks `cancel` only on the callback path. `Options` has no jobs field. `build_command` does not take a jobs argument. `_encode_all` and `_print_header` are called only from `main`.
- `run_batch` is at `mts_to_dnxhr_gui.py:225`. The five `RunBatchTests` still match an inline `jobs == 1` loop that posts the current row from `work` and unstarted rows after `run_indexed`. `ConversionCancelled` subclasses `Exception`, so the plan's catch order is required. `threading`, `dataclasses`, and `Sequence` are already imported in the GUI. Both modules have `from __future__ import annotations`.
- `_update_buttons` returns immediately while `self.running` is true. `_set_running_ui` is what `_start_batch` calls after setting `running`. `DefaultsTests` and `_parser_defaults` build `Options` field by field, so a `--jobs` dest stays out of `build_command`. `SmokeTest.test_short_hqx_mov_and_mxf` calls `main` without `--jobs` and asserts output files, not header text. Help assertions look for flag substrings, not a full snapshot.
- Uncommitted diff is still the timer work only: `mts_to_dnxhr_gui.py` and `tests/test_mts_to_dnxhr_gui.py`, +107/−15. Step 0 names those two files. `samples/01 American Landscape.MTS` is present (335,646,720 bytes). README Usage is line 60, Desktop app is line 103, and the "one at a time" limitation is line 174. The Verified section is line 50.
- Not executed: `python -m unittest`, the GUI, or the step 9 benchmark.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- Approach, one clause: the CLI uses `run_indexed` only for `jobs > 1`; `jobs == 1` stays the current loop.
- Step 4 / step 5 unknown-duration string: `Converting {i+1} of {count}: {name}…`.
- Step 5 `file_finished`: pop `_active[index]`, then call `_update_overall`.

## Confidence
high — the `None` resolution matches Python's calling convention and a live `os.cpu_count()` of 20, and the cleanup, grid, and timer line numbers were re-read against the current files.
