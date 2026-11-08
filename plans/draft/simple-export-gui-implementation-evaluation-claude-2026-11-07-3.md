# Simple Export GUI — Implementation Evaluation

*Claude Code turns used: 19 / max 100*

*Evaluator: claude · 2026-11-07 · Reviews the implemented `simple-export-gui-claude-2026-11-07.md` against the working tree (round 3, confirm mode).*

## Verdict: The three agent-closable Lows from round 2 are fixed and verified. Only the human acceptance checklist is left.

Since round 2, the only files that changed are:

- `mts_to_dnxhr_gui.py` (22:24:39)
- `tests/test_mts_to_dnxhr_gui.py` (22:24:32)
- `dist\MTS-to-DNxHR.exe` (22:26:14)

The CLI, its tests, the README, the requirements, the scripts, and the assets have the same mtimes as in rounds 1 and 2. All three round-2 fixes hold:

- **Fallback test.** The suite now passes with `tkinterdnd2` blocked for the whole run, and the new `_discard_failed_root` test fails when that function is turned into a no-op.
- **Finish dialogs.** A real-Tk harness shows they now wait behind **Stop converting?** and **Quit?** in all six orderings. Quit → Yes drops the summary.
- **Exe.** The rebuilt exe is newer than the source and contains the new code.

There are no Critical or High findings. The only open Low is the manual Explorer, icon, and DPI checklist, which only a human can run.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 1–9 are present. Round-2 Lows 1–3 and Trivial 6 are closed. Out-of-scope items stayed out |
| Contract fidelity | 5 | The CLI dry-run is byte-identical to `HEAD`. `tests/test_mts_to_dnxhr.py` is additive only (`238 0`). Defaults and argv parity tests pass. Stop and Quit semantics are correct under every modal ordering tested |
| Verification honesty | 4 | All gates pass with the default env, with FFmpeg off PATH, and with `tkinterdnd2` blocked. The new tests survive mutation. The exe is confirmed to contain the fixes. Not covered: the modal deferral has no automated guard (it is in the manual-only `App` scope), and the manual checklist is unrecorded |
| Finding severity | 4 | One Low, deferred to a human. The rest are Trivial or Noted |
| Merge readiness | 5 | Safe to merge as is. Nothing left for an agent to fix |

**Overall completeness:** 23/25 · **percent:** 92%
**Band:** ship
**Open findings:** Critical 0 · High 0 · Low 1 · Trivial/Noted 6

## Loop signal

**Loop signal:** ship-now
**Signal rationale:** Critical and High are both 0, and every agent-closable Low is closed and verified. The one remaining Low is a hands-on Explorer, taskbar, and DPI check that only a human can do, and another fix→eval round cannot close it.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. Hooks in `mts_to_dnxhr.py`** | Complete (unchanged) | mtime 21:48. `--dry-run` output from `git show HEAD:mts_to_dnxhr.py` and from the working tree → `diff` reports **identical** |
| **2. `HookTests`** | Complete (unchanged) | `git diff --numstat tests/test_mts_to_dnxhr.py` → `238 0` |
| **3. GUI core** | Complete (unchanged since round 2) | `run_batch`, `collect_items`, `plan_outputs`, `free_bytes`, `resource_path`, and `locate_tools` match round 2's verification |
| **4. GUI core tests** | Complete | `test_tkdnd_load_failure_falls_back_to_plain_tk` now patches `gui.tkinterdnd2` with a `types.SimpleNamespace` stand-in (`tests/test_mts_to_dnxhr_gui.py:372-388`). New `test_discard_failed_root_clears_default_root` (`:390-419`) uses a fake `Tk` that sets `tk._default_root` before raising. The suite has 48 tests (round 2 had 47) |
| **5. Tk `App` + `main()`** | Complete | `_ask_yes_no` sets `_modal_open` around both prompts (`mts_to_dnxhr_gui.py:775-781`). `_handle_event` defers `batch_finished` into `_pending_finish` while a prompt is open (`:823-826`). `_confirm_stop` replays the deferred summary after the prompt (`:795-797`). `_on_close` returns early while quitting (`:939-940`), clears the pending summary on Yes (`:947-953`), and replays it on No (`:954`) |
| **6. Dependencies** | Complete (unchanged) | — |
| **7. Icon** | Complete (unchanged) | Assets mtime 21:57. All 9 `.ico` images are embedded verbatim in the exe (see Verification) |
| **8. Packaging** | Complete. The manual parts are deferred to a human | The exe is from 22:26:14, newer than the GUI source (22:24:39). PE subsystem is 2 (GUI). The CArchive holds `assets/app.ico` and 66 tkdnd entries, and the bundled `mts_to_dnxhr_gui` code object contains `_modal_open`, `_pending_finish`, `_show_pending_finish`, and `_discard_failed_root`. A launch smoke test opened the window titled `MTS to DNxHR` in about 3 s, with no new `conhost` process, and `CloseMainWindow` exited it cleanly |
| **9. README** | Complete (unchanged) | mtime 21:55 |

## Findings (ranked)

### 1. The manual exe and icon checklist is still unrecorded. *(Low, deferred to a human)*

This carries over round-2 Finding 4 and round-1 Finding 5. There is still no file under `plans/draft/` that records pass or fail for these checks:

- item 1: a real Explorer drag onto the drop zone (this also proves the tkdnd binaries load inside the exe, which matches the plan's "tkdnd not bundled" risk)
- item 10: exe-dir FFmpeg with FFmpeg off PATH
- item 11: no console flash during probe or encode
- item 13: title bar, taskbar, Alt-Tab, pin and shortcut icons, a messagebox icon, and 150% DPI
- item 14: icon fallback from source
- step 8's "drag onto the built exe adds a row"

My automated evidence narrows the gap but does not close it:

- The exe is a GUI-subsystem binary.
- It embeds all 9 icon images, and `ExtractIconExW` reports one icon group.
- It bundles the tkdnd files.
- It starts with no console host.

None of that proves that a drag works, that the taskbar and pin icons look right, or that no console flashes when ffmpeg runs.

**Remediation:** A human should run checklist items 1, 10, 11, 13, and 14 against the current `dist\MTS-to-DNxHR.exe` and record the results in a short file under `plans/draft/`. This does not need another eval round.

### 2. The modal deferral has no automated test. *(Noted)*

On a scratch copy, I replaced `if event[0] == "batch_finished" and self._modal_open:` with `if False:`. `tests.test_mts_to_dnxhr_gui` still reports **OK**, so a regression here would go unnoticed. The plan scopes `App` to manual verification, so this is within the plan. I checked the behavior only with my harness (see Verification).

**Remediation:** No action required. If `App` gets tests later, a small test could drive `_handle_event` directly with `_modal_open = True` and patched `messagebox` functions.

### 3. A Failed-row error dialog can still sit under the finish summary. *(Trivial)*

`_on_double_click` (`mts_to_dnxhr_gui.py:609-625`) calls `messagebox.showerror` directly, not through `_ask_yes_no`, so `_modal_open` stays False. During a batch, a row that already failed can be double-clicked. If the batch finishes while that error box is open, the summary and **Open the export folder?** stack on top of it. This is the same class of issue as round-2 Finding 2, but it needs a deliberate action mid-run, and the error box is informational only.

**Remediation:** Optional. Set the same flag around that `showerror`, for example with a small `_modal` context helper.

### 4. While running, the drop zone says "drops are paused" even without drag-and-drop. *(Trivial)*

This carries over round-2 Trivial 5 unchanged. `_apply_drop_chrome` (`:473-478`) shows `_DROP_PAUSED` without checking `self.dnd`.

**Remediation:** Optional. Show "Converting…" when `not self.dnd`.

### 5. A leftover `samples\dnxhr\01 American Landscape.mov` (83 MB, dated 10:46) is still on disk. *(Noted)*

The plan says to delete `samples\dnxhr\` after verification. The file predates this GUI work and is gitignored (`.gitignore:11: dnxhr/`), so it does not affect the merge. It does make the CLI dry-run print `skip (exists)`, and it would make checklist item 3 report Skipped instead of encoding.

**Remediation:** Delete it before running the manual checklist.

### 6. Round-1 and round-2 carry-overs stand as written. *(Noted)*

These items are unchanged and need no action:

- sprocket-hole art
- `proc.wait()` not hoisted
- `file_started` shows "0%"
- the stale "not a git repo" constraint
- cancel removes a pre-existing empty export folder
- `mkdir` moved after the preflight checks (endorsed)
- the quit guard and drop-zone greying are verified by harness only

**Remediation:** No action.

## Net assessment

This is ready to merge. The wrap-don't-fork contract holds:

- no new FFmpeg flags
- defaults derived from the CLI parser
- a byte-identical CLI dry-run
- no edits to existing tests

The round-2 fixes are real and do not over-reach. The fallback test now runs in a `tkinterdnd2`-free environment, and it covers the half-built-root discard that previously had no coverage. The deferral logic is small and correct under every ordering I tried: Stop Yes or No after the batch finished, Quit No after it finished, Quit Yes before or after it finished, and Stop Yes mid-run. The shipped exe contains it.

Nothing is left for an agent to remediate. Before calling the plan's icon and drag-and-drop goals met, a human should run checklist items 1, 10, 11, 13, and 14 on the current exe (Finding 1). The two Trivials can wait.

## Verification performed

- `.\.venv\Scripts\python.exe -m unittest` → **Ran 48 tests, OK (skipped=2)**.
- Same with every FFmpeg entry removed from PATH (`shutil.which('ffmpeg')` → `None`) → **OK (skipped=2)**.
- Whole suite discovered with `sys.modules['tkinterdnd2'] = None` → **OK (skipped=2)**. Round 2 had **FAILED (errors=2)** here, so round-2 Finding 1 is closed.
- CLI regression: `--dry-run` on `"samples/01 American Landscape.MTS"`, once with `HEAD`'s `mts_to_dnxhr.py` and once with the working tree → `diff` **identical**.
- `git diff --numstat` → `tests/test_mts_to_dnxhr.py 238 0`, `mts_to_dnxhr.py 80 25`, unchanged from round 2.
- Mutation checks on a scratch copy (`D:\tmp\pwtest\r3\mut`), running `tests.test_mts_to_dnxhr_gui`:

  | Mutation | Result |
  |---|---|
  | `_discard_failed_root` turned into a no-op | **FAILED (failures=1)** |
  | `_create_root` except narrowed to `ZeroDivisionError` | **FAILED (errors=3)** |
  | Modal deferral disabled (`if False:`) | OK (Finding 2) |

- **Modal harness** (`D:\tmp\pwtest\r3\modal.py`): real `App`, a real `askyesno` for the prompt under test, answered by a `PostMessageW(WM_COMMAND, IDYES|IDNO)` thread after 2 s, and a fake `run_batch`. Results:

  | Scenario | Result |
  |---|---|
  | Stop → Yes, after the batch finished | The summary and **Open the export folder?** appear only *after* the prompt is answered. Final button text is `Convert`, `running=False`, `_pending_finish=None` |
  | Stop → No, after the batch finished | Same as Stop → Yes |
  | Quit → No, after the batch finished | The summary is shown only after the prompt is answered |
  | Quit → Yes, after the batch finished | No summary. The window is destroyed |
  | Quit → Yes, before the batch finished | No summary. The window is destroyed |
  | Stop → Yes, mid-run | "Stopped: 0 converted, 0 skipped, 0 failed, 1 not converted." |

  The `invalid command name …snapshot/destroy` stderr lines in the Quit scenarios are my harness's own `after` callbacks firing after the app destroyed the root. That is expected.
- **Exe inspection** (`dist\MTS-to-DNxHR.exe`, 22:26:14):
  - PE subsystem 2 (GUI).
  - The `CArchiveReader` TOC has `assets/app.ico` and 66 tkdnd entries.
  - The bundled `mts_to_dnxhr_gui` code contains the round-2 fix symbols.
  - All 9 images from `assets\app.ico` (16–256) appear verbatim in the exe.
  - `ExtractIconExW(..., -1)` → 1.
- **Exe launch smoke test** (PowerShell `Start-Process`): the window titled `MTS to DNxHR` appeared in about 3 s, with 0 new `conhost` processes. After `CloseMainWindow()`, 0 processes remained.
- Not performed (Finding 1): Explorer drag-and-drop, taskbar, Alt-Tab, pin and shortcut icons, 150% DPI, exe-dir FFmpeg, a console-flash check during a real encode, and icon fallback.
