# Simple Export GUI — Implementation Evaluation

*Claude Code turns used: 31 / max 100*

*Evaluator: claude · 2026-11-07 · Reviews the implemented `simple-export-gui-claude-2026-11-07.md` against the working tree.*

## Verdict: All nine steps are in place and the core contracts hold. Only Low and Trivial findings remain.

All nine implementation steps landed. The CLI hooks are backward-compatible: the dry-run argv is byte-identical to `HEAD`, and the existing tests have zero deleted lines. Every automated gate passes, with and without FFmpeg on PATH. A full GUI-driven encode produced the expected DNxHR HQX output. I also drove Stop and window-close with real ffmpeg, and both left no `.part` file, no stray ffmpeg process, and no empty export folder. The remaining issues are a few edge-case contract gaps: the tkdnd runtime fallback, a dialog race during quit, an empty folder left behind on a blocked run, plus thin coverage of the progress path and manual checklist items with no recorded evidence. None of these blocks a merge.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 1–9 all present; exe built; out-of-scope items stayed out (no extra options, no bundled FFmpeg) |
| Contract fidelity | 4 | Argv/defaults parity proven; CLI dry-run identical. Gaps: the plan's "tkdnd missing → Browse-only" fallback is not real at runtime; blocked runs leave an empty export folder |
| Verification honesty | 4 | Unit gates green both ways; mutation checks confirm the hook tests bite; smoke test passes. GUI tests never exercise the progress/throttle path; the manual checklist has no recorded results |
| Finding severity | 4 | Low only |
| Merge readiness | 4 | Safe to merge; the Lows are cheap to fix |

**Overall completeness:** 21/25 · **percent:** 84%
**Band:** nearly-done
**Open findings:** Critical 0 · High 0 · Low 5 · Trivial/Noted 6

## Loop signal

**Loop signal:** one-more-fix
**Signal rationale:** No Critical or High findings. A single pass can close the five cheap Lows (startup fallback, quitting guard, mkdir order, two tests, a recorded manual checklist).

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. Hooks in `mts_to_dnxhr.py`** | Complete | `_CREATE_NO_WINDOW` (`mts_to_dnxhr.py:45-48`); `ConversionCancelled` (`:55`); `probe` gets `creationflags` + `stdin=DEVNULL` (`:245-246`); `run_ffmpeg` keyword-only `on_progress`/`cancel`, tqdm branch unchanged, callback branch with per-line + pre-wait cancel checks and `(total,total)` only when total known (`:480-508`); `convert_one` `emit = log or tqdm.write`, cancel check after exists-check and before `mkdir` (`:566-571`), `except ConversionCancelled` after `KeyboardInterrupt` and before `OSError`/`Exception` (`:603-605`). Dry-run output identical to `git show HEAD:mts_to_dnxhr.py` |
| **2. `HookTests`** | Complete | 7 tests in `tests/test_mts_to_dnxhr.py` (+238 / −0 lines). The fake's `poll()` stays `None` until terminate/kill, as the plan requires. Mutation check: removing the pre-mkdir cancel check, the `except ConversionCancelled` clause, or probe's `creationflags`/`stdin` each turns the suite red |
| **3. GUI core** | Complete | stdout/stderr guard runs before `import mts_to_dnxhr` (`mts_to_dnxhr_gui.py:14-28`); `DEFAULT_OPTIONS` derived from the parser (`:64-76`); `collect_items`, `plan_outputs`, `estimate_needed_bytes`, `free_bytes`, `resource_path`, `locate_tools`, `run_batch` all match the spec (`:97-291`) |
| **4. GUI core tests** | Complete (thin in one area) | `tests/test_mts_to_dnxhr_gui.py`: defaults/argv parity incl. yadif, mixed-drop count = 3, case-variant dedupe, plan/collision, estimate/free, three `run_batch` cases, `locate_tools`, `resource_path` frozen, reimport without `tkinterdnd2`, ICO header parse. Progress events and throttle are never exercised (Finding 4) |
| **5. Tk `App` + `main()`** | Complete | Layout, controls, status strings, Stop/Quit flows, `iconbitmap(default=…)` in try/except, DPI awareness + AppUserModelID (`:294-934`). The harness-driven flows below all behave per spec |
| **6. Dependencies** | Complete | `requirements.txt` adds `tkinterdnd2>=0.4,<0.5` (installed 0.4.4.1); `requirements-build.txt` = `-r requirements.txt`, `pyinstaller>=6,<7` (6.22.3), `pillow>=11,<12` (11.3.0) |
| **7. Icon** | Complete | `scripts/make_icon.py` re-run to a temp path is byte-identical to the committed `assets/app.ico` and `app-256.png`, so the output is deterministic. All 9 sizes present; self-check passes. The art is close to spec; see Trivial 6 |
| **8. Packaging** | Complete | `scripts/build_exe.ps1` uses absolute `$ico` paths and fails fast. Generated spec has absolute `icon=`/`datas`. `dist/MTS-to-DNxHR.exe` (12.9 MB) is newer than the last GUI edit, PE subsystem = 2 (GUI, so no console), and the embedded icon is the custom tile. The Analysis TOC contains `tkdnd\win-x64\libtkdnd2.9.5.dll` |
| **9. README** | Complete | "Desktop app (Windows)" section sits between Usage and Output layout and covers run/build/pin/icon change/`ie4uinit`/SmartScreen/skip/mirroring/card-root tip. Requirements, Profiles free-space line, and Limitations are updated as specified |

## Findings (ranked)

### 1. A tkdnd load failure at runtime crashes startup instead of falling back to Browse-only. *(Low)*

The plan's Risks section promises: "If `--collect-all tkinterdnd2` misses the native tkdnd DLLs, the exe falls back to Browse-only (the guarded import keeps it working)." The guarded import only protects against a missing *Python package*. When the package imports but the DLL can't load, `tkinterdnd2.TkinterDnD.Tk()` raises `RuntimeError('Unable to load tkdnd library.')` (`.venv/Lib/site-packages/tkinterdnd2/TkinterDnD.py:71`, called from `:301`). `main()` (`mts_to_dnxhr_gui.py:929-932`) does not catch it, so a windowed exe would die at launch. Today the DLL is bundled (confirmed in the TOC), so this is latent. It is still exactly the failure mode the plan said was handled.

**Remediation:** In `main()`, wrap `TkinterDnD.Tk()` in `try/except (RuntimeError, tk.TclError)` and fall back to `tk.Tk()`. Pass an effective `dnd` flag into `App` (or reset the module `DND_AVAILABLE`) so `_register_drop` and the drop-zone text reflect the fallback.

### 2. No "quitting" guard: the finish dialogs can fire during Quit or over the Stop confirmation. *(Low)*

`_on_close` sets `cancel` and starts `_wait_to_quit`, but `_poll` keeps draining events. If it handles `batch_finished` before `_wait_to_quit` sees the worker dead, `_show_finished` (`:870-894`) pops the "Stopped: …" summary and "Open the export folder?" during a quit the user already confirmed. `root.destroy()` can then run while that modal is open. Tk services timers during `tk_messageBox` on Windows. Likewise, if the batch finishes while the "Stop converting?" modal is open, the summary dialog appears on top of it. In my harness (mocked dialogs, real ffmpeg), five close-mid-encode runs never showed the summary, so the race window is narrow. It is still unguarded, and the plan's Quit flow has no summary step.

**Remediation:** Set `self._quitting = True` in `_on_close` after the user confirms. Skip `_show_finished` (and any further UI work) when it is set.

### 3. A blocked run leaves an empty export folder. *(Low)*

`_start_batch` runs `out_dir.mkdir(...)` (`:697-705`) before the collision check and the disk-space prompt. A Name clash or a "No" on Low disk space therefore leaves a new empty folder behind. The harness showed `out created: True` after the Name clash dialog. This follows the plan's literal step order, but it contradicts verification item 8 ("nothing is written") and the "never touch outside the export folder unless converting" spirit.

**Remediation:** Run collisions and the disk check before `mkdir`. `free_bytes` already walks to an existing ancestor, so it works on a missing folder. Alternatively, record whether the folder existed and remove it if it is still empty on an early return.

### 4. The GUI tests never exercise the progress path or the pre-cancel path. *(Low)*

All three `RunBatchTests` fakes return immediately without calling `on_progress`. The 1% throttle, the 0–1 clamp, the `None`-fraction branch, and the `file_progress` event shape (`mts_to_dnxhr_gui.py:233-256`) therefore have no coverage. A regression there would only surface in manual testing. The "cancel already set before file *k*" branch (`:227-231`, which posts `cancelled` with no `file_started`) is also untested.

**Remediation:** Add a test whose fake `convert_one` calls `kwargs["on_progress"]` with, for example, 1,000 steps over a 10 s total, plus one overshoot and one `total=None` call. Assert at most 101 `file_progress` events for the known total, a fraction clamped to 1.0, and `None` for the unknown total. Add a test with `cancel` pre-set that asserts no `file_started` and `batch_finished == (0, 0, 0, n)`.

### 5. The manual GUI checklist has no recorded results. *(Low)*

No artifact records the Verification → Manual GUI checklist. I re-covered items 3, 4, 5, 6, 8, 9, 12, and 14 programmatically against source (see Verification performed). These items remain unverified by anyone I can see: 1 (a real Explorer drop), 10 (exe-dir FFmpeg on the built exe), 11 (no console flash in the exe; the PE subsystem and `CREATE_NO_WINDOW` tests make this very likely), 13 (title bar, taskbar, Alt-Tab, pin/shortcut, 150% scaling), and the step 8 done-when "drag the sample onto the built exe adds a row". These are the plan's acceptance criteria for the icon and drag-and-drop goals.

**Remediation:** Run items 1, 10, 11, and 13 on `dist\MTS-to-DNxHR.exe` and record pass/fail (a short checklist file in `plans/draft/` is enough).

### 6. The icon's sprocket holes render as white bumps, not holes. *(Trivial)*

`scripts/make_icon.py:84-92` draws filled white discs centered on the frame's top and bottom stroke. In `assets/app-256.png` they read as scalloped bumps sticking out of the frame, not as holes punched in a film strip. The frame is also portrait (41% × 52% of the tile). It is still original, legible, and on-palette; the 16 px variant correctly drops the holes.

**Remediation:** Optional. Draw the holes in the tile color inside a thicker top and bottom band, or accept the art as is.

### 7. The drop zone isn't visibly disabled while running. *(Trivial)*

Plan step 4 of Convert says to disable "drop zone, Add, …". Drops and clicks are correctly ignored while running (`:475`, `:492`), but the zone keeps its normal look and text, so a mid-batch drop silently does nothing.

**Remediation:** Optional. Grey the drop label or set its text to "Converting… drops are paused" while running.

### 8. `returncode = proc.wait()` was not hoisted out of the tqdm block. *(Noted)*

The plan asked to hoist it. The implementation instead keeps the tqdm branch verbatim and duplicates the wait in the callback branch (`mts_to_dnxhr.py:483-508`). Behavior is identical and the CLI path is literally unchanged, which is arguably safer.

**Remediation:** No action.

### 9. `file_started` always shows "0%". *(Noted)*

The row then switches to "Converting…" on the first progress event when the duration is unknown (`:787-806`). Duration isn't known until `probe` runs inside `convert_one`, so this is the only feasible reading of the spec.

**Remediation:** No action.

### 10. The plan's "not a git repo" constraint is stale. *(Noted)*

`.git` was created at 2026-11-07 21:39:55, four minutes after the plan's last edit at 21:36. It holds one commit, `2376a94` ("Add MTS/M2TS to DNxHR CLI…", the pre-GUI baseline only), and an `origin` remote. All GUI work is uncommitted. I can't tell who ran `git init`. No GUI work was committed or published, so the substance of the constraint holds for this implementation.

**Remediation:** No action. Update the plan's Constraints and the eval prompt if they are reused.

### 11. Cancelling removes a pre-existing empty export folder. *(Noted)*

`_remove_dir_if_empty(final_dst.parent)` on cancel also deletes a user-chosen export folder that was empty before the run. This is CLI behavior, not new in this change. The finish dialog correctly guards the "Open folder?" prompt with `is_dir()`.

**Remediation:** No action for v1.

## Net assessment

The implementation is safe to merge. The wrap-don't-fork constraint is respected: the GUI adds no FFmpeg flags, its defaults come from the CLI parser, and the CLI argv and tests are unchanged. The cancel and cleanup semantics work end to end with real ffmpeg. Before merge, the cheapest wins are:

- the `main()` fallback for tkdnd (Finding 1), which is what the plan already claimed;
- the quitting guard (Finding 2);
- moving `mkdir` after the preflight checks (Finding 3).

Each is a few lines. Adding the progress-path test (Finding 4) and recording the manual exe checks (Finding 5) would close out verification honestly. The icon art and drop-zone styling can wait.

## Verification performed

- `.\.venv\Scripts\python.exe -m unittest` → **Ran 44 tests, OK (skipped=2)**. The skips are the symlink test (no privilege) and the opt-in smoke test.
- Same with FFmpeg stripped from PATH (`Get-Command ffmpeg` → none) → **44 tests OK (skipped=2)**.
- `$env:MTS_SMOKE='1'; … unittest tests.test_mts_to_dnxhr.SmokeTest` → **OK** (real FFmpeg, 3.1 s).
- CLI regression: `git show HEAD:mts_to_dnxhr.py` vs the working tree, both with `"samples/01 American Landscape.MTS" --dry-run` → **identical output**.
- `git diff --numstat tests/test_mts_to_dnxhr.py` → `238 0`, so no existing test lines changed.
- Hook mutation tests (scratch copy in `D:\tmp\pwtest\mut`): (1) remove the pre-mkdir cancel check, (2) remove `except ConversionCancelled`, (3) remove probe `creationflags`/`stdin`. Each one → **FAILED**.
- `scripts/make_icon.py --out <tmp>` → byte-identical `.ico` and `.png` to the committed assets; the Pillow-reported sizes are all 9.
- Built exe: PE subsystem = 2 (GUI); `ExtractAssociatedIcon` shows the custom tile; the Analysis TOC includes `tkdnd\win-x64\libtkdnd2.9.5.dll` and `assets\app.ico`; the spec uses absolute icon and data paths.
- Tk harness, driving the real `App` from source with real ffmpeg and dialogs mocked (`D:\tmp\pwtest\gui_*.py`, outside the repo):
  - Add the sample plus the `samples` folder → "Added 1 clips. Ignored 2 other files." (README.md plus the existing `dnxhr\*.mov`). Export prefilled `…\samples\dnxhr`.
  - Full Convert → 30 s. Row % and overall bar advanced (3.8 → 95.7 → 100). Row "Done", status "Finished: 1 converted, 0 skipped, 0 failed.", then the showinfo and "Open the export folder?" prompts. `ffprobe` of the output: `dnxhd`, `DNXHR HQX`, `yuv422p10le`, 1920×1080, `30000/1001`, `pcm_s16le`, 48000, 2 ch, matching the README.
  - Convert again → "Skipped (already exists)", "0 converted, 1 skipped, 0 failed".
  - Stop at 4 s → "Stop converting?" prompt, status "Stopping…", then "Stopped: 0 converted, 0 skipped, 0 failed, 1 not converted." No `.part`, no `ffmpeg.exe` in `tasklist`, export folder removed, no "Open folder?" prompt.
  - Close at 4 s (5 runs) → only the "Quit?" prompt; no `.part`, no ffmpeg, folder removed.
  - Two loose `00000.MTS` → "Name clash" dialog listing the destination and both sources; not running; **empty `out\` was created** (Finding 3).
  - `.txt` plus `.mov` → "No .MTS/.M2TS files found in what you added. Ignored 2 other files."
  - Export `out` → "Choose a full folder path for Export to (use Browse…)."
  - `ICON_PATH` set to a missing file plus `locate_tools` → `(None, None)` with plain `tk.Tk()` → starts without error; banner mapped; Convert disabled.
  - `root.tk.splitlist("{C:/a b/c.MTS} D:/x.MTS")` → `('C:/a b/c.MTS', 'D:/x.MTS')`.
- Not performed: a real Explorer drag-and-drop, taskbar, Alt-Tab, pin, 150% DPI, exe-dir FFmpeg on the built exe, and an exe console-flash observation (Finding 5).
