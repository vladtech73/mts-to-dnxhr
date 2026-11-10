# Desktop UI Polish, Sortable and Resizable Columns — Implementation Evaluation

*Claude Code turns used: 15 / max 100*

*Evaluator: claude · 2026-11-10 · Round 2 (confirm) · Reviews the implemented `ui-polish-sort-resize-claude-2026-11-10.md` against the working tree (uncommitted changes on `ui-polish-sort-resize`, no commits ahead of `hwaccel-gpu-decode` @ `265794e`).*

## Verdict: Every round-1 code finding is fixed and every automated gate passes. The only open item is the plan's manual, DPI, and frozen-build pass, which has to be done by hand.

The remediation pass closed findings 1, 2, 3, 5, 6, and 7 from round 1 without regressions. The suite grew from 82 to 85 tests and passes, and all nine `AppTableTests` run instead of skipping. The grep gates and the core-file gate are clean. No Critical or High issues remain. A probe at simulated 100%, 150%, and 200% scaling, with and without the FFmpeg banner, shows no horizontal overflow at the default size and a scaled minimum size. Verification 3–6 (manual run, real DPI change, frozen exe, screenshots) are still unrecorded, and this eval could not stand in for them.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 1–9 are complete. The minsize deviation is now explained in a comment and clamped to the screen |
| Contract fidelity | 5 | The argv test passes. Core, requirements, and the build script are unchanged. The jobs-default change is still stashed |
| Verification honesty | 4 | Unit tests and grep gates pass, and the new tests check real behavior. Verification 3–6 have no recorded results |
| Finding severity | 4 | Low only (the manual pass) |
| Merge readiness | 4 | The code is merge-ready. The plan's manual DPI and frozen-build checks should happen first |

**Overall completeness:** 22/25 · **percent:** 88%
**Band:** nearly-done
**Open findings:** Critical 0 · High 0 · Low 1 · Trivial/Noted 5

## Loop signal

**Loop signal:** ship-now
**Signal rationale:** Nothing is left that a code-remediation round can fix. The one Low item is a human pass through Verification 3–6, which another fix→eval cycle can't do.

## Round-1 disposition

| R1 # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | Style `font=` on TEntry/TSpinbox did nothing | **Fixed** | `font=self._fonts.body` is now on the widgets (`mts_to_dnxhr_gui.py:880-881`, `:911`). The dead style keys are gone (`:636-674`). Probe: `export_entry.cget("font")` and `jobs_spin.cget("font")` return the App's named body font, not `TkTextFont` |
| 2 | Default window narrower than columns | **Fixed** | `folder` width is now 290, for a column total of 970 (`:106`). The geometry is scaled `_px(1024)×_px(660)` (`:730-735`). The new test `test_default_size_has_no_horizontal_overflow` asserts `xview() == (0.0, 1.0)`. Probe: reqwidth 1012 < 1024, and `xview` is `(0.0, 1.0)` at 1.0, 1.5, and 2.0 scale, with and without the banner |
| 3 | Scaled minsize could exceed the work area | **Fixed** | `minsize` is `min(_px(800), screen_w - _px(40))` × `min(_px(580), screen_h - _px(80))`, with a comment explaining the size (`:736-740`). The height dropped from 620 to 580 |
| 4 | Manual, DPI, frozen-build, and screenshot checks unrecorded | **Open** | Nothing under `plans/draft/` records results (see finding 1 below) |
| 5 | Pixel literals that skip `_px` | **Fixed** | The drop-zone `padx` (`:822`, `:824`), `wraplength=self._px(640)` (`:946`), and the banner `<Configure>` math (`:1051`) all go through `_px`. The only literal left is `width=16` on Convert (`:976`), which is a character count, not pixels |
| 6 | `drop_label` alias and dedupe loop | **Fixed** | No `drop_label` or `registered_labels` remain. The code is a plain two-label loop (`:827-829`) |
| 7 | Separator, heading double-click, and autofit untested | **Fixed** | New `test_autofit_clamps_to_minwidth_and_max` and `test_heading_double_click_does_not_open_error_dialog` (`tests/test_mts_to_dnxhr_gui.py:901-915`) |
| 8–11 | Noted items | Unchanged, no action needed | Status tags still color the whole row. Output summary still sits below the group. Repo hygiene is still intact. The extra contrast pairs are still untested (see finding 4) |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. iid-keyed rows** | Complete | The grep for `values[2]`, `self.items`, `self.errors`, and `children[` returns nothing. `test_status_follows_snapshot_after_resort` passes |
| **2. Status kinds & tags** | Complete | `_STATUS_RANK`/`_STATUS_TAG` (`:92-100`). `test_set_status_keeps_odd_stripe` passes |
| **3. Pure helpers** | Complete | The `SortHelperTests` cases (6) pass, including the mixed digit/letter names and two `None` rows |
| **4. Columns, sort, marks** | Complete | `_COLUMN_LAYOUT` (`:101-107`) matches the plan except `folder`, which went from 320 to 290 to fix round-1 overflow. That is an acceptable deviation, since the stretch column grows to fill the window anyway |
| **5. Resize / autofit / h-scroll** | Complete | Horizontal scrollbar (`:864-866`). No `<Motion>` binding. Autofit and heading double-click now have tests |
| **6. Palette / theme / fonts** | Complete | The hex grep matches only the palette block (`:52-80`). Entry and Spinbox now use the body font |
| **7. Layout refresh** | Complete | The minsize is scaled, clamped, and explained in a comment. The tree row keeps `weight=1` |
| **8. Tests** | Complete | 85 tests, OK (2 skipped, both in core: symlinks and the opt-in smoke test). All 9 `AppTableTests` and `PaletteContrastTests` run |
| **9. README** | Complete | "A hint shows…", plus the sort/resize/order paragraph (`README.md:125-127`). No claims about persistence. The jobs default still reads 1 |

## Findings (ranked)

### 1. The plan's manual, DPI, frozen-build, and screenshot checks still have no recorded results. *(Low)*

Carried over from round 1, finding 4. Verification 3 covers the dummy clips plus the real 335 MB sample (green Done, accent progress bar, parallel row timers), Stop leading to Cancelled, the banner and **Check again**, and the drop-zone states. Verification 4 is an actual Windows scaling change to 150% and 200%. Verification 5 is `scripts\build_exe.ps1` and launching `dist\MTS-to-DNxHR.exe`. Verification 6 is the screenshot pair. This eval's simulated-scale probe mocks `_dpi_scale`, so it checks the geometry math but not real Windows font scaling, clam rendering, or the cursor over separators.

**Remediation:** Run Verification 3–6 by hand before merge and attach the results or screenshots to the PR.

### 2. `test_default_size_has_no_horizontal_overflow` depends on the screen being at least ~1064 px wide. *(Trivial)*

The geometry clamps to `winfo_screenwidth() - _px(40)` (`:732`). On a display narrower than about 1052 px (a small VM or RDP window, for example), the window opens narrower than the 1012 px reqwidth. The test then fails even though the app is behaving as intended. The dev machine is far above that, so the test passes here.

**Remediation:** Optionally `skipTest` when `root.winfo_screenwidth() < app._px(1064)`, or call `root.geometry("1024x660")` explicitly in the test.

### 3. The default height of 660 is less than the requested height of 738 (800 with the banner). *(Noted)*

At 100% the tree gives up about 78–140 px from its default 10-row request, so a fresh window shows about 7 rows instead of 10. Nothing clips, because the tree is the only row with weight. The `minsize` comment's "two clip rows still visible" floor holds at 580.

**Remediation:** No action.

### 4. Contrast pairs beyond the plan's list are still untested. *(Noted)*

`TEXT_DISABLED` on `DISABLED_BG` (3.30) and `TEXT_SECONDARY` on `DROP_HOT_BG`/`DROP_PAUSED_BG` (7.37 / 6.76) all pass, but `PaletteContrastTests` (`tests/test_mts_to_dnxhr_gui.py:745-760`) doesn't assert them. The plan didn't require them.

**Remediation:** Optional.

### 5. The screen clamp uses the full screen size, not the work area. *(Noted)*

`winfo_screenheight() - _px(80)` approximates the taskbar. At 175% the margin is 140 device px, which covers a standard taskbar (about 84 px at that scale), so the round-1 concern is resolved in practice. A vertical or auto-hide taskbar setup isn't handled exactly, but nothing breaks.

**Remediation:** No action.

### 6. Carried-over Noted items. *(Noted)*

Status tags still color the whole row. The Output summary still sits below the settings group. The jobs-default change is still in `stash@{0}` and stays out of this work. There are still no commits, which matches "do not commit … without the user asking". The plan's commit-per-step split will need to happen at commit time.

**Remediation:** No action.

## Net assessment

Ready to merge as far as the code goes. The remediation pass was tight and well targeted. Each round-1 Low was fixed at its root (widget fonts, scaled and clamped geometry, a narrower stretch column) and came with tests where tests make sense. Nothing new turned up. Before opening the PR, the user should do the hand-only part of the plan: one real 150%/200% scaling check, a frozen-exe launch, the real-clip encode, and the before/after screenshots. Finding 2 is optional hardening.

## Verification performed

- `.\.venv\Scripts\python.exe -m unittest -v` → **Ran 85 tests, OK (skipped=2)**. Skipped: `test_symlink_inside_folder_maps_under_that_folder` (symlinks not available) and `SmokeTest` (opt-in `MTS_SMOKE=1`). All 9 `AppTableTests`, the 6 `SortHelperTests`, `PaletteContrastTests`, and `DefaultsTests.test_defaults_match_cli_encode_argv` ran and passed.
- Grep gate 1: `grep -n 'values\[2\]\|self\.items\|self\.errors\|children\[' mts_to_dnxhr_gui.py` → no matches.
- Grep gate 2: `grep -n '#[0-9a-fA-F]\{6\}\|fg="red"' mts_to_dnxhr_gui.py` → lines 52–80 only (the `_Palette` block starts at `:49`).
- Core gate: `git diff --stat hwaccel-gpu-decode -- mts_to_dnxhr.py requirements.txt requirements-build.txt scripts/build_exe.ps1` → empty. `git log hwaccel-gpu-decode..HEAD` → no commits. `stash@{0}` still holds the jobs-default change. `IntVar(value=1)` (`:905`) and the README's "defaults to 1" are unchanged.
- Pixel-literal grep `pad[xy]=[0-9]|wraplength=[0-9]|width=[0-9]{2,}` → only `width=16` on Convert (a character count).
- Live Tk probe (temporary script under `D:\tmp\pwtest`, deleted afterwards), with `_dpi_scale` mocked to 1.0, 1.5, and 2.0 and `locate_tools` set to found and to missing:
  - 1.0: geometry 1024×660, reqwidth 1012, minsize (800, 580), `xview` (0.0, 1.0), with and without the banner.
  - 1.5: geometry 1536×990, reqwidth 1509, minsize (1200, 870), `xview` (0.0, 1.0).
  - 2.0: geometry 2048×1280, reqwidth 2006, minsize (1600, 1160), `xview` (0.0, 1.0).
  - Entry and Spinbox `cget("font")` return the App's named body font at every scale.
- Not run: the manual GUI pass, a real Windows scaling change, `scripts\build_exe.ps1` plus the exe launch, and the screenshots (Verification 3–6).
