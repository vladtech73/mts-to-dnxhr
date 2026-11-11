"""Tests for the GUI wrapper.

Pure helpers and ``run_batch`` do not need a Tk window. ``AppTableTests``
creates a hidden Tk root and skips itself when no display is available.
"""

from __future__ import annotations

import importlib
import os
import struct
import sys
import tempfile
import time
import tkinter as tk
import types
import unittest
from pathlib import Path
from unittest import mock

import mts_to_dnxhr as core
import mts_to_dnxhr_gui as gui

ROOT = Path(__file__).resolve().parents[1]


def _interlaced() -> core.ProbeInfo:
    return core.ProbeInfo(
        duration=168.192,
        field_order="tt",
        avg_frame_rate="30000/1001",
        has_audio=True,
    )


def _progressive() -> core.ProbeInfo:
    return core.ProbeInfo(
        duration=10.0,
        field_order="progressive",
        avg_frame_rate="30000/1001",
        has_audio=True,
    )


class FormatElapsedTests(unittest.TestCase):
    def test_minutes_and_hours(self) -> None:
        self.assertEqual(gui.format_elapsed(0), "0:00")
        self.assertEqual(gui.format_elapsed(5.9), "0:05")
        self.assertEqual(gui.format_elapsed(83), "1:23")
        self.assertEqual(gui.format_elapsed(3723), "1:02:03")
        self.assertEqual(gui.format_elapsed(-1), "0:00")


class DefaultsTests(unittest.TestCase):
    def test_defaults_match_cli_encode_argv(self) -> None:
        args = core.build_parser().parse_args(["clip.mts"])
        expected = core.Options(
            profile=args.profile,
            container=args.container,
            audio_bit_depth=args.audio_bit_depth,
            deinterlace=args.deinterlace,
            overwrite=args.overwrite,
            duration=args.duration,
            hwaccel=args.hwaccel,
        )
        self.assertEqual(gui.DEFAULT_OPTIONS, expected)
        self.assertEqual(expected.hwaccel, "cuda")
        self.assertEqual(
            gui.OUTPUT_SUMMARY,
            "DNxHR HQX · MOV · PCM 16-bit 48 kHz · source size/fps",
        )
        src = Path("in.mts")
        dst = Path("out.mov")
        for info in (_interlaced(), _progressive()):
            self.assertEqual(
                core.build_command("ffmpeg", src, dst, gui.DEFAULT_OPTIONS, info, force=True),
                core.build_command("ffmpeg", src, dst, expected, info, force=True),
            )
        deinterlace = gui.options_for(True)
        cli_deinterlace = core.Options(
            profile=expected.profile,
            container=expected.container,
            audio_bit_depth=expected.audio_bit_depth,
            deinterlace=True,
            overwrite=expected.overwrite,
            duration=expected.duration,
            hwaccel=expected.hwaccel,
        )
        self.assertEqual(gui.options_for(False, gpu_decode=False).hwaccel, "off")
        self.assertEqual(gui.options_for(False, gpu_decode=True).hwaccel, "cuda")
        interlaced_cmd = core.build_command(
            "ffmpeg", src, dst, deinterlace, _interlaced(), force=True
        )
        progressive_cmd = core.build_command(
            "ffmpeg", src, dst, deinterlace, _progressive(), force=True
        )
        self.assertEqual(
            interlaced_cmd,
            core.build_command("ffmpeg", src, dst, cli_deinterlace, _interlaced(), force=True),
        )
        self.assertEqual(
            progressive_cmd,
            core.build_command(
                "ffmpeg", src, dst, cli_deinterlace, _progressive(), force=True
            ),
        )
        self.assertIn("yadif=mode=send_frame:parity=auto:deint=interlaced", interlaced_cmd)
        self.assertNotIn("yadif", progressive_cmd)

    def test_remux_options_summary_and_size_ratio(self) -> None:
        remux = gui.options_for(True, gpu_decode=False, mode="remux")
        self.assertEqual(remux.profile, "remux")
        self.assertEqual(remux.container, "mp4")
        self.assertFalse(remux.deinterlace)
        self.assertEqual(remux.hwaccel, "off")
        self.assertEqual(gui.options_for(False, gpu_decode=True, mode="remux").hwaccel, "off")
        cmd = core.build_command(
            "ffmpeg",
            Path("in.mts"),
            Path("out.mp4"),
            remux,
            _interlaced(),
            force=True,
        )
        self.assertNotIn("-hwaccel", cmd)
        self.assertIn("copy", cmd)
        self.assertIn("aac", cmd)
        self.assertNotIn("dnxhd", cmd)
        self.assertNotIn("yadif", cmd)
        self.assertEqual(
            gui.summary_for_mode("remux"),
            "Remux MP4 · H.264 copy · AAC 192 kb/s 48 kHz · source size/fps",
        )
        self.assertEqual(gui.summary_for_mode("dnxhr"), gui.OUTPUT_SUMMARY)
        self.assertEqual(gui.size_ratio_for_mode("remux"), 1)
        self.assertEqual(gui.size_ratio_for_mode("dnxhr"), gui.SIZE_RATIO)
        self.assertNotIn("14", gui.low_space_detail("remux"))
        self.assertIn("14", gui.low_space_detail("dnxhr"))
        self.assertEqual(gui.profile_for_mode("remux"), "remux")
        self.assertEqual(gui.profile_for_mode("dnxhr"), gui.DEFAULT_OPTIONS.profile)


class CollectItemsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mixed_drop_dedupes_and_counts_ignored(self) -> None:
        clip = self.root / "loose.MTS"
        clip.write_bytes(b"")
        notes = self.root / "note.txt"
        notes.write_bytes(b"")
        folder = self.root / "card"
        (folder / "A").mkdir(parents=True)
        (folder / "B").mkdir()
        (folder / "A" / "00000.MTS").write_bytes(b"")
        (folder / "B" / "00000.MTS").write_bytes(b"")
        (folder / "A" / "00000.CPI").write_bytes(b"")
        missing = self.root / "missing.mts"
        paths = [clip, notes, folder, missing]
        items, ignored = gui.collect_items(paths, [])
        self.assertEqual(len(items), 3)
        self.assertEqual(ignored, 3)
        self.assertEqual({item.src.name for item in items}, {"loose.MTS", "00000.MTS"})
        again, _ignored_again = gui.collect_items(paths, items)
        self.assertEqual(again, [])

    def test_dropped_group_is_alphabetical(self) -> None:
        names = ["clip10.MTS", "Clip2.MTS", "clip1.mts", "00000.MTS"]
        paths = []
        for name in names:
            path = self.root / name
            path.write_bytes(b"")
            paths.append(path)
        items, ignored = gui.collect_items(paths, [])
        self.assertEqual(ignored, 0)
        self.assertEqual(
            [item.src.name for item in items],
            ["00000.MTS", "clip1.mts", "Clip2.MTS", "clip10.MTS"],
        )

    @unittest.skipUnless(os.name == "nt", "Windows path case folding")
    def test_case_variant_duplicates_are_deduped(self) -> None:
        clip = self.root / "Clip.MTS"
        clip.write_bytes(b"")
        first, ignored = gui.collect_items([clip], [])
        self.assertEqual(len(first), 1)
        self.assertEqual(ignored, 0)
        variant = Path(str(clip).replace("Clip.MTS", "clip.mts"))
        second, _ignored = gui.collect_items([variant], first)
        self.assertEqual(second, [])
        both, _ignored = gui.collect_items([clip, variant], [])
        self.assertEqual(len(both), 1)


class PlanAndSpaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plan_outputs_mirrors_folders_and_reports_collisions(self) -> None:
        clip = self.root / "clip.MTS"
        clip.write_bytes(b"")
        out = self.root / "out"
        pairs, collisions = gui.plan_outputs(
            [gui.ClipItem(src=clip, root=clip)],
            out,
            "mov",
        )
        self.assertEqual(collisions, {})
        self.assertEqual(pairs[0][1], out / "clip.mov")

        folder = self.root / "card"
        src_a = folder / "A" / "00000.MTS"
        src_b = folder / "B" / "00000.MTS"
        src_a.parent.mkdir(parents=True)
        src_b.parent.mkdir(parents=True)
        src_a.write_bytes(b"")
        src_b.write_bytes(b"")
        pairs, collisions = gui.plan_outputs(
            [
                gui.ClipItem(src=src_a, root=folder),
                gui.ClipItem(src=src_b, root=folder),
            ],
            out,
            "mov",
        )
        self.assertEqual(collisions, {})
        self.assertEqual(pairs[0][1], out / "A" / "00000.mov")
        self.assertEqual(pairs[1][1], out / "B" / "00000.mov")

        loose_a = self.root / "one" / "00000.MTS"
        loose_b = self.root / "two" / "00000.MTS"
        loose_a.parent.mkdir()
        loose_b.parent.mkdir()
        loose_a.write_bytes(b"a")
        loose_b.write_bytes(b"b")
        _pairs, collisions = gui.plan_outputs(
            [
                gui.ClipItem(src=loose_a, root=loose_a),
                gui.ClipItem(src=loose_b, root=loose_b),
            ],
            out,
            "mov",
        )
        self.assertEqual(len(collisions), 1)
        sources = next(iter(collisions.values()))
        self.assertEqual(set(sources), {loose_a, loose_b})

    def test_estimate_skips_existing_and_free_bytes_walks_to_parent(self) -> None:
        src = self.root / "a.MTS"
        src.write_bytes(b"x" * 100)
        dst = self.root / "a.mov"
        missing = self.root / "gone.MTS"
        self.assertEqual(
            gui.estimate_needed_bytes([(src, dst), (missing, self.root / "gone.mov")]),
            100 * gui.SIZE_RATIO,
        )
        self.assertEqual(gui.estimate_needed_bytes([(src, dst)], ratio=1), 100)
        dst.write_bytes(b"already")
        self.assertEqual(gui.estimate_needed_bytes([(src, dst)]), 0)
        out = self.root / "not-yet" / "dnxhr"
        self.assertFalse(out.exists())
        free = gui.free_bytes(out)
        self.assertIsInstance(free, int)
        assert free is not None
        self.assertGreater(free, 0)
        with mock.patch("mts_to_dnxhr_gui.shutil.disk_usage", side_effect=OSError("denied")):
            self.assertIsNone(gui.free_bytes(self.root))


class RunBatchTests(unittest.TestCase):
    def _pairs(self, count: int) -> list[tuple[Path, Path]]:
        return [(Path("f{0}.MTS".format(i)), Path("f{0}.mov".format(i))) for i in range(count)]

    def test_event_order_for_ok_skipped_and_failed(self) -> None:
        results = [("ok", ""), ("skipped", ""), ("failed", "bad")]

        def fake_convert(*_args: object, **_kwargs: object) -> tuple[str, str]:
            return results.pop(0)

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(3),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                gui.threading.Event(),
            )
        self.assertEqual(
            events,
            [
                ("file_started", 0),
                ("file_finished", 0, "ok", ""),
                ("file_started", 1),
                ("file_finished", 1, "skipped", ""),
                ("file_started", 2),
                ("file_finished", 2, "failed", "bad"),
                ("batch_finished", 1, 1, 1, 0),
            ],
        )
        self.assertEqual(events[-1][0], "batch_finished")

    def test_cancel_during_second_file_cancels_the_rest(self) -> None:
        cancel = gui.threading.Event()
        calls = {"n": 0}

        def fake_convert(*_args: object, **_kwargs: object) -> tuple[str, str]:
            calls["n"] += 1
            if calls["n"] == 2:
                cancel.set()
                raise core.ConversionCancelled()
            return "ok", ""

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(3),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                cancel,
            )
        finished = [event for event in events if event[0] == "file_finished"]
        self.assertEqual([event[2] for event in finished], ["ok", "cancelled", "cancelled"])
        self.assertEqual(events[-1], ("batch_finished", 1, 0, 0, 2))

    def test_unexpected_exception_fails_the_file_and_continues(self) -> None:
        calls = {"n": 0}

        def fake_convert(*_args: object, **_kwargs: object) -> tuple[str, str]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return "ok", ""

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(2),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                gui.threading.Event(),
            )
        self.assertEqual(events[1], ("file_finished", 0, "failed", "boom"))
        self.assertEqual(events[3], ("file_finished", 1, "ok", ""))
        self.assertEqual(events[-1], ("batch_finished", 1, 0, 1, 0))
        self.assertEqual(events[-1][0], "batch_finished")

    def test_progress_is_throttled_clamped_and_can_be_unknown(self) -> None:
        def fake_convert(*_args: object, **kwargs: object) -> tuple[str, str]:
            on_progress = kwargs["on_progress"]
            for step in range(1000):
                on_progress(step * 10.0 / 1000.0, 10.0)  # type: ignore[operator]
            on_progress(100.0, 10.0)  # type: ignore[operator]
            on_progress(1.0, None)  # type: ignore[operator]
            return "ok", ""

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(1),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                gui.threading.Event(),
            )
        progress = [event for event in events if event[0] == "file_progress"]
        known = [event for event in progress if event[2] is not None]
        unknown = [event for event in progress if event[2] is None]
        self.assertLessEqual(len(known), 101)
        self.assertGreater(len(known), 1)
        self.assertTrue(all(0.0 <= event[2] <= 1.0 for event in known))
        self.assertEqual(known[-1][2], 1.0)
        self.assertEqual(unknown, [("file_progress", 0, None)])
        self.assertEqual(events[-1], ("batch_finished", 1, 0, 0, 0))

    def test_cancel_already_set_skips_every_file(self) -> None:
        cancel = gui.threading.Event()
        cancel.set()
        calls = {"n": 0}

        def fake_convert(*_args: object, **_kwargs: object) -> tuple[str, str]:
            calls["n"] += 1
            return "ok", ""

        events: list[tuple] = []
        count = 3
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(count),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                cancel,
            )
        self.assertEqual(calls["n"], 0)
        self.assertFalse(any(event[0] == "file_started" for event in events))
        finished = [event for event in events if event[0] == "file_finished"]
        self.assertEqual(len(finished), count)
        self.assertTrue(all(event[2] == "cancelled" for event in finished))
        self.assertEqual(events[-1], ("batch_finished", 0, 0, 0, count))

    def test_jobs_two_overlap_finishes_each_row_once(self) -> None:
        barrier = gui.threading.Barrier(2, timeout=5)

        def fake_convert(*_args: object, **_kwargs: object) -> tuple[str, str]:
            barrier.wait()
            return "ok", ""

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(2),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                gui.threading.Event(),
                jobs=2,
            )
        first_finished = next(
            index for index, event in enumerate(events) if event[0] == "file_finished"
        )
        started_before = [
            event for event in events[:first_finished] if event[0] == "file_started"
        ]
        self.assertEqual(len(started_before), 2)
        finished = [event for event in events if event[0] == "file_finished"]
        self.assertEqual(sorted(event[1] for event in finished), [0, 1])
        for index in (0, 1):
            start_at = next(
                position
                for position, event in enumerate(events)
                if event[0] == "file_started" and event[1] == index
            )
            finish_at = next(
                position
                for position, event in enumerate(events)
                if event[0] == "file_finished" and event[1] == index
            )
            self.assertLess(start_at, finish_at)
        self.assertEqual(events[-1], ("batch_finished", 2, 0, 0, 0))

    def test_jobs_two_cancel_mid_batch_finishes_every_row(self) -> None:
        cancel = gui.threading.Event()
        lock = gui.threading.Lock()
        calls = {"n": 0}

        def fake_convert(*_args: object, **_kwargs: object) -> tuple[str, str]:
            with lock:
                calls["n"] += 1
                call = calls["n"]
            if call == 2:
                cancel.set()
                raise core.ConversionCancelled()
            return "ok", ""

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(4),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                cancel,
                jobs=2,
            )
        finished = [event for event in events if event[0] == "file_finished"]
        self.assertEqual(sorted(event[1] for event in finished), [0, 1, 2, 3])
        counts = events[-1]
        self.assertEqual(counts[0], "batch_finished")
        self.assertEqual(counts[1] + counts[4], 4)
        self.assertEqual(counts[2], 0)
        self.assertEqual(counts[3], 0)

    def test_parallel_progress_throttling_is_independent(self) -> None:
        barrier = gui.threading.Barrier(2, timeout=5)

        def fake_convert(*_args: object, **kwargs: object) -> tuple[str, str]:
            barrier.wait()
            on_progress = kwargs["on_progress"]
            for step in range(1000):
                on_progress(step * 10.0 / 1000.0, 10.0)  # type: ignore[operator]
            return "ok", ""

        events: list[tuple] = []
        with mock.patch.object(gui.core, "convert_one", side_effect=fake_convert):
            gui.run_batch(
                self._pairs(2),
                gui.DEFAULT_OPTIONS,
                "ffmpeg",
                "ffprobe",
                events.append,
                gui.threading.Event(),
                jobs=2,
            )
        for index in (0, 1):
            fractions = [
                event[2]
                for event in events
                if event[0] == "file_progress" and event[1] == index
            ]
            self.assertLessEqual(len(fractions), 101)
            self.assertGreater(len(fractions), 1)
            self.assertEqual(fractions, sorted(fractions))

    def test_running_prefix_formats_zero_one_and_many(self) -> None:
        self.assertEqual(gui.running_prefix(4, []), "Converting…")
        self.assertEqual(
            gui.running_prefix(10, [(2, "clip.MTS", 42)]),
            "Converting 3 of 10: clip.MTS (42%)",
        )
        self.assertEqual(
            gui.running_prefix(10, [(2, "clip.MTS", None)]),
            "Converting 3 of 10: clip.MTS…",
        )
        self.assertEqual(
            gui.running_prefix(10, [(2, "a.MTS", 1), (3, "b.MTS", 2)]),
            "Converting 2 at once (3, 4 of 10)",
        )
        self.assertEqual(
            gui.running_prefix(
                10,
                [(3, "c.MTS", 1), (0, "a.MTS", 2), (1, "b.MTS", 3)],
            ),
            "Converting 3 at once (1, 2, 4 of 10)",
        )


class ToolLookupTests(unittest.TestCase):
    def test_locate_tools_returns_none_when_nothing_is_installed(self) -> None:
        with mock.patch.object(gui.core, "find_tool", return_value=None):
            base = Path(gui.__file__).resolve().parent
            self.assertFalse((base / "ffmpeg.exe").is_file())
            self.assertFalse((base / "ffprobe.exe").is_file())
            self.assertEqual(gui.locate_tools(), (None, None))

    def test_resource_path_source_and_frozen(self) -> None:
        self.assertEqual(
            gui.resource_path("assets/app.ico"),
            Path(gui.__file__).resolve().parent / "assets" / "app.ico",
        )
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sys, "frozen", True, create=True):
                with mock.patch.object(sys, "_MEIPASS", tmp, create=True):
                    self.assertEqual(
                        gui.resource_path("assets/app.ico"),
                        Path(tmp) / "assets" / "app.ico",
                    )

    def test_tkdnd_load_failure_falls_back_to_plain_tk(self) -> None:
        sentinel = object()
        for failure in (
            RuntimeError("Unable to load tkdnd library."),
            gui.tk.TclError("tkdnd"),
        ):
            with self.subTest(failure=type(failure).__name__):
                fake_dnd = types.SimpleNamespace(
                    TkinterDnD=types.SimpleNamespace(Tk=mock.Mock(side_effect=failure))
                )
                with mock.patch.object(gui, "DND_AVAILABLE", True):
                    with mock.patch.object(gui, "tkinterdnd2", fake_dnd):
                        with mock.patch.object(gui.tk, "Tk", return_value=sentinel) as plain:
                            root, dnd = gui._create_root()
                self.assertIs(root, sentinel)
                self.assertFalse(dnd)
                plain.assert_called_once()

    def test_discard_failed_root_clears_default_root(self) -> None:
        class _FakeRoot:
            def __init__(self) -> None:
                self.destroyed = False

            def destroy(self) -> None:
                self.destroyed = True

        fake_root = _FakeRoot()

        def _raise_after_setting_root() -> None:
            gui.tk._default_root = fake_root
            raise RuntimeError("Unable to load tkdnd library.")

        fake_dnd = types.SimpleNamespace(
            TkinterDnD=types.SimpleNamespace(Tk=mock.Mock(side_effect=_raise_after_setting_root))
        )
        sentinel = object()
        previous = getattr(gui.tk, "_default_root", None)
        try:
            with mock.patch.object(gui, "DND_AVAILABLE", True):
                with mock.patch.object(gui, "tkinterdnd2", fake_dnd):
                    with mock.patch.object(gui.tk, "Tk", return_value=sentinel):
                        root, dnd = gui._create_root()
            self.assertIs(root, sentinel)
            self.assertFalse(dnd)
            self.assertTrue(fake_root.destroyed)
            self.assertIsNone(gui.tk._default_root)
        finally:
            gui.tk._default_root = previous

    def test_import_without_tkinterdnd2(self) -> None:
        with mock.patch.dict(sys.modules, {"tkinterdnd2": None}):
            reloaded = importlib.reload(gui)
            self.assertFalse(reloaded.DND_AVAILABLE)
        importlib.reload(gui)
        self.assertIsInstance(gui.DND_AVAILABLE, bool)


class IconFileTests(unittest.TestCase):
    def test_icon_header_contains_required_square_sizes(self) -> None:
        path = ROOT / "assets" / "app.ico"
        self.assertTrue(path.is_file(), "assets/app.ico is missing; run scripts/make_icon.py")
        data = path.read_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", data, 0)
        self.assertEqual(reserved, 0)
        self.assertEqual(kind, 1)
        self.assertGreater(count, 0)
        sizes = set()
        for index in range(count):
            entry = 6 + index * 16
            width = data[entry]
            height = data[entry + 1]
            pixel_w = 256 if width == 0 else width
            pixel_h = 256 if height == 0 else height
            self.assertEqual(pixel_w, pixel_h)
            image_size = struct.unpack_from("<I", data, entry + 8)[0]
            offset = struct.unpack_from("<I", data, entry + 12)[0]
            self.assertGreater(image_size, 0)
            self.assertLessEqual(offset + image_size, len(data))
            sizes.add(pixel_w)
        self.assertTrue({16, 24, 32, 48, 256}.issubset(sizes))


def _channel(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2 relative contrast of two ``#rrggbb`` colors."""

    def luminance(color: str) -> float:
        text = color.lstrip("#")
        red = int(text[0:2], 16) / 255.0
        green = int(text[2:4], 16) / 255.0
        blue = int(text[4:6], 16) / 255.0
        return (
            0.2126 * _channel(red)
            + 0.7152 * _channel(green)
            + 0.0722 * _channel(blue)
        )

    lighter = luminance(fg)
    darker = luminance(bg)
    if darker > lighter:
        lighter, darker = darker, lighter
    return (lighter + 0.05) / (darker + 0.05)


def _make_row(
    name: str,
    seq: int,
    *,
    size: object = None,
    mtime: object = None,
    status: str = "waiting",
    parent: object = None,
) -> gui._Row:
    folder = Path("C:/clips") if parent is None else Path(str(parent))
    src = folder / name
    return gui._Row(
        item=gui.ClipItem(src=src, root=src),
        seq=seq,
        size=size if isinstance(size, int) else None,
        mtime=mtime if isinstance(mtime, float) else None,
        status=status,
        error="",
    )


class SortHelperTests(unittest.TestCase):
    def test_natural_key_orders_clip_numbers(self) -> None:
        ordered = sorted(
            ["clip10.MTS", "Clip2.MTS", "clip1.mts"],
            key=gui.natural_key,
        )
        self.assertEqual(ordered, ["clip1.mts", "Clip2.MTS", "clip10.MTS"])

    def test_natural_key_mixed_digit_and_letter_names(self) -> None:
        names = ["clip1.mts", "01 American Landscape.MTS", "Clip2.MTS", "00000.MTS"]
        self.assertEqual(
            sorted(names, key=gui.natural_key),
            ["00000.MTS", "01 American Landscape.MTS", "clip1.mts", "Clip2.MTS"],
        )
        rows = {
            name: _make_row(name, seq) for seq, name in enumerate(names, start=1)
        }
        descending = [
            rows[iid].item.src.name for iid in gui.sort_iids(rows, "file", True)
        ]
        self.assertEqual(
            descending,
            ["Clip2.MTS", "clip1.mts", "01 American Landscape.MTS", "00000.MTS"],
        )

    def test_format_size_and_mtime(self) -> None:
        self.assertEqual(gui.format_size(None), "—")
        self.assertEqual(gui.format_size(0), "0 MB")
        self.assertEqual(gui.format_size(335000000), "335 MB")
        self.assertEqual(gui.format_size(4700000000), "4700 MB")
        self.assertEqual(gui.format_size(500000), "0.5 MB")
        self.assertEqual(gui.format_mtime(None), "—")
        stamp = time.mktime((2020, 6, 15, 9, 5, 0, 0, 0, -1))
        self.assertEqual(gui.format_mtime(stamp), "2020-06-15 09:05")

    def test_sort_each_column_both_directions(self) -> None:
        rows = {
            "a": _make_row("a.mts", 1, size=None, mtime=None),
            "b": _make_row("b.mts", 2, size=10, mtime=20.0),
            "c": _make_row("c.mts", 3, size=None, mtime=None),
            "d": _make_row("d.mts", 4, size=5, mtime=10.0),
        }
        self.assertEqual(gui.sort_iids(rows, "size", False), ["d", "b", "a", "c"])
        self.assertEqual(gui.sort_iids(rows, "size", True), ["b", "d", "a", "c"])
        self.assertEqual(gui.sort_iids(rows, "mtime", False), ["d", "b", "a", "c"])
        self.assertEqual(gui.sort_iids(rows, "mtime", True), ["b", "d", "a", "c"])
        self.assertEqual(gui.sort_iids(rows, "file", False), ["a", "b", "c", "d"])
        self.assertEqual(gui.sort_iids(rows, "file", True), ["d", "c", "b", "a"])
        folders = {
            "wide": _make_row("clip.mts", 1, parent=Path("C:/folder10")),
            "narrow": _make_row("clip.mts", 2, parent=Path("C:/folder2")),
        }
        self.assertEqual(gui.sort_iids(folders, "folder", False), ["narrow", "wide"])
        self.assertEqual(gui.sort_iids(folders, "folder", True), ["wide", "narrow"])

    def test_ties_keep_add_order_both_ways(self) -> None:
        rows = {
            "a": _make_row("Same.MTS", 1, size=5, mtime=1.0, status="waiting"),
            "b": _make_row("same.mts", 2, size=5, mtime=1.0, status="waiting"),
            "c": _make_row("SAME.mts", 3, size=5, mtime=1.0, status="waiting"),
        }
        for column in ("file", "folder", "size", "mtime", "status"):
            self.assertEqual(gui.sort_iids(rows, column, False), ["a", "b", "c"])
            self.assertEqual(gui.sort_iids(rows, column, True), ["a", "b", "c"])

    def test_status_rank_order(self) -> None:
        specs = (
            ("w", "waiting"),
            ("a", "active"),
            ("o", "ok"),
            ("s", "skipped"),
            ("f", "failed"),
            ("c", "cancelled"),
        )
        rows = {
            iid: _make_row("{0}.mts".format(iid), seq, status=status)
            for seq, (iid, status) in enumerate(specs, start=1)
        }
        self.assertEqual(
            gui.sort_iids(rows, "status", False),
            ["a", "w", "f", "c", "s", "o"],
        )
        self.assertEqual(
            gui.sort_iids(rows, "status", True),
            ["o", "s", "c", "f", "w", "a"],
        )


class PaletteContrastTests(unittest.TestCase):
    def _assert_contrast(self, fg: str, bg: str, minimum: float) -> None:
        ratio = _contrast_ratio(fg, bg)
        self.assertGreaterEqual(
            ratio,
            minimum,
            "{0} on {1} is {2:.2f}, need {3:.1f}".format(fg, bg, ratio, minimum),
        )

    def test_body_status_accent_and_drop_contrast(self) -> None:
        palette = gui._Palette
        for bg in (palette.SURFACE, palette.FIELD):
            self._assert_contrast(palette.TEXT, bg, 4.5)
            self._assert_contrast(palette.TEXT_SECONDARY, bg, 4.5)
        for fg in (palette.OK_FG, palette.FAILED_FG, palette.ACTIVE_FG, palette.MUTED_FG):
            for bg in (palette.FIELD, palette.STRIPE, palette.SELECT_BG):
                self._assert_contrast(fg, bg, 4.5)
        self._assert_contrast(palette.ACCENT_FG, palette.ACCENT, 4.5)
        self._assert_contrast(palette.ACCENT_FG, palette.ACCENT_ACTIVE, 4.5)
        self._assert_contrast(palette.ACCENT_DISABLED_FG, palette.ACCENT_DISABLED, 3.0)
        self._assert_contrast(palette.HEADING_FG, palette.HEADING_BG, 4.5)
        self._assert_contrast(palette.HEADING_FG, palette.HEADING_ACTIVE, 4.5)
        self._assert_contrast(palette.ERROR_FG, palette.ERROR_BG, 4.5)
        for bg in (palette.DROP_BG, palette.DROP_HOT_BG, palette.DROP_PAUSED_BG):
            self._assert_contrast(palette.TEXT, bg, 4.5)
        self._assert_contrast(palette.TEXT_DISABLED, palette.SURFACE, 3.0)
        self._assert_contrast(palette.TEXT, palette.CONTROL_BG, 4.5)
        self._assert_contrast(palette.TEXT, palette.CONTROL_HOVER, 4.5)
        self._assert_contrast(palette.SELECT_FG, palette.SELECT_BG, 4.5)


class AppTableTests(unittest.TestCase):
    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(
                "no Tk display available: {0}".format(exc)
            ) from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        root = getattr(cls, "root", None)
        if root is not None:
            root.destroy()

    def setUp(self) -> None:
        tools = mock.patch(
            "mts_to_dnxhr_gui.locate_tools",
            return_value=("ffmpeg", "ffprobe"),
        )
        tools.start()
        self.addCleanup(tools.stop)
        for name in (
            "showerror",
            "showwarning",
            "showinfo",
            "askyesno",
            "askokcancel",
        ):
            patcher = mock.patch("mts_to_dnxhr_gui.messagebox.{0}".format(name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        folder = Path(self._tmp.name)
        self.paths = []
        for name in ("clip10.MTS", "Clip2.MTS", "clip1.mts"):
            path = folder / name
            path.write_bytes(b"")
            self.paths.append(path)
        self.app = gui.App(self.root, dnd=False)
        self.app._add_paths(self.paths)

    def tearDown(self) -> None:
        for widget in self.root.winfo_children():
            widget.destroy()

    def test_file_heading_sorts_and_marks_once(self) -> None:
        self.app._on_heading_click("file")
        names = [self.app.tree.set(iid, "file") for iid in self.app.tree.get_children()]
        self.assertEqual(names, ["clip1.mts", "Clip2.MTS", "clip10.MTS"])
        self.assertIn("▲", self.app.tree.heading("file", "text"))
        self.app._on_heading_click("file")
        names = [self.app.tree.set(iid, "file") for iid in self.app.tree.get_children()]
        self.assertEqual(names, ["clip10.MTS", "Clip2.MTS", "clip1.mts"])
        self.assertIn("▼", self.app.tree.heading("file", "text"))
        marks = 0
        for col in gui._HEADINGS:
            text = str(self.app.tree.heading(col, "text"))
            count = text.count("▲") + text.count("▼")
            self.assertLessEqual(count, 1)
            marks += count
        self.assertEqual(marks, 1)

    def test_status_follows_snapshot_after_resort(self) -> None:
        # Ascending file order matches add seq after alphabetical load; reverse
        # so the batch snapshot differs from a later equal-status seq sort.
        self.app._on_heading_click("file")
        self.app._on_heading_click("file")
        self.app._snapshot_batch_order()
        batch_iid = self.app._iids[0]
        batch_name = self.app._rows[batch_iid].item.src.name
        self.app._on_heading_click("status")
        self.assertNotEqual(self.app.tree.get_children()[0], batch_iid)
        self.app._handle_event(("file_started", 0))
        self.app._handle_event(("file_finished", 0, "failed", "boom"))
        self.assertEqual(self.app._rows[batch_iid].status, "failed")
        self.assertEqual(self.app._rows[batch_iid].error, "boom")
        self.assertTrue(str(self.app.tree.set(batch_iid, "status")).startswith("Failed"))
        displayed = self.app.tree.get_children()[0]
        self.assertNotEqual(self.app._rows[displayed].status, "failed")
        self.assertEqual(self.app._failed_names(), [batch_name])

    def test_remove_selected_on_sorted_view_restripes(self) -> None:
        self.app._on_heading_click("file")
        children = list(self.app.tree.get_children())
        target = children[1]
        self.app.tree.selection_set(target)
        self.app.remove_selected()
        self.assertNotIn(target, self.app._rows)
        self.assertNotIn(target, self.app._iids)
        remaining = [
            self.app.tree.set(iid, "file") for iid in self.app.tree.get_children()
        ]
        self.assertEqual(remaining, ["clip1.mts", "clip10.MTS"])
        for index, iid in enumerate(self.app.tree.get_children()):
            tags = self.app.tree.item(iid, "tags")
            stripe = "odd" if index % 2 == 1 else "even"
            other = "even" if stripe == "odd" else "odd"
            self.assertIn(stripe, tags)
            self.assertNotIn(other, tags)

    def test_column_left_of_boundaries_with_default_displaycolumns(self) -> None:
        shown = self.app.tree["displaycolumns"]
        self.assertTrue(shown == "#all" or shown == ("#all",))
        edge = 0
        for col in self.app.tree["columns"]:
            edge += int(self.app.tree.column(col, "width"))
            self.assertEqual(self.app._column_left_of(edge), col)

    def test_row_values_match_insert_columns(self) -> None:
        for iid in self.app.tree.get_children():
            row = self.app._rows[iid]
            self.assertEqual(self.app.tree.set(iid, "status"), "Waiting")
            self.assertEqual(self.app.tree.set(iid, "folder"), str(row.item.src.parent))
            self.assertTrue(self.app.tree.set(iid, "size"))
            self.assertTrue(self.app.tree.set(iid, "mtime"))

    def test_add_paths_autofits_file_and_folder(self) -> None:
        defaults = {name: self.app._px(width) for name, width, *_rest in gui._COLUMN_LAYOUT}
        deep = Path(self._tmp.name) / ("nested_" + ("folder_" * 12))
        deep.mkdir(parents=True)
        long_name = "very_long_clip_name_" + ("x" * 40) + ".MTS"
        clip = deep / long_name
        clip.write_bytes(b"")
        self.app._add_paths([clip])
        file_width = int(self.app.tree.column("file", "width"))
        folder_width = int(self.app.tree.column("folder", "width"))
        status_width = int(self.app.tree.column("status", "width"))
        self.assertGreater(file_width, defaults["file"])
        self.assertGreater(folder_width, defaults["folder"])
        file_needed = self.app._fonts.body.measure(long_name) + self.app._px(16)
        folder_needed = self.app._fonts.body.measure(str(deep)) + self.app._px(16)
        self.assertGreaterEqual(file_width, min(file_needed, self.app._px(600)))
        self.assertGreaterEqual(folder_width, min(folder_needed, self.app._px(600)))
        status_min = int(self.app.tree.column("status", "minwidth"))
        status_needed = max(
            self.app._fonts.heading.measure("Status"),
            self.app._fonts.body.measure("Waiting"),
        ) + self.app._px(16)
        self.assertEqual(status_width, max(status_min, status_needed))
        self.assertLessEqual(status_width, defaults["status"])

    def test_set_status_keeps_odd_stripe(self) -> None:
        self.app._restripe()
        odd_index = None
        for index, iid in enumerate(self.app._iids):
            if "odd" in self.app.tree.item(iid, "tags"):
                odd_index = index
                break
        self.assertIsNotNone(odd_index)
        assert odd_index is not None
        iid = self.app._iids[odd_index]
        self.app._set_status(odd_index, "active", "Converting…")
        tags = self.app.tree.item(iid, "tags")
        self.assertIn("odd", tags)
        self.assertIn("active", tags)

    def test_default_size_has_no_horizontal_overflow(self) -> None:
        self.root.update()
        self.assertEqual(self.app.tree.xview(), (0.0, 1.0))

    def test_autofit_clamps_to_minwidth_and_max(self) -> None:
        self.app._autofit("file")
        width = int(self.app.tree.column("file", "width"))
        self.assertGreaterEqual(width, int(self.app.tree.column("file", "minwidth")))
        self.assertLessEqual(width, self.app._px(600))

    def test_remux_mode_refreshes_auto_folder_and_disables_deinterlace(self) -> None:
        self.assertIn("DNxHR HQX", self.app.summary.cget("text"))
        self.assertEqual(Path(self.app.export_var.get()).name, "dnxhr")
        self.app.deinterlace_var.set(True)
        self.app.mode_var.set("remux")
        self.assertEqual(Path(self.app.export_var.get()).name, "remux")
        self.assertIn("Remux MP4", self.app.summary.cget("text"))
        self.assertIn("AAC", self.app.summary.cget("text"))
        self.assertEqual(str(self.app.deinterlace_chk.cget("state")), "disabled")
        self.assertEqual(str(self.app.gpu_decode_chk.cget("state")), "disabled")
        self.assertTrue(self.app.deinterlace_var.get())
        self.assertTrue(self.app.gpu_decode_var.get())
        self.app.mode_var.set("dnxhr")
        self.assertEqual(Path(self.app.export_var.get()).name, "dnxhr")
        self.assertEqual(str(self.app.deinterlace_chk.cget("state")), "normal")
        self.assertEqual(str(self.app.gpu_decode_chk.cget("state")), "normal")
        self.assertTrue(self.app.deinterlace_var.get())
        custom = Path(self._tmp.name) / "custom-out"
        self.app.export_var.set(str(custom))
        self.app.mode_var.set("remux")
        self.assertEqual(Path(self.app.export_var.get()), custom)
        self.assertEqual(str(self.app.deinterlace_chk.cget("state")), "disabled")
        self.assertEqual(str(self.app.gpu_decode_chk.cget("state")), "disabled")

    def test_start_batch_uses_remux_mp4_and_one_times_estimate(self) -> None:
        self.app.mode_var.set("remux")
        self.app.deinterlace_var.set(True)
        captured: dict[str, object] = {}

        def fake_thread(*_args: object, **kwargs: object) -> mock.Mock:
            captured["args"] = kwargs.get("args")
            worker = mock.Mock()
            worker.start = mock.Mock()
            worker.is_alive = mock.Mock(return_value=False)
            return worker

        with mock.patch.object(gui.threading, "Thread", side_effect=fake_thread), mock.patch.object(
            self.app.root, "after", return_value="idle"
        ), mock.patch.object(
            gui, "estimate_needed_bytes", wraps=gui.estimate_needed_bytes
        ) as estimate:
            self.app._start_batch()
        self.app.running = False
        args = captured["args"]
        assert isinstance(args, tuple)
        pairs, opts = args[0], args[1]
        self.assertEqual(opts.profile, "remux")
        self.assertEqual(opts.container, "mp4")
        self.assertFalse(opts.deinterlace)
        self.assertEqual(opts.hwaccel, "off")
        self.assertEqual(estimate.call_args.kwargs["ratio"], 1)
        for _src, dst in pairs:
            self.assertEqual(dst.suffix, ".mp4")
            self.assertEqual(dst.parent.name, "remux")

    def test_heading_double_click_does_not_open_error_dialog(self) -> None:
        iid = self.app.tree.get_children()[0]
        self.app._rows[iid].status = "failed"
        self.app._rows[iid].error = "boom"
        with mock.patch.object(self.app.tree, "identify_region", return_value="heading"):
            event = mock.Mock(x=5, y=5)
            self.assertIsNone(self.app._on_double_click(event))
        gui.messagebox.showerror.assert_not_called()


if __name__ == "__main__":
    unittest.main()
