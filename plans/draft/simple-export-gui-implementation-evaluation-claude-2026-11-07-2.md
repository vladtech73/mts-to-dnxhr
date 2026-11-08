# Simple Export GUI — Implementation Evaluation

*Claude Code turns used: 20 / max 100*

*Evaluator: claude · 2026-11-07 · Reviews the implemented `simple-export-gui-claude-2026-11-07.md` against the working tree (round 2, confirm mode).*

## Verdict: The round-1 fixes landed and hold up under test. Four cheap Lows remain, and one of them is a test-gate regression the fix pass introduced.

Since round 1, only `mts_to_dnxhr_gui.py` (22:14) and `tests/test_mts_to_dnxhr_gui.py` (22:15) changed. The CLI, its tests, the README, the requirements files, the scripts, and the assets have the same mtimes as before, so round 1's "Complete" verdicts for steps 1, 2, 6, 7, 8 (script), and 9 still apply. I re-checked all five agent-closable fixes, each against the live code with real Tk:

- tkdnd fallback
- quit guard
- `mkdir` order
- progress and pre-cancel tests
- greyed drop zone

All five work. Mutation checks show the new tests catch regressions. Four gaps are still open:

- The new fallback test breaks the plan's "suite passes without `tkinterdnd2` installed" gate.
- The finish dialogs still stack on top of an open **Stop converting?** or **Quit?** prompt.
- `dist\MTS-to-DNxHR.exe` predates every round-1 fix.
- The manual exe and icon checklist is still unrecorded (deferred to a human).

There are no Critical or High findings, and the change is safe to merge.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 1–9 present. Round-1 Lows 1–4 and Trivial 7 are closed. Out-of-scope items stayed out |
| Contract fidelity | 5 | Argv and defaults parity holds, and the CLI dry-run is identical to `HEAD`. The tkdnd → Browse-only promise is now real. A blocked run creates no folder. Quit shows no summary |
| Verification honesty | 3 | The default gates pass both ways, and the new tests survive mutation. But the suite now **fails** when `tkinterdnd2` is unavailable (2 errors), the built exe is stale relative to source, and the manual checklist is still unrecorded |
| Finding severity | 4 | Low only |
| Merge readiness | 4 | Safe to merge. A rebuild and a one-line test guard are worth doing first |

**Overall completeness:** 21/25 · **percent:** 84%
**Band:** nearly-done
**Open findings:** Critical 0 · High 0 · Low 4 · Trivial/Noted 7

## Loop signal

**Loop signal:** one-more-fix
**Signal rationale:** Critical and High are both 0. One small pass closes the three agent-closable Lows: guard the fallback test, add a "modal open" flag so the finish dialogs wait, and rebuild the exe. Finding 4 needs a human at the machine and does not need another eval round.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. Hooks in `mts_to_dnxhr.py`** | Complete (unchanged since round 1) | mtime 21:48, earlier than the round-1 report (22:11). Dry-run output from `git show HEAD:mts_to_dnxhr.py` and from the working tree is **identical** |
| **2. `HookTests`** | Complete (unchanged) | `git diff --numstat tests/test_mts_to_dnxhr.py` → `238 0` |
| **3. GUI core** | Complete | `run_batch` clamps to 0–1, throttles per 1% bucket, and posts `None` for an unknown total (`mts_to_dnxhr_gui.py:235-258`). A pre-set cancel posts `cancelled` with no `file_started` (`:229-233`) |
| **4. GUI core tests** | Complete, with one portability regression | New tests: `test_progress_is_throttled_clamped_and_can_be_unknown` (`tests/test_mts_to_dnxhr_gui.py:293`), `test_cancel_already_set_skips_every_file` (`:322`), and `test_tkdnd_load_failure_falls_back_to_plain_tk` (`:371`). The last one errors without `tkinterdnd2` (Finding 1) |
| **5. Tk `App` + `main()`** | Complete | `_create_root` falls back on `RuntimeError`/`TclError` and discards the half-built root (`:939-959`). `App(root, dnd=…)` drives the drop-zone text and drop registration (`:310`, `:345`, `:454`). `_quitting` is set after the Quit confirm, and `_handle_event` skips UI work while it is set (`:800-803`, `:924`). `mkdir` now runs after the Name clash and Low-disk checks (`:719-753`). The drop zone is greyed with "Converting… drops are paused" while running (`:468-481`) |
| **6. Dependencies** | Complete (unchanged) | — |
| **7. Icon** | Complete (unchanged) | Assets mtime 21:57 |
| **8. Packaging** | Partial: the artifact is stale | The script is unchanged and correct. `dist\MTS-to-DNxHR.exe` is from 22:01:21, older than the GUI source (22:14:44), so the exe has none of the round-1 fixes (Finding 3) |
| **9. README** | Complete (unchanged) | mtime 21:55 |

## Findings (ranked)

### 1. The new tkdnd fallback test breaks the "passes without `tkinterdnd2`" gate. *(Low)*

Step 4's done-when requires the suite to pass "without `tkinterdnd2` installed". `test_tkdnd_load_failure_falls_back_to_plain_tk` (`tests/test_mts_to_dnxhr_gui.py:371-388`) patches `gui.tkinterdnd2.TkinterDnD` directly. When the package is absent, `gui.tkinterdnd2` is `None`, so the test fails before it reaches `_create_root`. To check this, I ran the whole suite with `sys.modules['tkinterdnd2'] = None` → **`FAILED (errors=2, skipped=2)`**, with `AttributeError: 'NoneType' object has no attribute 'TkinterDnD'` in both subtests. The round-1 suite passed in that environment, so the fix pass introduced this. The plan's simulated check (the reimport test) still passes, so the literal gate holds. A CI job or a fresh venv that installs only `tqdm` would go red.

The test also replaces `TkinterDnD.Tk` with a pure `side_effect`, so it never builds the half-initialized root that the real failure leaves behind. `_discard_failed_root` therefore has no coverage. I exercised it by hand (see Verification), and it works.

**Remediation:** Add `@unittest.skipIf(gui.tkinterdnd2 is None, …)`. Better, patch `gui.tkinterdnd2` with a `types.SimpleNamespace(TkinterDnD=SimpleNamespace(Tk=Mock(side_effect=failure)))` so the test runs without the package. Optionally, add a case whose fake `Tk` sets `tk._default_root` before raising, and assert that it is cleared.

### 2. The finish dialogs still fire on top of an open "Stop converting?" or "Quit?" prompt. *(Low)*

Round-1 Finding 2 had two halves. The fix covered only the post-confirm Quit path: `_quitting` is set at `:924`, *after* `askyesno("Quit?")` returns. `_confirm_stop` (`:773-784`) sets no flag at all. Tk keeps servicing `after()` timers while a native messagebox is open, so `_poll` drains `batch_finished`, and `_show_finished` opens its summary and **Open the export folder?** on top of the pending prompt.

I reproduced this with a real `askyesno("Stop converting?")` that a helper thread answers 2 s later. The batch finished at 0.5 s. The recorded call order was `askyesno(Stop…)` → `showinfo("Finished: 1 converted…")` → `askyesno("Open the export folder?")` → the Stop prompt answered. The trailing "Yes" is then correctly ignored by `if not self.running: return` (`:780`), so no state is corrupted. The user still gets a nested modal stack and a Stop prompt that no longer means anything. The same path applies to the **Quit?** prompt before it is confirmed.

**Remediation:** Set a `self._modal_open` flag (or reuse a counter) around the two `askyesno` calls. In `_handle_event`, defer `batch_finished` while it is set, for example by re-queuing it or setting a "pending finish" flag that runs after the prompt returns. When **Quit?** is answered Yes, skip the deferred summary.

### 3. The built exe predates every round-1 fix. *(Low)*

`dist\MTS-to-DNxHR.exe` was written at 22:01:21. `mts_to_dnxhr_gui.py` was last modified at 22:14:44. The binary the user would double-click therefore still has:

- the uncaught tkdnd `RuntimeError` at startup
- the dialogs during Quit
- the empty folder left after a Name clash
- the un-greyed drop zone

Step 8's done-when and checklist items 10, 11, and 13 are defined against this exe. `dist/` is gitignored, so this does not affect the merge diff, only the deliverable.

**Remediation:** Re-run `powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1`, then confirm the exe's mtime is later than the GUI source.

### 4. The manual exe and icon checklist is still unrecorded. *(Low, deferred to a human)*

This carries over round-1 Finding 5, which the remediation notes defer as human input. Nothing records results for these items:

- item 1: a real Explorer drop
- item 10: exe-dir FFmpeg on the built exe
- item 11: no console flash from the exe
- item 13: title bar, taskbar, Alt-Tab, pin and shortcut icons, and 150% DPI
- step 8's "drag onto the built exe adds a row"

These are the acceptance criteria for the plan's icon and drag-and-drop goals. They should run against the rebuilt exe from Finding 3, not the stale one.

**Remediation:** After rebuilding, run those items and record pass/fail in a short file under `plans/draft/`.

### 5. While running, the drop-zone text says "drops are paused" even when drag-and-drop is unavailable. *(Trivial)*

`_apply_drop_chrome` (`:471-476`) shows `_DROP_PAUSED` regardless of `self.dnd`. In a Browse-only session, the user is told drops are paused when drops were never possible.

**Remediation:** Optional. Use "Converting…" when `not self.dnd`.

### 6. A second close-click during the quit wait asks "Quit?" again. *(Trivial)*

During `_wait_to_quit`, `self.running` stays `True` until `batch_finished` drains, and the worker is alive, so a second `WM_DELETE_WINDOW` re-enters `_on_close` and prompts again (`:916-923`).

**Remediation:** Optional. Return early from `_on_close` when `self._quitting` is set.

### 7. The `mkdir` step now comes after the preflight checks, which reorders the plan's literal Convert flow. *(Noted)*

The plan's Convert step 1 puts `mkdir` before collisions and the disk check. The implementation moves it to after both. Round-1 Finding 3 and Grok's plan feedback both endorsed this order, and it satisfies checklist item 8 ("nothing is written"). I confirmed that both a Name clash and a "No" on Low disk space leave no folder.

**Remediation:** No action. Update the plan text if it is reused.

### 8. The quit guard, `mkdir` order, and greyed drop zone have no automated tests. *(Noted)*

The plan scopes the `App` class to manual verification, so this is within the plan. The behaviors were verified only by my harness runs, not by the suite.

**Remediation:** No action required.

### 9. Round-1 carry-overs stand as written. *(Noted)*

These round-1 items are unchanged and need no action:

- sprocket-hole art (round-1 Trivial 6)
- `proc.wait()` not hoisted (Noted 8)
- `file_started` shows "0%" (Noted 9)
- stale "not a git repo" constraint (Noted 10)
- cancel removes a pre-existing empty export folder (Noted 11)

**Remediation:** No action.

## Net assessment

The change is safe to merge. The wrap-don't-fork contract still holds: no new FFmpeg flags, parser-derived defaults, a byte-identical CLI dry-run, and no edits to existing tests. Round 1's three behavior fixes all work against real Tk:

- the runtime tkdnd fallback
- the post-confirm quit guard
- no folder created on a blocked run

Three small things are worth doing before calling it done:

- Guard or decouple the fallback test so a `tkinterdnd2`-less environment stays green (Finding 1).
- Defer the finish dialogs while a confirm prompt is open (Finding 2).
- Rebuild the exe (Finding 3).

After that, the human checklist on the fresh exe (Finding 4) is the only real acceptance gap left, and none of the Trivial items needs attention before merge.

## Verification performed

- `.\.venv\Scripts\python.exe -m unittest` → **Ran 47 tests, OK (skipped=2)** (round 1 had 44, plus 3 new tests).
- Same with FFmpeg stripped from PATH (`shutil.which('ffmpeg')` → `None`) → **47 OK (skipped=2)**.
- Suite with `sys.modules['tkinterdnd2'] = None` for the whole run → **FAILED (errors=2)**, both in `test_tkdnd_load_failure_falls_back_to_plain_tk` (Finding 1).
- CLI regression: the `--dry-run` output of `"samples/01 American Landscape.MTS"` from `git show HEAD:mts_to_dnxhr.py` and from the working tree → **identical**.
- `git diff --numstat tests/test_mts_to_dnxhr.py` → `238 0`.
- File mtimes: only the GUI module and the GUI tests changed after the round-1 report (22:11). `dist\MTS-to-DNxHR.exe` is 22:01:21 and the GUI source is 22:14:44 (Finding 3).
- Mutation checks on a scratch copy (`D:\tmp\pwtest\r2\mut`), against the GUI test module:

  | Mutation | Result |
  |---|---|
  | Throttle check removed | FAILED |
  | `>1.0` clamp removed | FAILED |
  | Pre-cancel branch disabled | FAILED |
  | `_create_root` except narrowed to `ZeroDivisionError` | FAILED (errors=2) |

- **Real tkdnd failure** (`D:\tmp\pwtest\r2\dndfail.py`): patched `tkinterdnd2.TkinterDnD._require` to raise `RuntimeError`, then called `gui._create_root()` → plain `Tk`, `dnd=False`, `tk._default_root` is the new root, one child frame. `App` showed "Drag-and-drop unavailable. Use Add files… or Add folder…", and mainloop exited cleanly.
- **Guards harness** (`D:\tmp\pwtest\r2\guards.py`, real `App`, dialogs mocked, fake `run_batch` that stays alive 1 s *after* posting `batch_finished`):
  - Close mid-run → the only dialog was `askyesno("Quit?")`. No summary and no Open-folder prompt.
  - Drop zone while running → "Converting… drops are paused", `#d0d0d0`.
  - Two loose `00000.MTS` → `showerror("Name clash")`, `out_clash` **not created**, not running.
  - `free_bytes` patched to 1 with "No" on Low disk space → `out_disk\deep` **not created**, not running.
- **Stop-modal race** (`D:\tmp\pwtest\r2\stopmodal.py`, real `askyesno` answered by a `PostMessageW(WM_COMMAND, IDYES)` thread) → `showinfo` summary and "Open the export folder?" fired while **Stop converting?** was still open (Finding 2).
- Not performed: an Explorer drag-and-drop, taskbar, Alt-Tab, pin, 150% DPI, exe-dir FFmpeg, or an exe console-flash check (Finding 4). I did not rebuild the exe, because this eval does not change the deliverable.
