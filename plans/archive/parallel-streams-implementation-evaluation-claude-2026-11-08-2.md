# Parallel Encodes (Streams) — Implementation Evaluation

*Claude Code turns used: 21 / max 100*

*Evaluator: claude · 2026-11-08 · Reviews the implemented `parallel-streams-claude-2026-11-08.md` against the working tree (round 2, confirm mode, after round-1 remediation).*

## Verdict: Not ready to ship. The round-1 layout fix clips the drop zone's Add files…/Add folder… buttons at this PC's 144 DPI.

The round-1 remediation closed the cheap findings: the RAM note, the header test, the docstring and the blank lines. All automated gates are still green (68 tests). The fix for the High finding (the tree collapsing at minsize) shrank the fixed-pixel drop zone from 110 to 75 px. That restored the tree height to exactly HEAD's, but it introduced a new visible regression. At 144 DPI the drop zone's content needs about 98 px, so both buttons are cut off at the bottom border. Because the drop zone has a fixed height, this happens at every window size, including the default 720×540, not only at the minimum. The tree at 560×440 is back to HEAD parity (heading only), but the "heading + 2 rows" re-measure target from round 1 is still not met. No Critical findings remain. One High needs one more small, deliberate geometry pass.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 0–9 all landed. The suggestion was adjusted to cap at 2, as step 9 allows. Round-1 Lows 3 and 4 and Trivial 8 are closed. |
| Contract fidelity | 4 | The `jobs=1` paths, argv, `convert_one` signature and transcript are preserved. The plan's "tree still shows at least a few rows" at minsize is still unmet, though it is now at HEAD parity. |
| Verification honesty | 3 | Automated gates are green and honest. The layout fix was not checked visually: one screenshot at the real DPI shows clipped buttons, and the round-1 re-measure target (heading + 2 rows) was not met. |
| Finding severity | 3 | One High (the clipped drop-zone buttons, a regression the remediation introduced). The rest are Low, Trivial or Noted. |
| Merge readiness | 3 | Functionally safe. The primary input buttons render clipped on every launch on the target PC. |

**Overall completeness:** 18/25 · **percent:** 72%
**Band:** needs-work
**Open findings:** Critical 0 · High 1 · Low 2 · Trivial/Noted 3

## Loop signal

**Loop signal:** one-more-fix
**Signal rationale:** The only High is a single geometry decision for the drop-zone height and minsize, and it can be verified with one screenshot. Everything else is optional or advisory.

## Round-1 finding disposition

| # | Round-1 finding | Status now | Evidence |
|---|---|---|---|
| 1 | Tree collapses to 1 px at 560×440 (High) | **Partially fixed, regression introduced** | The tree at 560×440 is 31 px, versus 30 px at HEAD, so it is back to parity. The drop zone shrank from 110 to 75 px and now clips its buttons (Finding 1 below). |
| 2 | Four-clip benchmark is biased against jobs=3 (Low) | Open (advisory) | The README table is unchanged and still shows four clips with a single run per cell. |
| 3 | RAM is 3–6× the estimate with no guidance (Low) | **Fixed** | "Each parallel encode uses about 2 GB of RAM" is now in the README's Usage and Desktop app sections. |
| 4 | No test for the `jobs:` header line or the note (Low) | **Fixed** | `test_header_prints_jobs_and_above_suggestion_note` (`tests/test_mts_to_dnxhr.py:577`) covers (1,1,no note), (2,1,note) and (2,2,no note) through `main(... --dry-run)`. |
| 5 | Failure reprint is in completion order (Trivial) | Open (optional) | `mts_to_dnxhr.py:949` still appends at completion. |
| 6 | `Stopping…` uses `include_file=False` (Noted) | No action | — |
| 7 | A bug in `work` leaves queued rows at Waiting (Noted) | No action | — |
| 8 | Docstring and blank-line nits (Trivial) | **Fixed** | The `suggested_jobs` docstring mentions CPU headroom and ~28 MB/s HQX streams (`mts_to_dnxhr.py:53`). There are two blank lines before `_FFMPEG_MISSING`. |
| 9 | PR split not reflected (Noted) | Open (Noted) | Still one uncommitted change set. |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **0. Land timer work** | Complete | `da63a1a` is HEAD. |
| **1. Core cap / suggestion / scheduler / dir refcount** | Complete | Unchanged since round 1. `git diff` hunks touch only constants, `_claim_dir`/`_release_dir`, `run_indexed` (pure addition after `run_ffmpeg`), `convert_one`, the parser, `_print_header`, `_encode_all` and `main`. There are no hunks in `build_command` or `run_ffmpeg`. |
| **2. Core tests** | Complete | `JobsTests` plus `test_shared_parent_survives_sibling_failure`. `test_probe_error_strips_duplicate_path_and_empty_dir` is unmodified. |
| **3. GUI `run_batch`** | Complete | Unchanged since round 1. The five original `RunBatchTests` pass. |
| **4. GUI worker tests** | Complete | Unchanged since round 1. |
| **5. GUI state / status / control** | Partial | All the logic is complete. The jobs row is on row 5. The drop zone is now `height=75` (`mts_to_dnxhr_gui.py:384`), and its buttons are clipped (Finding 1). The tree shows only its heading at minsize, the same as HEAD (Finding 2). |
| **6. CLI `--jobs`** | Complete | `--help` → `Suggested for this PC: 2 (default: 1)`. `--jobs 0/5/x` → exit 2/2/2. |
| **7. CLI tests** | Complete | It now also includes the header/note test. |
| **8. README** | Complete | Usage, Desktop app and Limitations are updated, and the RAM note was added. |
| **9. Benchmark** | Complete (method flawed) | Unchanged. See Finding 3. |

## Findings (ranked)

### 1. At this PC's 144 DPI, the 75 px drop zone clips the Add files… and Add folder… buttons at every window size. *(High)*

The round-1 remediation changed `tk.Frame(..., height=110)` to `height=75` (`mts_to_dnxhr_gui.py:384`). The frame keeps `pack_propagate(False)`, and `height` is in raw pixels, so it does not scale with DPI. I measured this with a live `App` under `SetProcessDpiAwareness(1)`, which matches `main()`. Tk scaling was 2.0, which is 144 DPI.

| Build | Drop-zone height | Label height | Button height (natural 35) | Button bottom inside the drop zone |
|---|---|---|---|---|
| HEAD | 110 | 31 | **35** | 98 of 110 |
| Working tree | 75 | 31 | **26** (squashed by 9 px) | 73 of 75 (flush with the inner edge of the 2 px border) |

Screenshots at 560×440 (`D:\tmp\pwtest\r2eval_head.png` and `r2eval_wt.png`) show the bottom edges of both buttons cut off by the groove border in the working tree, and fully drawn at HEAD. The drop zone does not grow with the window, so the clipping also appears at 720×540, which is the size every launch uses. When I simulated larger system fonts (×1.17 and ×1.33, roughly 175% and 200% display scaling), the buttons squashed further to 21 px and 19 px. At HEAD they kept 38–40 px inside a 110 px zone that still fit.

The remediation moved the cost of the new row from the tree to the drop zone's primary controls. These are the first two buttons a user clicks when drag-and-drop is unavailable.

**Remediation:** Choose one of these, then re-screenshot at 144 DPI:
- **(Preferred)** Size the drop zone from its content instead of a pixel constant. After packing the children, call `self.drop.configure(height=label.winfo_reqheight() + button_row.winfo_reqheight() + pady + 2*bd + small margin)`, and optionally tighten the label `pady` from `(8, 6)` to `(6, 4)`. This is DPI-safe and recovers about 10–15 px compared with 110 at 144 DPI.
- Revert to `height=110` and raise `minsize` and the default `geometry` instead, for example `minsize(560, 480)` and `geometry("720x580")`. Update the plan's "Keep `minsize(560, 440)`" note.

Either way, confirm that the buttons are fully drawn and the tree shows the heading plus at least one data row at the chosen minsize.

### 2. At 560×440 the tree still shows only its heading, so manual check 6 ("a few rows") is still unmet. *(Low)*

At 144 DPI the tree is 31 px tall at 560×440 (HEAD: 30 px), 71 px at 560×480 (HEAD: 70 px) and 131 px at 720×540 (HEAD: 130 px). The requested height is 636 px (HEAD: 637 px). The new row is now cost-neutral, so this is no longer a regression. However, the plan's step 5 "Done when" and manual check 6 text, and the round-1 re-measure target of the heading plus 2 rows, are still not met at the minimum size. The constraint is older than this plan: HEAD also showed zero data rows at minsize.

**Remediation:** Fold this into the Finding 1 fix. If `minsize` stays at 440, update the plan's check 6 wording to "at parity with HEAD" so the gate reflects what was actually decided.

### 3. The four-clip benchmark is still structurally biased against `--jobs 3`. *(Low, carried over)*

This is unchanged from round 1. With four clips, jobs=2 and jobs=3 both need two rounds. Each cell is a single run, and the jobs=1 deinterlace row (20.9 s) beat the non-deinterlace row (24.0 s), which suggests noise or a cold cache. The conservative cap of 2 is still safe.

**Remediation:** Optional. Re-run with 12 copies, two runs per cell after a warm-up, before raising the suggestion above 2.

### 4. With `jobs > 1`, the CLI failure reprint is in completion order. *(Trivial, carried over)*

**Remediation:** Optional sort by input index before the reprint.

### 5. The plan's PR split is not reflected yet. *(Noted, carried over)*

**Remediation:** Split when committing, or update the PR split note in the plan.

### 6. The layout fix was not checked visually. *(Noted, process)*

Round 1 asked for a re-measure after the geometry change. The remediation apparently checked only the tree height, which did return to parity, and not the region it borrowed the pixels from. A single screenshot at the real DPI would have caught Finding 1.

**Remediation:** For future GUI geometry changes, include a before/after screenshot at the native DPI in the remediation evidence.

## Net assessment

The parallel-encode functionality, the CLI flag, the docs and the tests are complete and correct. Nothing in core, the scheduler or the event flow regressed in this round. The only blocker is cosmetic but visible on every launch on the target PC: the drop-zone buttons are clipped. It is a one-line or few-line fix with a screenshot to confirm it. After that, the change set is in ship territory. The benchmark re-run, the failure-order sort and the PR split can be done later or accepted.

## Verification performed

- `.venv\Scripts\python.exe -m unittest` → `Ran 68 tests … OK (skipped=2)`. That is one more than round 1: the new header/note test.
- `MTS_SMOKE=1 … -m unittest` → `OK (skipped=1)`. The real encode wrote `01 American Landscape.mxf`.
- `python -c "import mts_to_dnxhr as m; print(m.suggested_jobs(), m.MAX_JOBS)"` → `2 4`. This is the expected value after the step 9 adjustment.
- `python mts_to_dnxhr.py --help` → `-j N, --jobs N  Encode up to N clips at once (1-4). Suggested for this PC: 2 (default: 1)`.
- `--jobs 0` / `5` / `x` → exit 2, 2, 2.
- `git diff HEAD -- mts_to_dnxhr.py` hunk headers: there are no hunks inside `build_command` or `run_ffmpeg`. The hunk anchored at `def run_ffmpeg(` is the pure addition of `run_indexed` after it.
- Grep for `_active_index|_file_t0|_status_pct|_elapsed_file|_current_fraction|_known_total` in the GUI and tests → no matches.
- README diff: the RAM note is in Usage and Desktop app, the Limitations line is rewritten, the disk-full note is added and the benchmark table is present.
- **Live Tk layout measurement** (scratch script, `SetProcessDpiAwareness(1)`, Tk scaling 2.0 = 144 DPI, six tree rows inserted). HEAD was loaded from `git show HEAD:mts_to_dnxhr_gui.py`.
  - HEAD: reqheight 637. Tree heights were 30 / 70 / 130 px at 560×440 / 560×480 / 720×540. Drop zone 110 px, button height 35.
  - Working tree: reqheight 636. Tree heights were 31 / 71 / 131 px. Drop zone 75 px, button height 26, button bottom at 73 of 75.
  - Without DPI awareness (96 DPI), the working tree fits: button bottom at 62 of 75. This is why a non-DPI-aware check would miss the problem.
- **Simulated larger fonts** (TkDefaultFont/TkTextFont/TkHeadingFont ×1.17 and ×1.33): working-tree button height 21 and 19 px, still inside 75 px. HEAD button height 40 and 38 px inside 110 px.
- **Screenshots** at 560×440: `D:\tmp\pwtest\r2eval_head.png` (buttons intact) and `D:\tmp\pwtest\r2eval_wt.png` (button bottoms clipped). I kept them as evidence. The scratch scripts `r2eval_*.py` were deleted. `D:\tmp\pwtest\gui_head.py` was rewritten with HEAD's GUI for the comparison.
- Manual GUI checks 1–5 (live parallel rows, Stop, Stop and quit with Task Manager) were not re-run this round. The logic is unchanged since round 1, where it was verified with synthetic events and real-FFmpeg CLI runs.
