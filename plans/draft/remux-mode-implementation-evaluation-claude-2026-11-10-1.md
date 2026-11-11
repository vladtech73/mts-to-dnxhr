# MTS Remux Mode — Implementation Evaluation

*Claude Code turns used: 15 / max 100*

*Evaluator: claude · 2026-11-10 · Reviews the implemented `remux-mode-grok-2026-11-10.md` against the working tree.*

## Verdict: Complete and correct. One cheap docs fix is left before merge.

Every workstream in the plan landed: core profile and CLI validation, GUI mode control, README, and tests. The default DNxHR HQX / `.mov` path is unchanged, the plan's dry-run and unit-test gates pass, and a real 8-second remux of the sample produced a clean H.264-copy + AAC MP4 with timestamps starting at 0. No Critical or High issues. The main defect is wording: README and `--help` say `--hwaccel` affects audio decode in remux mode. That is wrong. `-hwaccel` is a video-decoder option, so with `-c:v copy` it does nothing. There are also two small robustness and quality notes.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | All 4 steps done. Nothing out of scope was added (no ProRes, no AC-3 copy, no rename). |
| Contract fidelity | 5 | DNxHR default and output paths unchanged (verified by dry-run). Remux command matches the plan's shape exactly. |
| Verification honesty | 4 | 93 tests pass with and without FFmpeg on PATH. One new test locks in `-hwaccel cuda` on the remux command, which follows the misleading docs. |
| Finding severity | 4 | Low only. |
| Merge readiness | 4 | Safe to merge. A docs correction is recommended first. |

**Overall completeness:** 22/25 · **percent:** 88%
**Band:** nearly-done
**Open findings:** Critical 0 · High 0 · Low 2 · Trivial/Noted 5

## Loop signal

**Loop signal:** one-more-fix
**Signal rationale:** Only Low findings are open. A single small pass (fix the hwaccel wording and optionally add a profile/container guard in core) closes them.

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Core: `remux` profile + `mp4` container** | Complete | `mts_to_dnxhr.py:35-37` adds `mp4` to `CONTAINERS`, `REMUX_PROFILE`, `PROFILE_CHOICES`. |
| **Core: `build_command` remux branch** | Complete | `mts_to_dnxhr.py:331-357`. `-fflags +genpts` goes before `-i` (input option, correct). Then `-c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart -f mp4`. No `-vf`, `-pix_fmt`, `-field_order`, or PCM. The function returns early, so the DNxHR branch is not touched. |
| **Core: `default_output_dir(profile)`** | Complete | `mts_to_dnxhr.py:143-154`. Remux uses `remux` / `<name>_remux`. The default argument keeps existing callers on `dnxhr`. |
| **CLI validation and defaults** | Complete | `_apply_profile_args` (`mts_to_dnxhr.py:1034`) plus `_MarkSetAction` tell an explicitly passed flag apart from a default. Remux with `--container mov` → exit 2. `--deinterlace` → 2. `--audio-bit-depth 16` (even the default value, if passed) → 2. `--container mp4` → 0. A DNxHR profile with `--container mp4` → 2. Output folder: `main` passes `args.profile` to `default_output_dir`. |
| **CLI header / dry-run notes** | Complete | Header prints `audio: aac`. The ffprobe/field-order notes are skipped for remux (`mts_to_dnxhr.py:938-943`). |
| **GUI mode control** | Complete | Radiobuttons **DNxHR HQX** / **Remux MP4** in Export settings (`mts_to_dnxhr_gui.py` mode row). They are disabled while a batch runs (`_set_running_ui`). |
| **GUI options wiring** | Complete | `options_for(..., mode="remux")` → `profile="remux", container="mp4", deinterlace=False`. `_start_batch` now builds `opts` before `plan_outputs`, so `.mp4` destinations are planned (`mts_to_dnxhr_gui.py:1897-1904`). |
| **GUI estimate / summary / low-space text** | Complete | `size_ratio_for_mode` gives 1× for remux (`:1917`). `summary_for_mode` and `low_space_detail` cover remux, and the warning no longer hard-codes "14×". |
| **GUI auto export-folder refresh** | Complete | `_auto_export_root` + `_note_export_edit` + `_on_mode_changed` (`:1540-1566`). The folder is rewritten only while it still equals the previous mode's auto default. Folders the user typed or browsed to are kept (tested). |
| **GUI deinterlace disable** | Complete | `_update_buttons` disables the checkbox in remux mode (`:1747`). |
| **README** | Complete (one inaccuracy) | New "Remux to MP4" section, plus updates to output naming, `.part`, the GUI paragraph, and Limitations. The hwaccel wording is wrong; see Finding 1. |
| **Tests** | Complete | 4 core tests + 2 GUI tests + extra assertions (output dir, parser `*_set` defaults, `estimate_needed_bytes(ratio=1)`, `_start_batch` remux path). |
| **Step 4 gate: `python -m unittest -v`** | Complete | `Ran 93 tests … OK (skipped=2)`, both with FFmpeg on PATH and with it removed. |
| **Optional sample smoke** | Done by evaluator | Real remux works (see Verification). |

## Findings (ranked)

### 1. Docs and help say `--hwaccel` affects audio decode in remux mode. It does not. *(Low)*

- `README.md:81`: "`--hwaccel` still selects how FFmpeg decodes audio for the AAC encode."
- `README.md:134`: "hardware decode only applies to the audio."
- `mts_to_dnxhr.py:884` (`--help`): "this only affects audio decode."

`-hwaccel` only selects a hardware **video** decoder. With `-c:v copy` no video decoder is opened, and audio decoding is never hardware-accelerated. So in remux mode the flag does nothing. The plan's own reasoning ("remux still decodes audio for AAC") is where this came from. The implementation turned that into a false user-facing claim. The GUI also leaves **GPU decode (hardware)** enabled in remux mode, and the CLI header prints `hwaccel: cuda`. Both suggest the setting does something. The plan said "GPU decode / jobs still apply", so leaving it enabled matches the plan, but the docs should not state a false reason for it. The harm is small: users may tick or untick the checkbox, or pass `--hwaccel off`, expecting a change that never happens.

**Remediation:** Change README lines 81 and 134 and the help text to say `--hwaccel` has no effect with `--profile remux`, because the video is copied and audio decode never uses the GPU. Optionally go further: leave `-hwaccel` out of the remux command, and disable the GPU checkbox in remux mode the same way deinterlace is disabled. If you do that, update `test_remux_copies_video_and_encodes_aac`, which currently asserts `cmd[cmd.index("-hwaccel") + 1] == "cuda"`.

### 2. Core `build_command` does not enforce the remux ↔ mp4 pairing. *(Low)*

The remux branch always writes `-f mp4` and ignores `opts.container`. The DNxHR branch accepts `container="mp4"`. Only the CLI (`_apply_profile_args`) and the GUI (`options_for`) guard the pairing. A library caller of `convert_one` / `run_batch` (the GUI is one) with `Options(profile="remux", container="mov")` would get MP4 bytes in a `.mov` file. With `Options(profile="dnxhr_hqx", container="mp4")` it would get DNxHR muxed into MP4, which Resolve handles poorly. No current caller does this, so the risk is latent.

**Remediation:** Add a cheap guard in `build_command` (or an `Options.__post_init__`) that raises `ValueError` when `(profile == "remux") != (container == "mp4")`, plus a test for it.

### 3. AAC at 192 kb/s is the total bitrate, so 5.1 sources get about 32 kb/s per channel. *(Noted)*

`-b:a 192k` is fixed and the channel count follows the source. Many AVCHD cameras record 5.1 AC-3 at 384–448 kb/s. Squeezing that into 192 kb/s across 6 channels is audibly lossy. The plan locked in 192k, so this is not a deviation, and the sample used here is stereo. The README says "Channel count follows the source" but does not spell out what that means for bitrate.

**Remediation:** Optional. Add one README sentence, or a later follow-up to scale the bitrate by channel count (for example 384k for 5.1). Out of scope for this plan.

### 4. The deinterlace checkbox stays ticked while disabled in remux mode. *(Noted)*

This is intentional and tested (`test_remux_mode_refreshes_auto_folder_and_disables_deinterlace` asserts `deinterlace_var` stays `True`), so the setting survives a switch back to DNxHR. `options_for` forces `deinterlace=False` for remux, so the behavior is correct. A disabled checkbox showing a tick can still mislead a little.

**Remediation:** No action.

### 5. Drive-by window-size change. *(Noted)*

The default height went from 660 to 700 and the minimum from 580 to 620, and a `TRadiobutton` style was added. Both are justified by the new mode row and documented in the comment. They are acceptable, but they go beyond what the plan listed.

**Remediation:** No action.

### 6. Auto-folder tracking treats a typed-in "other mode" default as automatic. *(Noted)*

`_note_export_edit` keeps `_auto_export_root` while the entry matches *either* the dnxhr or the remux default. If a user in remux mode deliberately types the `dnxhr` default path, the app still treats it as auto. This is an edge case and harmless: mode switches only rewrite the path when it equals the *previous* mode's default.

**Remediation:** No action.

### 7. `_on_mode_changed` assumes there are exactly two modes. *(Trivial)*

`previous = "remux" if mode != "remux" else "dnxhr"` is correct today but would break silently if a third mode were added. Tracking the last mode in an attribute would be sturdier.

**Remediation:** No action now. Revisit if a third mode is added.

## Net assessment

This is safe to merge. The implementation is faithful to the plan, and no DNxHR behavior changed. The default dry-run command is byte-for-byte what HEAD produced: `-field_order tt -c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000 -f mov`. The CLI validation is careful: `_MarkSetAction` correctly catches an explicitly passed default value. Fix before merge: the hwaccel wording (Finding 1), which is a few lines. Worth doing in the same pass if convenient: the core profile/container guard (Finding 2). Everything else can wait or needs no action.

## Verification performed

- `.venv/Scripts/python.exe -m unittest` → `Ran 93 tests in 1.1s OK (skipped=2)`. The "failed: … denied" and "Invalid data" lines in the output are expected log lines from negative-path tests.
- Same suite with `PATH=/usr/bin` (`shutil.which('ffmpeg')` → `None`) → `Ran 93 tests … OK (skipped=2)`. This meets the plan's "Unittests pass without FFmpeg" gate.
- `mts_to_dnxhr.py "samples/01 American Landscape.MTS" --profile remux --dry-run` → exit 0. Header shows `profile: remux`, `container: mp4`, `audio: aac`, output `samples\remux`. Command: `-hwaccel cuda -fflags +genpts -i … -map 0:v:0 -map "0:a?" -map_metadata 0 -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart -f mp4 "…\remux\01 American Landscape.mp4"`. No DNxHR, PCM, or yadif.
- Default dry-run (no `--profile`) → `-c:v dnxhd -profile:v dnxhr_hqx … -f mov` into `samples\dnxhr\…mov`. Unchanged.
- CLI rejection matrix: remux + `--container mov` → 2; remux + `--deinterlace` → 2; remux + `--audio-bit-depth 16` → 2; remux + `--container mp4` → 0; DNxHR + `--container mp4` → 2. All print the expected messages.
- Real smoke: `--profile remux --duration 8 -o <tmp>` → `wrote …mp4`, exit 0, 15.5 MB. `ffprobe` of the output: `h264` start 0.000, `aac` 48000 Hz 2ch start 0.000, duration 8.04 s. Source: `h264` `field_order=tt` + `ac3` 2ch.
- Spot-checks: `convert_one` / `_bar_total` / `.part` naming have no profile-specific lookups (`PROFILES[` and `AUDIO_CODECS[` appear only in the DNxHR branch and in the header's non-remux branch). `clear_all` leaves the export folder and auto-root as they were, which is consistent with pre-existing behavior.
