# DNxHR Conversion CLI — Implementation Evaluation

*Claude Code turns used: 22 / max 100*

*Evaluator: claude · 2026-11-06 · Reviews the implemented `mts-to-dnxhr-cli-claude-2026-11-06.md` against the working tree.*

## Verdict: Ready to ship. Every workstream landed, every gate I could run passed, and only Low/Trivial findings remain.

All ten implementation steps exist on disk and match the plan's contracts. These include the profile table, stream mapping, deinterlace and field-order rules, `.part` rename and cleanup, `-n`/`-y` dry-run semantics, exit codes, and output layout. The unit suite (19 pass, 1 skipped) and the opt-in smoke test both pass. I also re-ran the full-length encode the implementer skipped, and it matches the plan's expectations exactly. Nothing is Critical or High. The remaining findings are robustness polish (an unhandled `relative_to` on symlinked inputs, PowerShell copy-paste of dry-run commands when the ffmpeg path has spaces, and a smoke test that hardcodes facts about this particular sample).

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | Steps 1–10 are all complete. Out-of-scope items (packaging, `git init`, `-r`/mono-track fallbacks) stayed out. |
| Contract fidelity | 5 | Argv order, `-n`/`-y` split, `.part` rename, exit codes 0/1/2/130, sibling `_dnxhr` dir, and fail-closed collisions all match the plan. |
| Verification honesty | 4 | Gates are green, and the README "Verified" section is honest that a full encode was not run. However, the smoke test asserts facts specific to this sample, and real console Ctrl+C was only exercised in simulation. |
| Finding severity | 4 | Low findings only. |
| Merge readiness | 5 | Safe to merge as-is. The Lows are optional polish. |

**Overall completeness:** 23/25 · **percent:** 92%
**Band:** ship
**Open findings:** Critical 0 · High 0 · Low 4 · Trivial/Noted 5

### Band guide (required)

| Band | When |
|------|------|
| **ship** | percent ≥ 90 **and** Critical=0 **and** High=0 |
| **nearly-done** | percent ≥ 75, or only cheap Low/Trivial left after Critical/High=0 |
| **needs-work** | percent 50–74, or any Critical/High that needs a real fix pass |
| **incomplete** | percent < 50, or Missing workstreams / failed plan gates |

## Loop signal

**Loop signal:** ship-now
**Signal rationale:** No Critical/High findings, all runnable plan gates pass (including a full 168 s encode), and the four Lows are optional hardening that can land later without changing behavior contracts.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **1. Repo hygiene** | Complete | `requirements.txt` = `tqdm>=4.60`. `.gitignore` has all 13 planned patterns. `LICENSE` is MIT. `samples/README.md` covers the drop-in, gitignore, and `MTS_SMOKE` points. In a throwaway temp git repo using this `.gitignore`, `.MTS`/`.m2ts`/`.M2TS`, `samples/_check/*.mov/.mxf/.part`, `samples_dnxhr/`, `sub/dnxhr/`, `.venv/` and `converted/` were all ignored. Only `.gitignore`, `mts_to_dnxhr.py` and `samples/README.md` showed as untracked. |
| **2. Constants / types / `find_tool`** | Complete | `mts_to_dnxhr.py:24-72`. `PROFILES`, `AUDIO_CODECS`, `CONTAINERS` and `INTERLACED_FIELD_ORDERS` match the plan exactly. The frozen `Options`/`ProbeInfo` dataclasses include the `interlaced` property. Import has no side effects (tests import it). |
| **3. Discovery / path mapping** | Complete | `discover_inputs`/`find_inputs` (`:79-106`) are case-insensitive and count skipped non-MTS files. `default_output_dir` (`:109-114`) resolves first, so a trailing slash works. `output_path_for` (`:117-125`) mirrors subfolders. `find_collisions` (`:128-139`) uses `normcase`. Small additive API: `discover_inputs` returns `(inputs, skipped)`. |
| **4. Probe** | Complete | `parse_probe_json` (`:159-192`) takes field order and rate from the first video stream only, maps `unknown` to `None`, and treats a bad duration as `None`. `probe` (`:195-226`) uses argv, `timeout=60`, and `ProbeError` on non-zero exit, timeout, OSError, or bad JSON. `parse_progress_line` (`:229-252`) handles `N/A` and never raises. The smoke test probe returned 168.192 / `tt` / `30000/1001` / has_audio. |
| **5. Command builder** | Complete | `build_command` (`:260-306`) follows the planned argv order exactly. yadif is added only with `--deinterlace` and an interlaced or unprobed source. `-field_order` is added only for woven interlaced output. `format_command` (`:309-319`) double-quotes `?`/`*` on Windows. |
| **6. Runner / cleanup** | Complete | `run_ffmpeg` (`:371-456`) sends stderr to a temp file, adds `-progress pipe:1 -nostats`, does `os.replace` only on exit 0 with a non-empty `.part`, and deletes the `.part` in the `finally` block whenever the run did not succeed. `convert_one` (`:459-492`) checks for skips before probing and reports through `tqdm.write`. |
| **7. CLI / orchestration** | Complete | `build_parser` (`:495-574`) has every flag and the defaults `dnxhr_hqx`/`mov`/`16`. The epilog lists the four canonical examples and the exit codes. `main` (`:666-723`) follows the planned 8-step flow, and a dry run works without ffmpeg. It also validates `--duration > 0`, which is a reasonable addition. |
| **8. Tests** | Complete | `tests/test_mts_to_dnxhr.py` has 20 tests, covering every step-5 assertion, probe fixtures (audio-first, video-only, `unknown`), progress parsing, dry-run `-n`/`-y`, and exit 2 for missing, `.txt` and empty inputs. The smoke test is gated on `MTS_SMOKE=1` plus ffmpeg and ffprobe. |
| **9. Real-sample verification** | Complete | The README "Verified on FFmpeg 8.0.1" section (`README.md:50-58`) records the results for 9.1–9.5. `samples/_check` is gone. No fallback was needed, so no fallback test was required. I independently re-measured LB 45.2, SQ 145.3 and 444 440.0 Mb/s, all matching. |
| **10. README** | Complete | It has every planned section: what & why, requirements with venv steps, the profiles table, all the usage examples, output layout, interlaced footage, using in Resolve, testing, and limitations. It contains no 180 Mb/s or 3.8 GB figures. |

## Findings (ranked)

### 1. A symlinked clip inside an input folder crashes `main` with a traceback. *(Low)*

`discover_inputs` stores `candidate.resolve()` (`mts_to_dnxhr.py:97`). That follows symlinks and junctions, so a link inside `footage/` that points elsewhere resolves outside `input_root`. Then `output_path_for` calls `src_abs.relative_to(root_abs)` (`:124`), which raises `ValueError`. Nothing catches it in the list comprehension at `:696-699`, so the user gets a traceback with exit code 1 instead of the plan's exit 2 for a "usage or preflight error". It's rare on camera cards, but common when users gather footage with links.

**Remediation:** Map from the unresolved candidate path (`candidate.absolute()`) and compute `relative_to` against the unresolved root. Alternatively, catch `ValueError` in `main` around the mapping and exit 2 with a message. Add a unit test if the platform allows symlinks (skip otherwise).

### 2. A non-`OSError` failure path can abort the whole batch: `mkdir` errors escape `convert_one`. *(Low)*

`convert_one` calls `final_dst.parent.mkdir(...)` (`:470`) outside any try block. A `PermissionError` or other `OSError` there, for example on a read-only output share or an over-long path, propagates through `_encode_all` (`:644-657`), which only catches `KeyboardInterrupt`. The batch stops with a traceback. That contradicts the plan's contract that "the batch continues past failures" with exit 1.

**Remediation:** Wrap the mkdir (or the whole body after the skip check) in `try/except OSError` and return `("failed", str(exc))`.

### 3. A pasted dry-run command breaks in PowerShell when the ffmpeg path contains spaces. *(Low)*

`format_command` (`:309-319`) uses `list2cmdline` quoting. If ffmpeg lives under, say, `C:\Program Files\ffmpeg\bin\ffmpeg.exe`, the first token is printed as a quoted string. PowerShell then treats it as an expression and fails with `Unexpected token '-nostdin'`. You would need to prefix it with `&`. On this machine the Gyan winget path has no spaces, so Verification #4 passes. But the README presents PowerShell as the shell, and the plan's goal is a "copy-pasteable command".

**Remediation:** Print the bare program name (`ffmpeg`) when `shutil.which("ffmpeg")` resolves to the same file. Alternatively, add a README line saying to prefix the command with `& ` in PowerShell, or have `format_command` emit the `& ` prefix when the first token is quoted on win32.

### 4. The smoke test hardcodes properties of this one sample, but the docs say it uses "the first `.mts`/`.m2ts` it finds". *(Low)*

`tests/test_mts_to_dnxhr.py:509-513` asserts `duration≈168.192`, `field_order == "tt"` and `avg_frame_rate == "30000/1001"` for whatever `_first_sample()` returns. `samples/README.md` invites users to "drop one or more" clips. Any clip that sorts before `01 American Landscape.MTS`, or any progressive or 25p clip, makes the smoke test fail even though the tool works. The plan's step-4 "Done when" check against this specific sample is fine as a one-off, but it shouldn't be baked into a generic smoke test.

**Remediation:** Make the hardcoded probe checks conditional on `sample.name == "01 American Landscape.MTS"`, or replace them with generic checks (`duration > 0`, `avg_frame_rate` present). The output-vs-source comparisons already do the generic work.

### 5. The failure message duplicates the source path. *(Trivial)*

ffprobe's stderr already starts with the path, and `convert_one` prefixes it again (`:473-476`). In my run with a corrupt input, the output was `failed: D:\...\junk.MTS: D:\...\junk.MTS: Invalid data found when processing input`.

**Remediation:** Drop the `{src}:` prefix for `ProbeError`s, or strip a leading `"{src}: "` from the message.

### 6. An empty output folder is left behind when probing or encoding fails. *(Trivial)*

`convert_one` creates the destination directory (`:470`) before probing. The corrupt-input run left an empty `out/bad/`. The plan prescribes this order, so it's faithful, just untidy.

**Remediation:** Optionally create the directory after a successful probe, or `rmdir` it on failure if it's empty. Otherwise no action.

### 7. The README's quick-test example writes into `samples/_readme_check`. *(Trivial)*

`README.md:94`. The `.mov` inside is gitignored, but the folder pattern is not, and the plan specifically asked for scratch folders under `samples/` to be deleted. It's harmless, but it invites leftovers in the repo.

**Remediation:** Point the example at an ignored location such as `-o converted/` or `-o samples/dnxhr`, or add a "delete it afterwards" note.

### 8. Real console Ctrl+C and the Resolve import have not been exercised by the implementer or this eval. *(Noted)*

I simulated `KeyboardInterrupt` mid-encode by patching `parse_progress_line`. It produced exit 130, no `.part` file, and no `ffmpeg.exe` left running. A true Ctrl+C in Windows Terminal, where ffmpeg also receives `CTRL_C_EVENT`, has not been run, and neither has Verification #9, the manual Resolve import, which belongs to the user. The code paths for the real case look correct: the read loop unblocks on ffmpeg's exit, and the `finally` block deletes the `.part`.

**Remediation:** The user should do one manual Ctrl+C during a full encode and one Resolve import before tagging a release.

### 9. Python 3.9 has been checked for syntax only, not at runtime. *(Noted)*

Both files parse with `ast.parse(..., feature_version=(3, 9))`, and every PEP 585/604 annotation is protected by `from __future__ import annotations`. No 3.9 interpreter is installed here (`py -0` shows only 3.11 and 3.14).

**Remediation:** No action now. Add a 3.9 job if CI is set up later.

## Net assessment

This is merge-ready. The implementation follows the plan closely, with no drive-by refactors. The two additions beyond the plan (`discover_inputs` returning a skipped count, and `--duration` validation) are small and justified. The fail-closed behaviors the plan cared most about all hold under test: never overwrite without `--overwrite`, no orphaned `.part` files, a dry-run that can't clobber, and exit 2 on collisions. Findings 1 and 2 are the only ones I'd fix before calling the tool "robust for batch use", and each is a few lines. Findings 3–7 can wait. Before a public release, the user should still do the manual Resolve import (Verification #9) and one real Ctrl+C. `git init` and publishing remain user-gated, as the plan requires.

## Verification performed

- `python -m unittest -v` (global 3.11.9 and `.venv`) → 20 tests, OK (skipped=1, the smoke test).
- `$env:MTS_SMOKE='1'; .venv\Scripts\python.exe -m unittest tests.test_mts_to_dnxhr.SmokeTest -v` → OK in 2.9 s. HQX MOV with s16 and HQX MXF with s24 were both written, both bars rendered, and no `.part` file remained.
- `python mts_to_dnxhr.py --help` → every flag is present, with defaults `dnxhr_hqx`, `mov` and `16`, the four examples, and the exit codes.
- `python mts_to_dnxhr.py samples/ --dry-run` → exit 0. The command contains `-n -i` and `-c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000`, and the output is `...\samples_dnxhr\01 American Landscape.mov`. No directory was created.
- The same run with `--overwrite --deinterlace` → `-y -i`, and yadif present with no `-field_order`.
- `does-not-exist` → exit 2. A `.txt` file → exit 2 with "not an .MTS/.M2TS file", and no traceback.
- **Full encode (Verification #5)** to a scratch dir: exit 0 in 28 s, producing a 4.66 GB file (~4.7 GB, as the plan predicted). The output is DNXHR HQX `yuv422p10le` at 1920×1080, `30000/1001`, 5040 frames, `pcm_s16le` 48 kHz stereo, 168.192 s, `field_order=unknown` (as documented). No `.part` file remained. The file was deleted afterwards.
- Harness (scratch dir, removed afterwards):
  - Simulated Ctrl+C → exit 130, no files left, no `ffmpeg.exe` in `tasklist`.
  - Encode, then a re-run → `skipped 1`, exit 0. With `--overwrite` → re-encoded, exit 0.
  - A corrupt `junk.MTS` → `failed 1`, exit 1, no `.part` (an empty dir was left; see finding 6).
  - A video-only progressive `.m2ts` with `--deinterlace` → printed the "progressive; skipping deinterlace" note, exit 0, DNXHR HQX at 25/1.
  - A file named `-y.MTS` → encoded correctly to `-y.mov` (the absolute path protects against flag injection).
- Bitrate spot-check (3 s): LB 45.2, SQ 145.3, 444 440.0 Mb/s. These match the README and plan tables.
- Grep gates: no `shell=True`, no `match`, no runtime `X | Y`, and no `180 Mb`/`3.8 GB` in the README.
- `.gitignore`: the pattern check in a throwaway temp git repo (outside the project) passed. The project itself is still not a git repo, as the plan requires.
- Python 3.9 syntax: `ast.parse(feature_version=(3,9))` passes for both files.
