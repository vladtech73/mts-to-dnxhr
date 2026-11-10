# Feedback: Parallel encodes ("streams") for the GUI and CLI

*Loop signal: revise*

*Plan: [parallel-streams-claude-2026-11-08.md](parallel-streams-claude-2026-11-08.md) · Reviewer: grok · 2026-11-08*

## Verdict
ship-after-fixes — the previous layout and shared-folder blockers are fixed, and the scheduler is implementable, but `suggested_jobs` as written cannot both return 1 for `None` and return 3 when called with no arguments on this PC.

## Summary
Round 1's two blockers are resolved in the plan: the spinbox and hint sit on their own row under the deinterlace checkbox, and `convert_one` claims the output parent under one lock so a sibling probe cannot have its folder removed. The `jobs == 1` paths, event tuples, argv constraint, and new tests still match the repo. Step 1 and the `JobsTests` table disagree about what `None` means, so a literal implementation either fails the unit test or shows "suggested max 1" on a 20-processor machine.

## Blocking
Must fix or resolve before implementation (missing gates, wrong paths, unsafe approach, scope bombs, contradicted repo facts).

- **`suggested_jobs(None)` and `suggested_jobs()` are the same call, and the plan requires two different results.** Step 1 gives the signature `suggested_jobs(cpu_count: Optional[int] = None)` and says it defaults to `os.cpu_count()`, while `None` or `0` returns 1. The step 2 table then expects `None → 1`. In Python the omitted argument is that default, so `suggested_jobs()` is `suggested_jobs(None)`. On this PC `os.cpu_count()` is 20, and the step 1 done-when, the GUI hint, and `--help` all require that no-argument call to return 3. Following the table makes the hint and the `3 4` check wrong; following the lookup makes `JobsTests` fail. Pick one sentinel and say it in both steps. Either use a private sentinel for "not passed" and keep `suggested_jobs(None) → 1`, or drop `None` from the direct-argument table and cover a missing processor count by mocking `os.cpu_count` to return `None` while calling `suggested_jobs()` with no arguments. `0 → 1` can stay a direct argument either way.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

- Put the per-row `{pct}% · M:SS` rewrite in `_refresh_running_status` before the `Stopping…` return. That return is currently the second exit (`mts_to_dnxhr_gui.py` around line 869). A rewrite placed after it never runs once Stop has set the status line, so the row clocks freeze while `total` keeps ticking. Progress events still update the cells; this only covers the gap between those events.

## Nits
Wording, structure, minor clarity.

- Step 1 says `_dir_users: dict[Path, int]` and "increment `_dir_users[directory]`", then says to key by `os.path.normcase(os.path.abspath(directory))`. Those are different keys (`Path` equality is case-sensitive on Windows). State once that the dict is `dict[str, int]` and that both claim and release use that string.
- `_elapsed_file` is the only reader of `_file_t0` besides the sites step 5 names, and `_with_times` is its only caller. Name it in the removal list so it is not left calling a field the step deletes.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- Required sections are present: Goal, Constraints, Approach, Implementation, Verification, Risks, Out of scope, plus Existing data / APIs, Open questions, and PR split.
- Prior layout blocker: `deinterlace_chk` is grid row 4; summary 5, banner 6, separator 7, status 8, progress 9, actions 10. `minsize` is 560×440. `banner.grid()` / `grid_remove()` pass no row, so shifting the original `grid` call is enough. `outer.rowconfigure(2, weight=1)` is the tree. The two-row layout matches the round-1 measurement (parallel-only row about 420 px). Widths were not re-measured this round.
- Prior cleanup blocker: `_remove_dir_if_empty` is `rmdir` and swallows `OSError` (`mts_to_dnxhr.py:377`). The six call sites are lines 582, 587, 607, 610, 614, and 620, all after `mkdir` at line 573. The pre-mkdir skip and already-cancelled returns stay outside that region, which keeps `test_convert_one_already_cancelled_does_not_create_dir` and `test_mkdir_oserror_fails_the_file_and_returns` meaningful. `probe` is the global `probe(src, ffprobe)` at line 579, so patching `mts_to_dnxhr.probe` is the right target. `threading` is already imported in core.
- `os.cpu_count()` is 20. `max(1, min(3, 20 // 6))` is 3. That is what makes the `None` default and the `None → 1` table row collide.
- `run_batch` is at `mts_to_dnxhr_gui.py:225`. The five `RunBatchTests` still match an inline `jobs == 1` loop that posts the current row from `work` and unstarted rows after `run_indexed`. `ConversionCancelled` subclasses `Exception`, so the plan's catch order (cancelled, then any other `Exception`) is required for `test_cancel_during_second_file_cancels_the_rest` and `test_unexpected_exception_fails_the_file_and_continues`.
- `_update_buttons` still returns immediately while `self.running` is true. `_set_running_ui` exists and is what `_start_batch` calls after setting `running`, so disabling the spinbox there is the path that actually runs.
- `DefaultsTests.test_defaults_match_cli_encode_argv` builds `Options` field by field. A `--jobs` dest does not flow into `build_command` as long as `jobs` stays out of `Options`.
- `SmokeTest.test_short_hqx_mov_and_mxf` calls `main` without `--jobs` and asserts output files, not header text. The extra `jobs: 1` line does not break it.
- Uncommitted diff is still the timer work only: `mts_to_dnxhr_gui.py` and `tests/test_mts_to_dnxhr_gui.py`, +107/−15. Step 0 names the right files.
- `samples/01 American Landscape.MTS` is present (335,646,720 bytes). README Usage, Desktop app, and the "one at a time" limitation are still where step 8 points.
- Not executed: `python -m unittest`, the GUI, or the step 9 benchmark.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- In step 1, replace the default-argument sentence with: omitted argument reads `os.cpu_count()`; a resolved count of `None` or `0` returns 1; the omitted argument is not `None`. In step 2, either pass a sentinel-free explicit `None` meaning "resolved count was missing", or mock `os.cpu_count` and call `suggested_jobs()` with no arguments for that row. The no-argument call on this box stays 3.
- One line in `_claim_dir` / `_release_dir`: `key = os.path.normcase(os.path.abspath(directory))`, dict type `dict[str, int]`.
- Step 5 removal list: `_elapsed_file` goes away with `_file_t0`, and the per-row rewrite in `_refresh_running_status` runs before the `Stopping…` return.

## Confidence
high — the `None` clash is the language calling convention plus `os.cpu_count()` of 20 on this machine, and the cleanup and grid line numbers were re-read against the current files.
