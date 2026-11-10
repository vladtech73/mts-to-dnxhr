# MTS/M2TS to DNxHR

A single-file Python CLI that converts AVCHD `.MTS` and `.M2TS` clips into DNxHR intermediates for DaVinci Resolve.

Resolve struggles with camera originals in three ways. Long-GOP H.264 is expensive to scrub, AC-3 audio often comes in silent, and import of an `.MTS` file or a `PRIVATE/AVCHD/BDMV/STREAM` card layout is unreliable. DNxHR is intra-frame, so it decodes cheaply on Windows, macOS, and Linux, and the PCM audio is what Resolve actually plays.

```powershell
python mts_to_dnxhr.py "samples/01 American Landscape.MTS"
```

That writes `samples/dnxhr/01 American Landscape.mov`: DNxHR HQX (`yuv422p10le`) with 48 kHz PCM, at the source resolution, frame rate, and duration.

## Requirements

- Python 3.9 or newer
- FFmpeg and ffprobe on `PATH` (they are not bundled)

Install FFmpeg:

- Windows: `winget install Gyan.FFmpeg`
- macOS: `brew install ffmpeg`
- Debian/Ubuntu: `apt install ffmpeg`

`tqdm` is the CLI dependency. The desktop window also uses `tkinterdnd2` for drag-and-drop. From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

If activation is blocked, call `.\.venv\Scripts\python.exe` instead of `python` in the examples below. `--dry-run` still prints commands when FFmpeg is missing. A real encode exits with code 2 and the install hint above.

## Profiles

The default is `dnxhr_hqx` in a `.mov` container. Audio is PCM at 48 kHz, 16-bit (`pcm_s16le`) unless you pass `--audio-bit-depth 24` (`pcm_s24le`). 24-bit leaves more headroom for grading. Channel count is kept as in the source.

Rates below are video bitrate at 1920×1080, `30000/1001`, measured with FFmpeg 8.0.1. They are not Avid's published figures. GB/min includes that video rate plus 1.536 Mb/s of stereo 16-bit PCM. HQ is the same size as HQX on this FFmpeg build.

| Profile | Bit depth | Chroma | ~1080p29.97 | ~GB/min | Use |
|---|---|---|---|---|---|
| `dnxhr_hqx` | 10-bit | 4:2:2 (`yuv422p10le`) | ~220 Mb/s | ~1.66 GB | Grading. The default. |
| `dnxhr_hq` | 8-bit | 4:2:2 (`yuv422p`) | ~220 Mb/s | ~1.66 GB | 8-bit compatibility only. Same size as HQX here. |
| `dnxhr_sq` | 8-bit | 4:2:2 (`yuv422p`) | ~145 Mb/s | ~1.1 GB | Lighter editing. |
| `dnxhr_lb` | 8-bit | 4:2:2 (`yuv422p`) | ~45 Mb/s | ~0.35 GB | Proxies. |
| `dnxhr_444` | 10-bit | 4:4:4 (`yuv444p10le`) | ~440 Mb/s | ~3.3 GB | Rarely useful for 4:2:0 AVCHD. The encoder upsamples; it does not recover chroma. |

A full HQX or HQ encode of a 168-second 1080i clip is about 4.7 GB (about 14× a 335 MB source). LB is about 1.0 GB, SQ about 3.1 GB, and 444 about 9.3 GB for that same duration. The CLI does not check free space before encoding. The desktop app warns when the estimate (about 14× the source size of files that are not already in the export folder) is larger than the free space on that drive.

### Verified on FFmpeg 8.0.1

Checked against `samples/01 American Landscape.MTS` (H.264 1920×1080, `field_order=tt`, `avg_frame_rate=30000/1001`, AC-3 stereo, 168.192 s). Short `--duration` encodes were used so a full HQX file (~4.7 GB) was not written.

- 10 seconds of default HQX MOV: `DNXHR HQX`, `yuv422p10le`, 1920×1080, `avg_frame_rate=30000/1001`, `r_frame_rate=30000/1001`, 300 frames, `pcm_s16le` at 48 kHz, 2 channels. The tool does not pass `-r`.
- The same 10 seconds as MXF: stereo `pcm_s16le` accepted in one track, 300 frames, `30000/1001`. `field_order=progressive`.
- MOV `field_order=unknown` with or without `--deinterlace`. Frame flags are not interlaced either way, so a woven 1080i file does not tell Resolve it is interlaced.
- `--deinterlace` for 10 seconds stayed at `30000/1001` and 300 frames.
- 3-second video bitrates: LB 45.2 Mb/s, SQ 145.3 Mb/s, HQ 220.0 Mb/s, HQX 220.0 Mb/s, 444 440.0 Mb/s. All are within 10% of the table. HQ and HQX were the same size.

Four copies of that sample, first 30 seconds each, default HQX MOV, written to an NVMe SSD on this PC (20 logical processors). Wall time is for the whole batch. Peak RAM is the highest sampled sum of `ffmpeg.exe` working sets. Write rate is output bytes divided by wall time.

| Jobs | Deinterlace | Wall | Peak RAM | Write |
| --- | --- | --- | --- | --- |
| 1 | no | 24.0 s | 1.8 GB | 139 MB/s |
| 2 | no | 19.2 s | 3.6 GB | 173 MB/s |
| 3 | no | 19.9 s | 5.4 GB | 167 MB/s |
| 4 | no | 18.5 s | 7.1 GB | 180 MB/s |
| 1 | yes | 20.9 s | 1.8 GB | 159 MB/s |
| 2 | yes | 18.4 s | 3.6 GB | 181 MB/s |
| 3 | yes | 18.2 s | 5.4 GB | 183 MB/s |
| 4 | yes | 17.3 s | 7.2 GB | 192 MB/s |

Two streams were faster than one. A third was not, so the suggestion caps at 2. Each ffmpeg process used about 1.8 GB.

## Usage

Quote paths that contain spaces.

```powershell
python mts_to_dnxhr.py "samples/01 American Landscape.MTS"
python mts_to_dnxhr.py ./footage/
python mts_to_dnxhr.py ./footage/ --recursive -o ./converted/
python mts_to_dnxhr.py ./footage/ --profile dnxhr_hq --container mxf --audio-bit-depth 24
```

Preview the ffmpeg command without writing a file. The printed command uses `-n` unless you also pass `--overwrite`, so pasting it will not replace an existing output. It starts with `ffmpeg` when that name is on `PATH`. If a quoted path containing spaces is printed instead, PowerShell needs the call operator: put `& ` in front of the pasted line.

```powershell
python mts_to_dnxhr.py "samples/01 American Landscape.MTS" --dry-run
python mts_to_dnxhr.py "samples/01 American Landscape.MTS" --dry-run --overwrite
```

MXF (OP1a) and 24-bit PCM:

```powershell
python mts_to_dnxhr.py "samples/01 American Landscape.MTS" -c mxf --dry-run
python mts_to_dnxhr.py "samples/01 American Landscape.MTS" --audio-bit-depth 24 --dry-run
```

AVCHD cards repeat names such as `00000.MTS` across folders. `--recursive` mirrors those folders so the outputs do not collide. A stream directory looks like this:

```powershell
python mts_to_dnxhr.py "PRIVATE/AVCHD/BDMV/STREAM" --recursive
```

Encode a few seconds while trying settings. This is a testing aid, not a trimmer for finished masters:

```powershell
python mts_to_dnxhr.py "samples/01 American Landscape.MTS" --duration 3 -o converted/
python mts_to_dnxhr.py ./footage/ --jobs 2
```

`converted/` is gitignored. Delete it when you are done; it is only a scratch folder.

`--jobs N` encodes up to N clips at once (1-4, default 1). `--help` prints a suggestion for this PC: `max(1, min(2, logical processors // 6))`. Use 1 when the export folder is on a spinning disk or a USB drive. Each parallel encode uses about 2 GB of RAM.

`--hwaccel` selects hardware decode (`cuda` by default; also `auto`, `d3d11va`, `qsv`, or `off`). DNxHR encode stays on the CPU. Use `--hwaccel off` to force software decode.

Other flags: `--profile` (`dnxhr_hqx` by default), `--deinterlace`, `--overwrite`, `--output`, `--recursive`, `--jobs`, `--hwaccel`. `--help` lists them.

Exit codes: `0` every file converted or skipped, `1` at least one file failed (the batch continues), `2` usage or preflight error (bad path, no clips, FFmpeg missing, two inputs mapping to one output), `130` interrupted. Ctrl+C stops ffmpeg and deletes the partial file.

## Desktop app (Windows)

The desktop app drops `.MTS` / `.M2TS` files or folders, asks for one export folder, and converts with the CLI defaults: DNxHR HQX, `.mov`, 16-bit PCM at 48 kHz, source size and frame rate. Deinterlace is off unless you tick **Deinterlace interlaced (1080i) clips**. **GPU decode (hardware)** is on by default (`-hwaccel cuda`); uncheck it for software decode. **Parallel encodes** runs from 1 to 4 clips at once and defaults to 1. A grey hint shows the suggested maximum for this PC, such as `(suggested max 2 for this PC)`. Use 1 when the export folder is on a spinning disk or a USB drive. Each parallel encode uses about 2 GB of RAM. Existing outputs are skipped. A dropped folder is scanned recursively and the export mirrors its subfolders, same as `--recursive`. Dropping a card root nests `PRIVATE\AVCHD\BDMV\STREAM` under the export folder; drop the `STREAM` folder instead when you want a flat list of clips.

Run it from source, from the repo root:

```powershell
.\.venv\Scripts\pythonw.exe mts_to_dnxhr_gui.py
```

`pythonw mts_to_dnxhr_gui.py` does the same thing when that interpreter already has the requirements installed. Use `python.exe` instead of `pythonw.exe` if you want a console for debugging.

Build a double-clickable exe:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

That writes `dist\MTS-to-DNxHR.exe`.

The exe is self-contained. Copy it anywhere, such as `C:\Tools\MTS-to-DNxHR\`. Then right-click it and choose **Pin to Start** or **Pin to taskbar**, or **Show more options → Send to → Desktop (create shortcut)**. FFmpeg must be on `PATH`, or `ffmpeg.exe` and `ffprobe.exe` must sit in the folder where the **exe** lives, not where the shortcut is. An unsigned exe can show a SmartScreen prompt; choose **More info → Run anyway**.

To change the icon, replace `assets\app.ico` with another multi-size `.ico`, or edit and re-run `scripts\make_icon.py`, then rebuild. If Explorer still shows the old icon, run `ie4uinit.exe -show` or sign out and back in.

## Output layout

- A file input writes to `<file parent>/dnxhr/` when `--output` is omitted. `clip.MTS` becomes `dnxhr/clip.mov`.
- A folder input writes to a sibling `<parent>/<folder name>_dnxhr/`, so the outputs are not inside the folder being scanned. `./footage/` becomes `./footage_dnxhr/`.
- `--recursive` mirrors subfolders under the output directory.
- The stem is unchanged. The extension becomes `.mov` or `.mxf`.
- An output that already exists is skipped unless `--overwrite` is set. Re-running prints `skipped` and exits 0.
- The encoder writes `<name>.mov.part` (or `.mxf.part`) and renames it into place only after ffmpeg succeeds. A failed encode or Ctrl+C deletes the `.part` file.
- If two inputs would write the same path (`A.MTS` and `A.M2TS` in one folder), the tool lists them and exits 2. Nothing is encoded.
- Files that are not `.MTS` or `.M2TS` (`.CPI`, `.MPL`, notes, and so on) are counted in the header and not listed.

## Interlaced footage

1080i AVCHD often probes as `field_order=tt` (top field first) with `avg_frame_rate=30000/1001` and a different `r_frame_rate`. This tool does not pass `-r`, and on FFmpeg 8.0.1 the output stays at `30000/1001` with one frame per source frame.

`--deinterlace` adds `yadif=mode=send_frame:parity=auto:deint=interlaced`. That is one output frame per input frame, so 29.97 stays 29.97. It is not a 59.94p field-rate conversion. Progressive sources skip the filter and print a one-line note. If the file could not be probed, the filter is still included; `deint=interlaced` does nothing on frames that are already progressive.

Without `--deinterlace`, woven frames are kept and `-field_order` is passed through. On FFmpeg 8.0.1 that value does not survive: MOV reports `field_order=unknown`, and MXF reports `progressive`. For 1080i sources, set Clip Attributes → Field Dominance → Upper in Resolve, or use `--deinterlace`.

## Using in Resolve

Import the `.mov` or `.mxf` files from the output folder through the Media Pool or the Media page as normal source media. They are full-quality masters, not proxies. Picture and PCM audio should both be present.

For a 1080i clip that was not deinterlaced, set Clip Attributes → Field Dominance → Upper. The file itself does not carry that flag.

LB outputs can be attached as proxies with Link Proxy Media. The HQX (or SQ/HQ) file remains the full media.

## Testing

From the repo root, with `tqdm` installed:

```powershell
python -m unittest -v
```

That suite does not need FFmpeg or a sample. To encode the first `.mts` or `.m2ts` file in `samples/` (about three seconds, twice: HQX MOV, then MXF with 24-bit audio):

```powershell
$env:MTS_SMOKE='1'; python -m unittest -v
```

See `samples/README.md`. Media in that folder is gitignored and must not be committed.

## Limitations

- There is a minimal Windows GUI (DNxHR HQX, MOV, and 16-bit PCM only; use the CLI for other profiles). No installer, code signing, `pyproject.toml`, or bundled FFmpeg.
- Encodes run in software. Up to 4 clips can encode at once (default 1). There is no GPU encoder.
- Spanned AVCHD recordings stay as separate files. Each clip converts on its own, so there is a cut at each file boundary. Frames are not dropped. Joining them, reading `.MPL` playlists, and preserving camera timecode are out of scope.
- No 59.94p (field-rate) deinterlace, scaling, frame-rate conversion, color tagging, or LUTs.
- Inputs other than `.MTS` and `.M2TS` are rejected.
- 1440×1080 anamorphic AVCHD is untested. The only sample here is 1920×1080. DNxHR can store 1440×1080, but the sample aspect ratio has to survive for Resolve to show it at 16:9.
- Outputs are much larger than the camera files. A batch can fail midway if the disk fills. The failure is reported for that file, the `.part` file is removed, and later files are still attempted. With several parallel encodes, a full disk can fail every in-flight file at once.
- If a future FFmpeg changes the `-progress` keys, the time bar falls back to elapsed time. The encode itself is unchanged.
