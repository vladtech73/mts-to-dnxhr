# Feedback: MTS/M2TS → DNxHR CLI for DaVinci Resolve
*Loop signal: satisfied*

*Plan: [mts-to-dnxhr-cli-claude-2026-11-06.md](mts-to-dnxhr-cli-claude-2026-11-06.md) · Reviewer: grok · 2026-11-06*

## Verdict
solid-with-nits — Round-1 blockers are fixed in the plan, and the encode path matches this sample and FFmpeg 8.0.1.

## Summary
The disk table, dry-run `-n`/`-y` split, progress `N/A` handling, field-order README note, probe fixture, and exit-2 wiring are all in the steps an implementer would follow. Probe values, output paths, and a trailing `-progress pipe:1` on FFmpeg 8.0.1 match what the plan tells the runner to do. What remains is edge-case wording: the smoke test's extension check, and `min()` when probe duration is missing.

## Blocking
None.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

- **Smoke selection should use `suffix.lower()` / `is_input_file`.** The sample on disk is `samples/01 American Landscape.MTS`. Step 8 says "the first `.mts`/`.m2ts`". A case-sensitive suffix check finds nothing, `skipUnless` still lets `python -m unittest` exit 0, and Verification item 2's "against the sample" is easy to miss in a skip line.
- **Bar total when duration did not parse.** Step 4 sets `ProbeInfo.duration` to `None` and wants an elapsed bar. Step 6 then says `duration = min(probed duration, opts.duration)` whenever `--duration` is set. `min(None, 3.0)` raises, so `-t` never runs. When the probe duration is `None`, use `opts.duration` as the total.

## Nits
Wording, structure, minor clarity.

- The step 8 fixture says "copied from the sample's real probe" and also requires audio before video. Real `ffprobe -of json` lists video then AC-3 under top-level `streams`, and repeats them in `programs[0].streams`. Parse top-level `streams`. Keep audio-first as a hand-built reorder so `0/0` cannot be taken as the frame rate.
- Step 3 shows non-MTS skips "in the summary." Step 7's header has that count, and the summary `skipped` count is existing outputs. Verification item 6 expects `skipped 1` on a re-run. Keep the two counters separate.
- Step 10's done-when runs every README command successfully. `./footage/` and `PRIVATE/AVCHD/BDMV/STREAM` are not in this tree, so those dry-runs exit 2. Verification items 1–8 are the live checks; the footage lines are examples.
- The dry-run unit test patches `find_tool` to `None`. Print the literal `ffmpeg` in that command.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- Repo has no `.git`. Visible files are the plan, round-1 feedback, and `samples/01 American Landscape.MTS` (335,646,720 bytes).
- Python 3.11.9. FFmpeg and ffprobe 8.0.1 Gyan full build.
- `Path("samples").resolve()` maps to `D:\GitHub\mts-to-dnxhr\samples_dnxhr`. The file input maps to `samples\dnxhr\01 American Landscape.mov`. `Path("./footage/").name` is `footage`.
- ffprobe JSON: `format.duration` `"168.192000"`, `start_time` `0.522411`, video `h264` 1920×1080 `field_order=tt` `avg_frame_rate=30000/1001` `r_frame_rate=60000/1001`, then AC-3 48 kHz stereo with `avg_frame_rate=0/0` and no `field_order`. Same objects under `programs[0].streams`.
- `subprocess.list2cmdline` emits `0:a?` without quotes. The plan's extra quoting still matches that.
- FFmpeg 8.0.1 accepts `-progress pipe:1 -nostats` after the output file (lavfi, 0.5 s, exit 0) and writes `out_time_us=500000` / `out_time_ms=500000` to stdout.
- Constraints arithmetic matches the round-1 video rates plus 1.536 Mb/s stereo PCM s16 over 168.192 s (HQX ~4.66 GB, ~1.66 GB/min). Profiles were not re-encoded this round.
- Not re-run: full 168 s encode, Resolve import, Ctrl+C, Python 3.9, anamorphic, or a clip with no audio.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- In step 8, select the smoke sample with `is_input_file` so `.MTS` is included.
- In step 6, define the bar total as `opts.duration` when the probed duration is missing, otherwise `min(probed, opts.duration)` when `--duration` is set.

## Confidence
high — The revised text matches a fresh probe of this sample and a trailing-progress check on the named FFmpeg; Resolve was not opened.
