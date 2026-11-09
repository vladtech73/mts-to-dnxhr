"""Unit tests for mts_to_dnxhr. The smoke test encodes a real sample when opted in."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

import mts_to_dnxhr as m

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_PROBE = """
{
  "streams": [
    {"codec_type": "audio", "avg_frame_rate": "0/0"},
    {
      "codec_type": "video",
      "field_order": "tt",
      "avg_frame_rate": "30000/1001"
    }
  ],
  "format": {"duration": "168.192000"}
}
"""

VIDEO_ONLY_PROBE = """
{
  "streams": [
    {
      "codec_type": "video",
      "field_order": "tt",
      "avg_frame_rate": "30000/1001"
    }
  ],
  "format": {"duration": "1.000000"}
}
"""

UNKNOWN_FIELD_PROBE = """
{
  "streams": [
    {
      "codec_type": "video",
      "field_order": "unknown",
      "avg_frame_rate": "30000/1001"
    },
    {"codec_type": "audio", "avg_frame_rate": "0/0"}
  ],
  "format": {"duration": "1.5"}
}
"""


def _opts(**overrides: object) -> m.Options:
    values = {
        "profile": "dnxhr_hqx",
        "container": "mov",
        "audio_bit_depth": 16,
        "deinterlace": False,
        "overwrite": False,
        "duration": None,
    }
    values.update(overrides)
    return m.Options(**values)  # type: ignore[arg-type]


def _interlaced(**overrides: object) -> m.ProbeInfo:
    values = {
        "duration": 168.192,
        "field_order": "tt",
        "avg_frame_rate": "30000/1001",
        "has_audio": True,
    }
    values.update(overrides)
    return m.ProbeInfo(**values)  # type: ignore[arg-type]


def _assert_sequence(test: unittest.TestCase, cmd: list[str], seq: list[str]) -> None:
    for index in range(len(cmd) - len(seq) + 1):
        if cmd[index : index + len(seq)] == seq:
            return
    test.fail(f"{seq!r} not found in {cmd!r}")


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "A.MTS").write_bytes(b"")
        (self.root / "b.mts").write_bytes(b"")
        (self.root / "c.M2TS").write_bytes(b"")
        (self.root / "d.m2ts").write_bytes(b"")
        (self.root / "notes.txt").write_bytes(b"")
        (self.root / "00000.CPI").write_bytes(b"")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "00000.MTS").write_bytes(b"")
        (self.root / "sub" / "notes.txt").write_bytes(b"")
        (self.root / "sub2").mkdir()
        (self.root / "sub2" / "00000.MTS").write_bytes(b"")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_find_inputs_non_recursive_skips_sidecars_and_subfolders(self) -> None:
        found = m.find_inputs(self.root, recursive=False)
        self.assertEqual(
            [path.name for path in found],
            ["A.MTS", "b.mts", "c.M2TS", "d.m2ts"],
        )
        _inputs, skipped = m.discover_inputs(self.root, recursive=False)
        self.assertEqual(skipped, 2)

    def test_find_inputs_recursive(self) -> None:
        found = {
            path.relative_to(self.root).as_posix()
            for path in m.find_inputs(self.root, recursive=True)
        }
        self.assertEqual(
            found,
            {
                "A.MTS",
                "b.mts",
                "c.M2TS",
                "d.m2ts",
                "sub/00000.MTS",
                "sub2/00000.MTS",
            },
        )
        _inputs, skipped = m.discover_inputs(self.root, recursive=True)
        self.assertEqual(skipped, 3)

    def test_file_argument_and_rejected_extension(self) -> None:
        clip = self.root / "A.MTS"
        self.assertEqual(m.find_inputs(clip, recursive=False), [clip])
        with self.assertRaises(ValueError) as caught:
            m.find_inputs(self.root / "notes.txt", recursive=False)
        self.assertIn("not an .MTS/.M2TS file", str(caught.exception))

    def test_output_paths_mirror_subfolders_and_trailing_slash(self) -> None:
        out = self.root / "out"
        nested = self.root / "sub" / "00000.MTS"
        other = self.root / "sub2" / "00000.MTS"
        nested_out = m.output_path_for(nested, self.root, out, "mov")
        other_out = m.output_path_for(other, self.root, out, "mov")
        self.assertEqual(nested_out, out / "sub" / "00000.mov")
        self.assertEqual(other_out, out / "sub2" / "00000.mov")
        self.assertEqual(m.find_collisions([(nested, nested_out), (other, other_out)]), {})

        clip = self.root / "A.MTS"
        self.assertEqual(
            m.output_path_for(clip, clip, self.root / "dnxhr", "mxf"),
            self.root / "dnxhr" / "A.mxf",
        )
        self.assertEqual(m.default_output_dir(clip), self.root / "dnxhr")

        footage = self.root / "footage"
        footage.mkdir()
        slashed = Path(str(footage) + os.sep)
        self.assertEqual(m.default_output_dir(slashed), self.root / "footage_dnxhr")

    def test_collisions_are_case_insensitive_on_windows(self) -> None:
        out = self.root / "out"
        upper = self.root / "A.MTS"
        transport = self.root / "A.M2TS"
        pairs = [
            (upper, m.output_path_for(upper, self.root, out, "mov")),
            (transport, m.output_path_for(transport, self.root, out, "mov")),
        ]
        collisions = m.find_collisions(pairs)
        self.assertEqual(len(collisions), 1)
        sources = next(iter(collisions.values()))
        self.assertEqual({path.name for path in sources}, {"A.MTS", "A.M2TS"})

    def test_symlink_inside_folder_maps_under_that_folder(self) -> None:
        link_dir = self.root / "linked"
        link_dir.mkdir()
        link = link_dir / "via_link.MTS"
        try:
            link.symlink_to(self.root / "A.MTS")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")
        if not link.is_symlink():
            self.skipTest("symlinks are not available")

        found = m.find_inputs(self.root, recursive=True)
        self.assertTrue(any(path.name == "via_link.MTS" for path in found))
        mapped = m.output_path_for(link, self.root, self.root / "out", "mov")
        self.assertEqual(mapped, self.root / "out" / "linked" / "via_link.mov")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("mts_to_dnxhr.find_tool", return_value=None), contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            code = m.main(
                [str(self.root), "--recursive", "--dry-run", "-o", str(self.root / "out")]
            )
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("via_link.mov", stdout.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_clip_outside_the_input_folder_is_a_preflight_error(self) -> None:
        outside = self.root / "A.MTS"
        folder = self.root / "sub"
        with self.assertRaises(ValueError) as caught:
            m.output_path_for(outside, folder, self.root / "out", "mov")
        self.assertIn("not inside the input folder", str(caught.exception))

        stderr = io.StringIO()
        with mock.patch(
            "mts_to_dnxhr.discover_inputs", return_value=([outside], 0)
        ), contextlib.redirect_stderr(stderr):
            code = m.main([str(folder), "--dry-run"])
        self.assertEqual(code, 2)
        self.assertIn("not inside the input folder", stderr.getvalue())


class ProbeAndProgressTests(unittest.TestCase):
    def test_parse_progress_line(self) -> None:
        self.assertAlmostEqual(m.parse_progress_line("out_time_us=967633"), 0.967633)
        self.assertEqual(m.parse_progress_line("out_time_ms=1000000"), 1.0)
        self.assertIsNone(m.parse_progress_line("out_time_us=N/A"))
        self.assertIsNone(m.parse_progress_line("frame=30"))

    def test_parse_probe_json_audio_before_video(self) -> None:
        info = m.parse_probe_json(SAMPLE_PROBE)
        self.assertEqual(info.duration, float("168.192000"))
        self.assertEqual(info.field_order, "tt")
        self.assertEqual(info.avg_frame_rate, "30000/1001")
        self.assertTrue(info.has_audio)
        self.assertTrue(info.interlaced)

    def test_parse_probe_json_video_only_and_unknown_field_order(self) -> None:
        video_only = m.parse_probe_json(VIDEO_ONLY_PROBE)
        self.assertFalse(video_only.has_audio)
        self.assertEqual(video_only.field_order, "tt")

        unknown = m.parse_probe_json(UNKNOWN_FIELD_PROBE)
        self.assertIsNone(unknown.field_order)
        self.assertFalse(unknown.interlaced)
        self.assertTrue(unknown.has_audio)
        self.assertEqual(unknown.avg_frame_rate, "30000/1001")

    def test_unparseable_duration_is_none(self) -> None:
        info = m.parse_probe_json(
            '{"streams": [{"codec_type": "video"}], "format": {"duration": "nope"}}'
        )
        self.assertIsNone(info.duration)
        self.assertFalse(info.has_audio)


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.src = Path("C:/My Clips/clip.MTS")
        self.dst = Path("C:/My Clips/out/clip.mov")

    def test_default_hqx_mov_argv(self) -> None:
        cmd = m.build_command("ffmpeg", self.src, self.dst, _opts(), _interlaced(), False)
        _assert_sequence(
            self,
            cmd,
            [
                "-profile:v",
                "dnxhr_hqx",
                "-pix_fmt",
                "yuv422p10le",
                "-c:a",
                "pcm_s16le",
                "-ar",
                "48000",
                "-f",
                "mov",
            ],
        )
        self.assertNotIn("-progress", cmd)
        self.assertNotIn("-r", cmd)
        self.assertEqual(cmd[cmd.index("-i") + 1], str(self.src.resolve()))
        self.assertEqual(cmd[-1], str(self.dst.resolve()))
        self.assertGreater(len(cmd[cmd.index("-i") + 1].split(" ")), 1)

    def test_profile_pixel_formats_audio_depth_and_mxf(self) -> None:
        hq = m.build_command(
            "ffmpeg",
            self.src,
            self.dst,
            _opts(profile="dnxhr_hq"),
            _interlaced(),
            False,
        )
        self.assertIn("yuv422p", hq)
        self.assertNotIn("yuv422p10le", hq)

        four = m.build_command(
            "ffmpeg",
            self.src,
            self.dst.with_suffix(".mxf"),
            _opts(profile="dnxhr_444", container="mxf", audio_bit_depth=24),
            _interlaced(),
            False,
        )
        _assert_sequence(
            self,
            four,
            ["-profile:v", "dnxhr_444", "-pix_fmt", "yuv444p10le", "-c:a", "pcm_s24le"],
        )
        self.assertIn("-f", four)
        self.assertEqual(four[four.index("-f") + 1], "mxf")

    def test_deinterlace_and_field_order(self) -> None:
        deint = m.build_command(
            "ffmpeg",
            self.src,
            self.dst,
            _opts(deinterlace=True),
            _interlaced(),
            False,
        )
        self.assertIn(m.YADIF, deint)
        self.assertNotIn("-field_order", deint)

        woven = m.build_command(
            "ffmpeg",
            self.src,
            self.dst,
            _opts(deinterlace=False),
            _interlaced(),
            False,
        )
        self.assertNotIn(m.YADIF, woven)
        self.assertEqual(woven[woven.index("-field_order") + 1], "tt")

        progressive = m.build_command(
            "ffmpeg",
            self.src,
            self.dst,
            _opts(deinterlace=True),
            _interlaced(field_order=None),
            False,
        )
        self.assertNotIn(m.YADIF, progressive)
        self.assertNotIn("-field_order", progressive)

        unprobed = m.build_command(
            "ffmpeg",
            self.src,
            self.dst,
            _opts(deinterlace=True),
            None,
            False,
        )
        self.assertIn(m.YADIF, unprobed)

    def test_force_flag_and_duration(self) -> None:
        forced = m.build_command("ffmpeg", self.src, self.dst, _opts(), None, True)
        self.assertIn("-y", forced)
        self.assertNotIn("-n", forced)
        self.assertEqual(forced[forced.index("-i") - 1], "-y")

        protected = m.build_command(
            "ffmpeg",
            self.src,
            self.dst,
            _opts(duration=3),
            None,
            False,
        )
        self.assertIn("-n", protected)
        self.assertNotIn("-y", protected)
        self.assertEqual(protected[protected.index("-i") - 1], "-n")
        self.assertEqual(protected[protected.index("-t") + 1], "3")

    def test_windows_quoting_of_optional_map(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows quoting")
        text = m.format_command(["ffmpeg", "-map", "0:a?", "-i", r"C:\Clips\a.MTS"])
        self.assertIn('"0:a?"', text)


class JobsTests(unittest.TestCase):
    def test_suggested_jobs_table(self) -> None:
        expected = {
            0: 1,
            4: 1,
            8: 1,
            11: 1,
            12: 2,
            16: 2,
            18: 2,
            20: 2,
            128: 2,
        }
        for cpu_count, jobs in expected.items():
            self.assertEqual(m.suggested_jobs(cpu_count), jobs)
            self.assertLessEqual(jobs, m.MAX_JOBS)

    def test_suggested_jobs_reads_cpu_count_when_omitted(self) -> None:
        with mock.patch("mts_to_dnxhr.os.cpu_count", return_value=None):
            self.assertEqual(m.suggested_jobs(), 1)
            self.assertEqual(m.suggested_jobs(None), 1)
        with mock.patch("mts_to_dnxhr.os.cpu_count", return_value=20):
            self.assertEqual(m.suggested_jobs(), 2)
            self.assertEqual(m.suggested_jobs(None), 2)

    def test_run_indexed_bounds_in_flight_and_covers_every_index(self) -> None:
        cancel = threading.Event()
        lock = threading.Lock()
        in_flight = 0
        max_in_flight = 0
        seen: list[int] = []

        def work(index: int) -> None:
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                if in_flight > max_in_flight:
                    max_in_flight = in_flight
                seen.append(index)
            time.sleep(0.02)
            with lock:
                in_flight -= 1

        m.run_indexed(8, 3, work, cancel)
        self.assertEqual(max_in_flight, 3)
        self.assertEqual(sorted(seen), list(range(8)))

    def test_run_indexed_overlaps(self) -> None:
        barrier = threading.Barrier(2, timeout=5)
        cancel = threading.Event()

        def work(_index: int) -> None:
            barrier.wait()

        m.run_indexed(2, 2, work, cancel)

    def test_jobs_above_cap_are_clamped(self) -> None:
        cancel = threading.Event()
        lock = threading.Lock()
        in_flight = 0
        max_in_flight = 0

        def work(_index: int) -> None:
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                if in_flight > max_in_flight:
                    max_in_flight = in_flight
            time.sleep(0.02)
            with lock:
                in_flight -= 1

        m.run_indexed(8, 99, work, cancel)
        self.assertLessEqual(max_in_flight, m.MAX_JOBS)

    def test_jobs_one_runs_inline_in_order(self) -> None:
        caller = threading.current_thread()
        order: list[int] = []
        cancel = threading.Event()

        def work(index: int) -> None:
            self.assertIs(threading.current_thread(), caller)
            order.append(index)

        self.assertEqual(m.run_indexed(0, 2, work, cancel), [])
        m.run_indexed(4, 1, work, cancel)
        self.assertEqual(order, [0, 1, 2, 3])

    def test_cancel_during_work_jobs_one_returns_the_rest(self) -> None:
        cancel = threading.Event()
        ran: list[int] = []

        def work(index: int) -> None:
            ran.append(index)
            if index == 1:
                cancel.set()

        unstarted = m.run_indexed(5, 1, work, cancel)
        self.assertEqual(ran, [0, 1])
        self.assertEqual(unstarted, [2, 3, 4])

    def test_cancel_during_work_jobs_two_partitions_indices(self) -> None:
        cancel = threading.Event()
        lock = threading.Lock()
        ran: list[int] = []

        def work(index: int) -> None:
            with lock:
                ran.append(index)
            if index == 1:
                cancel.set()

        count = 6
        unstarted = m.run_indexed(count, 2, work, cancel)
        self.assertEqual(sorted(ran + unstarted), list(range(count)))
        self.assertEqual(len(set(ran) & set(unstarted)), 0)

    def test_cancel_already_set_runs_nothing(self) -> None:
        cancel = threading.Event()
        cancel.set()
        calls: list[int] = []

        def work(index: int) -> None:
            calls.append(index)

        self.assertEqual(m.run_indexed(4, 2, work, cancel), [0, 1, 2, 3])
        self.assertEqual(calls, [])

    def test_exception_is_reraised_and_sets_cancel(self) -> None:
        cancel = threading.Event()

        def work(index: int) -> None:
            if index == 0:
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            m.run_indexed(3, 2, work, cancel)
        self.assertTrue(cancel.is_set())


class CliTests(unittest.TestCase):
    def test_help_lists_flags_and_defaults(self) -> None:
        parser = m.build_parser()
        help_text = parser.format_help()
        for flag in (
            "--output",
            "--recursive",
            "--profile",
            "--container",
            "--audio-bit-depth",
            "--deinterlace",
            "--overwrite",
            "--dry-run",
            "--duration",
            "--jobs",
        ):
            self.assertIn(flag, help_text)
        self.assertIn("testing aid", help_text)
        args = parser.parse_args(["clip.MTS"])
        self.assertEqual(args.profile, "dnxhr_hqx")
        self.assertEqual(args.container, "mov")
        self.assertEqual(args.audio_bit_depth, 16)
        self.assertFalse(args.deinterlace)
        self.assertFalse(args.overwrite)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.jobs, 1)

    def test_dry_run_without_ffmpeg_prints_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            clip = root / "clip.MTS"
            clip.write_bytes(b"")
            (root / "notes.txt").write_bytes(b"")
            stdout = io.StringIO()
            with mock.patch("mts_to_dnxhr.find_tool", return_value=None), contextlib.redirect_stdout(
                stdout
            ):
                code = m.main([str(clip), "--dry-run"])
            text = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("-n -i", text)
            self.assertIn("dnxhr_hqx", text)
            self.assertIn("yuv422p10le", text)
            self.assertIn("pcm_s16le", text)
            self.assertFalse((root / "dnxhr").exists())

    def test_header_prints_jobs_and_above_suggestion_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp).resolve() / "clip.MTS"
            clip.write_bytes(b"")
            for jobs, suggested, expect_note in ((1, 1, False), (2, 1, True), (2, 2, False)):
                stdout = io.StringIO()
                with mock.patch("mts_to_dnxhr.find_tool", return_value=None), mock.patch(
                    "mts_to_dnxhr.suggested_jobs", return_value=suggested
                ), contextlib.redirect_stdout(stdout):
                    code = m.main([str(clip), "--dry-run", "--jobs", str(jobs)])
                text = stdout.getvalue()
                self.assertEqual(code, 0)
                self.assertIn(f"jobs: {jobs}", text)
                self.assertEqual("note: --jobs" in text, expect_note)

    def test_dry_run_overwrite_flag_matches_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            clip = root / "clip.MTS"
            clip.write_bytes(b"")
            out_dir = root / "dest"
            out_dir.mkdir()
            existing = out_dir / "clip.mov"
            existing.write_bytes(b"keep")
            with mock.patch("mts_to_dnxhr.find_tool", return_value=None):
                protected = io.StringIO()
                with contextlib.redirect_stdout(protected):
                    code = m.main([str(clip), "-o", str(out_dir), "--dry-run"])
                self.assertEqual(code, 0)
                self.assertIn("-n -i", protected.getvalue())
                self.assertNotIn("-y -i", protected.getvalue())
                self.assertIn("skip (exists):", protected.getvalue())

                replaced = io.StringIO()
                with contextlib.redirect_stdout(replaced):
                    code = m.main(
                        [str(clip), "-o", str(out_dir), "--dry-run", "--overwrite"]
                    )
                self.assertEqual(code, 0)
                self.assertIn("-y -i", replaced.getvalue())
                self.assertNotIn("-n -i", replaced.getvalue())
            self.assertEqual(existing.read_bytes(), b"keep")

    def test_missing_path_bad_extension_and_empty_dir_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            missing = io.StringIO()
            with contextlib.redirect_stderr(missing):
                self.assertEqual(m.main([str(root / "does-not-exist")]), 2)
            self.assertIn("does not exist", missing.getvalue())

            notes = root / "notes.txt"
            notes.write_text("x", encoding="utf-8")
            rejected = io.StringIO()
            with contextlib.redirect_stderr(rejected):
                self.assertEqual(m.main([str(notes)]), 2)
            self.assertIn("not an .MTS/.M2TS file", rejected.getvalue())

            empty = root / "empty"
            empty.mkdir()
            none = io.StringIO()
            with contextlib.redirect_stderr(none):
                self.assertEqual(m.main([str(empty)]), 2)
            self.assertIn("no .MTS/.M2TS files found (use --recursive?)", none.getvalue())

    def test_bare_ffmpeg_name_when_path_matches_which(self) -> None:
        self.assertEqual(m._command_tool(None), "ffmpeg")
        located = shutil.which("ffmpeg")
        if located:
            self.assertEqual(m._command_tool(located), "ffmpeg")
        other = r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"
        if located is None or os.path.normcase(os.path.normpath(located)) != os.path.normcase(
            os.path.normpath(other)
        ):
            self.assertEqual(m._command_tool(other), other)

    def test_mkdir_oserror_fails_the_file_and_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / "clip.MTS"
            src.write_bytes(b"")
            dst = root / "out" / "clip.mov"
            with mock.patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
                status, err = m.convert_one(src, dst, _opts(), "ffmpeg", "ffprobe")
            self.assertEqual(status, "failed")
            self.assertIn("denied", err)

    def test_probe_error_strips_duplicate_path_and_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / "clip.MTS"
            src.write_bytes(b"")
            dst = root / "out" / "clip.mov"
            detail = f"{src.resolve()}: Invalid data found when processing input"
            with mock.patch("mts_to_dnxhr.probe", side_effect=m.ProbeError(detail)):
                status, err = m.convert_one(src, dst, _opts(), "ffmpeg", "ffprobe")
            self.assertEqual(status, "failed")
            self.assertEqual(err, "Invalid data found when processing input")
            self.assertFalse(dst.parent.exists())

    def test_shared_parent_survives_sibling_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src_a = root / "a.MTS"
            src_b = root / "b.MTS"
            src_a.write_bytes(b"")
            src_b.write_bytes(b"")
            dst_a = root / "out" / "a.mov"
            dst_b = root / "out" / "b.mov"
            b_in_probe = threading.Event()
            release_b = threading.Event()

            def fake_probe(src: Path, _ffprobe: str) -> m.ProbeInfo:
                if src.name == "b.MTS":
                    b_in_probe.set()
                    if not release_b.wait(timeout=5):
                        raise m.ProbeError("timed out waiting to release b")
                    raise m.ProbeError("b failed")
                if not b_in_probe.wait(timeout=5):
                    raise m.ProbeError("timed out waiting for b")
                raise m.ProbeError("a failed")

            results: dict[str, tuple[str, str]] = {}

            def run(name: str, src: Path, dst: Path) -> None:
                results[name] = m.convert_one(
                    src,
                    dst,
                    _opts(),
                    "ffmpeg",
                    "ffprobe",
                    log=lambda _line: None,
                )

            with mock.patch("mts_to_dnxhr.probe", side_effect=fake_probe):
                thread_a = threading.Thread(target=run, args=("a", src_a, dst_a))
                thread_b = threading.Thread(target=run, args=("b", src_b, dst_b))
                thread_a.start()
                thread_b.start()
                thread_a.join(timeout=5)
                self.assertFalse(thread_a.is_alive())
                self.assertEqual(results["a"][0], "failed")
                self.assertTrue(dst_a.parent.exists())
                release_b.set()
                thread_b.join(timeout=5)
                self.assertFalse(thread_b.is_alive())
                self.assertEqual(results["b"][0], "failed")
                self.assertFalse(dst_b.parent.exists())
                self.assertEqual(m._dir_users, {})

    def test_collision_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "A.MTS").write_bytes(b"")
            (root / "A.M2TS").write_bytes(b"")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = m.main([str(root), "--dry-run"])
            self.assertEqual(code, 2)
            self.assertIn("collision", stderr.getvalue())

    def test_jobs_outside_range_exit_2(self) -> None:
        parser = m.build_parser()
        for bad in ("0", "5", "x"):
            with self.assertRaises(SystemExit) as caught:
                with contextlib.redirect_stderr(io.StringIO()):
                    parser.parse_args(["clip.MTS", "--jobs", bad])
            self.assertEqual(caught.exception.code, 2)

    def test_encode_all_jobs_two_ok_failed_and_cancelled(self) -> None:
        pairs = [(Path("a.MTS"), Path("a.mov")), (Path("b.MTS"), Path("b.mov"))]
        opts = _opts()

        def check_parallel(*_args: object, **kwargs: object) -> None:
            self.assertIsNotNone(kwargs.get("on_progress"))
            self.assertIsNotNone(kwargs.get("cancel"))

        barrier = threading.Barrier(2, timeout=5)

        def ok_convert(*args: object, **kwargs: object) -> tuple[str, str]:
            check_parallel(*args, **kwargs)
            barrier.wait()
            return "ok", ""

        with mock.patch("mts_to_dnxhr.convert_one", side_effect=ok_convert):
            code = m._encode_all(pairs, opts, "ffmpeg", "ffprobe", jobs=2)
        self.assertEqual(code, 0)

        fail_barrier = threading.Barrier(2, timeout=5)

        def fail_convert(*args: object, **kwargs: object) -> tuple[str, str]:
            check_parallel(*args, **kwargs)
            fail_barrier.wait()
            src = args[0]
            assert isinstance(src, Path)
            if src.name == "b.MTS":
                return "failed", "nope"
            return "ok", ""

        stdout = io.StringIO()
        with mock.patch("mts_to_dnxhr.convert_one", side_effect=fail_convert):
            with contextlib.redirect_stdout(stdout):
                code = m._encode_all(pairs, opts, "ffmpeg", "ffprobe", jobs=2)
        text = stdout.getvalue()
        self.assertEqual(code, 1)
        summary_at = text.find("converted 1, skipped 0, failed 1")
        failed_at = text.find("failed: b.MTS")
        self.assertGreater(summary_at, -1)
        self.assertGreater(failed_at, summary_at)
        self.assertIn("nope", text[failed_at:])

        def cancel_convert(*args: object, **kwargs: object) -> tuple[str, str]:
            check_parallel(*args, **kwargs)
            src = args[0]
            assert isinstance(src, Path)
            if src.name == "b.MTS":
                raise m.ConversionCancelled()
            return "ok", ""

        stdout = io.StringIO()
        with mock.patch("mts_to_dnxhr.convert_one", side_effect=cancel_convert):
            with contextlib.redirect_stdout(stdout):
                code = m._encode_all(pairs, opts, "ffmpeg", "ffprobe", jobs=2)
        self.assertEqual(code, 0)
        self.assertIn("converted 1, skipped 0, failed 0", stdout.getvalue())
        self.assertNotIn("failed: b.MTS", stdout.getvalue())

    def test_jobs_one_omits_on_progress(self) -> None:
        def fake_convert(*_args: object, **kwargs: object) -> tuple[str, str]:
            self.assertIsNone(kwargs.get("on_progress"))
            return "ok", ""

        with mock.patch("mts_to_dnxhr.convert_one", side_effect=fake_convert) as convert:
            code = m._encode_all(
                [(Path("a.MTS"), Path("a.mov"))],
                _opts(),
                "ffmpeg",
                "ffprobe",
                jobs=1,
            )
        self.assertEqual(code, 0)
        self.assertIsNone(convert.call_args.kwargs.get("on_progress"))


class _FakeFfmpeg:
    """Popen stand-in. ``poll`` stays ``None`` until terminate or kill."""

    def __init__(self, tmp_dst: Path, script: str) -> None:
        self.stdout = io.StringIO(script)
        self.stderr = None
        self.returncode: Optional[int] = None
        self._stopped = False
        self.terminate_calls = 0
        self.kill_calls = 0
        tmp_dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst.write_bytes(b"encoded")

    def poll(self) -> Optional[int]:
        if self._stopped:
            return 1
        return None

    def wait(self, timeout: Optional[float] = None) -> int:
        if self._stopped:
            self.returncode = 1
            return 1
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._stopped = True
        self.returncode = 1

    def kill(self) -> None:
        self.kill_calls += 1
        self._stopped = True
        self.returncode = 1


_PROGRESS_SCRIPT = "out_time_us=500000\nout_time_us=1000000\nprogress=end\n"


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _paths(self) -> tuple[Path, Path]:
        final = self.root / "out" / "clip.mov"
        part = final.with_name(final.name + ".part")
        final.parent.mkdir(parents=True, exist_ok=True)
        return final, part

    def test_on_progress_renames_part_and_skips_tqdm(self) -> None:
        final, part = self._paths()
        calls: list[tuple[float, Optional[float]]] = []

        def on_progress(seconds: float, total: Optional[float]) -> None:
            calls.append((seconds, total))

        proc = _FakeFfmpeg(part, _PROGRESS_SCRIPT)

        def refuse_tqdm(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("tqdm should not be constructed")

        with mock.patch("mts_to_dnxhr.subprocess.Popen", return_value=proc) as popen:
            with mock.patch("mts_to_dnxhr.tqdm", side_effect=refuse_tqdm):
                ok, err = m.run_ffmpeg(
                    ["ffmpeg", "-i", "in.mts", str(part)],
                    final,
                    part,
                    2.0,
                    "clip",
                    on_progress=on_progress,
                    cancel=None,
                )
        self.assertEqual(calls, [(0.5, 2.0), (1.0, 2.0), (2.0, 2.0)])
        self.assertEqual((ok, err), (True, ""))
        self.assertFalse(part.exists())
        self.assertTrue(final.is_file())
        self.assertGreater(final.stat().st_size, 0)
        self.assertEqual(popen.call_args.kwargs.get("creationflags"), m._CREATE_NO_WINDOW)

    def test_on_progress_omits_final_callback_when_duration_unknown(self) -> None:
        final, part = self._paths()
        calls: list[tuple[float, Optional[float]]] = []

        def on_progress(seconds: float, total: Optional[float]) -> None:
            calls.append((seconds, total))

        proc = _FakeFfmpeg(part, _PROGRESS_SCRIPT)
        with mock.patch("mts_to_dnxhr.subprocess.Popen", return_value=proc):
            with mock.patch("mts_to_dnxhr.tqdm", side_effect=AssertionError("tqdm")):
                ok, err = m.run_ffmpeg(
                    ["ffmpeg"],
                    final,
                    part,
                    None,
                    "clip",
                    on_progress=on_progress,
                )
        self.assertEqual(calls, [(0.5, None), (1.0, None)])
        self.assertEqual((ok, err), (True, ""))
        self.assertTrue(final.is_file())
        self.assertFalse(part.exists())

    def test_cancel_during_progress_stops_ffmpeg_and_removes_part(self) -> None:
        final, part = self._paths()
        cancel = threading.Event()
        calls: list[tuple[float, Optional[float]]] = []

        def on_progress(seconds: float, total: Optional[float]) -> None:
            calls.append((seconds, total))
            cancel.set()

        proc = _FakeFfmpeg(part, _PROGRESS_SCRIPT)
        with mock.patch("mts_to_dnxhr.subprocess.Popen", return_value=proc):
            with self.assertRaises(m.ConversionCancelled):
                m.run_ffmpeg(
                    ["ffmpeg"],
                    final,
                    part,
                    2.0,
                    "clip",
                    on_progress=on_progress,
                    cancel=cancel,
                )
        self.assertEqual(calls, [(0.5, 2.0)])
        self.assertGreaterEqual(proc.terminate_calls, 1)
        self.assertFalse(part.exists())
        self.assertFalse(final.exists())

    def test_convert_one_already_cancelled_does_not_create_dir(self) -> None:
        src = self.root / "clip.MTS"
        src.write_bytes(b"")
        dst = self.root / "out" / "clip.mov"
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(m.ConversionCancelled):
            m.convert_one(src, dst, _opts(), "ffmpeg", "ffprobe", cancel=cancel)
        self.assertFalse(dst.parent.exists())

    def test_convert_one_cancel_during_encode_removes_empty_dir(self) -> None:
        src = self.root / "clip.MTS"
        src.write_bytes(b"")
        dst = self.root / "out" / "clip.mov"
        part = dst.with_name(dst.name + ".part")
        cancel = threading.Event()
        info = m.ProbeInfo(
            duration=2.0,
            field_order="tt",
            avg_frame_rate="30000/1001",
            has_audio=True,
        )

        def on_progress(seconds: float, total: Optional[float]) -> None:
            cancel.set()

        proc = _FakeFfmpeg(part, _PROGRESS_SCRIPT)
        with mock.patch("mts_to_dnxhr.probe", return_value=info):
            with mock.patch("mts_to_dnxhr.subprocess.Popen", return_value=proc):
                with self.assertRaises(m.ConversionCancelled):
                    m.convert_one(
                        src,
                        dst,
                        _opts(),
                        "ffmpeg",
                        "ffprobe",
                        on_progress=on_progress,
                        cancel=cancel,
                    )
        self.assertFalse(dst.parent.exists())
        self.assertFalse(part.exists())
        self.assertGreaterEqual(proc.terminate_calls, 1)

    def test_log_callback_replaces_tqdm_write(self) -> None:
        src = self.root / "clip.MTS"
        src.write_bytes(b"")
        dst = self.root / "out" / "clip.mov"
        info = m.ProbeInfo(
            duration=1.0,
            field_order="progressive",
            avg_frame_rate="30/1",
            has_audio=False,
        )
        messages: list[str] = []
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch("mts_to_dnxhr.probe", return_value=info):
            with mock.patch("mts_to_dnxhr.run_ffmpeg", return_value=(True, "")):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    status, err = m.convert_one(
                        src,
                        dst,
                        _opts(),
                        "ffmpeg",
                        "ffprobe",
                        log=messages.append,
                    )
        self.assertEqual((status, err), ("ok", ""))
        self.assertEqual(messages, [f"wrote {dst}"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

        dst.write_bytes(b"keep")
        skipped: list[str] = []
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status, err = m.convert_one(
                src,
                dst,
                _opts(),
                "ffmpeg",
                "ffprobe",
                log=skipped.append,
            )
        self.assertEqual((status, err), ("skipped", ""))
        self.assertEqual(skipped, [f"skipped (exists): {dst}"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    @unittest.skipUnless(sys.platform == "win32", "CREATE_NO_WINDOW is Windows-only")
    def test_child_processes_hide_console_on_windows(self) -> None:
        completed = mock.Mock(returncode=0, stdout='{"streams":[]}', stderr="")
        with mock.patch("mts_to_dnxhr.subprocess.run", return_value=completed) as run:
            m.probe(self.root / "clip.MTS", "ffprobe")
        self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

        final, part = self._paths()
        proc = _FakeFfmpeg(part, _PROGRESS_SCRIPT)
        with mock.patch("mts_to_dnxhr.subprocess.Popen", return_value=proc) as popen:
            m.run_ffmpeg(["ffmpeg"], final, part, 1.0, "clip", on_progress=lambda *_a: None)
        self.assertEqual(popen.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)


def _first_sample() -> Optional[Path]:
    samples = ROOT / "samples"
    if not samples.is_dir():
        return None
    found = [
        path
        for path in samples.iterdir()
        if path.is_file() and path.suffix.lower() in {".mts", ".m2ts"}
    ]
    found.sort()
    return found[0] if found else None


def _ffprobe_json(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise unittest.SkipTest("ffprobe is not on PATH")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,sample_rate,codec_type",
            "-of",
            "json",
            str(path.resolve()),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def _stream(payload: dict, codec_type: str) -> dict:
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == codec_type:
            return stream
    raise AssertionError(f"no {codec_type} stream in {payload}")


@unittest.skipUnless(
    os.environ.get("MTS_SMOKE") == "1" and shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "set MTS_SMOKE=1 and install ffmpeg to encode samples/",
)
class SmokeTest(unittest.TestCase):
    def test_short_hqx_mov_and_mxf(self) -> None:
        sample = _first_sample()
        if sample is None:
            self.skipTest("no .mts/.m2ts file in samples/")
        ffprobe = shutil.which("ffprobe")
        assert ffprobe is not None
        info = m.probe(sample, ffprobe)
        if sample.name == "01 American Landscape.MTS":
            self.assertAlmostEqual(info.duration or 0, 168.192, places=2)
            self.assertEqual(info.field_order, "tt")
            self.assertEqual(info.avg_frame_rate, "30000/1001")
            self.assertTrue(info.has_audio)
        else:
            if info.duration is not None:
                self.assertGreater(info.duration, 0)
            self.assertTrue(info.avg_frame_rate)

        source_video = _stream(_ffprobe_json(sample), "video")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            self.assertEqual(
                m.main([str(sample), "-o", str(out_dir), "--duration", "3"]),
                0,
            )
            mov = out_dir / f"{sample.stem}.mov"
            self.assertTrue(mov.is_file())
            self.assertGreater(mov.stat().st_size, 0)
            self.assertFalse(mov.with_name(mov.name + ".part").exists())
            self._assert_video(mov, source_video)
            self._assert_audio(mov, "pcm_s16le")

            self.assertEqual(
                m.main(
                    [
                        str(sample),
                        "-o",
                        str(out_dir),
                        "--duration",
                        "3",
                        "-c",
                        "mxf",
                        "--audio-bit-depth",
                        "24",
                    ]
                ),
                0,
            )
            mxf = out_dir / f"{sample.stem}.mxf"
            self.assertTrue(mxf.is_file())
            self._assert_video(mxf, source_video)
            self._assert_audio(mxf, "pcm_s24le")

    def _assert_video(self, path: Path, source_video: dict) -> None:
        video = _stream(_ffprobe_json(path), "video")
        self.assertEqual(video.get("codec_name"), "dnxhd")
        self.assertEqual(video.get("profile"), "DNXHR HQX")
        self.assertEqual(video.get("pix_fmt"), "yuv422p10le")
        self.assertEqual(video.get("width"), source_video.get("width"))
        self.assertEqual(video.get("height"), source_video.get("height"))
        self.assertEqual(video.get("avg_frame_rate"), source_video.get("avg_frame_rate"))

    def _assert_audio(self, path: Path, codec: str) -> None:
        audio = _stream(_ffprobe_json(path), "audio")
        self.assertEqual(audio.get("codec_name"), codec)
        self.assertEqual(str(audio.get("sample_rate")), "48000")


if __name__ == "__main__":
    unittest.main()
