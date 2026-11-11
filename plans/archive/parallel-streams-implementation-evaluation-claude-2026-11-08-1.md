# Parallel Encodes (Streams) — Implementation Evaluation

*Claude Code turns used: 25 / max 100*

*Evaluator: claude · 2026-11-08 · Reviews the implemented `parallel-streams-claude-2026-11-08.md` against the working tree.*

## Verdict: Nearly done. Core, CLI, GUI, tests and docs match the plan, but the plan's own 560×440 layout gate fails.

Every workstream (steps 0–9) is in the uncommitted working tree. All plan gates I could run pass: the unit suite, the `MTS_SMOKE=1` suite, the `--help` text, exit code 2 for bad `--jobs` values, and the argv invariant. Real parallel encodes, a sibling failure in a shared export folder, and a simulated Ctrl+C all behave correctly. The `jobs == 1` paths are preserved. One finding should be fixed before merge: at the 560×440 minimum window size, the new row collapses the file list to 1 px, so manual check 6 ("the tree still shows at least a few rows") fails. The step 9 benchmark also has a design flaw (four clips) that weakens the "cap at 2" conclusion. It is advisory only and does not block merge.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 0–9 all landed. The suggestion was adjusted to cap at 2, as step 9 allows. |
| Contract fidelity | 4 | `jobs=1` event order, argv, `convert_one` signature and transcript are preserved. The tree-height expectation at the minimum size is broken. |
| Verification honesty | 4 | Automated gates are green and the tests check live behavior. Manual check 6 fails when measured. The benchmark is confounded by the clip count. |
| Finding severity | 3 | One High (layout gate). The rest are Low or Trivial. |
| Merge readiness | 4 | Safe for functionality. Fix the minimum-size layout first, or accept it as a known regression. |

**Overall completeness:** 20/25 · **percent:** 80%
**Band:** nearly-done
**Open findings:** Critical 0 · High 1 · Low 3 · Trivial/Noted 5

## Loop signal

**Loop signal:** one-more-fix
**Signal rationale:** The only High is a one-line geometry or minsize decision. The Low items are cheap test and docs additions, so one remediation pass closes everything.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **0. Land timer work** | Complete | `da63a1a` is HEAD. The GUI timer code is in HEAD. |
| **1. Core cap / suggestion / scheduler / dir refcount** | Complete | `MAX_JOBS = 4` (`mts_to_dnxhr.py:37`). `suggested_jobs` (`:52`) is capped at 2 after step 9. `run_indexed` (`:587`) has an inline path for `workers == 1`, daemon threads, a `join(0.2)` loop, KeyboardInterrupt → `cancel.set()` → join → re-raise, and first-error re-raise. `_DIR_LOCK` / `_dir_users` / `_claim_dir` / `_release_dir` (`:391–418`) use the `normcase(abspath)` key. In `convert_one`, the six `_remove_dir_if_empty` calls became `cleanup = True` under one `try/finally`. |
| **2. Core tests** | Complete | The `JobsTests` table and `cpu_count` patch use the adjusted 2-cap. Tests cover the bound, Barrier overlap, the clamp, inline order, both cancel cases, cancel set up front, and exception plus `cancel` set. `test_shared_parent_survives_sibling_failure` follows the plan (also asserts `_dir_users == {}`). `test_probe_error_strips_duplicate_path_and_empty_dir` is unmodified. |
| **3. GUI `run_batch(jobs=1)`** | Complete | A `work(index)` closure has its own `last_bucket`. The tally is locked. `ConversionCancelled` posts for its own index and then sets `cancel`. Unstarted indices are posted after `run_indexed`. `batch_finished` stays in `finally`. The five existing `RunBatchTests` pass unmodified. |
| **4. GUI worker tests** | Complete | Tests cover overlap ordering, cancel in the middle of four pairs, independent throttling, and `running_prefix` with zero, one (known and unknown pct), two and three (unsorted) active clips. |
| **5. GUI state / status / control** | Partial | `_ActiveFile`, `self._active`, `_batch_jobs`, `running_prefix`, `_with_times` single-entry file time, per-row timers placed before the `Stopping…` return, `Done (M:SS)` keyed on `_active` membership, Σ-fraction overall bar, spinbox on row 5, rows shifted 5→6 … 10→11, readonly/disabled toggling, `jobs` clamp with TclError fallback, and the plural stop text are all done. Grep finds no `_active_index`, `_file_t0`, `_status_pct`, `_elapsed_file`, `_current_fraction` or `_known_total` left. **Gap:** the tree is 1 px tall at 560×440 (Finding 1). |
| **6. CLI `--jobs`** | Complete | `_jobs_arg` gives exit code 2 for 0, 5 and x. Help reads `Suggested for this PC: 2 (default: 1)`. The header prints `jobs: N` plus an "above the suggested" note. The `jobs == 1` loop is byte-identical. The `jobs > 1` path uses a no-op `on_progress`, `cancel`, a locked tally, `bar.update(1)` and a local `ConversionCancelled` catch. `main` passes `args.jobs` through. |
| **7. CLI tests** | Complete | `--jobs` was added to the help test along with `args.jobs == 1`. Tests cover bad values exiting 2, jobs=2 ok, failed with the reprint after the summary, and cancelled, plus `jobs=1` omitting `on_progress`. |
| **8. README** | Complete | Usage has an example plus the formula and HDD/USB advice. The Desktop app section describes the control and hint. The Limitations line was rewritten, and a disk-full note for parallel encodes was added. |
| **9. Benchmark** | Complete (method flawed) | The table is in "Verified on FFmpeg 8.0.1". The formula was adjusted to cap at 2. `D:\tmp\par` was removed. See Finding 2. |

## Findings (ranked)

### 1. At the 560×440 minimum size the file list collapses to 1 px, which fails manual check 6. *(High)*

I measured this with a live Tk `App` at this PC's 144 DPI. The working tree was measured the same way and compared against HEAD's `mts_to_dnxhr_gui.py`:

| Window | HEAD tree height | Working-tree tree height |
|---|---|---|
| 560×440 (minsize) | 30 px (heading only) | **1 px** (the heading is gone too) |
| 560×520 | 110 px | 76 px |
| 720×540 (default) | ~130 px | ~96 px |

The requested height grew from 637 to 671 px, so the new row costs about 34 px. The plan said "the tree (the only weighted row) absorbs it", but at minsize the tree had only 30 px left to give. At the default 720×540 the list drops from about 3 to about 2 visible rows. The plan's step 5 "Done when" and manual check 6 both require the tree to "still show at least a few rows" at 560×440, and that is not true. The plan also says "Keep `minsize(560, 440)`", so the plan cannot meet both requirements as written. The cause is partly pre-existing: HEAD already showed zero data rows at the minimum size.

The horizontal fit passes: the jobs row is 432 px wide, and the hint's right edge is at x=442 inside a 560 px window.

**Remediation:** Choose one of these:
- Raise `minsize` to about `(560, 480)` and the default `geometry` to about `720x580`, then update the plan note.
- Shrink the drop zone (`height=110` at `mts_to_dnxhr_gui.py:382`) by about 35 px.

Then re-measure: the tree should be at least the heading plus 2 rows at minsize.

### 2. The four-clip benchmark is structurally biased against `--jobs 3`. *(Low)*

With four equal clips, `--jobs 2` runs two full rounds (2+2) and `--jobs 3` also needs two rounds (3, then 1 running alone). So jobs=3 cannot show its throughput advantage, and jobs=4 (one round) wins at 18.5 s and 17.3 s. "A third was not [faster]" may be an artifact of the clip count. The table also has a likely noise or cold-cache signal: jobs=1 with deinterlace (20.9 s) beat jobs=1 without it (24.0 s), which is implausible if yadif adds work. Each cell looks like a single run. The conservative cap of 2 is still a safe advisory value, so this does not block merge. The implementation also followed the plan's prescribed method exactly.

**Remediation:** Re-run with 12 copies (the LCM of 2, 3 and 4), or report aggregate throughput per stream count. Run each cell at least twice, with a warm-up run first. Revisit the cap only if jobs=3 is 10% or more faster.

### 3. Measured RAM is 3–6× the plan estimate, and nothing guards against it. *(Low)*

The plan estimated 0.3–0.6 GB per process. The README table shows about 1.8 GB per `ffmpeg.exe`, which reaches 7.1–7.2 GB at 4 jobs. Values up to 4 are allowed without a prompt. On an 8 GB machine with 12 or more logical processors (suggestion 2), choosing 4 would page heavily. The README records the 1.8 GB figure but does not turn it into user guidance.

**Remediation:** Add one README sentence to the Usage and Desktop app sections: "each parallel encode uses about 2 GB of RAM". A RAM-aware suggestion is optional and is out of scope as planned.

### 4. No test covers the `jobs:` header line or the above-suggestion note. *(Low)*

`_print_header` gained a required `jobs` parameter (no default) and two output lines. The plan calls this "the one intended change to the default transcript". No test asserts `jobs: 1` on the default or `--dry-run` path, or that the note appears only when `jobs > suggested_jobs()`. I verified both by hand: `--dry-run` printed `jobs: 1`, and `--jobs 3` / `--jobs 4` printed the note.

**Remediation:** Add a `CliTests` case: run `main([...,"--dry-run"])` and assert `jobs: 1` is present and `note: --jobs` is absent. Then patch `suggested_jobs` to return 1, run with `--jobs 2`, and assert the note.

### 5. The parallel CLI failure reprint is in completion order, not input order. *(Trivial)*

`failures.append` happens when a worker finishes, so the trailing `failed: {src}` block can list files out of input order when `jobs > 1`. This does not affect correctness.

**Remediation:** Optional: `failures.sort(key=lambda f: order[f[0]])` before the reprint, or store the index.

### 6. A small behavior change in `_confirm_stop` was not called out as a change. *(Noted)*

`self._with_times("Stopping…")` became `self._with_times("Stopping…", include_file=False)` (`mts_to_dnxhr_gui.py:871`). At HEAD, on the `jobs=1` path, the first `Stopping…` frame showed `file M:SS` for up to about 100 ms before `_refresh_running_status` rewrote it without the file time. The change is consistent with the plan line "`Stopping…` keeps `include_file=False`", and the visible effect is negligible.

**Remediation:** No action.

### 7. A bug inside `work` would leave queued rows without `file_finished`. *(Noted)*

If `work` raises (only possible through a `BaseException` or a bug, since GUI `work` catches `Exception`), `run_indexed` re-raises and drops the drained `unstarted` list. Queued rows would then stay `Waiting`, even though `batch_finished` still fires. The plan accepts this ("can only happen for a bug in `work`").

**Remediation:** No action.

### 8. Docstring and style nits. *(Trivial)*

- The `suggested_jobs` docstring does not point at the rationale (CPU headroom, about 28 MB/s per HQX stream) as step 1 asked.
- `running_prefix` is followed directly by `_FFMPEG_MISSING` with no blank lines. HEAD's `format_elapsed` already did this, so the new function inherits the existing style.

**Remediation:** Optional one-line docstring tweak and two blank lines.

### 9. The plan's PR split is not reflected yet. *(Noted)*

The plan splits the work into PR 1 (steps 0–5 plus the Desktop app docs) and PR 2 (CLI, docs, benchmark). Everything is currently one uncommitted change set. The two halves are cleanly separable: the GUI work does not depend on `--jobs`.

**Remediation:** Split when committing if two PRs are still wanted. Otherwise, update the plan's PR split note.

## Net assessment

The functionality is correct and well covered, and it is safe to merge from a correctness point of view:
- The `jobs=1` paths match today's behavior exactly.
- `build_command` and `run_ffmpeg` are untouched.
- The `convert_one` change is limited to the refcounted claim/release.
- The parallel paths handle cancel, sibling failure and Ctrl+C correctly on real FFmpeg.

Before merging, fix the minimum-size layout regression (Finding 1). It is one line, but it needs a decision against the plan's "keep `minsize(560, 440)`" constraint. Adding the RAM note (Finding 3) and the header test (Finding 4) is cheap and worth doing in the same pass. Re-running the benchmark (Finding 2) can wait until someone wants to raise the suggestion above 2.

I did not perform manual GUI checks 1–5: watching live parallel rows, Stop during an encode, and "Stop and quit" with Task Manager. Instead I drove `App._handle_event` with synthetic events (results below). The CLI equivalents of Stop and Ctrl+C were verified with real FFmpeg.

## Verification performed

- `.venv\Scripts\python.exe -m unittest` → `Ran 67 tests … OK (skipped=2)`.
- `MTS_SMOKE=1 … -m unittest` → `Ran 67 tests in 3.3s … OK (skipped=1)`. The real encode wrote `01 American Landscape.mxf`.
- `python -c "import mts_to_dnxhr as m; print(m.suggested_jobs(), m.MAX_JOBS)"` → `2 4`. This is the expected value after the step 9 adjustment; the plan's literal gate said `3 4`.
- `python mts_to_dnxhr.py --help` → `-j N, --jobs N  Encode up to N clips at once (1-4). Suggested for this PC: 2 (default: 1)`.
- `--jobs 0` / `5` / `x` → exit 2, 2, 2.
- `git diff mts_to_dnxhr.py`: no hunks in `build_command` or `run_ffmpeg`. The only `convert_one` changes are `_claim_dir`, the `try/finally` with `_release_dir` and the `cleanup` flag (plus re-indentation). `DefaultsTests` passes.
- `git diff tests/`: additions only. No existing test was modified apart from the plan-directed `--jobs` additions to `test_help_lists_flags_and_defaults`.
- Grep for `_active_index|_file_t0|_status_pct|_elapsed_file|_current_fraction|_known_total` in the GUI and tests → no matches.
- **Real CLI, `--jobs 3`, three sample copies, `--duration 2`** → three `.mov` files written, exit 0, header `jobs: 3` plus the above-suggestion note.
- **Real CLI, `--jobs 4`, three good clips plus one zero-byte clip in a shared output folder** → three written, one failed, the reprint after the summary, exit 1. The shared folder survived.
- **Simulated Ctrl+C** (`_thread.interrupt_main()` 3 s into a `--jobs 3 --duration 60` run) → `interrupted`, exit 130 after 3.8 s. No `ffmpeg.exe` left in `tasklist`. No `.part` files, and the empty output folder was removed.
- `--dry-run` header → includes `jobs: 1` and no note.
- **Live Tk `App` with synthetic events** (jobs=2, four rows):
  - Status line: `Converting 2 at once (1, 2 of 4) · total 0:00`.
  - Row cells: `42% · 0:00` and `Converting… · 0:00`.
  - After row 0 finished: `Converting 2 of 4: b.MTS… · file 0:00 · total 0:00`, row 0 `Done (0:00)`, bar 25.0.
  - A failed row reads `Failed (double-click for details) (0:00)`. An unstarted cancelled row reads a plain `Cancelled`.
- **Live Tk layout measurement** at 144 DPI, HEAD vs the working tree (Finding 1): jobs row 432 px wide, hint right edge x=442 of 560. Tree height at 560×440 went from 30 px to 1 px.
- Scratch folders `D:\tmp\pwtest\par-eval` and `D:\tmp\pwtest\ev` were created for these checks and deleted. `D:\tmp\par` from step 9 is absent.
