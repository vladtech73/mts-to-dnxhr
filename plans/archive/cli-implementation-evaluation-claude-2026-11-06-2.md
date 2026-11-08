# DNxHR Conversion CLI — Implementation Evaluation

*Claude Code turns used: 19 / max 100*

*Evaluator: claude · 2026-11-06 · Round 2 (confirm) · Reviews the implemented `mts-to-dnxhr-cli-claude-2026-11-06.md` against the working tree after round-1 remediation.*

## Verdict: Ship. All seven actionable round-1 findings are fixed and verified. One new Low: the empty-folder cleanup can also delete an empty output folder the user created.

The remediation pass changed `mts_to_dnxhr.py`, `tests/test_mts_to_dnxhr.py` and `README.md`. Each round-1 finding is closed, and each is checked by a new unit test, a scratch-dir run, or both:

- symlink mapping
- `mkdir` failures aborting the batch
- PowerShell paste of dry-run commands
- the smoke test's hardcoded sample facts
- the duplicated path in failure messages
- empty folders left after a failure
- the README scratch folder

The unit suite (25 tests, 2 skipped) and the opt-in smoke test both pass. A real NTFS junction now maps under the input folder and encodes correctly. Nothing is Critical or High.

The one new Low comes from fixing round-1 finding 6. `_remove_dir_if_empty(final_dst.parent)` removes any empty destination folder, including one the user created before the run. It deletes no data, but it reaches outside the "writes only under the output directory" contract.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 1–10 remain complete. All round-1 findings 1–7 are fixed. Out-of-scope items (packaging, `git init`, the `-r` and mono-track fallbacks) stayed out. |
| Contract fidelity | 4 | Argv order, the `-n`/`-y` split, `.part` handling, exit codes and output layout are unchanged. One small deviation is new: a failed file can `rmdir` an empty output folder that existed before the run (finding 1). |
| Verification honesty | 5 | Unit and smoke gates are green. The new tests assert the real fixed behavior (the mkdir `PermissionError`, the stripped path prefix plus folder removal, a clip outside the folder exiting 2, the bare `ffmpeg` name). The smoke test is now generic for clips other than the reference sample. |
| Finding severity | 4 | One Low. The rest are Trivial or Noted. |
| Merge readiness | 5 | Safe to merge as-is. The Low is a cheap optional hardening fix. |

**Overall completeness:** 23/25 · **percent:** 92%
**Band:** ship
**Open findings:** Critical 0 · High 0 · Low 1 · Trivial/Noted 5

### Band guide (required)

| Band | When |
|------|------|
| **ship** | percent ≥ 90 **and** Critical=0 **and** High=0 |
| **nearly-done** | percent ≥ 75, or only cheap Low/Trivial left after Critical/High=0 |
| **needs-work** | percent 50–74, or any Critical/High that needs a real fix pass |
| **incomplete** | percent < 50, or Missing workstreams / failed plan gates |

## Loop signal

**Loop signal:** ship-now
**Signal rationale:** All round-1 Lows are verified fixed, every gate passes, and the only new Low (removing a pre-existing empty output folder) deletes no data. It is a few lines to fix and does not need another fix→eval cycle.

## Round-1 findings: remediation status

| # | Round-1 finding | Status | Evidence |
|---|---|---|---|
| 1 | Symlinked clip crashes `main` via `relative_to` | **Fixed** | `_absolute_path` uses `absolute()`, not `resolve()` (`mts_to_dnxhr.py:79-85`, `:94`, `:107`, `:134-135`). `output_path_for` turns `relative_to` failures into a clear `ValueError` (`:139-144`), and `main` exits 2 on it (`:771-778`). The unit test `test_symlink_inside_folder_maps_under_that_folder` **skips on this machine**: Windows symlinks need privileges. So I used an NTFS junction instead. `footage\linked → elsewhere\` encoded to `out\linked\real.mov`, exit 0. `test_clip_outside_the_input_folder_is_a_preflight_error` passes. |
| 2 | A `mkdir` `OSError` escapes `convert_one` and aborts the batch | **Fixed** | `mts_to_dnxhr.py:528-533`. The unit test `test_mkdir_oserror_fails_the_file_and_returns` passes. In a real run with `-o <file>\out` on a batch of 2, both files report `failed` (WinError 183), the summary prints, and the exit code is 1 with no traceback. |
| 3 | Pasted dry-run breaks in PowerShell when the ffmpeg path has spaces | **Fixed** | `_command_tool` (`:342-355`) prints a bare `ffmpeg` when `which` resolves to the same binary. The README now tells the user to put `& ` in front (`README.md:71`). A dry run on `samples/` printed `ffmpeg -nostdin ...`. |
| 4 | Smoke test hardcodes facts about the sample | **Fixed** | The hardcoded probe checks now run only when `sample.name == "01 American Landscape.MTS"`. Other clips get generic checks (`tests/test_mts_to_dnxhr.py:588-596`). |
| 5 | Failure message repeats the source path | **Fixed** | `_without_path_prefix` (`:372-384`). A real corrupt `junk.MTS` printed `failed: ...\junk.MTS: Invalid data found when processing input` with the path once. A unit test also covers it. |
| 6 | Empty output folder left behind on failure | **Fixed, but overreaches** | `_remove_dir_if_empty(final_dst.parent)` runs on every failure path (`:538`, `:543`, `:555`, `:565`). See new finding 1 (it also removes a pre-existing folder) and finding 2 (it only removes the innermost folder). |
| 7 | README quick-test writes into `samples/_readme_check` | **Fixed** | `README.md:94` now uses `-o converted/`, which is gitignored, and `:97` says to delete it afterwards. |
| 8 | Real Ctrl+C and Resolve import never exercised | **Still open (Noted)** | Only a simulated Ctrl+C was re-run (see Verification). |
| 9 | Python 3.9 checked for syntax only | **Still open (Noted)** | `ast.parse(feature_version=(3,9))` passes. No 3.9 interpreter is installed. |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. Repo hygiene** | Complete | Unchanged since round 1. `requirements.txt`, `.gitignore`, MIT `LICENSE` and `samples/README.md` are present. The repo is still not a git repo. |
| **2. Constants / types / `find_tool`** | Complete | `mts_to_dnxhr.py:24-72`. Unchanged. Import has no side effects. |
| **3. Discovery / path mapping** | Complete | Now keeps symlink locations (`:79-145`). Case-insensitive matching, the skipped-file count, trailing-slash handling, mirroring and `normcase` collisions are all still covered by tests. |
| **4. Probe** | Complete | `parse_probe_json` / `probe` / `parse_progress_line` (`:179-272`) are unchanged in behavior. In the smoke test the sample probed as 168.192 / `tt` / `30000/1001` / has audio. |
| **5. Command builder** | Complete | `build_command` (`:280-326`) follows the planned argv order. The dry run prints `-n -i ... -field_order tt -c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000 -f mov "...samples_dnxhr\01 American Landscape.mov"`. |
| **6. Runner / cleanup** | Complete | `run_ffmpeg` (`:429-514`) is unchanged. `convert_one` (`:517-567`) now fails a file instead of raising on `mkdir`, probe, or runner errors, and still re-raises `KeyboardInterrupt`. |
| **7. CLI / orchestration** | Complete | `main` (`:741-802`) exits 2 when mapping fails with `ValueError`. Exit codes 0/1/2/130 are all confirmed by real or simulated runs. |
| **8. Tests** | Complete | 25 tests: 23 pass and 2 skip (the symlink test on Windows, and the smoke test without `MTS_SMOKE`). With `MTS_SMOKE=1` the smoke test passes in 3.15 s. |
| **9. Real-sample verification** | Complete | The README "Verified on FFmpeg 8.0.1" section is still present (`README.md:50`). `samples/_check` is absent. |
| **10. README** | Complete | All planned sections are present. New text covers the PowerShell `&` note and the `converted/` scratch folder. No `180 Mb`/`3.8 GB` figures. |

## Findings (ranked)

### 1. A failed file can delete an empty output folder the user created before the run. *(Low)*

`convert_one` calls `_remove_dir_if_empty(final_dst.parent)` on every failure path (`mts_to_dnxhr.py:538`, `:543`, `:555`, `:565`). It does not check whether this run created that folder.

Repro: I created an empty `userout\` myself, then ran `mts_to_dnxhr.py bad\junk.MTS -o userout`. The run exited 1, and **`userout` no longer existed**. The same happens with a folder the user prepared for a batch, such as an empty `converted\` or a mapped share folder. Only empty folders are removed, so no data is lost. But it breaks the plan's contract that the tool "writes only under the output directory", and removing the user's own folder is surprising. This came from fixing round-1 finding 6, which was Trivial, so the fix is now riskier than the problem it fixed.

**Remediation:** Remove only folders this run created. Before `mkdir`, record whether `final_dst.parent` already existed, and skip `rmdir` if it did. Alternatively, drop the cleanup altogether: an empty folder left behind was rated Trivial. Add a unit test that pre-creates the output folder and asserts it survives a probe failure.

### 2. Failure cleanup removes only the innermost folder, and Ctrl+C leaves one behind. *(Trivial)*

`mkdir(parents=True)` can create several levels, but `_remove_dir_if_empty` removes only the innermost one. In a recursive run of `bad2\sub\junk.MTS -o out2`, `out2\sub` was removed but an empty `out2\` was left. A simulated Ctrl+C mid-encode left an empty `ctrlc\` output folder, because `KeyboardInterrupt` skips the cleanup. Neither causes harm. The cleanup is just inconsistent.

**Remediation:** If finding 1 is fixed by tracking created folders, remove that whole created chain from the innermost folder upward. Otherwise no action.

### 3. With default output, a symlinked input folder still resolves to the link target. *(Trivial)*

`default_output_dir` still calls `input_path.resolve()` (`:121`). Symlinks inside the folder are now kept as written (finding 1 fix), but when the input folder itself is a link or junction, the default `<name>_dnxhr` sibling is created next to the link's target, not next to the link. That is inconsistent with the new "do not follow links" mapping, though it is predictable, and `-o` overrides it.

**Remediation:** Use `_absolute_path` in `default_output_dir`, after checking that a trailing slash still works. The test already covers that. Optional.

### 4. The smoke test still assumes the sample has audio and that HQX is the output. *(Trivial)*

The smoke test's audio check (`tests/test_mts_to_dnxhr.py:642-645`) raises `AssertionError("no audio stream")` for a video-only clip. The plan allows such clips (`-map 0:a?`). If a user drops a silent `.M2TS` that sorts first in `samples/`, the smoke test fails while the tool works correctly.

**Remediation:** Skip the audio check when the source has no audio stream. Optional.

### 5. On Windows, the symlink fix is covered only by a test that skips. *(Noted)*

`test_symlink_inside_folder_maps_under_that_folder` skips on this machine ("symlinks are not available"). I confirmed the fix with a real NTFS junction instead, and it would run on POSIX CI. A junction-based variant (`_winapi.CreateJunction`, which needs no admin rights) would cover it locally, but that is optional.

**Remediation:** No action required. Consider a junction fallback in the test on win32.

### 6. Real Ctrl+C, the Resolve import, and Python 3.9 at runtime are still unverified. *(Noted, carried over from round 1)*

These belong to the user (Verification #8 and #9) or need a 3.9 interpreter that is not installed. A simulated interrupt still behaves correctly: exit 130, no `.part` file, and no `ffmpeg` process left.

**Remediation:** Before tagging a release, the user should do one real Ctrl+C during a full encode and one Resolve import.

## Net assessment

Merge-ready. The remediation pass was focused: every change maps to a round-1 finding, with no unrelated changes. The new unit tests check real behavior, not the old baseline. The fail-closed contracts the plan cared about all still hold:

- never overwrite without `--overwrite`
- no orphaned `.part` files
- a dry run that cannot replace an existing output (`-n`)
- exit 2 on collisions and on clips outside the input folder
- the batch continues past per-file failures

Finding 1 is the only change I'd make before a public release. It is a few lines (only remove folders this run created) plus one test. Findings 2–4 are optional polish. `git init` and publishing remain user-gated.

## Verification performed

- `.venv\Scripts\python.exe -m unittest -v` → **25 tests, OK (skipped=2)**: the symlink test (no symlink privilege on Windows) and the smoke test (opt-in).
- `$env:MTS_SMOKE='1'; .venv\Scripts\python.exe -m unittest tests.test_mts_to_dnxhr.SmokeTest -v` → **OK in 3.15 s**. HQX MOV with s16 and HQX MXF with s24 were both written. Both progress bars rendered, the inner bar reached 3.0/3.0, and no `.part` file remained.
- `python mts_to_dnxhr.py samples/ --dry-run` (from the repo root) → exit 0, header `skipped non-MTS: 1` (`samples/README.md`). The printed command starts with a bare `ffmpeg` and contains `-n -i` and `-c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000`. Output `...\samples_dnxhr\01 American Landscape.mov`. No `samples_dnxhr` folder was created.
- Scratch harness in `D:\tmp\mtseval2` (removed afterwards; the junction was deleted as a link first):
  - **Junction** `footage\linked → elsewhere\` with `-r -o out` → `out\linked\real.mov` and `out\top.mov`, exit 0. Re-run → `skipped 2`, exit 0.
  - Corrupt `junk.MTS` with a pre-existing empty `-o userout` → `failed 1`, exit 1, path printed once, **`userout` deleted** (finding 1).
  - Recursive corrupt input `-o out2` → `out2\sub` removed, empty `out2\` left (finding 2).
  - `-o <file>\out` on a 2-clip batch → both clips `failed` with WinError 183, summary printed, exit 1, no traceback (round-1 finding 2 fixed).
  - Simulated Ctrl+C (patched `parse_progress_line`) on the sample → `interrupted`, rc 130, no `.part` file, 0 `ffmpeg` processes, empty output folder left (finding 2).
- Grep gates: no `shell=True` in the product or test files. No `_readme_check` and no `180 Mb`/`3.8 GB` in the README.
- Python 3.9 syntax: `ast.parse(feature_version=(3, 9))` passes for both files.
- The repo tree after the eval contains only product files, `plans/`, `samples/` (the sample plus README), `.venv/` and `__pycache__/`. No scratch output was left.
