# Feedback: MTS/M2TS → DNxHR CLI for DaVinci Resolve
*Loop signal: revise*

*Plan: [mts-to-dnxhr-cli-claude-2026-11-06.md](mts-to-dnxhr-cli-claude-2026-11-06.md) · Reviewer: grok · 2026-11-06*

## Verdict
ship-after-fixes — Correct the HQX disk figure and make the dry-run command honor the no-overwrite rule; the encode design matches this sample.

## Summary
The plan is implementable as a single root script: real paths, pure functions, argv subprocesses, temp-file rename, and a probe table that matches the file on disk. A one-second run of the planned HQX/MOV command on `samples/01 American Landscape.MTS` succeeded with `DNXHR HQX`, `yuv422p10le`, `30000/1001`, 30 frames, `dup_frames=0`, and stereo `pcm_s16le`. Two written claims are wrong enough to fix before coding: the 180 Mb/s / 3.8 GB disk warning, and a dry-run argv that includes `-y` on the final path.

## Blocking
Must fix or resolve before implementation (missing gates, wrong paths, unsafe approach, scope bombs, contradicted repo facts).

- **HQX size in Constraints is contradicted.** The plan says HQX at 1080p29.97 is about 180 Mb/s and about 3.8 GB for the 168.192 s sample. A 1 s encode with the plan's codec args (`-c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le`, 1920×1080, `30000/1001`) reported video `bit_rate=219980979` (~220 Mb/s). With stereo PCM s16 (1.536 Mb/s) that is about **4.66 GB** for this sample. The same video rate was measured for `dnxhr_hq`. Video-only 1 s encodes: LB **45.2 Mb/s**, SQ **145.3 Mb/s**, 444 **440.0 Mb/s**. Step 10's bitrate / GB/min table and the disk warning need these rates (or a fresh measurement in step 9). HQ is not a smaller file than HQX on this FFmpeg. Nothing in Verification checks the README numbers, so the 180 Mb/s figure would ship.

- **Dry-run `-y` breaks the overwrite rule.** Constraints forbid replacing an existing output unless `--overwrite` is set, and forbid a half-written final. Step 5's `build_command` template always includes `-y`, and the dry-run notes say to print that command with the **final** path so it can be pasted and run. A paste then overwrites the final in place. The same step says `-y` only targets the `.part` file and that overwrite is decided in step 6. Those instructions cannot all be true. Resolve them in the plan: the runner passes the `.part` path and may use `-y` on that temp file, then `os.replace` only after exit 0 and a non-zero size; the dry-run string uses the final path and includes `-y` only when `--overwrite` is set. Add a unit test that a dry-run with an existing destination omits `-y` unless `--overwrite` is passed.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

- **`parse_progress_line` must ignore non-numeric values.** On the planned argv, FFmpeg 8.0.1's first `-progress` block is `out_time_us=N/A` / `out_time_ms=N/A`, then later real values (`out_time_us=967633` with `out_time_ms` the same number). Both keys are microseconds; the plan is right about units. A literal `int()` of `N/A` throws. Step 6 only deletes `.part` on a non-zero ffmpeg exit or Ctrl+C, so a parser exception can leave the temp file. Specify: non-numeric → `None`; any exception in the read loop still deletes `tmp_dst` and closes the stderr temp file.

- **Field order does not survive, and Verification item 9 should say so.** `-field_order tt` still produced MOV `field_order=unknown`. MXF reported `field_order=progressive` both with and without `-field_order tt`. Step 9.2 already allows a README note; write that note as the expected outcome, not an open branch: for 1080i, set Resolve Clip Attributes → Field Dominance → Upper, or pass `--deinterlace`. Verification item 9 should require picture, sound, 1920×1080, and `30000/1001`. It should not require the file to carry `tt` by itself.

- **Step 9's other branches already came out clean on this machine.** Keep the checks, and record the likely result so a fallback is not implemented "just in case": default (no `-r`) was `avg_frame_rate=30000/1001`, `nb_frames=30` for `-t 1`, `dup_frames=0`. `yadif=mode=send_frame:parity=auto:deint=interlaced` changed frame 10 (MD5 `e28a91b0…` vs `9fc05c4a…`) and stayed at 30 frames / `30000/1001`. MXF OP1a accepted stereo `pcm_s16le` and `pcm_s24le`. The mono-track MXF fallback and the `-r` fallback should stay conditional on a failed re-check.

- **Progress total ignores `--duration`.** The inner bar is given the probed duration (~168 s) even when `-t 3` stops the encode. Use `min(probe, opts.duration)` when `--duration` is set.

- **`ValueError` from `find_inputs` is not wired to exit 2.** Step 3 raises; Verification item 7 expects exit 2 and a clear message for `samples/notes.txt`. Step 7's flow should catch that and return 2 without a traceback.

- **The four "request" examples are not in the repo.** Flags are listed; the examples step 7 and step 10 must copy are not. Inline those four commands in the plan.

- **Probe parsing has no unit fixture.** ffprobe's JSON `duration` is the string `"168.192000"`. The audio stream has `avg_frame_rate` `0/0` and no `field_order`. Lock "first video stream" with a fixture so a bad parse is not only caught by the manual probe.

## Nits
Wording, structure, minor clarity.

- Verification item 4 should say the dry-run output path is absolute and ends with `samples_dnxhr\01 American Landscape.mov`. The constraint requires absolute paths; the check text looks relative.
- Open questions 1–3 already pick defaults (MIT, 16-bit, `dnxhr/` and `<folder>_dnxhr/`). They are not implementation gates.
- Declare `--duration` as `type=float`. The smoke test and step 9 only need integers.
- Smoke assertions should expect `pcm_s16le` on the first run and `pcm_s24le` on the second, not either codec on both.
- `subprocess.list2cmdline` leaves `0:a?` unquoted. PowerShell passed it through in this directory; quote it in `format_command` so a cwd glob cannot eat it.
- Delete `samples/_check` after step 9 records results. Those encodes are large and only `*.mov` / `*.mxf` are gitignored.
- Sample length is 335,646,720 bytes (335.6 MB). The plan's "335 MB" is fine.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- Repo layout matches the plan: no `.git`; only `plans/` and `samples/`. Sample file is `samples/01 American Landscape.MTS`.
- Python 3.11.9. FFmpeg/ffprobe 8.0.1 Gyan full build on PATH via WinGet. `shutil.which` would find `ffmpeg.exe` and `ffprobe.exe`.
- Exact plan probe command: container `mpegts`, duration `168.192000`, start `0.522411`, video H.264 High 1920×1080 `yuv420p` SAR `1:1`, `field_order=tt`, `avg_frame_rate=30000/1001`, `r_frame_rate=60000/1001`, AC-3 48 kHz stereo. First decoded frames have `interlaced_frame=1`, `top_field_first=1`, PTS step ~1001/30000. No data stream.
- `ffmpeg -h encoder=dnxhd`: profiles `dnxhr_lb|sq|hq|hqx|444`; pixel formats `yuv422p`, `yuv422p10le`, `yuv444p10le`, `gbrp10le`. Muxers include `mov`, `mxf`, `mxf_opatom`.
- yadif help: `deint` default is `all`; the plan's explicit `deint=interlaced` still deinterlaced this file because frames are flagged.
- Planned 1 s HQX/MOV command exited 0. Output profile string is `DNXHR HQX` (the smoke test's expected text). `pcm_s24le` stereo in MXF exited 0. `-map 0:a?` plus `-c:a pcm_s16le` on a video-only lavfi source exited 0.
- `-progress` on FFmpeg 8: `out_time_us` and `out_time_ms` are both microseconds (`1000000` at 1.0 s).
- Not checked: DaVinci Resolve import, Ctrl+C exit 130, a full 168 s encode, Python 3.9 syntax on a 3.9 interpreter, 1440×1080 anamorphic, spanned clips, or a clip with no audio inside an `.MTS`.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- Replace the Constraints disk sentence with measured 1080p29.97 video rates and sample sizes (PCM s16 stereo included): LB 45 Mb/s (~1.0 GB), SQ 145 Mb/s (~3.1 GB), HQ 220 Mb/s (~4.7 GB), HQX 220 Mb/s (~4.7 GB), 444 440 Mb/s (~9.3 GB). Point the README table at the same numbers.
- Pre-write the step 9 results above into a short "Verified on FFmpeg 8.0.1" note so the README interlacing section and the `-r` / MXF-mono fallbacks stay conditional.
- In step 7, state that `main` returns 130 on `KeyboardInterrupt` after `run_ffmpeg` has terminated ffmpeg and deleted `.part`.

## Confidence
high — Probe table, encoder help, and the planned argv were run on this sample with the FFmpeg the plan names; Resolve itself was not opened.
