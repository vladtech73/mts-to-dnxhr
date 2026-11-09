"""Convert AVCHD .MTS/.M2TS clips to DNxHR intermediates for DaVinci Resolve.

FFmpeg and ffprobe must be on PATH for a real encode. ``--dry-run`` prints
commands even when they are missing. Nothing runs at import time.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, TextIO

from tqdm import tqdm

INPUT_EXTENSIONS = {".mts", ".m2ts"}
PROFILES = {
    "dnxhr_hqx": "yuv422p10le",
    "dnxhr_hq": "yuv422p",
    "dnxhr_sq": "yuv422p",
    "dnxhr_lb": "yuv422p",
    "dnxhr_444": "yuv444p10le",
}
AUDIO_CODECS = {16: "pcm_s16le", 24: "pcm_s24le"}
CONTAINERS = {"mov": "mov", "mxf": "mxf"}
INTERLACED_FIELD_ORDERS = {"tt", "bb", "tb", "bt"}
YADIF = "yadif=mode=send_frame:parity=auto:deint=interlaced"
MAX_JOBS = 4
INSTALL_HINT = (
    "error: ffmpeg and ffprobe must be on PATH.\n"
    "Install FFmpeg, then run this command again:\n"
    "  winget install Gyan.FFmpeg\n"
    "  brew install ffmpeg\n"
    "  apt install ffmpeg"
)

# Hide the console window that a windowed GUI would otherwise flash for each child.
_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)


def suggested_jobs(cpu_count: Optional[int] = None) -> int:
    """Advisory parallel encodes: about 6 logical CPUs per extra stream (CPU headroom
    for ~28 MB/s HQX streams), capped at 2."""
    n = os.cpu_count() if cpu_count is None else cpu_count
    return max(1, min(2, (n or 0) // 6))


class ProbeError(Exception):
    """ffprobe failed or returned data that could not be parsed."""


class ConversionCancelled(Exception):
    """The caller asked to stop; ffmpeg was stopped and the .part removed."""


@dataclass(frozen=True)
class Options:
    profile: str
    container: str
    audio_bit_depth: int
    deinterlace: bool
    overwrite: bool
    duration: Optional[float]


@dataclass(frozen=True)
class ProbeInfo:
    duration: Optional[float]
    field_order: Optional[str]
    avg_frame_rate: Optional[str]
    has_audio: bool

    @property
    def interlaced(self) -> bool:
        return self.field_order in INTERLACED_FIELD_ORDERS


def find_tool(name: str) -> Optional[str]:
    return shutil.which(name)


def is_input_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in INPUT_EXTENSIONS


def _absolute_path(path: Path) -> Path:
    """Absolute path that does not follow symlinks.

    ``resolve()`` would turn a link inside the scanned folder into the target
    path, which then fails ``relative_to`` against that folder.
    """
    return path.absolute()


def discover_inputs(path: Path, recursive: bool) -> tuple[list[Path], int]:
    """Return matching clips and a count of other files that were skipped.

    A file argument with the wrong extension raises ``ValueError``.
    Returned paths are absolute and keep symlink locations inside the folder.
    """
    absolute = _absolute_path(path)
    if absolute.is_file():
        if not is_input_file(absolute):
            raise ValueError(f"not an .MTS/.M2TS file: {absolute}")
        return [absolute], 0
    if not absolute.is_dir():
        raise ValueError(f"not a file or directory: {absolute}")

    walker = absolute.rglob("*") if recursive else absolute.iterdir()
    inputs: list[Path] = []
    skipped = 0
    for candidate in walker:
        if is_input_file(candidate):
            inputs.append(_absolute_path(candidate))
        elif candidate.is_file():
            skipped += 1
    inputs.sort()
    return inputs, skipped


def find_inputs(path: Path, recursive: bool) -> list[Path]:
    inputs, _skipped = discover_inputs(path, recursive)
    return inputs


def default_output_dir(input_path: Path) -> Path:
    """File input writes to ``<parent>/dnxhr``. A folder writes to a sibling."""
    resolved = input_path.resolve()
    if resolved.is_file():
        return resolved.parent / "dnxhr"
    return resolved.parent / f"{resolved.name}_dnxhr"


def output_path_for(src: Path, input_root: Path, out_dir: Path, container: str) -> Path:
    """Map one source clip to its output path, mirroring subfolders for a directory.

    Paths are made absolute without following symlinks, so a link that lives
    in the input tree still maps under that tree. ``ValueError`` means the
    clip is not inside the input folder.
    """
    src_abs = _absolute_path(src)
    root_abs = _absolute_path(input_root)
    filename = f"{src_abs.stem}.{container}"
    if root_abs.is_file():
        return out_dir / filename
    try:
        relative_parent = src_abs.relative_to(root_abs).parent
    except ValueError:
        raise ValueError(
            f"cannot place {src} under {input_root}: the clip is not inside the input folder"
        ) from None
    return out_dir / relative_parent / filename


def find_collisions(pairs: list[tuple[Path, Path]]) -> dict[Path, list[Path]]:
    """Group sources that would write the same output. Comparison is case-insensitive on Windows."""
    grouped: dict[str, list[tuple[Path, Path]]] = {}
    for src, dst in pairs:
        key = os.path.normcase(os.path.normpath(str(dst)))
        grouped.setdefault(key, []).append((src, dst))
    collisions: dict[Path, list[Path]] = {}
    for items in grouped.values():
        if len(items) < 2:
            continue
        collisions[items[0][1]] = [src for src, _dst in items]
    return collisions


def _parse_duration(raw: object) -> Optional[float]:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def parse_probe_json(text: str) -> ProbeInfo:
    """Parse ffprobe JSON. Only the first video stream supplies rate and field order."""
    data = json.loads(text)
    duration = _parse_duration((data.get("format") or {}).get("duration"))
    field_order: Optional[str] = None
    avg_frame_rate: Optional[str] = None
    has_audio = False
    saw_video = False
    for stream in data.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        codec_type = stream.get("codec_type")
        if codec_type == "audio":
            has_audio = True
            continue
        if codec_type != "video" or saw_video:
            continue
        saw_video = True
        raw_order = stream.get("field_order")
        if isinstance(raw_order, str):
            cleaned = raw_order.strip()
            if cleaned and cleaned.lower() != "unknown":
                field_order = cleaned
        raw_rate = stream.get("avg_frame_rate")
        if isinstance(raw_rate, str):
            cleaned_rate = raw_rate.strip()
            if cleaned_rate and cleaned_rate not in {"0/0", "N/A"}:
                avg_frame_rate = cleaned_rate
    return ProbeInfo(
        duration=duration,
        field_order=field_order,
        avg_frame_rate=avg_frame_rate,
        has_audio=has_audio,
    )


def probe(src: Path, ffprobe: str) -> ProbeInfo:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,field_order,avg_frame_rate",
        "-of",
        "json",
        str(src.resolve()),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"ffprobe timed out: {src}") from exc
    except OSError as exc:
        raise ProbeError(str(exc)) from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or f"ffprobe exited {result.returncode}"
        raise ProbeError(detail)
    try:
        return parse_probe_json(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe returned invalid JSON: {exc}") from exc


def parse_progress_line(line: str) -> Optional[float]:
    """Return seconds from an ffmpeg ``-progress`` line.

    On FFmpeg 8 both ``out_time_us`` and ``out_time_ms`` are microseconds.
    ``N/A`` and unrelated keys return ``None``.
    """
    text = line.strip()
    key = None
    for candidate in ("out_time_us=", "out_time_ms="):
        if text.startswith(candidate):
            key = candidate
            break
    if key is None:
        return None
    raw = text[len(key) :].strip()
    if not raw or raw.upper() == "N/A":
        return None
    try:
        microseconds = float(raw)
    except ValueError:
        return None
    if not math.isfinite(microseconds) or microseconds < 0:
        return None
    return microseconds / 1_000_000.0


def _duration_arg(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def build_command(
    ffmpeg: str,
    src: Path,
    dst: Path,
    opts: Options,
    info: Optional[ProbeInfo],
    force: bool,
) -> list[str]:
    """Build an ffmpeg argv. ``-progress`` is added later by the runner, not here."""
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if force else "-n",
        "-i",
        str(src.resolve()),
    ]
    if opts.duration is not None:
        cmd.extend(["-t", _duration_arg(opts.duration)])
    cmd.extend(["-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0"])
    # No probe data: still deinterlace when asked. deint=interlaced is a no-op
    # on frames that are already progressive.
    if opts.deinterlace and (info is None or info.interlaced):
        cmd.extend(["-vf", YADIF])
    elif info is not None and info.interlaced and info.field_order is not None:
        # Kept even though FFmpeg 8 does not store this in MOV or MXF.
        cmd.extend(["-field_order", info.field_order])
    cmd.extend(
        [
            "-c:v",
            "dnxhd",
            "-profile:v",
            opts.profile,
            "-pix_fmt",
            PROFILES[opts.profile],
            "-c:a",
            AUDIO_CODECS[opts.audio_bit_depth],
            "-ar",
            "48000",
            "-f",
            CONTAINERS[opts.container],
            str(dst.resolve()),
        ]
    )
    return cmd


def format_command(cmd: list[str]) -> str:
    """Render argv for copy-paste. Windows quoting also covers ``?`` and ``*``."""
    if sys.platform == "win32":
        rendered: list[str] = []
        for arg in cmd:
            if any(ch in arg for ch in ("?", "*")):
                rendered.append('"' + arg.replace('"', '\\"') + '"')
            else:
                rendered.append(subprocess.list2cmdline([arg]))
        return " ".join(rendered)
    return shlex.join(cmd)


def _command_tool(located: Optional[str]) -> str:
    """Use the bare program name when it resolves to the same binary.

    A quoted full path whose directory contains spaces is not a valid
    PowerShell command unless the line starts with ``&``.
    """
    if not located:
        return "ffmpeg"
    which = find_tool("ffmpeg")
    if which is None:
        return located
    if os.path.normcase(os.path.normpath(which)) == os.path.normcase(os.path.normpath(located)):
        return "ffmpeg"
    return located


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _remove_dir_if_empty(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        pass


# One lock for every output folder so mkdir(parents=True) cannot interleave with rmdir.
_DIR_LOCK = threading.Lock()
_dir_users: dict[str, int] = {}


def _dir_key(directory: Path) -> str:
    return os.path.normcase(os.path.abspath(directory))


def _claim_dir(directory: Path) -> None:
    """Create ``directory`` and count one user. A failed ``mkdir`` does not count."""
    key = _dir_key(directory)
    with _DIR_LOCK:
        directory.mkdir(parents=True, exist_ok=True)
        _dir_users[key] = _dir_users.get(key, 0) + 1


def _release_dir(directory: Path, remove_if_empty: bool) -> None:
    """Drop one user. Remove the folder only when the last user asks for it."""
    key = _dir_key(directory)
    with _DIR_LOCK:
        count = _dir_users.get(key, 0) - 1
        if count <= 0:
            _dir_users.pop(key, None)
            if remove_if_empty:
                _remove_dir_if_empty(directory)
        else:
            _dir_users[key] = count


def _without_path_prefix(src: Path, detail: str) -> str:
    """Drop a leading ``path:`` that ffprobe already includes in stderr."""
    text = detail.strip()
    prefixes = [str(src)]
    try:
        prefixes.insert(0, str(src.resolve()))
    except OSError:
        pass
    for prefix in prefixes:
        lead = prefix + ":"
        if text.startswith(lead):
            return text[len(lead) :].lstrip()
    return text


def _stop_process(proc: Optional[subprocess.Popen[str]]) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
    if proc.stdout is not None:
        try:
            proc.stdout.close()
        except OSError:
            pass


def _stderr_tail(handle: TextIO, path: str, limit: int = 20) -> str:
    try:
        handle.flush()
        handle.close()
    except OSError:
        pass
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-limit:])


def _bar_total(info: ProbeInfo, opts: Options) -> Optional[float]:
    duration = info.duration
    if opts.duration is None:
        return duration
    if duration is None:
        return opts.duration
    return min(duration, opts.duration)


def run_ffmpeg(
    cmd: list[str],
    final_dst: Path,
    tmp_dst: Path,
    duration: Optional[float],
    desc: str,
    *,
    on_progress: Optional[Callable[[float, Optional[float]], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> tuple[bool, str]:
    """Run ffmpeg and publish ``tmp_dst`` on success.

    With no ``on_progress`` callback, an inner tqdm bar tracks ``-progress``.
    When the callback is set, it receives ``(seconds, total)`` and no bar is
    created. ``cancel`` is checked only on that callback path. stderr goes to
    a temp file so it cannot fill a pipe and deadlock the progress read. The
    ``.part`` file is removed on failure and on any error.
    """
    stderr_handle: Optional[TextIO] = None
    stderr_path: Optional[str] = None
    proc: Optional[subprocess.Popen[str]] = None
    succeeded = False
    try:
        fd, stderr_path = tempfile.mkstemp(prefix="mts_to_dnxhr_", suffix=".log")
        stderr_handle = os.fdopen(fd, "w", encoding="utf-8", errors="replace")
        # stderr is a file, not a pipe: ffmpeg can write errors without blocking
        # the thread that reads the progress pipe.
        proc = subprocess.Popen(
            cmd + ["-progress", "pipe:1", "-nostats"],
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_CREATE_NO_WINDOW,
        )
        total = duration if duration is not None and duration > 0 else None
        assert proc.stdout is not None
        if on_progress is None:
            with tqdm(total=total, unit="s", leave=False, desc=desc) as bar:
                for line in proc.stdout:
                    seconds = parse_progress_line(line)
                    if seconds is None:
                        continue
                    if bar.total is not None:
                        bar.n = min(seconds, float(bar.total))
                    else:
                        bar.n = seconds
                    bar.refresh()
                returncode = proc.wait()
                if returncode == 0 and bar.total is not None:
                    bar.n = float(bar.total)
                    bar.refresh()
        else:
            for line in proc.stdout:
                if cancel is not None and cancel.is_set():
                    raise ConversionCancelled()
                seconds = parse_progress_line(line)
                if seconds is None:
                    continue
                on_progress(seconds, total)
            if cancel is not None and cancel.is_set():
                raise ConversionCancelled()
            returncode = proc.wait()
            if returncode == 0 and total is not None:
                on_progress(total, total)
        if (
            returncode == 0
            and tmp_dst.is_file()
            and tmp_dst.stat().st_size > 0
        ):
            os.replace(tmp_dst, final_dst)
            succeeded = True
            return True, ""
        assert stderr_handle is not None and stderr_path is not None
        tail = _stderr_tail(stderr_handle, stderr_path)
        stderr_handle = None
        if not tail:
            tail = f"ffmpeg exited with status {returncode}"
        return False, tail
    except KeyboardInterrupt:
        _stop_process(proc)
        _unlink_quiet(tmp_dst)
        raise
    except Exception:
        _stop_process(proc)
        _unlink_quiet(tmp_dst)
        raise
    finally:
        if proc is not None and proc.poll() is None:
            _stop_process(proc)
        if proc is not None and proc.stdout is not None:
            try:
                proc.stdout.close()
            except OSError:
                pass
        if not succeeded:
            _unlink_quiet(tmp_dst)
        if stderr_handle is not None:
            try:
                stderr_handle.close()
            except OSError:
                pass
        if stderr_path is not None:
            _unlink_quiet(Path(stderr_path))


def run_indexed(
    count: int,
    jobs: int,
    work: Callable[[int], None],
    cancel: threading.Event,
) -> list[int]:
    """Run ``work(i)`` for ``i`` in ``0..count-1`` on up to ``jobs`` threads.

    Indices still queued when ``cancel`` is set are not started. Returns those
    indices, sorted. ``jobs == 1`` runs inline on the caller thread.
    """
    if count <= 0:
        return []
    workers = max(1, min(jobs, MAX_JOBS, count))
    lock = threading.Lock()
    next_index = 0
    unstarted: list[int] = []
    first_error: list[BaseException] = []

    def loop() -> None:
        nonlocal next_index
        while True:
            with lock:
                if next_index >= count:
                    return
                index = next_index
                next_index += 1
                if cancel.is_set():
                    unstarted.append(index)
                    continue
            try:
                work(index)
            except BaseException as exc:
                with lock:
                    if not first_error:
                        first_error.append(exc)
                cancel.set()
                return

    if workers == 1:
        loop()
    else:
        threads = [
            threading.Thread(target=loop, daemon=True) for _ in range(workers)
        ]
        for thread in threads:
            thread.start()
        try:
            for thread in threads:
                while thread.is_alive():
                    thread.join(0.2)
        except KeyboardInterrupt:
            cancel.set()
            for thread in threads:
                while thread.is_alive():
                    thread.join(0.2)
            raise
    if first_error:
        raise first_error[0]
    return sorted(unstarted)


def convert_one(
    src: Path,
    final_dst: Path,
    opts: Options,
    ffmpeg: str,
    ffprobe: str,
    *,
    log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[float, Optional[float]], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> tuple[str, str]:
    """Convert one clip. Returns ``(status, error)`` with status ok, skipped, or failed.

    ``log`` replaces ``tqdm.write`` when the caller has no console. ``cancel``
    raises ``ConversionCancelled`` instead of reporting a failure.
    """
    emit = log or tqdm.write
    if final_dst.exists() and not opts.overwrite:
        emit(f"skipped (exists): {final_dst}")
        return "skipped", ""
    if cancel is not None and cancel.is_set():
        raise ConversionCancelled()
    try:
        _claim_dir(final_dst.parent)
    except OSError as exc:
        message = str(exc)
        emit(f"failed: {src}: {message}")
        return "failed", message
    cleanup = False
    try:
        try:
            info = probe(src, ffprobe)
        except ProbeError as exc:
            message = _without_path_prefix(src, str(exc))
            cleanup = True
            emit(f"failed: {src}: {message}")
            return "failed", message
        except OSError as exc:
            message = str(exc)
            cleanup = True
            emit(f"failed: {src}: {message}")
            return "failed", message
        if opts.deinterlace and not info.interlaced:
            emit(f"note: {src.name} is progressive; skipping deinterlace")
        tmp_dst = final_dst.with_name(final_dst.name + ".part")
        cmd = build_command(ffmpeg, src, tmp_dst, opts, info, force=True)
        try:
            ok, err = run_ffmpeg(
                cmd,
                final_dst,
                tmp_dst,
                _bar_total(info, opts),
                src.name,
                on_progress=on_progress,
                cancel=cancel,
            )
        except KeyboardInterrupt:
            raise
        except ConversionCancelled:
            cleanup = True
            raise
        except OSError as exc:
            cleanup = True
            emit(f"failed: {src}: {exc}")
            return "failed", str(exc)
        except Exception as exc:
            cleanup = True
            emit(f"failed: {src}: {exc}")
            return "failed", str(exc)
        if ok:
            emit(f"wrote {final_dst}")
            return "ok", ""
        cleanup = True
        emit(f"failed: {src}: {err}")
        return "failed", err
    finally:
        _release_dir(final_dst.parent, remove_if_empty=cleanup)

def build_parser() -> argparse.ArgumentParser:
    class _Formatter(
        argparse.ArgumentDefaultsHelpFormatter,
        argparse.RawDescriptionHelpFormatter,
    ):
        pass

    parser = argparse.ArgumentParser(
        prog="mts_to_dnxhr.py",
        description=(
            "Convert AVCHD .MTS/.M2TS clips to DNxHR intermediates "
            "that DaVinci Resolve can import, scrub, and play with audio."
        ),
        formatter_class=_Formatter,
        epilog=(
            "examples:\n"
            '  python mts_to_dnxhr.py "samples/01 American Landscape.MTS"\n'
            "  python mts_to_dnxhr.py ./footage/\n"
            "  python mts_to_dnxhr.py ./footage/ --recursive -o ./converted/\n"
            "  python mts_to_dnxhr.py ./footage/ --profile dnxhr_hq "
            "--container mxf --audio-bit-depth 24\n"
            "\n"
            "exit codes: 0 every file converted or skipped, "
            "1 at least one file failed, "
            "2 usage or preflight error, "
            "130 interrupted"
        ),
    )
    parser.add_argument("input", help="Input .MTS/.M2TS file, or a folder of clips")
    parser.add_argument("-o", "--output", metavar="DIR", help="Output directory")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search subfolders. Output mirrors those subfolders",
    )
    parser.add_argument(
        "-p",
        "--profile",
        choices=list(PROFILES),
        default="dnxhr_hqx",
        help="DNxHR profile",
    )
    parser.add_argument(
        "-c",
        "--container",
        choices=list(CONTAINERS),
        default="mov",
        help="Output container",
    )
    parser.add_argument(
        "--audio-bit-depth",
        type=int,
        choices=sorted(AUDIO_CODECS),
        default=16,
        help="PCM bit depth. 24 has more headroom for grading",
    )
    parser.add_argument(
        "--deinterlace",
        action="store_true",
        help="Deinterlace interlaced sources with yadif, keeping the original frame rate",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output files",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg command for each file and do not encode",
    )
    parser.add_argument(
        "--duration",
        type=float,
        metavar="SECONDS",
        help="Encode only the first N seconds (testing aid)",
    )
    return parser


def _print_header(
    inputs: list[Path],
    skipped: int,
    opts: Options,
    out_dir: Path,
) -> None:
    print(f"inputs: {len(inputs)}")
    print(f"skipped non-MTS: {skipped}")
    print(f"profile: {opts.profile}")
    print(f"container: {opts.container}")
    print(f"audio: {AUDIO_CODECS[opts.audio_bit_depth]}")
    print(f"output: {out_dir}")


def _report_collisions(collisions: dict[Path, list[Path]]) -> None:
    print("error: output path collision:", file=sys.stderr)
    for dst, srcs in collisions.items():
        print(f"  {dst}", file=sys.stderr)
        for src in srcs:
            print(f"    {src}", file=sys.stderr)


def _dry_run(
    pairs: list[tuple[Path, Path]],
    opts: Options,
    ffmpeg: Optional[str],
    ffprobe: Optional[str],
) -> int:
    if ffprobe is None and opts.deinterlace:
        print(
            "note: ffprobe not found; including yadif because --deinterlace is set. "
            "deint=interlaced is a no-op on progressive frames."
        )
    elif ffprobe is None:
        print("note: ffprobe not found; field order is unknown, so -field_order is omitted.")
    ffmpeg_bin = _command_tool(ffmpeg)
    for src, dst in pairs:
        if dst.exists() and not opts.overwrite:
            print(f"skip (exists): {dst}")
        info: Optional[ProbeInfo] = None
        if ffprobe is not None:
            try:
                info = probe(src, ffprobe)
            except ProbeError as exc:
                print(f"note: probe failed for {src}: {exc}")
        if info is not None and opts.deinterlace and not info.interlaced:
            print(f"note: {src.name} is progressive; skipping deinterlace")
        elif info is None and opts.deinterlace and ffprobe is not None:
            print(
                f"note: {src.name}: including yadif without probe data; "
                "it is a no-op on progressive frames."
            )
        cmd = build_command(ffmpeg_bin, src, dst, opts, info, force=opts.overwrite)
        print(format_command(cmd))
    return 0


def _encode_all(
    pairs: list[tuple[Path, Path]],
    opts: Options,
    ffmpeg: str,
    ffprobe: str,
) -> int:
    converted = 0
    skipped = 0
    failed = 0
    failures: list[tuple[Path, str]] = []
    try:
        with tqdm(pairs, unit="file", desc="files") as bar:
            for src, dst in bar:
                status, err = convert_one(src, dst, opts, ffmpeg, ffprobe)
                if status == "ok":
                    converted += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1
                    failures.append((src, err))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    print(f"converted {converted}, skipped {skipped}, failed {failed}")
    for src, err in failures:
        print(f"failed: {src}")
        if err:
            print(err)
    return 1 if failed else 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.duration is not None and (
        not math.isfinite(args.duration) or args.duration <= 0
    ):
        print("error: --duration must be a positive number of seconds", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"error: path does not exist: {input_path}", file=sys.stderr)
        return 2
    try:
        inputs, skipped = discover_inputs(input_path, args.recursive)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not inputs:
        print(
            "error: no .MTS/.M2TS files found (use --recursive?)",
            file=sys.stderr,
        )
        return 2

    out_dir = (
        Path(args.output).resolve()
        if args.output
        else default_output_dir(input_path)
    )
    try:
        pairs = [
            (src, output_path_for(src, input_path, out_dir, args.container))
            for src in inputs
        ]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    collisions = find_collisions(pairs)
    if collisions:
        _report_collisions(collisions)
        return 2

    opts = Options(
        profile=args.profile,
        container=args.container,
        audio_bit_depth=args.audio_bit_depth,
        deinterlace=args.deinterlace,
        overwrite=args.overwrite,
        duration=args.duration,
    )
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not args.dry_run and (ffmpeg is None or ffprobe is None):
        print(INSTALL_HINT, file=sys.stderr)
        return 2

    _print_header(inputs, skipped, opts, out_dir)
    if args.dry_run:
        return _dry_run(pairs, opts, ffmpeg, ffprobe)
    assert ffmpeg is not None and ffprobe is not None
    return _encode_all(pairs, opts, ffmpeg, ffprobe)


if __name__ == "__main__":
    sys.exit(main())
