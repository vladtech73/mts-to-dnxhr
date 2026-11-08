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

`tqdm` is the only Python dependency. From the repo root:

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

A full HQX or HQ encode of a 168-second 1080i clip is about 4.7 GB (about 14× a 335 MB source). LB is about 1.0 GB, SQ about 3.1 GB, and 444 about 9.3 GB for that same duration. There is no free-space check before encoding.

### Verified on FFmpeg 8.0.1

Checked against `samples/01 American Landscape.MTS` (H.264 1920×1080, `field_order=tt`, `avg_frame_rate=30000/1001`, AC-3 stereo, 168.192 s). Short `--duration` encodes were used so a full HQX file (~4.7 GB) was not written.

- 10 seconds of default HQX MOV: `DNXHR HQX`, `yuv422p10le`, 1920×1080, `avg_frame_rate=30000/1001`, `r_frame_rate=30000/1001`, 300 frames, `pcm_s16le` at 48 kHz, 2 channels. The tool does not pass `-r`.
- The same 10 seconds as MXF: stereo `pcm_s16le` accepted in one track, 300 frames, `30000/1001`. `field_order=progressive`.
- MOV `field_order=unknown` with or without `--deinterlace`. Frame flags are not interlaced either way, so a woven 1080i file does not tell Resolve it is interlaced.
- `--deinterlace` for 10 seconds stayed at `30000/1001` and 300 frames.
- 3-second video bitrates: LB 45.2 Mb/s, SQ 145.3 Mb/s, HQ 220.0 Mb/s, HQX 220.0 Mb/s, 444 440.0 Mb/s. All are within 10% of the table. HQ and HQX were the same size.

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
```

`converted/` is gitignored. Delete it when you are done; it is only a scratch folder.

Other flags: `--profile` (`dnxhr_hqx` by default), `--deinterlace`, `--overwrite`, `--output`, `--recursive`. `--help` lists them.

Exit codes: `0` every file converted or skipped, `1` at least one file failed (the batch continues), `2` usage or preflight error (bad path, no clips, FFmpeg missing, two inputs mapping to one output), `130` interrupted. Ctrl+C stops ffmpeg and deletes the partial file.

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

- No installer, `pyproject.toml`, or bundled FFmpeg. No GUI.
- Encodes run one at a time, in software. There is no GPU encoder and no parallel batch.
- Spanned AVCHD recordings stay as separate files. Each clip converts on its own, so there is a cut at each file boundary. Frames are not dropped. Joining them, reading `.MPL` playlists, and preserving camera timecode are out of scope.
- No 59.94p (field-rate) deinterlace, scaling, frame-rate conversion, color tagging, or LUTs.
- Inputs other than `.MTS` and `.M2TS` are rejected.
- 1440×1080 anamorphic AVCHD is untested. The only sample here is 1920×1080. DNxHR can store 1440×1080, but the sample aspect ratio has to survive for Resolve to show it at 16:9.
- Outputs are much larger than the camera files. A batch can fail midway if the disk fills. The failure is reported for that file, the `.part` file is removed, and later files are still attempted.
- If a future FFmpeg changes the `-progress` keys, the time bar falls back to elapsed time. The encode itself is unchanged.
