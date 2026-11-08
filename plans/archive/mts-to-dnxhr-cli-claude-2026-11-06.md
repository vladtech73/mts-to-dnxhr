# MTS/M2TS → DNxHR CLI for DaVinci Resolve

*Author: claude · 2026-11-06*

## Goal

A small open-source Python CLI, `mts_to_dnxhr.py`, run from the repo root, that converts AVCHD `.MTS` / `.M2TS` clips (one file or a whole folder, optionally recursive) into DNxHR intermediates that DaVinci Resolve imports, scrubs, and plays back reliably, audio included.

Success looks like:

- `python mts_to_dnxhr.py "samples/01 American Landscape.MTS"` produces `samples/dnxhr/01 American Landscape.mov`. It is DNxHR HQX (`yuv422p10le`) with 48 kHz PCM audio, at the same resolution, frame rate and duration as the source, and it imports into Resolve with picture and sound.
- Folder mode (`./footage/`, `--recursive`), every flag in the request, `--dry-run`, and the progress bars all behave as the README says.
- Unit tests run with no FFmpeg installed and no sample file present. An opt-in smoke test runs against the real sample in `samples/`.

## Constraints

- **Python 3.9+**. Stdlib plus `tqdm` only. Write 3.9-safe syntax: no `match`, no runtime `X | Y` unions. `from __future__ import annotations` and `Optional[...]` are fine.
- **FFmpeg/ffprobe are external binaries**, found on `PATH` via `shutil.which`. They are not bundled. Exit with a clear message if they are missing; `--dry-run` must still work without them (see step 5).
- **No `shell=True`.** Every FFmpeg/ffprobe call takes an argv list. Filenames contain spaces: the existing sample is `samples/01 American Landscape.MTS`. Pass absolute paths so a filename starting with `-` can never be read as a flag.
- **Never destroy source media.** The tool only reads inputs. It writes only under the output directory, and it never overwrites an existing output unless `--overwrite` is given.
- **No half-written outputs left behind.** Encode to a temp name, then rename on success. Delete the temp file on failure or Ctrl+C.
- **Large media must not be committed.** The sample is 335 MB (`samples/01 American Landscape.MTS`). `.gitignore` must exclude `*.mts`, `*.m2ts`, `*.mov`, `*.mxf` and the default output folders.
- **Disk usage is large.** Measured on FFmpeg 8.0.1 at 1920×1080 `30000/1001` (1 s encodes, video rate plus 1.536 Mb/s stereo PCM s16; sizes for the 168.192 s sample):

  | Profile | Video rate | Sample size | Per minute |
  |---|---|---|---|
  | `dnxhr_lb` | ~45 Mb/s | ~1.0 GB | ~0.35 GB |
  | `dnxhr_sq` | ~145 Mb/s | ~3.1 GB | ~1.1 GB |
  | `dnxhr_hq` | ~220 Mb/s | ~4.7 GB | ~1.66 GB |
  | `dnxhr_hqx` | ~220 Mb/s | ~4.7 GB | ~1.66 GB |
  | `dnxhr_444` | ~440 Mb/s | ~9.3 GB | ~3.3 GB |

  HQ is **not** smaller than HQX on this FFmpeg build. Document these numbers in the README; there is no hard preflight check. Step 9.5 re-measures them.
- The repo is **not a git repo yet**. It contains only `plans/draft/` and `samples/`. Do not run `git init`, commit, or publish without asking the user.

## Existing data / APIs

Facts gathered on 2026-11-06 in this environment:

- **FFmpeg 8.0.1** (Gyan full build, WinGet) is on PATH, with `ffprobe` next to it. **Python 3.11.9** is the global interpreter.
- `ffmpeg -h encoder=dnxhd`:
  - Profiles `dnxhr_lb`, `dnxhr_sq`, `dnxhr_hq`, `dnxhr_hqx`, `dnxhr_444`.
  - Pixel formats `yuv422p`, `yuv422p10le`, `yuv444p10le`, `gbrp10le`.
- Muxers available: `mov`, `mxf` (OP1a), `mxf_opatom`.
- Sample probe for `samples/01 American Landscape.MTS`:

  | Field | Value |
  |---|---|
  | Container | `mpegts` |
  | Duration | 168.192 s |
  | Video | H.264 1920×1080, `yuv420p` 8-bit |
  | Field order | `field_order=tt` (1080i, top field first) |
  | Frame rate | `avg_frame_rate=30000/1001`, `r_frame_rate=60000/1001` |
  | Audio | AC-3, 48 kHz, 2 channels |

  This sample covers the two main risks: interlaced handling, and an `r_frame_rate` that differs from `avg_frame_rate`.

- **Pre-checked on FFmpeg 8.0.1** (reviewer's 1 s encodes of this sample with the planned argv). Step 9 re-confirms these; fallbacks stay conditional on a failed re-check and are **not** implemented up front:
  - No `-r`: output `avg_frame_rate=30000/1001`, 30 frames for 1 s, `dup_frames=0`. The `-r` fallback is not needed.
  - Output profile string is `DNXHR HQX`, `pix_fmt=yuv422p10le`.
  - `yadif=mode=send_frame:parity=auto:deint=interlaced` does deinterlace (frames are flagged interlaced) and stays at 30 frames / `30000/1001`.
  - MXF OP1a accepts stereo `pcm_s16le` and `pcm_s24le`. The mono-track fallback is not needed.
  - Field order does **not** survive: `-field_order tt` gives MOV `field_order=unknown`; MXF reports `progressive` with or without it.
  - `-progress` emits `out_time_us=N/A` / `out_time_ms=N/A` in its first block, then numbers. Both keys are microseconds.
  - `-map 0:a?` with `-c:a pcm_s16le` on a video-only input exits 0.

## Approach

**A single-file script, `mts_to_dnxhr.py`, at the repo root, using argparse.** This matches the requested usage `python mts_to_dnxhr.py ...` exactly and needs no install step. The script is split into small pure functions (discovery, path mapping, command building) so tests can import it without running FFmpeg. Only `probe()` and `run_ffmpeg()` touch subprocesses.

Key decisions:

1. **Profile → pixel format table.**

   | Profile | Pixel format |
   |---|---|
   | `dnxhr_hqx` | `yuv422p10le` |
   | `dnxhr_hq` | `yuv422p` |
   | `dnxhr_sq` | `yuv422p` |
   | `dnxhr_lb` | `yuv422p` |
   | `dnxhr_444` | `yuv444p10le` |

   This matches the encoder's supported formats above. The default is `dnxhr_hqx` in `.mov`.

2. **Stream mapping.**
   - Video: `-map 0:v:0`.
   - Audio: `-map 0:a?`. This keeps every audio track and tolerates clips with no audio.
   - Data and subtitle streams are dropped (AVCHD often carries private data streams).
   - Audio is encoded as `pcm_s16le` or `pcm_s24le` with `-ar 48000`, and the channel count is kept.
   - Converting AC-3 to PCM is what fixes "missing audio" in Resolve.

3. **ffprobe is run once per file before encoding.** It gives:
   - the duration, used for the per-file progress bar;
   - `field_order`, used for deinterlacing and interlace flagging;
   - `avg_frame_rate`.

4. **Deinterlace** (`--deinterlace`).
   - When ffprobe reports `field_order` as `tt`, `bb`, `tb` or `bt`, add `-vf yadif=mode=send_frame:parity=auto:deint=interlaced`.
   - This produces one frame per frame, so the 29.97 rate is preserved.
   - For progressive sources, skip the filter and print a one-line note.
   - Field-rate output (`send_field`, 59.94p) is out of scope.

5. **Interlaced sources without `--deinterlace`.**
   - Keep the woven frames and pass `-field_order <probed value>` so the output carries the field order.
   - FFmpeg's DNxHR encoder may not accept interlaced-DCT flags. Do **not** pass `-flags +ildct`.
   - The pre-check shows the field order does **not** survive in MOV or MXF. Keep `-field_order` anyway (harmless, and may help other readers); the README tells users to set Clip Attributes → Field Dominance → Upper in Resolve for 1080i, or to use `--deinterlace`. Step 9.2 re-confirms.

6. **Frame rate.** Do not force `-r` by default; the pre-check already shows `30000/1001` with no duplicated frames. Step 9 re-confirms. **Fallback, only if that check fails:** pass `-r <probed avg_frame_rate>`.

7. **Progress and runner.**
   - Progress:
     - Outer `tqdm` bar: files.
     - Inner `tqdm` bar: seconds of media.
     - FFmpeg is run with `-nostdin -hide_banner -loglevel error -progress pipe:1 -nostats`, and the inner bar is driven by parsing `out_time_us=`.
   - Output handling:
     - stderr goes to a temp file, not a pipe, to avoid deadlock.
     - On failure, the tail of that log is shown.
     - Encode to `<stem>.<ext>.part` with an explicit `-f mov`/`-f mxf`, then `os.replace` it to the final name on success.
   - Overwrite flags: the runner always writes to the `.part` path with `-y` (the temp file is ours). The dry-run command targets the final path and carries `-y` only when `--overwrite` is set, otherwise `-n` (FFmpeg refuses to overwrite). A pasted dry-run command therefore never replaces an existing output unless the user asked for it.

8. **Output layout.**
   - Default output directory, when `--output` is omitted:
     - File input → `<file parent>/dnxhr/`.
     - Folder input → sibling `<parent>/<folder name>_dnxhr/`. A sibling keeps outputs out of the scanned tree.
   - Recursive mode mirrors subfolders under the output directory. This matters because AVCHD cards repeat names like `00000.MTS` across folders.
   - Filenames keep the original stem; only the extension changes.
   - Collisions: if two inputs map to the same output (e.g. `A.MTS` and `A.M2TS` in one folder), detect it during preflight, list the pairs, and exit with code 2 (fail closed).

9. **Exit codes.**

   | Code | Meaning |
   |---|---|
   | 0 | Every file converted or skipped (already exists) |
   | 1 | At least one file failed (the batch continues past failures) |
   | 2 | Usage or preflight error (bad path, no inputs, FFmpeg missing, collisions) |
   | 130 | Ctrl+C (FFmpeg is terminated and `.part` files removed) |

**Rejected alternatives:**

- **Click**: an extra dependency for no real gain at this size.
- **A package with `pyproject.toml` and a console script**: fine later, but the request centers on `python mts_to_dnxhr.py`. Listed under Out of scope.
- **`ffmpeg-python` or similar wrappers**: unmaintained, and they hide the exact argv we want to show in `--dry-run`.
- **Always deinterlacing 1080i**: changes the footage without being asked. Resolve can deinterlace too.

## Library / dependency choice

- `tqdm>=4.60` in `requirements.txt`. It is the only runtime dependency, chosen because it is mature and handles nested bars on Windows consoles.
- Tests use stdlib `unittest`, run with `python -m unittest`, so no test-only dependency is needed.

## Implementation

### 1. Scaffold repo hygiene files

Create:

- `requirements.txt`: one line, `tqdm>=4.60`.
- `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `*.part`, `*.mts`, `*.MTS`, `*.m2ts`, `*.M2TS`, `*.mov`, `*.mxf`, `dnxhr/`, `*_dnxhr/`, `converted/`.
- `samples/README.md`: says to drop one or more `.MTS`/`.M2TS` files here for local testing, that media files are gitignored and never committed, and that the smoke test (step 8) uses the first `.mts`/`.m2ts` it finds here.
- `LICENSE`: MIT, unless the user picks another license (see Open questions).

**Done when:** these files exist, and the existing sample matches the gitignore patterns. Check with `git check-ignore` after the user runs `git init`, or by reading the patterns.

### 2. `mts_to_dnxhr.py`: constants, data types, ffmpeg discovery

Create `mts_to_dnxhr.py` at the repo root with:

- A module docstring and `from __future__ import annotations`.
- `INPUT_EXTENSIONS = {".mts", ".m2ts"}`.
- `PROFILES = {"dnxhr_hqx": "yuv422p10le", "dnxhr_hq": "yuv422p", "dnxhr_sq": "yuv422p", "dnxhr_lb": "yuv422p", "dnxhr_444": "yuv444p10le"}`.
- `AUDIO_CODECS = {16: "pcm_s16le", 24: "pcm_s24le"}`.
- `CONTAINERS = {"mov": "mov", "mxf": "mxf"}`, mapping extension to the `-f` muxer.
- `INTERLACED_FIELD_ORDERS = {"tt", "bb", "tb", "bt"}`.
- `@dataclass(frozen=True) class Options`: `profile`, `container`, `audio_bit_depth`, `deinterlace`, `overwrite`, `duration: Optional[float]`.
- `@dataclass(frozen=True) class ProbeInfo`: `duration: Optional[float]`, `field_order: Optional[str]`, `avg_frame_rate: Optional[str]`, `has_audio: bool`, plus an `interlaced` property.
- `find_tool(name) -> Optional[str]`, wrapping `shutil.which`.

**Done when:** `python -c "import mts_to_dnxhr"` succeeds with no side effects. No work happens at import time.

### 3. Discovery and output-path mapping (pure functions)

In `mts_to_dnxhr.py`, add:

- `is_input_file(p: Path) -> bool`: `p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS`. This is case-insensitive, so `.MTS`, `.mts`, `.M2TS` and `.m2ts` all match. It skips AVCHD sidecars such as `.CPI`, `.MPL`, `.BDM`.
- `find_inputs(path: Path, recursive: bool) -> list[Path]`.
  - A file argument must have a valid extension; otherwise raise `ValueError` with a clear message.
  - A directory uses `iterdir()` (or `rglob("*")` when recursive) filtered by `is_input_file`.
  - Results are sorted for deterministic order.
  - Skipped non-MTS files are counted, not listed, and shown in the summary.
- `default_output_dir(input_path: Path) -> Path`: file → `parent / "dnxhr"`; directory → `parent / f"{name}_dnxhr"`. Resolve the path first, so `./footage/` with its trailing slash works.
- `output_path_for(src: Path, input_root: Path, out_dir: Path, container: str) -> Path`.
  - For directory input, keep `src.relative_to(input_root).parent` under `out_dir`.
  - For file input, place it directly in `out_dir`.
  - The extension becomes `.mov` or `.mxf`.
- `find_collisions(pairs) -> dict[Path, list[Path]]`, compared case-insensitively on Windows via `os.path.normcase`.

**Done when:** the step 8 unit tests for these functions pass, covering mixed-case extensions, non-MTS files, recursive mirroring, a trailing slash, and collision detection.

### 4. Probe

In `mts_to_dnxhr.py`, add:

- `probe(src: Path, ffprobe: str) -> ProbeInfo`.
  - Runs `ffprobe -v error -show_entries format=duration:stream=codec_type,field_order,avg_frame_rate -of json <abs src>` with `subprocess.run(..., capture_output=True, text=True, timeout=60, check=False)`.
  - Parse the result with `json`. Take the first video stream; `has_audio` is true if any stream has `codec_type == "audio"`.
  - Split into `probe()` (subprocess) and a pure `parse_probe_json(text: str) -> ProbeInfo`, so parsing is unit-testable.
  - Robustness:
    - `format.duration` arrives as a string (`"168.192000"`); convert with `float()`.
    - Audio streams carry `avg_frame_rate="0/0"` and no `field_order`; only the first `codec_type == "video"` stream supplies those fields.
    - A missing or `"unknown"` field order becomes `None`.
    - An unparseable duration becomes `None`; the inner bar then shows elapsed time with no total.
    - A non-zero exit raises `ProbeError` with stderr. The caller marks the file failed and continues.
- `parse_progress_line(line) -> Optional[float]`: reads `out_time_us=` (or `out_time_ms=`, which FFmpeg also reports in microseconds) and returns seconds. Non-numeric values (FFmpeg 8 emits `N/A` in the first block) and unrelated keys return `None`; it never raises. It is pure and unit-tested.

**Done when:** probing `samples/01 American Landscape.MTS` returns `duration≈168.19`, `field_order="tt"`, `avg_frame_rate="30000/1001"`, `has_audio=True`, and the step 8 `parse_probe_json` fixture test passes.

### 5. Command builder (pure)

In `mts_to_dnxhr.py`, add `build_command(ffmpeg: str, src: Path, dst: Path, opts: Options, info: Optional[ProbeInfo], force: bool) -> list[str]`. It produces, in order:

```text
<ffmpeg> -nostdin -hide_banner -loglevel error <-y if force else -n>
  -i <abs src>
  [-t <opts.duration>]
  -map 0:v:0 -map 0:a? -map_metadata 0
  [-vf yadif=mode=send_frame:parity=auto:deint=interlaced]   # only if opts.deinterlace and info.interlaced
  [-field_order <info.field_order>]                          # only if interlaced and NOT deinterlacing
  -c:v dnxhd -profile:v <profile> -pix_fmt <PROFILES[profile]>
  -c:a <AUDIO_CODECS[bits]> -ar 48000
  -f <mov|mxf>
  <abs dst>
```

Notes:

- Two callers, two `dst`/`force` pairs:
  - The runner (step 6) passes `dst=<.part path>`, `force=True`. `-y` only ever touches our own temp file; whether the final file may be replaced is decided in `convert_one` before encoding.
  - Dry-run passes `dst=<final path>`, `force=opts.overwrite`. Without `--overwrite` the printed command has `-n`, so pasting it can never clobber an existing output.
- `-progress pipe:1 -nostats` is appended by the runner, not here. That way `--dry-run` prints a clean, copy-pasteable command.
- When `info is None` (dry run without ffprobe) and `--deinterlace` is set, include the yadif filter anyway. `deint=interlaced` makes it a no-op on progressive frames. The tool notes this in the output.
- `format_command(cmd) -> str`: `subprocess.list2cmdline` on Windows, `shlex.join` elsewhere. On Windows, also double-quote any argument containing `?` or `*` (e.g. `0:a?`), since `list2cmdline` leaves those bare.

**Done when:** unit tests assert:

- HQX/MOV default argv contains `-profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000 -f mov`.
- HQ uses `yuv422p`; 444 uses `yuv444p10le`.
- `--audio-bit-depth 24` gives `pcm_s24le`.
- MXF gives `-f mxf`.
- yadif appears only for interlaced input with `--deinterlace`.
- `-field_order tt` appears only for interlaced input without `--deinterlace`.
- Paths containing spaces stay a single argv element.
- `force=True` gives `-y` and no `-n`; `force=False` gives `-n` and no `-y`.
- Dry-run via `main` with an existing destination file: the printed command contains `-n` and not `-y`; with `--overwrite` it contains `-y`.

### 6. Runner with progress, temp file, cleanup

In `mts_to_dnxhr.py`, add `run_ffmpeg(cmd, final_dst: Path, tmp_dst: Path, duration: Optional[float], desc: str) -> tuple[bool, str]`. It:

- Calls `subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"], stdout=PIPE, stderr=<tempfile>, text=True)`.
- Reads stdout line by line and updates an inner `tqdm(total=duration, unit="s", leave=False, desc=desc)` from `parse_progress_line`. The caller passes `duration = min(probed duration, opts.duration)` when `--duration` is set, so the bar ends at 100%.
- On exit code 0, if `tmp_dst` exists and has a non-zero size, does `os.replace(tmp_dst, final_dst)` and returns `(True, "")`.
- Otherwise deletes `tmp_dst` and returns `(False, last ~20 lines of stderr)`.
- On `KeyboardInterrupt`: `proc.terminate()`, then `wait(timeout=10)`, then `kill()` if needed. It deletes `tmp_dst` and re-raises.
- Wraps the whole read loop in `try/finally`: on **any** exception (not only Ctrl+C) it stops ffmpeg if still running, deletes `tmp_dst` if it exists, and closes the stderr temp file. No `.part` survives a Python-side error.

`convert_one(...)` handles a single file:

- If `final_dst` exists and `not opts.overwrite`, return `"skipped"`.
- Otherwise `mkdir(parents=True, exist_ok=True)` the destination folder, probe, build the command, run it, and return `"ok"` or `"failed"`.
- Report messages through `tqdm.write` so they don't break the bars.

**Done when:**

- A manual run on the sample leaves only the final `.mov`, with no `.part` file.
- Pressing Ctrl+C mid-encode leaves no `.part` file and exits with code 130.
- Re-running without `--overwrite` reports "skipped".

### 7. CLI and batch orchestration

In `mts_to_dnxhr.py`, add `build_parser()` and `main(argv: Optional[list[str]] = None) -> int`, plus `if __name__ == "__main__": sys.exit(main())`.

Arguments:

- Positional `input` (file or folder).
- `-o/--output DIR`.
- `-r/--recursive`.
- `-p/--profile {PROFILES}` (default `dnxhr_hqx`).
- `-c/--container {mov,mxf}` (default `mov`).
- `--audio-bit-depth {16,24}`, as `type=int`, default `16`. The request's examples use `pcm_s16le`. README recommends `24` for grading.
- `--deinterlace`.
- `--overwrite`.
- `-n/--dry-run`.
- `--duration SECONDS`, `type=float`. This is a small **addition beyond the request**: it encodes only the first N seconds, for quick tests of settings and for the smoke test. Its help text describes it as a testing aid.

Flow:

1. Validate that the input exists (exit 2 if not).
2. Run `find_inputs`. Catch its `ValueError` (e.g. a `.txt` file argument) and exit 2 with the message, no traceback. If there are no inputs, exit 2 with "no .MTS/.M2TS files found (use --recursive?)".
3. Map output paths and check for collisions (exit 2 if any).
4. Find ffmpeg and ffprobe.
   - When missing and not a dry run, exit 2 with an install hint (e.g. `winget install Gyan.FFmpeg`, `brew install ffmpeg`, `apt install ffmpeg`).
   - In a dry run without ffprobe, use `info=None` and print a note.
5. Print a header: input count, skipped non-MTS count, profile, container, audio codec, and output directory.
6. For a dry run, print one command per file (marking ones that would be skipped as existing) and exit 0. Otherwise loop over files with an outer `tqdm(unit="file")` and call `convert_one`.
7. Print a summary line, `converted X, skipped Y, failed Z`, list failed files with an error excerpt, and return the exit code.
8. `main` catches `KeyboardInterrupt` around the batch loop and returns 130. By then `run_ffmpeg` has already terminated ffmpeg and deleted the `.part` file.

`main` takes `argv` so tests can call it directly.

Canonical usage examples. These are the contract for this step and for the README (step 10):

```text
python mts_to_dnxhr.py "samples/01 American Landscape.MTS"
python mts_to_dnxhr.py ./footage/
python mts_to_dnxhr.py ./footage/ --recursive -o ./converted/
python mts_to_dnxhr.py ./footage/ --profile dnxhr_hq --container mxf --audio-bit-depth 24
```

**Done when:**

- `python mts_to_dnxhr.py --help` lists every flag.
- Each of the four canonical examples above parses and runs, or dry-runs, correctly.
- Exit codes match the table in Approach.

### 8. Tests

Create `tests/__init__.py` (empty) and `tests/test_mts_to_dnxhr.py`, written with stdlib `unittest` and run from the repo root.

**Unit tests** need no FFmpeg and no media:

- Use `tempfile.TemporaryDirectory()` holding empty files such as `A.MTS`, `b.mts`, `c.M2TS`, `notes.txt`, `00000.CPI`, plus `sub/00000.MTS` and `sub2/00000.MTS`.
- Test `find_inputs` in both non-recursive and recursive modes.
- Test that `output_path_for` mirrors subfolders and that `find_collisions` catches `A.MTS` + `A.M2TS`.
- Cover every assertion listed in step 5 for `build_command`.
- Test `parse_progress_line`: `out_time_us=967633` → 0.967633, `out_time_ms=1000000` → 1.0, `out_time_us=N/A` → `None`, `frame=30` → `None`.
- Test `parse_probe_json` with an inline fixture copied from the sample's real probe: `format.duration` as the string `"168.192000"`, an audio stream listed **before** the video stream with `avg_frame_rate="0/0"` and no `field_order`. Expect `duration=168.192`, `field_order="tt"`, `avg_frame_rate="30000/1001"`, `has_audio=True`. Add a video-only fixture (`has_audio=False`) and one with `field_order="unknown"` (→ `None`).
- Test `main([...,"--dry-run"])` with `find_tool` patched to return `None`. It should print commands and return 0.
- Test the dry-run overwrite cases from step 5 (existing destination: `-n` without `--overwrite`, `-y` with it).
- Test that `main` on a nonexistent path returns 2, and that `main` on a `.txt` file returns 2 without raising.

**Opt-in smoke test:**

- `class SmokeTest`, decorated with `@unittest.skipUnless(os.environ.get("MTS_SMOKE") == "1" and shutil.which("ffmpeg"), ...)`.
- Takes the first `.mts`/`.m2ts` in `samples/` (skip if none).
- Runs `main([sample, "-o", tmpdir, "--duration", "3"])` for the default HQX/MOV, then again with `-c mxf --audio-bit-depth 24`.
- Checks each output with ffprobe:
  - `codec_name=dnxhd`, with profile reported as DNXHR HQX.
  - `pix_fmt=yuv422p10le`.
  - Width and height equal the source's.
  - `avg_frame_rate` equals the source's.
  - Audio at 48000 Hz: `pcm_s16le` for the first (MOV) run, `pcm_s24le` for the second (MXF) run.

**Done when:** `python -m unittest -v` passes with the smoke test skipped, and `MTS_SMOKE=1 python -m unittest -v` (PowerShell: `$env:MTS_SMOKE='1'; python -m unittest -v`) passes against the sample.

### 9. Verify the open technical behaviors on the real sample, and adjust if needed

Run these against `samples/01 American Landscape.MTS`. The expected results are the pre-check in Existing data / APIs; a fallback is implemented only if a re-check contradicts it.

1. `python mts_to_dnxhr.py "samples/01 American Landscape.MTS" --duration 10 -o samples/_check`. Then run `ffprobe -v error -show_entries stream=codec_name,profile,pix_fmt,width,height,field_order,avg_frame_rate,nb_frames,sample_rate,channels -of json` on the output.
   - Expect `avg_frame_rate=30000/1001` and `nb_frames≈300` for 10 s.
   - **If** it is 60000/1001 or frames are duplicated, apply the fallback from Approach #6 (`-r <avg_frame_rate>`) and add a unit test for it.
2. Check `field_order` in the `.mov` and in `-c mxf` output. Expected: MOV `unknown`, MXF `progressive` (it does not survive).
   - Keep the `-field_order` pass-through (it is harmless) and write the README note: "for 1080i sources, set Clip Attributes → Field Dominance → Upper in Resolve, or use `--deinterlace`". If a future FFmpeg does carry `tt`, soften the note.
3. Run with `--deinterlace --duration 10` and confirm the output is progressive at 30000/1001 with 300 frames.
4. Run with `-c mxf` and confirm the MXF muxer accepts DNxHR HQX plus stereo PCM at 29.97.
   - **If** the muxer rejects multichannel PCM in one track, switch MXF audio mapping to one mono track per channel and record the reason in a code comment. This is MXF-only; MOV is unaffected.
5. Run all five profiles with `--duration 3` and confirm each encodes at 1920×1080. `dnxhr_444` upsamples a 4:2:0 source; the README notes this gives no quality benefit. Record each output's video `bit_rate` from ffprobe and confirm it is within ±10% of the Constraints table (LB ~45, SQ ~145, HQ ~220, HQX ~220, 444 ~440 Mb/s). If not, update the Constraints table and the README table to the measured values.
6. Delete `samples/_check` once results are recorded. Those encodes are large and only `*.mov`/`*.mxf`/`*.part` inside it are gitignored.

**Done when:** each check above has a recorded result, either in the PR description or as a short "Verified on FFmpeg 8.0.1" note in the README, any fallback taken is covered by a test, and `samples/_check` is gone.

### 10. README

Create `README.md` with these sections:

- **What & why.** Resolve's trouble with AVCHD: long-GOP H.264 makes scrubbing heavy, AC-3 audio often shows up as silence, and import of the MTS/`PRIVATE/AVCHD/BDMV/STREAM` structure is spotty. DNxHR is intra-frame, decodes cheaply on Windows, macOS and Linux, and carries PCM audio.
- **Requirements.**
  - Python 3.9+ and FFmpeg on PATH (install hints per OS).
  - Windows setup:
    - `python -m venv .venv`
    - `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- **Profiles table.** Bit depth, chroma, approximate 1080p29.97 bitrate and GB/min, and a recommended use for each. Bitrates and sizes come from the Constraints table (as re-measured in step 9.5), not from published Avid figures:
  - HQX: grading, the default.
  - HQ: 8-bit compatibility only; on FFmpeg 8.0.1 it is the same size as HQX.
  - SQ: lighter editing.
  - LB: proxies.
  - 444: rarely useful for 4:2:0 AVCHD.
- **Usage examples.** The four canonical examples from step 7, plus:
  - `--dry-run`;
  - `-c mxf`;
  - `--audio-bit-depth 24`;
  - quoting paths with spaces (`"samples/01 American Landscape.MTS"`);
  - pointing at an AVCHD card's `PRIVATE/AVCHD/BDMV/STREAM` with `--recursive`.
- **Output layout.** The default output folders, subfolder mirroring, the skip/`--overwrite` behavior, and the `.part` temp files.
- **Interlaced footage.** What `--deinterlace` does (yadif, same frame rate). Without it, the output does not carry field order, so set Clip Attributes → Field Dominance → Upper in Resolve for 1080i sources.
- **Using in Resolve.** Import the `.mov`/`.mxf` from the output folder through the Media Pool or Media page as normal **source media**; the clips are full-quality masters, not proxies. Optionally, link LB outputs as proxies via "Link Proxy Media".
- **Testing.** `python -m unittest -v` and the `MTS_SMOKE=1` opt-in, with `samples/README.md` referenced.
- **Limitations.** See Out of scope.

**Done when:** every command in the README has been copy-pasted and run (or dry-run) successfully from the repo root on this machine.

## Verification

Run from the repo root (`D:\GitHub\mts-to-dnxhr`), in a venv with `tqdm` installed:

1. `python -m unittest -v`: all pass, smoke test skipped.
2. `$env:MTS_SMOKE='1'; python -m unittest -v`: smoke test passes against `samples/01 American Landscape.MTS`.
3. `python mts_to_dnxhr.py --help`: every flag from the request appears, with defaults `dnxhr_hqx`, `mov` and `16`.
4. `python mts_to_dnxhr.py samples/ --dry-run`: prints one HQX/MOV command containing `-n -i` and `-c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s16le -ar 48000`, with an absolute output path ending in `samples_dnxhr\01 American Landscape.mov`. Exit 0, and no file is created. With `--overwrite` added, the command shows `-y` instead of `-n`.
5. `python mts_to_dnxhr.py "samples/01 American Landscape.MTS"`: a full encode. Both progress bars render. The output `samples/dnxhr/01 American Landscape.mov` has duration ≈168.19 s, 1920×1080, `30000/1001`, `pcm_s16le` at 48 kHz, 2 channels. No `.part` files remain.
6. Re-run step 5: reports `skipped 1`, exit 0. Re-run with `--overwrite`: re-encodes.
7. `python mts_to_dnxhr.py samples/notes.txt` (a temporary file): exit 2 with a clear "not an .MTS/.M2TS file" message. `python mts_to_dnxhr.py does-not-exist`: exit 2.
8. Ctrl+C during step 5: exit 130, no `.part` file.
9. **Manual Resolve check (user):** import the step 5 output into a Resolve project. Picture and audio are present, the clip scrubs smoothly, and Clip Attributes show 1920×1080 at 29.97 (`30000/1001`). Field dominance is **not** expected to be carried by the file; setting it to Upper per the README note must work.
10. Static check: `grep -n "shell=True" mts_to_dnxhr.py` returns nothing. Every `subprocess` call takes a list.
11. README numbers: the profile table's bitrates and GB/min match the step 9.5 measurements (±10%). No 180 Mb/s / 3.8 GB figure remains.

## Risks

- **Frame-rate misdetection.** `r_frame_rate` (59.94) differs from `avg_frame_rate` (29.97) on 1080i AVCHD, so FFmpeg could emit 59.94 output with duplicated frames. The pre-check on FFmpeg 8.0.1 was clean; other FFmpeg versions or cameras may differ. Step 9.1 re-checks and has a planned fallback.
- **Interlace metadata is lost.** The pre-check shows MOV and MXF do not carry `field_order`, so Resolve treats 1080i as progressive unless the user sets Field Dominance. Mitigations: the README note and `--deinterlace`.
- **MXF quirks.** The FFmpeg MXF OP1a muxer is stricter than MOV about frame rates and audio layout. Stereo PCM passed the pre-check; multichannel or odd-rate sources are untested. Step 9.4 re-checks and has a planned mono-track fallback. MOV stays the default.
- **1440×1080 anamorphic AVCHD** (some camcorders). DNxHR accepts it, but the sample aspect ratio has to survive for Resolve to display it at 16:9. This is untested because the only sample is 1920×1080; it is listed as a README limitation and should be tested if a sample turns up.
- **Spanned clips.** AVCHD splits long recordings across several `.MTS` files. Each converts on its own, so there is a cut at each boundary, though no frames are lost. Joining them is out of scope.
- **Disk space.** Outputs are about 3× (LB) to 28× (444) larger than the source; HQX is about 14× (4.7 GB from a 335 MB clip). There is no preflight check, so a batch can fail partway when the disk fills. Failures are reported per file, `.part` files are cleaned up, and the README warns about this.
- **Progress parsing.** If FFmpeg changes its `-progress` keys, the inner bar degrades to elapsed time only; conversion itself is unaffected.
- **Windows console.** Nested `tqdm` bars can render poorly in some terminals, but they work in Windows Terminal, which is assumed acceptable.

## Open questions

Each has a default already chosen; none blocks implementation.

1. **License.** MIT is assumed for "open-source". Confirm or pick another.
2. **Default audio bit depth.** 16 (matches the request's example commands) or 24 (more headroom for grading)? The plan defaults to **16** to match the request.
3. **Default output folder naming.** `dnxhr/` next to a file and `<folder>_dnxhr/` next to a folder. Confirm, or prefer a single convention.

## Out of scope

- Packaging (`pyproject.toml`, PyPI, console-script entry point), bundling FFmpeg, and GUI/drag-drop.
- Parallel/multi-process encoding, and hardware acceleration.
- Joining spanned AVCHD clips, reading AVCHD playlist (`.MPL`) metadata, and preserving camera timecode.
- Field-rate deinterlacing (59.94p), scaling or frame-rate conversion, color-space tagging/conversion, LUTs.
- Non-AVCHD inputs (MP4, MOV, MXF sources).
- `git init`, CI setup, publishing to GitHub. Do these only when the user asks.

**Ready for implementation whenever you are.**
