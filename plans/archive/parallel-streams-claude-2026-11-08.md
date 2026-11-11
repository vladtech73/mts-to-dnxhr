# Parallel encodes ("streams") for the GUI and CLI

*Author: claude · 2026-11-08*

## Goal

Let a batch encode more than one clip at a time, both in the desktop app and in the CLI, with a per-machine **suggested max** shown next to the control.

Success looks like this:

- **GUI.** A "Parallel encodes" spinbox sits on its own row under the deinterlace checkbox. It ranges from 1 to a hard cap of 4, defaults to 1, and is followed by a grey hint such as `(suggested max 3 for this PC)`. While a batch runs, up to N tree rows show live `%` at the same time. Each running row shows its own elapsed time. The status line still shows `total M:SS`, and when only one clip is active it still shows `file M:SS`. Stop cancels every in-flight encode and deletes every `.part` file. Finished files are kept.
- **CLI.** `-j/--jobs N` (default 1, valid 1–4). `--help` shows the suggested value for this PC. `--jobs 1` keeps today's encode loop, inner tqdm bar, and failure report. The only transcript difference on the default path is one extra header line, `jobs: 1`, which also appears on `--dry-run`.
- With 1 parallel encode, the GUI and CLI behave exactly as they do now. All existing tests pass unchanged.

## Constraints

- **Wrap, don't fork.** Every encode goes through `core.convert_one(..., on_progress=..., cancel=...)` in `mts_to_dnxhr.py`. `build_command`, `run_ffmpeg`, and the ffmpeg argv do not change: no `-threads` flag and no new encoder options. The only `convert_one` change is making its output-folder `mkdir`/`rmdir` safe across threads (step 1); its signature, return values, and single-call behavior stay the same. The GUI defaults-parity test (`DefaultsTests.test_defaults_match_cli_encode_argv` in `tests/test_mts_to_dnxhr_gui.py`) has to keep passing. `jobs` is a batch setting and is **not** added to `core.Options`.
- **Python 3.9+.** Match the existing modules: `from __future__ import annotations`, `typing.Optional` and `Callable`, no `match`, and no runtime `X | Y` unions.
- **Tk thread rule.** Widgets are touched only on the Tk thread. Workers talk to the UI only through `post` (`self.events.put`), which is already thread-safe. Event tuple shapes stay the same: `file_started`, `file_progress`, `file_finished`, `batch_finished`.
- **`run_batch` never exits without posting `batch_finished`.** That holds for N workers too.
- **Each row gets exactly one `file_finished`**, whether it ran, failed, or was cancelled.
- **Tests make no live calls.** No FFmpeg, Tk window, or network in the default suite. The existing `MTS_SMOKE=1` opt-in stays the only real-encode path.
- **No new runtime dependencies.** stdlib `threading` only. `requirements.txt` is unchanged.
- **Disk.** The total-batch free-space estimate (`estimate_needed_bytes`, ×14) still applies. Parallelism does not change total bytes, only peak write rate.

## Approach

**One small, shared scheduler in core, used by both front ends.** Add `run_indexed(count, jobs, work, cancel)` to `mts_to_dnxhr.py`. It hands out indices `0..count-1` to up to `jobs` threads, stops handing them out once `cancel` is set, and returns the indices that never started. The GUI `run_batch` and the CLI `_encode_all` each pass in a `work(i)` closure that calls `convert_one` exactly as they do today. With `jobs == 1`, `run_indexed` runs `work` inline in the calling thread, so the event order is identical to the current sequential loop.

**Suggested max (concrete).**

- `MAX_JOBS = 4` is the hard cap. It is enforced in the CLI parser, the GUI spinbox range, and inside `run_indexed`.
- `suggested_jobs(cpu_count) = max(1, min(3, cpu_count // 6))`, where `cpu_count` is `os.cpu_count()` (logical processors). If `os.cpu_count()` itself returns `None`, the result is 1. Resulting values:
  - up to 11 logical processors (for example, 4c/8t laptops): 1
  - 12–17 logical processors (6c/12t, 8c/16t): 2
  - 18 or more logical processors: 3. This dev box reports 20, so it gets 3.
- Why these numbers:
  - **CPU.** One `dnxhd` ffmpeg already frame-threads across all cores, but it rarely saturates them. H.264 decode, and the single-threaded `yadif` when deinterlacing, are the bottleneck. A second or third process fills the idle cores. Beyond that, N processes that each auto-thread to every core mostly oversubscribe the CPU. Roughly 6 logical processors per extra stream is a conservative ratio.
  - **Disk.** HQX writes about 27.7 MB/s per stream at real-time speed (about 1.66 GB/min, derived from the README's verified run of ~4.7 GB for 168 s). At 2–3× real time, 3 streams write about 170–250 MB/s. That is fine for SATA or NVMe SSDs and too much for a single HDD or a USB drive. This is why the cap is 4, the suggestion is at most 3, and the default is 1.
  - **RAM.** A 1080p `yuv422p10le` frame is about 8 MB. Frame-threaded decode and encode buffers come to roughly 0.3–0.6 GB per process, so 3 processes need 2 GB or less. Step 9 checks this estimate on a real machine.
- The suggestion is **advisory**. Values from the suggestion up to 4 are allowed without a prompt. The hint text plus a README note ("use 1 when exporting to a spinning disk or USB drive") are the guardrail.

**Where it appears.**

- GUI: a new grid row 5 of `outer` in `App._build`, directly under the deinterlace checkbox (which stays on row 4), as `Parallel encodes: [ 1 ▴▾ ]  (suggested max 3 for this PC)`. A single combined row was measured at about 717–745 px at this PC's 144 DPI, which does not fit the roughly 540 px content width at the 560 px minimum. The parallel-only row is about 420 px and fits.
- CLI: `-j/--jobs`, with help text `Encode up to N clips at once (1-4). Suggested for this PC: 3`. `_print_header` also prints `jobs: N`.

**Status line under parallelism.** GUI per-file state moves from the scalar fields (`_active_index`, `_file_t0`, `_status_pct`, `_current_fraction`, `_known_total`) to `self._active: dict[int, _ActiveFile]`.

- One active clip: the status line keeps the current format, `Converting 3 of 10: clip.MTS (42%) · file 1:23 · total 4:56`.
- Two or more active clips: `Converting {k} at once ({every active 1-based index, sorted, comma-joined} of 10) · total 4:56`. For example, `Converting 2 at once (3, 4 of 10)` or `Converting 3 at once (1, 2, 4 of 10)`. The per-file timers move into each active row's Status cell as `42% · 1:23`.
- When a row finishes, its cell still gets the current elapsed stamp after its existing label: `Done (1:23)`, `Skipped (already exists) (1:23)`, `Failed (double-click for details) (1:23)`, or `Cancelled (1:23)`.
- The overall bar is `(finished + Σ known fractions of active) / count`.

**Alternatives rejected.**

- `concurrent.futures.ThreadPoolExecutor`: it does not stop dequeuing on cancel without extra bookkeeping, and `shutdown(cancel_futures=)` is 3.9+ but hides which rows never started. A 30-line lock-and-counter loop is simpler to test.
- `multiprocessing`: the work is already in ffmpeg subprocesses, and Python threads just wait on pipes.
- Adding `-threads` per process to reduce oversubscription: it changes the argv and breaks wrap-don't-fork. It is listed under Out of scope.
- Defaulting the spinbox to the suggested value: it changes current behavior and risks HDD thrash for users who never touch the control. It is listed under Open questions.

## Existing data / APIs (reuse)

- `core.convert_one(src, dst, opts, ffmpeg, ffprobe, *, log, on_progress, cancel)` (`mts_to_dnxhr.py:550`) raises `ConversionCancelled` when `cancel` is set, and cleans up `.part` and empty directories. It calls `final_dst.parent.mkdir(parents=True, exist_ok=True)` (line 573) and `_remove_dir_if_empty(final_dst.parent)` (a bare `rmdir`, line 377) on six failure or cancel paths (lines 582, 587, 607, 610, 614, 620). That cleanup is **not** safe when sibling workers share one output folder; step 1 fixes it.
- `core.run_ffmpeg` (`mts_to_dnxhr.py:441`) checks `cancel` only when `on_progress` is given. When `on_progress` is given, it creates no tqdm bar. The CLI parallel path depends on both behaviors.
- GUI `run_batch` (`mts_to_dnxhr_gui.py:225`): per-file `on_progress` bucket throttling via a `last_bucket` closure, and status normalization.
- GUI timers (`_with_times`, `_elapsed_file`, `_elapsed_batch`, `format_elapsed`, `_summary_line`) are the uncommitted working-tree changes in `mts_to_dnxhr_gui.py` and `tests/test_mts_to_dnxhr_gui.py`. **Commit those first.** This plan builds on them.

## Implementation

### 0. Land the timer work

Commit the current uncommitted timer changes in `mts_to_dnxhr_gui.py` and `tests/test_mts_to_dnxhr_gui.py` on their own.
**Done when:** `git status` shows those two files clean, and `python -m unittest -v` passes.

### 1. Core: cap, suggestion, scheduler (`mts_to_dnxhr.py`)

- Add `MAX_JOBS = 4` near the other module constants (after `YADIF`, around line 36).
- Add `suggested_jobs(cpu_count: Optional[int] = None) -> int`. An omitted argument (or an explicit `None`, which is the same call in Python) means "read `os.cpu_count()`": `n = os.cpu_count() if cpu_count is None else cpu_count`. The result is `max(1, min(3, (n or 0) // 6))`, so a **resolved** count of `None` (when `os.cpu_count()` cannot tell) or `0` gives 1. `suggested_jobs()` and `suggested_jobs(None)` both return 3 on this box. Add a one-line docstring that points at this plan's rationale (CPU idle headroom, ~28 MB/s per HQX stream).
- Add `run_indexed(count: int, jobs: int, work: Callable[[int], None], cancel: threading.Event) -> list[int]`:
  - `workers = max(1, min(jobs, MAX_JOBS, count))`. If `count <= 0`, return `[]`.
  - Each worker loops. Under a `threading.Lock`, it takes the next index; it stops when the indices run out. If `cancel.is_set()`, it appends the index to `unstarted` and continues, which drains the rest. Otherwise it releases the lock and calls `work(i)`.
  - `workers == 1`: run the loop inline in the caller's thread, with no thread.
  - `workers > 1`: start `daemon=True` threads, then join with `while t.is_alive(): t.join(0.2)`. Plain `join()` is not Ctrl+C-interruptible on Windows. On `KeyboardInterrupt` during the join, call `cancel.set()`, finish joining, then re-raise.
  - If `work` raises inside a thread, keep the first exception, call `cancel.set()`, stop that worker, and re-raise in the caller after the join.
  - Return `sorted(unstarted)`.
- **Thread-safe output-folder cleanup in `convert_one`.** Today two workers that share `final_dst.parent` can race. Worker B has run `mkdir` and is inside `probe` (no `.part` yet). Worker A fails or is cancelled, and its `_remove_dir_if_empty` removes the now-empty export folder, so B's encode fails. Fix:
  - Add a module-level `_DIR_LOCK = threading.Lock()` and `_dir_users: dict[str, int] = {}`. Both `_claim_dir` and `_release_dir` compute `key = os.path.normcase(os.path.abspath(directory))` and use only that string as the key (see the last bullet). Use one lock, not one per folder, so `mkdir(parents=True)` of `out/sub` can never interleave with an `rmdir` of `out`.
  - Add `_claim_dir(directory)`: under `_DIR_LOCK`, run `directory.mkdir(parents=True, exist_ok=True)`, then increment `_dir_users[key]`. Increment only after `mkdir` succeeds, so the existing `OSError → failed` path (and `test_mkdir_oserror_fails_the_file_and_returns`) is unchanged.
  - Add `_release_dir(directory, remove_if_empty: bool)`: under `_DIR_LOCK`, decrement the count, delete the key at 0, and call `_remove_dir_if_empty(directory)` only when `remove_if_empty` is true **and** the count reached 0.
  - In `convert_one`, replace the `mkdir` at line 573 with `_claim_dir(final_dst.parent)`. Wrap everything after it (probe through the final return) in one `try/finally` that calls `_release_dir(final_dst.parent, remove_if_empty=cleanup)`. Replace each of the six `_remove_dir_if_empty(final_dst.parent)` calls with `cleanup = True`. `cleanup` starts `False`, so the `ok` path and the re-raised `KeyboardInterrupt` path keep today's behavior of not removing the folder.
  - With one caller at a time, the count always returns to 0 on the same call, so single-file behavior (and `test_probe_error_strips_duplicate_path_and_empty_dir`) is unchanged.
  - Key the dict by `os.path.normcase(os.path.abspath(directory))`, so the same folder spelled two ways on Windows maps to one entry, without the filesystem access of `resolve()`. In one batch, every destination comes from the same output root anyway.

**Done when:** the module imports, and `python -c "import mts_to_dnxhr as m; print(m.suggested_jobs(), m.MAX_JOBS)"` prints `3 4` on this box (20 logical processors).

### 2. Core tests (`tests/test_mts_to_dnxhr.py`)

Add a new `JobsTests` class:

- **`suggested_jobs` table (direct argument):** `0→1`, `4→1`, `8→1`, `11→1`, `12→2`, `16→2`, `18→3`, `20→3`, `128→3`. The result is always `<= MAX_JOBS`. `None` is **not** a row here, because it means "read `os.cpu_count()`".
- **`suggested_jobs()` with no argument:** patch `mts_to_dnxhr.os.cpu_count` to return `None` and assert 1; patch it to return `20` and assert 3. This covers the missing-count path and the default lookup without depending on the test machine.
- **`run_indexed` concurrency bound:** `count=8`, `jobs=3`. `work` increments a lock-guarded "in flight" counter, records the max, sleeps about 20 ms, then decrements. Assert max in flight is 3 and every index ran exactly once.
- **Proof of parallelism:** `jobs=2` with a `threading.Barrier(2, timeout=5)` inside `work`. The test passes only if two calls overlap.
- **`jobs > MAX_JOBS` is clamped:** `jobs=99` gives max in flight `<= 4`.
- **`jobs=1` runs inline:** `threading.current_thread()` inside `work` is the caller's thread, and the order is `0..n-1`.
- **Cancel:** `work(1)` sets `cancel`. With `jobs=1`, the return value is `[2, 3, ...]`. With `jobs=2`, every index appears exactly once, in either the ran set or the returned set.
- **Cancel set up front:** `work` is never called, and the return value is `list(range(count))`.
- **Exception propagation:** `work(0)` raises `RuntimeError`. It is re-raised from `run_indexed`, and `cancel` is set.

In `CliTests` (next to `test_probe_error_strips_duplicate_path_and_empty_dir` at `tests/test_mts_to_dnxhr.py:506`, which must still pass unmodified), add:

- **`test_shared_parent_survives_sibling_failure`:** two sources, one shared `root / "out"` parent. Patch `mts_to_dnxhr.probe` with a side effect keyed by `src.name`. B's probe sets `b_in_probe` and then waits on `release_b` (`Event`, `timeout=5`); A's probe waits on `b_in_probe` (`timeout=5`) and raises `ProbeError`. Run each `convert_one` in its own thread. After A's thread joins, assert A returned `failed` **and `dst.parent.exists()`**. Then set `release_b`. B's probe also raises `ProbeError`. After B joins, assert the parent is gone, because the last failing user cleans up. Also assert `m._dir_users` is empty at the end.

**Done when:** `python -m unittest tests.test_mts_to_dnxhr -v` passes.

### 3. GUI worker: parallel `run_batch` (`mts_to_dnxhr_gui.py`)

- Signature: `run_batch(pairs, opts, ffmpeg, ffprobe, post, cancel, jobs: int = 1)`. Existing callers and tests stay valid.
- Move today's per-file body into a local `work(index)` closure with its own `last_bucket`, `on_progress`, `convert_one` call, and status normalization. Tally `ok`, `skipped`, `failed`, `cancelled` under a `threading.Lock`.
- On `core.ConversionCancelled`: post `file_finished … cancelled` for **that** index, call `cancel.set()` so sibling workers stop, and return. The loop no longer posts "later" rows itself.
- On any other `Exception`: post `failed` with `str(exc)` (unchanged).
- Body: `unstarted = core.run_indexed(len(pairs), jobs, work, cancel)`. Then post `("file_finished", i, "cancelled", "")` for each `i` in `unstarted` and count them. Keep the existing `try/finally` that posts `batch_finished`. If `run_indexed` re-raises, which can only happen for a bug in `work` because `work` catches `Exception`, the `finally` still fires.
- Check that the `jobs=1` event sequence is identical for all five existing `RunBatchTests` (ok/skipped/failed order, cancel during the second file, unexpected exception, throttling, cancel set up front).

**Done when:** the existing `RunBatchTests` pass unmodified.

### 4. GUI worker tests (`tests/test_mts_to_dnxhr_gui.py`, `RunBatchTests`)

- **`jobs=2` overlap:** `fake_convert` waits on `Barrier(2, timeout=5)`. Assert that two `file_started` events come before the first `file_finished`, that every index gets exactly one `file_finished`, that `file_started(i)` precedes `file_finished(i)`, and that `batch_finished` is last with the correct counts.
- **`jobs=2` cancel mid-batch (4 pairs):** the second call sets `cancel` and raises `ConversionCancelled`. Assert one `file_finished` per index, `ok + cancelled == 4`, and `batch_finished` last.
- **Per-file throttling stays independent:** with `jobs=2`, two fakes interleave progress. Each index's `file_progress` fractions are non-decreasing, and each index has 101 or fewer of them.
- **Status-line helper (pure, no Tk):** see step 5. Assert the zero-active, one-active (known and unknown `pct`), two-active, and three-active strings. The k=3 case passes unsorted input `[(3, …), (0, …), (1, …)]` with count 10 and expects `Converting 3 at once (1, 2, 4 of 10)`.

**Done when:** `python -m unittest tests.test_mts_to_dnxhr_gui -v` passes.

### 5. GUI state, status line, and control (`mts_to_dnxhr_gui.py`, `App`)

- **State.** Add a small `@dataclasses.dataclass class _ActiveFile` with `t0: float`, `pct: Optional[int]` (`None` means unknown duration), and `fraction: float`. Replace the scalar fields `_file_t0`, `_active_index`, `_status_pct`, `_current_fraction`, `_known_total` with `self._active: dict[int, _ActiveFile]` and `self._batch_jobs: int = 1`. Update `__init__`, `_start_batch`, and the `batch_finished` reset. Delete `_elapsed_file` (its only reader of `_file_t0`); `_with_times`, its only caller, computes the file time from the single `_active` entry instead (next bullets).
- **Pure helper** for tests: `running_prefix(count: int, active: Sequence[tuple[int, str, Optional[int]]]) -> str`, taking `(index, name, pct)` tuples.
  - Zero active: `Converting…`.
  - One active: today's exact `Converting {i+1} of {count}: {name} ({pct}%)`, or the `…` form when the duration is unknown.
  - Two or more: `Converting {k} at once ({ids} of {count})`, where `ids = ", ".join(str(i + 1) for i in sorted(indices))`. Every active index appears, not just two.
  - `App._running_prefix` calls this helper.
- **`_with_times`.** Append `file M:SS` only when `len(self._active) == 1`, using that entry's `t0`. Always append `total`. `Stopping…` keeps `include_file=False`.
- **`_handle_event`:**
  - `file_started`: insert `_ActiveFile(time.monotonic(), 0, 0.0)`.
  - `file_progress`: update that entry's `pct` and `fraction`.
  - `file_finished`: for every status (`ok`, `skipped`, `failed`, `cancelled`), append ` (M:SS)` to that status's existing label using the entry's `t0`, if the index is in `_active`, then pop it. Unstarted rows posted as `cancelled` are not in `_active` and get the plain `Cancelled`, as they do today. This replaces the current `self._active_index == index` guard.
  - `_update_overall` uses `Σ fraction` over active entries with a known `pct`.
- **`_refresh_running_status` gap.** Keep the early return, changed from `if self._active_index is None: return` to `if not self._active: return`. This leaves the previous line up between files instead of flashing `Converting…` on the `jobs == 1` path.
- **Per-row timers.** When `self._batch_jobs > 1`, `_refresh_running_status` (already called from `_poll` every 100 ms) also rewrites each active row's cell to `{pct}% · M:SS`, or `Converting… · M:SS`. Place this rewrite right after the `not self.running or self._quitting` return and **before** the `Stopping…` return (`mts_to_dnxhr_gui.py:869`), so row clocks keep ticking after Stop until each row's `file_finished` arrives. It writes only when the text changed, to avoid flicker. Progress events use the same format.
- **Control.** Leave `deinterlace_chk` on grid row 4 of `outer`, unchanged. Add a new `ttk.Frame` `jobs_row` at **row 5** (`sticky="w"`, `pady=(0, 4)`), packed left to right with `ttk.Label(text="Parallel encodes:")`, then `self.jobs_var = tk.IntVar(value=1)` with `self.jobs_spin = ttk.Spinbox(jobs_row, from_=1, to=core.MAX_JOBS, width=3, textvariable=self.jobs_var, state="readonly")`, then a grey (`foreground="#666666"`, matching `self.summary`) `ttk.Label` reading `(suggested max {core.suggested_jobs()} for this PC)`.
  - Shift every later row of `outer` down by one: summary 5→6, banner 6→7, separator 7→8, status label 8→9, progress 9→10, actions 10→11. `banner.grid_remove()` / `banner.grid()` (around line 665) keep the stored options, so they need no change. `outer.rowconfigure(2, weight=1)` (the tree) is unchanged, so the tree absorbs the lost height.
  - Keep `minsize(560, 440)`.
  - `_update_buttons` sets the spinbox to `readonly`, and `_set_running_ui` sets it to `disabled` or `readonly`.
- **Start.** In `_start_batch`, read `jobs = max(1, min(core.MAX_JOBS, int(self.jobs_var.get())))`, falling back to 1 on `tk.TclError` or `ValueError`. Set `self._batch_jobs = jobs` and pass `jobs` to `run_batch` as `kwargs`.
- **Stop text.** In `_confirm_stop`, when `self._batch_jobs > 1`, use "Files being converted now will be deleted. Finished files are kept."
- **Quit.** No change. `self.worker` is the `run_batch` thread, which stays alive until `run_indexed` has joined every encode thread, so `_wait_to_quit`'s 15 s deadline still covers all in-flight `_stop_process` calls. Those calls run concurrently, one per worker.

**Done when:** the unit tests pass, and the manual GUI check in Verification passes, including the hint being fully visible at 560×440 on this 144 DPI display.

### 6. CLI `--jobs` (`mts_to_dnxhr.py`)

- In `build_parser`, add `-j/--jobs`, `type=_jobs_arg`, `default=1`, `metavar="N"`, with help `"Encode up to N clips at once (1-{MAX_JOBS}). Suggested for this PC: {suggested_jobs()}"`. `_jobs_arg` raises `argparse.ArgumentTypeError` outside the range 1 to `MAX_JOBS`, which argparse turns into exit code 2.
- `_print_header` gains a `jobs` parameter and prints `jobs: N`. This is the one intended change to the default transcript. If `jobs > suggested_jobs()`, it also prints `note: --jobs N is above the suggested {S} for this PC`.
- In `_encode_all(pairs, opts, ffmpeg, ffprobe, jobs=1)`:
  - **`jobs == 1`:** keep the current loop exactly as it is, with the inner tqdm bar and the current `KeyboardInterrupt → 130` handling.
  - **`jobs > 1`:**
    - Create `cancel = threading.Event()` and an outer `tqdm(total=len(pairs), unit="file", desc="files")`.
    - `work(i)` calls `convert_one(src, dst, opts, ffmpeg, ffprobe, on_progress=lambda _s, _t: None, cancel=cancel)`. The no-op callback turns off the per-file tqdm bars, which cannot share a terminal across threads, and enables cancel checks.
    - `work(i)` is a short copy of the current per-file tally: `ok` / `skipped` / `failed` counters plus `failures.append((src, err))` on `failed`, all under a lock, followed by `bar.update(1)` under the same lock.
    - `work` catches `ConversionCancelled` itself, counts it as "not converted" (no counter, no failure), and calls `bar.update(1)`. This keeps `ConversionCancelled` from being re-raised by `run_indexed` in place of the `KeyboardInterrupt` path.
    - `run_indexed(...)` is wrapped in the existing `except KeyboardInterrupt: print("\ninterrupted", file=sys.stderr); return 130`. That is the only path to exit 130. `run_indexed` sets `cancel` and joins before re-raising, so the in-flight ffmpeg processes are stopped and their `.part` files removed.
    - After the loop, both paths share the existing summary line (`converted …, skipped …, failed …`) and the existing `for src, err in failures:` reprint (`failed: {src}` plus the multi-line tail), unchanged.
- `--dry-run` ignores `--jobs`.
- In `main`, pass `args.jobs` through.

**Done when:** `python mts_to_dnxhr.py --help` lists `--jobs` with the suggestion. `python mts_to_dnxhr.py x.MTS --jobs 0` and `--jobs 5` exit with code 2.

### 7. CLI tests (`tests/test_mts_to_dnxhr.py`, `CliTests`)

- `test_help_lists_flags_and_defaults`: add `"--jobs"` to the flag tuple and assert `args.jobs == 1`.
- `--jobs 0`, `--jobs 5`, and `--jobs x` cause `SystemExit(2)` from `parse_args`.
- With `convert_one` mocked and a `Barrier(2)`, `_encode_all(pairs, …, jobs=2)` returns 0 for all-ok and 1 when one file fails, and `convert_one` is called with a non-`None` `on_progress` and `cancel`. In the failing case, captured stdout contains the `failed: {src}` reprint after the summary line.
- `jobs=2` where the mocked `convert_one` raises `ConversionCancelled` for one file: `_encode_all` returns normally (not 130, no exception), and that file is in neither the converted nor the failed count.
- `jobs=1` still calls `convert_one` without `on_progress`, so the inner bar is preserved.

**Done when:** `python -m unittest -v` passes.

### 8. Docs (`README.md`)

- Usage (`## Usage`, around line 60): add a `--jobs` example and a sentence on the suggestion formula, and say to use 1 for HDD or USB export targets.
- Desktop app (`## Desktop app (Windows)`, around line 103): describe the "Parallel encodes" control and the hint.
- Limitations (line 174): replace "Encodes run one at a time … no parallel batch" with "Encodes run in software. Up to 4 clips can encode at once (default 1). There is no GPU encoder." Keep the disk-full bullet and add "with several parallel encodes, a full disk can fail every in-flight file at once."

**Done when:** the README matches the shipped flags and labels.

### 9. Benchmark the suggestion (manual, records evidence)

Make four copies of `samples/01 American Landscape.MTS` in a gitignored temp folder on an SSD. Run:

`python mts_to_dnxhr.py <dir> -o D:\tmp\par --duration 30 --overwrite --jobs N` for N = 1, 2, 3, 4

Record the wall time, peak RAM from Task Manager, and disk MB/s. Repeat with `--deinterlace`.

- If 3 is not at least about 10% faster than 2 on this 20-logical-processor box, change the divisor or the cap in `suggested_jobs` to make the suggestion 2, and update the tests.
- Put a short results table in the README "Verified" section.
- Delete `D:\tmp\par` afterward.

**Done when:** the numbers are recorded and the formula is either confirmed or adjusted.

## Verification

- `python -m unittest -v` passes with no FFmpeg or Tk window. That covers the existing tests plus `JobsTests`, the new `RunBatchTests` cases, the `running_prefix` cases, and the CLI `--jobs` cases.
- `$env:MTS_SMOKE='1'; python -m unittest -v` still passes. The default `jobs=1` path is unchanged.
- `python -c "import mts_to_dnxhr as m; print(m.suggested_jobs(), m.MAX_JOBS)"` prints `3 4` on the dev box.
- `python mts_to_dnxhr.py --help` shows `-j N, --jobs N … Suggested for this PC: 3 (default: 1)`.
- Invariant: `git diff` shows no change to `build_command` or `run_ffmpeg`, and `DefaultsTests` passes. That means no argv fork. The only `convert_one` diff is `_claim_dir` / `_release_dir` and the `cleanup` flag.
- `test_probe_error_strips_duplicate_path_and_empty_dir` passes unmodified, and `test_shared_parent_survives_sibling_failure` passes.
- **Manual GUI check** (`python mts_to_dnxhr_gui.py`, 3–4 sample copies, `Parallel encodes = 2`, export to an SSD folder):
  1. Two rows show rising `% · M:SS` at the same time. The status line reads `Converting 2 at once (1, 2 of 4) · total M:SS` and ticks every second. When the last clip runs alone, it returns to `Converting 4 of 4: … · file M:SS · total M:SS`.
  2. The overall bar moves smoothly with no jumps backward.
  3. Finished rows read `Done (M:SS)`, and the summary reads `Finished: … · Total M:SS`. Include one corrupt or zero-byte clip and check that its `Failed (double-click for details) (M:SS)` cell is readable. The Status column is `width=180, stretch=False`, and that text is already wider than 180 px. If it is clipped, note it; widening the column is a separate fix. Check that the sibling encodes in the same export folder still finish.
  4. Stop during the encode deletes both in-flight `.part` files, and later rows read `Cancelled`. The summary counts add up to the clip count.
  5. Close the window during the encode and choose "Stop and quit". No `ffmpeg.exe` processes are left in Task Manager after 15 s.
  6. The spinbox is disabled while running. At the 560×440 minimum size on this 144 DPI display, the "Parallel encodes" row sits under the deinterlace checkbox and the full `(suggested max 3 for this PC)` hint is visible. The tree still shows at least a few rows.
- Benchmark evidence from step 9 is recorded in the README.

## Risks

- **CPU oversubscription.** Every ffmpeg auto-threads to all cores, so N processes each with T threads compete. Throughput can plateau or regress past 2–3 streams. Mitigated by cap 4, suggestion ≤3, default 1, and the step 9 benchmark. A real fix (`-threads`) is out of scope.
- **HDD or USB export targets.** Parallel writes interleave and can be slower than sequential ones. Drive type can't be detected reliably from stdlib, so the README and hint guidance are the only guardrail.
- **Shared output folder cleanup.** Without the step 1 refcount, one worker's failure could `rmdir` the export folder out from under a sibling that is still probing. The refcount and the single `_DIR_LOCK` close this. The residual risk is a caller that creates folders outside `convert_one` (the GUI's `_start_batch` `mkdir`), which runs before any worker starts and so cannot race.
- **Vertical space.** The new options row costs about one line of height at 440 px. The tree (the only weighted row) absorbs it. Manual check 6 confirms the tree stays usable.
- **Disk full mid-batch** can now fail up to N files at once instead of one. The estimate dialog still runs first, and each failure is still reported per row.
- **Event ordering assumptions.** Any GUI code that assumes "one active row" (for example, the old `_active_index` guard on the `Done (M:SS)` stamp) gives wrong timers. Step 5 removes every scalar per-file field; grep for `_active_index`, `_file_t0`, `_status_pct`, and `_elapsed_file` to confirm none are left.
- **Quit with N encodes.** `_stop_process` can take up to 20 s per process (terminate, wait 10 s, kill, wait 10 s), which is longer than the 15 s quit deadline. This is true today, and with daemon threads it can now leave up to N orphaned ffmpeg processes instead of one. The terminate path normally returns in well under a second, but check this in manual step 5.
- **Ctrl+C on Windows.** Children are spawned with `_CREATE_NO_WINDOW`, so they do not get the console Ctrl+C. Shutdown depends on `cancel`, which is why the CLI parallel path has to pass `on_progress` (cancel is only checked on that path) and use the `join(0.2)` polling loop.
- **Test flakiness.** Barrier-based tests use `timeout=5` so a broken scheduler fails fast instead of hanging CI.

## Open questions

- **Default value.** Should the GUI spinbox default to `suggested_jobs()` instead of 1? This plan keeps 1 for a zero-surprise rollout. The change is one line once the step 9 numbers are in.
- **Persisting the choice** between launches: there is no settings file today, so it is listed under Out of scope unless requested.

## PR split

1. **PR 1:** steps 0–5 and the Desktop app part of step 8 (core scheduler and constants, `convert_one` folder refcount, GUI parallelism, tests).
2. **PR 2:** steps 6–7, the rest of step 8, and step 9 (CLI `--jobs`, docs, benchmark).

PR 1 is usable on its own. PR 2 reuses `run_indexed` without changing it.

## Out of scope

- Per-process `-threads` tuning, GPU encode or decode, or any other ffmpeg argv change.
- Auto-detecting SSD vs HDD, auto-tuning N from live CPU or disk load, or changing N while a batch is running.
- Splitting one clip into segments to encode a single file in parallel.
- Saving the parallel setting between launches, or a settings dialog.
- Changing the ×14 free-space estimate or adding a per-stream write-rate check.
- Editing the prior plan `plans/draft/simple-export-gui-claude-2026-11-07.md`. This plan supersedes its "parallel encodes" non-goal.

**Ready for implementation whenever you are.**
