# MTS Remux Mode — Implementation Evaluation

*Claude Code turns used: 11 / max 100*

*Evaluator: claude · 2026-11-10 · Round 2 (confirm) · Reviews the implemented `remux-mode-grok-2026-11-10.md` against the working tree.*

## Verdict: Ready to ship. Both Low findings from round 1 are fixed, and no new Critical, High, or Low issues turned up.

The round-1 hwaccel wording problem is fixed in README, `--help`, the CLI header, the remux command, and the GUI. The latent profile/container mismatch is now blocked in core by `Options.__post_init__`, and a new test covers it. The plan gates pass: 94 tests pass with and without FFmpeg on PATH. The remux dry-run shows copy + AAC + mp4. The default DNxHR command is unchanged. A real 8-second remux produced a clean H.264 + AAC MP4. What remains is Noted or Trivial. One item is a deliberate departure from the plan text: the GUI now disables GPU decode in remux mode, where the plan said "GPU decode / jobs still apply". The departure is technically correct and documented.

## Scorecard

| Dimension | Score (1–5) | Notes |
|-----------|-------------|-------|
| Completeness vs plan scope | 5 | All 4 steps landed. Nothing out of scope was added (no ProRes, no AC-3 copy, no H.264 re-encode, no rename). |
| Contract fidelity | 4 | DNxHR default is byte-identical to HEAD, and the remux shape matches the plan. One deliberate departure: the plan says remux should keep `-hwaccel` / GPU decode, but the implementation drops it. That is correct, because `-hwaccel` does nothing with `-c:v copy`, and it is documented. |
| Verification honesty | 5 | 94 tests pass, with and without FFmpeg. The test that previously locked in `-hwaccel cuda` was flipped to `assertNotIn("-hwaccel")`. The help test now guards against the old false wording. A real smoke run was probed with ffprobe. |
| Finding severity | 5 | No Critical, High, or Low findings are open. |
| Merge readiness | 5 | Safe to merge as-is. |

**Overall completeness:** 24/25 · **percent:** 96%
**Band:** ship
**Open findings:** Critical 0 · High 0 · Low 0 · Trivial/Noted 7

## Loop signal

**Loop signal:** ship-now
**Signal rationale:** Both round-1 Lows are fixed, with tests. Everything still open is Noted or Trivial, and none of it needs a fix pass before merge.

## Round-1 remediation check

| Round-1 finding | Status | Evidence |
|---|---|---|
| 1. hwaccel docs and help said it affects audio decode *(Low)* | **Fixed** | `README.md:81` and `:134` now say "has no effect with `--profile remux`". The `--help` text (`mts_to_dnxhr.py:893`) says "-hwaccel does not decode audio". The remux command leaves out `-hwaccel` (`mts_to_dnxhr.py:337-339`). The CLI header prints `hwaccel: unused` (`:927`). The GUI disables **GPU decode** in remux mode (`mts_to_dnxhr_gui.py:1748-1750`), and `options_for(mode="remux")` forces `hwaccel="off"`. Tests: `assertNotIn("-hwaccel", cmd)` in the core, dry-run, and GUI tests; `assertNotIn("affects audio decode", help_text)`. |
| 2. Core did not enforce the remux ↔ mp4 pairing *(Low)* | **Fixed** | `Options.__post_init__` (`mts_to_dnxhr.py:82-88`) raises `ValueError` for remux+mov, remux+mxf, and dnxhr+mp4. It also runs through `dataclasses.replace`, which the GUI's `options_for` and `_parser_defaults` rely on. Test: `test_options_require_remux_mp4_pairing`. |
| 3. AAC 192k for 5.1 *(Noted)* | Unchanged, as accepted | Locked by the plan. |
| 4. Deinterlace stays ticked while disabled *(Noted)* | Unchanged, now also applies to GPU decode | Tested on purpose (`assertTrue(self.app.gpu_decode_var.get())` while disabled). |
| 5. Window-size drive-by *(Noted)* | Unchanged | 700 / 620 px. |
| 6. Typed other-mode default treated as auto *(Noted)* | Unchanged | `_note_export_edit` (`mts_to_dnxhr_gui.py:1541`). |
| 7. Two-mode assumption in `_on_mode_changed` *(Trivial)* | Unchanged | `mts_to_dnxhr_gui.py:1555`. |

## Completeness & accuracy by workstream

| Workstream | Status | Evidence |
|---|---|---|
| **Core: `remux` profile + `mp4` container** | Complete | `CONTAINERS` gains `mp4`; `REMUX_PROFILE` and `PROFILE_CHOICES` added (`mts_to_dnxhr.py:35-37`). |
| **Core: `build_command` remux branch** | Complete | `-fflags +genpts` goes before `-i`. Then `-c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart -f mp4`, with an early return. No `-vf`, `-pix_fmt`, `-field_order`, `-profile:v`, or PCM. No `-hwaccel` (a round-2 change). |
| **Core: profile/container invariant** | Complete (round-2 addition) | `Options.__post_init__`. |
| **Core: `default_output_dir(profile)`** | Complete | `mts_to_dnxhr.py:151`. Remux uses `remux` / `<name>_remux`; DNxHR is unchanged. Tested for both the file and folder forms. |
| **CLI validation and defaults** | Complete | `_apply_profile_args` (`:1046`) plus `_MarkSetAction` (`:788`). The rejection matrix was re-run and matches the plan (see Verification). |
| **CLI header / dry-run notes** | Complete | `audio: aac`, `hwaccel: unused`. ffprobe notes are skipped for remux. |
| **GUI mode control** | Complete | DNxHR HQX / Remux MP4 radiobuttons in Export settings, disabled while a batch runs. |
| **GUI options wiring** | Complete | `options_for(..., mode="remux")` → `profile="remux", container="mp4", deinterlace=False, hwaccel="off"`. `_start_batch` builds `opts` before `plan_outputs`, so `.mp4` destinations are planned. |
| **GUI estimate / summary / low-space text** | Complete | `size_ratio_for_mode` gives 1× (`:1918`). `summary_for_mode` and `low_space_detail` cover remux. The dialog no longer hard-codes "14×". |
| **GUI auto export-folder refresh** | Complete | `_auto_export_root` / `_note_export_edit` / `_on_mode_changed`. Tested both for the auto-default case and for a folder the user typed. |
| **GUI deinterlace (and GPU) disable** | Complete | `mts_to_dnxhr_gui.py:1748-1750`. |
| **README** | Complete | New "Remux to MP4" section, plus updates to output naming, `.part`, usage, flags, the desktop-app paragraph, the disk-estimate paragraph, and Limitations. The round-1 wording is corrected. |
| **Tests** | Complete | Core: command shape, pairing invariant, output dir, dry-run file and folder, rejection matrix. GUI: options, summary, ratio, mode switch, `_start_batch` remux path. |
| **Step 4 gate: `python -m unittest -v`** | Complete | `Ran 94 tests … OK (skipped=2)`, with and without FFmpeg. |

## Findings (ranked)

### 1. The GUI departs from the plan's "GPU decode / jobs still apply" for remux. *(Noted)*

The plan's GUI section said GPU decode still applies in remux mode, and its CLI section said "Keep `--hwaccel` optional … remux still decodes audio for AAC". The implementation disables the **GPU decode** checkbox in remux mode and drops `-hwaccel` from the remux command. That is the correct behavior: `-hwaccel` only selects a hardware video decoder, and with `-c:v copy` no video decoder is opened. This was the optional remediation from round 1. The departure is documented in `README.md:81,89,142` and the inline comment at `mts_to_dnxhr.py:337`. It is a plan-text deviation in the user's favor, not a regression.

**Remediation:** No action. Optionally note in the plan's disposition that its hwaccel premise was wrong.

### 2. `--hwaccel` is silently accepted with `--profile remux`, while `--deinterlace` and `--audio-bit-depth` are errors. *(Noted)*

`--profile remux --hwaccel off` (and any other value) exits 0. The header shows `hwaccel: unused`. The other two flags that don't apply are hard errors, so this is a slight inconsistency. However, the plan explicitly said to keep `--hwaccel` optional for remux, `--hwaccel` has a non-`off` default, and erroring on it would require a `_MarkSetAction` and would break scripts that pass `--hwaccel` globally. Accepting it is the friendlier choice.

**Remediation:** No action.

### 3. AAC at 192 kb/s is the total for all channels, so a 5.1 source gets about 32 kb/s per channel. *(Noted, carried over)*

The plan locked this in. The README says "Channel count follows the source" but does not spell out what that means for bitrate.

**Remediation:** No action in this plan. A possible follow-up is to scale the bitrate by channel count.

### 4. The disabled Deinterlace and GPU decode checkboxes keep their ticks in remux mode. *(Noted, carried over)*

This is intentional and tested: the settings survive a switch back to DNxHR. `options_for` ignores both values in remux mode. A disabled checkbox that shows a tick can still mislead a little.

**Remediation:** No action.

### 5. `README.md:132` still calls each `--jobs` job "a full convert (decode + DNxHR encode)". *(Trivial)*

In remux mode a job is a stream copy plus an AAC encode. The GUI paragraph's "each stream already includes decode and encode for that clip" has the same DNxHR slant. Users will not be misled about anything they can act on.

**Remediation:** Optional one-word fix, for example "(decode + encode, or copy + AAC for remux)".

### 6. In `options_for`, `hwaccel` is computed before the remux early return. *(Trivial)*

`mts_to_dnxhr_gui.py:446` computes `hwaccel` from `gpu_decode`. The remux branch then hard-codes `"off"`, so in remux mode the computed value is never used. It is harmless.

**Remediation:** No action. Optionally move the line below the remux branch.

### 7. Two-mode assumptions in `_on_mode_changed`, plus the window-size and auto-folder edge cases. *(Trivial/Noted, carried over)*

These are carried over from round 1 as findings 5–7. None changed, and none affects correctness with two modes.

**Remediation:** No action now. Revisit if a third mode is added.

## Net assessment

Merge-ready. Every workstream in the plan landed, and both round-1 Lows are fixed with tests that guard the corrected behavior instead of the old one. The DNxHR default is unchanged: the default dry-run still emits `-hwaccel cuda … -field_order tt -c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000 -f mov` into `dnxhr/`. Core now rejects mismatched profile/container pairs from any caller, not only the CLI and GUI. Nothing needs fixing before merge. Findings 5 and 6 are optional one-liners.

## Verification performed

- `.venv/Scripts/python.exe -m unittest` → `Ran 94 tests in 1.1s OK (skipped=2)`. That is up from 93 in round 1 because of the new `test_options_require_remux_mp4_pairing`. The `failed: … denied` and `Invalid data` lines are expected output from negative-path tests.
- Same suite with `PATH=/usr/bin` (`shutil.which('ffmpeg')` → `None`) → `OK (skipped=2)`. This meets the "Unittests pass without FFmpeg" gate.
- `mts_to_dnxhr.py "samples/01 American Landscape.MTS" --profile remux --dry-run` → exit 0. Header: `profile: remux`, `container: mp4`, `audio: aac`, `output: …\samples\remux`, `hwaccel: unused`. Command: `ffmpeg … -n -fflags +genpts -i "…MTS" -map 0:v:0 -map "0:a?" -map_metadata 0 -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart -f mp4 "…\remux\01 American Landscape.mp4"`. No `-hwaccel`, DNxHR, PCM, or yadif.
- Default dry-run → `-hwaccel cuda … -field_order tt -c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000 -f mov` into `samples\dnxhr\…mov`. Unchanged.
- CLI matrix with `--profile remux`: `--container mov` → 2, `--container mxf` → 2, `--deinterlace` → 2, `--audio-bit-depth 16` → 2, `--container mp4` → 0, `--hwaccel off` → 0. DNxHR with `--container mp4` → 2. All error messages are clear.
- Real smoke: `--profile remux --duration 8 -o <tmp>` → `wrote …mp4`, `converted 1`, exit 0, 15,516,231 bytes. `ffprobe`: `h264` start 0.000, `aac` 48000 Hz 2ch start 0.000, format `mov,mp4,…`, duration 8.041 s.
- Spot-checks: `Options(` is constructed only at `mts_to_dnxhr.py:1120` (after `_apply_profile_args`) and `mts_to_dnxhr_gui.py:422` (parser defaults: dnxhr_hqx/mov). `dataclasses.replace` in `options_for` runs `__post_init__`, and the remux branch sets `container="mp4"`, so the GUI cannot trip the guard. The GUI has no other `.container` / `DEFAULT_OPTIONS.container` lookups besides `OUTPUT_SUMMARY`, which is for the DNxHR label only.
