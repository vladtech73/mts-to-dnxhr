# Parallel Encodes (Streams) — Implementation Evaluation

*Claude Code turns used: 16 / max 100*

*Evaluator: claude · 2026-11-08 · Reviews the implemented `parallel-streams-claude-2026-11-08.md` against the working tree (round 3, confirm mode, after round-2 remediation).*

## Verdict: Merge-ready. The round-2 High is fixed. The only geometry item left is a Low at the minimum window size, where the tree heading is clipped.

The drop zone now sizes from its content. Both Add buttons render at their full natural height (35 px) at 144 DPI, at every window size. That closes the round-2 High. Every automated gate is still green: 68 tests, the opt-in smoke encode, `suggested_jobs`, `--help`, the `--jobs` exit codes and the argv invariant. The fix has a cost the remediation summary understates. The content-sized drop zone is 84 px, not the 75 px of round 2, so the tree is **8 px shorter than HEAD at every window size**. At the 560×440 minimum, the tree is 22 px against a 26 px heading row, so the "File / Source folder" heading text is cut off (HEAD: 30 px, heading intact). At the default 720×540, four data rows are visible instead of HEAD's five. No Critical or High findings remain.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 4 | Steps 0–9 all landed. Manual check 6 ("tree still shows at least a few rows" at 560×440) is unmet and was deferred, not resolved. |
| Contract fidelity | 4 | The `jobs=1` paths, argv, `convert_one` signature, event shapes and CLI transcript are preserved. The tree is 8 px shorter than HEAD everywhere, and its heading is clipped at minsize. |
| Verification honesty | 4 | Gates are green, and this time the remediation included a screenshot at the native DPI (`r3_fix.png`). Calling the minsize tree "header-only (~22 px)" understates it, because that screenshot shows the heading itself clipped. |
| Finding severity | 4 | No Critical or High. One new Low (the minsize tree), plus the carried-over Low, Trivial and Noted items. |
| Merge readiness | 4 | Safe to merge. What remains is cosmetic at a non-default size, or optional. |

**Overall completeness:** 20/25 · **percent:** 80%
**Band:** nearly-done
**Open findings:** Critical 0 · High 0 · Low 2 · Trivial/Noted 4

## Loop signal

**Loop signal:** ship-now
**Signal rationale:** No Critical or High findings remain. The one geometry Low is a single `minsize`/`geometry` decision at a window size the user has to drag to. It can be made at commit time without another fix-and-eval cycle.

## Round-2 finding disposition

| # | Round-2 finding | Status now | Evidence |
|---|---|---|---|
| 1 | The 75 px drop zone clips the Add buttons at 144 DPI (High) | **Fixed** | `height=` and `pack_propagate(False)` are gone (`mts_to_dnxhr_gui.py:384-395`, with a comment explaining why). The label `pady` went from `(22, 8)` to `(8, 6)`. Measured: drop zone 84 px, both buttons 35 px of a requested 35, at 560×440, 560×480 and 720×540. |
| 2 | The minsize tree shows only its heading (Low) | **Open, slightly worse** | The tree is 22 px versus 30 px at HEAD (31 px in round 2), and the heading text is now clipped. See Finding 1. |
| 3 | The four-clip benchmark is biased against jobs=3 (Low) | Open (advisory) | The README benchmark table (`README.md:62-71`) is unchanged. |
| 4 | With jobs > 1, the failure reprint is in completion order (Trivial) | Open (optional) | The `_encode_all` parallel path still appends in completion order. |
| 5 | The PR split is not reflected (Noted) | Open (Noted) | It is still one uncommitted change set. |
| 6 | The layout fix was not checked visually (Noted, process) | **Fixed** | `D:\tmp\pwtest\r3_fix.png` was taken at 560×440, 144 DPI, by `r3_measure.py`. |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **0. Land timer work** | Complete | HEAD is `da63a1a` ("Show elapsed file and total time…"). |
| **1. Core cap / suggestion / scheduler / dir refcount** | Complete | `git diff HEAD -U0 -- mts_to_dnxhr.py` hunks: the constants (`@@ -36`, `@@ -50`), `_claim_dir`/`_release_dir` (`@@ -383`), `run_indexed` (a pure insertion after `run_ffmpeg`, `@@ -549,0 +588,62`), `convert_one`, `build_parser`, `_print_header`, `_encode_all` and `main`. There are no hunks inside `build_command` or `run_ffmpeg`. |
| **2. Core tests** | Complete | `JobsTests` and `test_shared_parent_survives_sibling_failure` are present. The existing tests are unmodified: the test diffs are additions only (+290 / +127). |
| **3. GUI `run_batch`** | Complete | Unchanged since round 1. The original `RunBatchTests` pass. |
| **4. GUI worker tests** | Complete | Unchanged since round 1. |
| **5. GUI state / status / control** | Complete except manual check 6 | The grep for the scalar fields returns 0 matches. The jobs row sits under the deinterlace checkbox, and `(suggested max 2 for this PC)` is fully visible at 560×440 (screenshot). The drop zone is content-sized. `minsize(560, 440)` and `geometry("720x540")` (`:344-345`) are unchanged, so the tree absorbs the cost (Finding 1). |
| **6. CLI `--jobs`** | Complete | `--help` → `Suggested for this PC: 2 (default: 1)`. `--jobs 0`, `5` and `x` each exit 2. |
| **7. CLI tests** | Complete | This includes the header/note test added in round 1. |
| **8. README** | Complete | Usage (`:110`, `:115`, `:117`), Desktop app (`:123`), Limitations/disk-full, and the 2 GB RAM note in both sections. |
| **9. Benchmark** | Complete (method flawed) | The suggestion cap was adjusted to 2 (`max(1, min(2, n // 6))`), as step 9 allows. See Finding 2. |

## Findings (ranked)

### 1. The content-sized drop zone takes 9 px more than round 2. At 560×440 the tree heading is clipped; at 720×540 one fewer row shows than at HEAD. *(Low)*

I measured a live `App` under `SetProcessDpiAwareness(1)`, with Tk at 144.07 px per inch and six rows inserted (`D:\tmp\pwtest\r3confirm_measure.py`). I confirmed `gui_head.py` is byte-identical to `git show HEAD:mts_to_dnxhr_gui.py`. The heading row is 26 px and each data row is 20 px (the first-row bbox is `(1, 26, 680, 20)`).

| Window | HEAD drop / tree | Working tree drop / tree | Full data rows visible (HEAD → WT) |
|---|---|---|---|
| 560×440 | 110 / **30** | 84 / **22** | 0 → 0. In the working tree, 22 < 26, so the heading text is cut at the bottom. |
| 560×480 | 110 / 70 | 84 / 62 | 2 → 1 |
| 720×540 (default launch) | 110 / 130 | 84 / 122 | 5 → 4 |

Round 2 kept the tree at HEAD parity (31 px) by squeezing the drop zone to 75 px. Round 3 correctly stopped squeezing the buttons, but it left `minsize` and `geometry` unchanged, so the extra 9 px came out of the tree. The screenshots `r3confirm_wt_560x440.png` and `r3_fix.png` show the heading clipped, with the tree's scrollbar column reduced to a stub. `r3confirm_head_560x440.png` shows the heading intact. The remediation summary's "header-only (~22 px)" is therefore inaccurate: there is no intact header at minsize.

This is Low, not High. HEAD also showed zero data rows at minsize, and the default launch still shows four rows. The plan's own requirements, "Keep `minsize(560, 440)`" and "tree still shows at least a few rows", cannot both be met at 144 DPI. Even so, manual check 6 is unmet as written, and the only record of the deferral is the remediation note.

**Remediation:** Choose one:
- `minsize(560, 480)` gives one full data row, and `(560, 500)` gives two. Optionally use `geometry("720x560")` to restore HEAD's five rows at launch.
- Accept the current state, and record "at minsize the tree heading is partly clipped and no rows show; HEAD showed none either" as the decided check-6 outcome in the commit or PR description.

### 2. The four-clip benchmark is still structurally biased against `--jobs 3`. *(Low, carried over)*

This is unchanged since round 1. With four clips, jobs=2 and jobs=3 both need two rounds. Each cell is a single run. Capping the suggestion at 2 is the safe direction, so this affects only how much the README table can prove.

**Remediation:** Optional. Re-run with 12 copies and two warm runs per cell before raising the suggestion above 2.

### 3. The Add buttons sit flush against the drop zone's bottom border. *(Trivial)*

The button bottom is at 82 of an 84 px frame, which is the inner edge of the 2 px groove. The label has 8 px above it, and the button row has 0 px below. The screenshot `r3confirm_wt_720x540.png` shows the buttons touching the border. Nothing is clipped, but the layout looks cramped next to HEAD's balanced padding.

**Remediation:** Optional `button_row.pack(pady=(0, 6))`. It costs 6 px of tree height, so decide it together with Finding 1.

### 4. With `jobs > 1`, the CLI failure reprint is in completion order. *(Trivial, carried over)*

**Remediation:** Optional. Sort `failures` by input index before the reprint.

### 5. The plan's PR split (PR 1: steps 0–5; PR 2: steps 6–9) is not reflected. *(Noted, carried over)*

**Remediation:** Split when committing, or accept a single PR.

### 6. The scratch files `D:\tmp\pwtest\r3_head.txt` and `r3_wt.txt` predate this plan. *(Noted)*

Both are dated 2026-11-07 22:27 and are 526 bytes each, so they cannot reflect the `jobs:` header. They are not evidence for this round. Live `--dry-run` output is the source of truth for transcript parity, and `test_header_prints_jobs_and_above_suggestion_note` covers it.

**Remediation:** No action, or delete them.

## Net assessment

Merge-ready. Core, the scheduler, the directory refcount, GUI parallelism, the CLI `--jobs` flag, the docs and the tests have been stable and green for three rounds, and the round-3 diff touches only drop-zone geometry. The round-2 regression (clipped primary buttons on every launch) is gone. What remains is a trade-off at the minimum window size, where the clipped heading is a small regression compared with HEAD. It is a one-line `minsize`/`geometry` decision that can be made in the commit, or recorded as accepted. The benchmark re-run, failure-order sort, button padding and PR split are optional.

## Verification performed

- `.venv\Scripts\python.exe -m unittest` → `Ran 68 tests … OK (skipped=2)`.
- `MTS_SMOKE=1 .venv\Scripts\python.exe -m unittest` → `Ran 68 tests … OK (skipped=1)`. The real encodes printed `converted 1, skipped 0, failed 0` and `converted 2, skipped 0, failed 0`.
- `python -c "import mts_to_dnxhr as m; print(m.suggested_jobs(), m.MAX_JOBS)"` → `2 4`, as expected after the step 9 adjustment.
- `python mts_to_dnxhr.py --help` → `-j N, --jobs N  Encode up to N clips at once (1-4). Suggested for this PC: 2 (default: 1)`.
- `python mts_to_dnxhr.py x.MTS --jobs 0|5|x` → exit 2, 2, 2.
- `git diff HEAD -U0 -- mts_to_dnxhr.py | grep '^@@'` → no hunks inside `build_command` or `run_ffmpeg`.
- `git diff HEAD --stat` → tests +290 (core) and +127 (GUI), additions only.
- Grep for `pack_propagate|height=110|height=75|_active_index|_file_t0|_status_pct|_elapsed_file|_current_fraction|_known_total` in `mts_to_dnxhr_gui.py` and `tests/*.py` → 0 matches.
- `git diff HEAD -- mts_to_dnxhr_gui.py` → `tk.Frame(..., height=110)` was removed, and the label `pady` changed from `(22, 8)` to `(8, 6)`.
- **Live Tk measurement** (`D:\tmp\pwtest\r3confirm_measure.py`, a copy of `r3eval_measure.py` with a new output prefix, DPI-aware, 144.07 px/in). Results are in the Finding 1 table.
  - Working-tree buttons: 35/35 px at all three sizes. The button row starts at y=47 and the buttons end at 82 of 84.
  - HEAD buttons: 35/35 px, ending at 98 of 110.
  - The Convert button bottom is 430 / 470 / 530 in both builds, so nothing below the tree is cut off.
- **Screenshots** in `D:\tmp\pwtest\`. I reviewed the remediator's `r3_fix.png` and took `r3confirm_{head,wt}_{560x440,560x480,720x540}.png`.
  - Working tree: buttons fully drawn and the jobs hint fully visible at 560×440. The tree heading is clipped at 560×440, and four rows show at 720×540.
  - HEAD: the heading is intact at 560×440.
- Manual GUI checks 1–5 (live parallel rows, Stop, Stop and quit with Task Manager) were not re-run this round. That logic is unchanged since round 1, where it was verified, and the round-3 diff touches only drop-zone geometry.
- A round-3 report from an earlier attempt already existed at this path, written at 23:31 the same night. I verified its claims independently, the measurements matched exactly, and this file replaces it. The round-1 and round-2 reports were not touched.
