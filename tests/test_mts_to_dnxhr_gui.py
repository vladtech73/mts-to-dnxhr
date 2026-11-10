"""Tests for the GUI wrapper. No Tk window, FFmpeg, or tkinterdnd2 required."""

from __future__ import annotations

import importlib
import os
import struct
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
