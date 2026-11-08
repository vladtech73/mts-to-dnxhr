# Feedback: Simple drop-and-convert GUI for MTS → DNxHR

*Loop signal: revise*

*Plan: [simple-export-gui-claude-2026-11-07.md](simple-export-gui-claude-2026-11-07.md) · Reviewer: grok · 2026-11-07*

## Verdict
ship-after-fixes — the wrapper matches the CLI, but four written steps contradict `mts_to_dnxhr.py` or the plan’s own tests and Stop flow.

## Summary
The plan reuses `convert_one` instead of scraping ffmpeg, keeps product choices fixed, and grounds the UI in real symbols. Line numbers for `probe`, `run_ffmpeg`, and `convert_one` match the file. The hook steps still mis-state control flow around `mkdir`, `cancel`, and `discover_inputs`’s return value, and the Finish flow calls `os.startfile` on a directory the Stop path is required to delete.

## Blocking
Must fix or resolve before implementation (missing gates, wrong paths, unsafe approach, scope bombs, contradicted repo facts).

- **Cancel-before-probe skips the empty-directory cleanup the new test requires.** In `convert_one`, `mkdir` runs at line 529, then `probe` at line 535. The new `except ConversionCancelled: _remove_dir_if_empty(...); raise` is specified only on the `run_ffmpeg` try (lines 550–561). A cancel check placed “before `probe`” therefore creates `final_dst.parent` and raises outside that handler. `HookTests` says `convert_one(..., cancel=<already set>)` leaves no empty output directory. Raise `ConversionCancelled` before `mkdir` when the destination does not already exist, and keep the `run_ffmpeg` handler for a cancel that arrives after the directory exists. `except ConversionCancelled` has to stay ahead of `except Exception`, which today returns `"failed"`.
- **`cancel.is_set()` is unsafe when `cancel` is `None`.** The new parameter defaults to `None`, and the first hook test drives the `on_progress` loop without setting `cancel`. `run_ffmpeg`’s `except Exception` (lines 494–497) stops ffmpeg, deletes the `.part`, and re-raises, so an `AttributeError` fails the encode instead of leaving the tqdm path alone. Write the check as `cancel is not None and cancel.is_set()`, in the `on_progress` loop and once before `proc.wait()`. Leave the `on_progress is None` tqdm loop as it is, other than `creationflags`.
- **`collect_items` never uses `discover_inputs`’s skipped count.** `discover_inputs` returns `(clips, skipped)` (lines 88–111). The step only says a non-MTS file or a missing path counts as ignored. Folder-internal files such as `.CPI`, `samples/README.md`, and `samples/dnxhr/*.mov` are the `skipped` integer, not top-level rejects. Verification item 2 and the mixed-drop fixture (folder plus a `.CPI`) require that integer added to the ignored total. Say so in `collect_items`, and state the fixture’s expected ignored count (loose `.txt` + missing path + `.CPI`).
- **Finish opens the export folder Stop just deleted.** Checklist item 5 requires the empty `dnxhr` directory to be removed. Finish, which also runs after Stop, always `askyesno`s “Open the export folder?” and then calls `os.startfile(out_dir)`. Tk’s default button is Yes, and `os.startfile` raises `OSError` when the directory is gone. Offer that question only when `out_dir` is an existing directory, and catch `OSError` around `os.startfile`.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

- Hoist `returncode = proc.wait()` out of the `with tqdm` block (it is assigned at line 472 today) so the `on_progress` branch falls through to the existing `.part` size check and `os.replace`. The hook success test should assert `run_ffmpeg` returns `(True, "")` and the `.part` name is gone.
- The cancel fake’s `poll()` must return `None` until `terminate`/`kill`. `_stop_process` (line 390) skips `terminate` otherwise, and a `Mock` poll is not `None`, so “terminate was called” fails.
- Call `on_progress(total, total)` only when `total` is not `None`, matching lines 473–475. The callback annotation is `(float, Optional[float])`. When duration is unknown, the GUI fraction stays `None` until `file_finished`.
- In `run_batch`, catch `ConversionCancelled` before `Exception`. `Exception` would mark that file `failed`.
- While a batch is running, ignore the Delete key. Remove and Clear are disabled, but the key binding is not, and row updates use list indexes.
- Low-disk `askyesno` needs `default="no"` so it matches the product decision. Omitting it selects Yes.
- If `free_bytes` returns `None`, skip the warning. Comparing with `>` raises `TypeError`.
- Format the dialog with decimal gigabytes (`bytes / 1e9`) so the 335 MB sample warns at about 4.7 GB, as in the README.
- Status text “Converting {i} of {n}” is 1-based. Event index `i` from `enumerate` is 0-based; the label should use `i + 1`. On `file_started`, set the row to `0%` or `Converting…` before the first progress event.
- `probe`’s `subprocess.run` (timeout 60s) does not see `cancel`. Note that beside the ffmpeg stall risk.
- Update the Profiles sentence “There is no free-space check before encoding.” The CLI still has none; the GUI warns.
- Add an argv parity case for `options_for(True)`: yadif on interlaced `ProbeInfo`, no yadif on progressive. The written parity test uses `deinterlace=False` only.
- Point `sys.stdout` and `sys.stderr` at `os.devnull` before importing `tqdm` or creating Tk, when they are `None`. `main()` runs after those imports.
- The hook test should cover both `log` lines (`wrote …` and `skipped (exists): …`), with a destination that does not exist in the cancel case so the early exists-check does not return `"skipped"`.

## Nits
Wording, structure, minor clarity.

- `OUTPUT_SUMMARY` is specified as profile, container, and PCM. The wireframe also has “source size/fps”. Build the label from `DEFAULT_OPTIONS` plus that static tail.
- Step 3 should list `from __future__ import annotations` and `import dataclasses` in the GUI module. The constraint already requires the future import.
- The build snippet uses `$py` without showing the assignment. The prose already names `.\.venv\Scripts\python.exe`.
- Checklist item 2 names a `.mov` inside `samples`. That file is on disk now and is gitignored; a tree with only `samples/README.md` ignores one file, not two.
- “Byte-for-byte the same ffmpeg argv as `python mts_to_dnxhr.py <clip>`” is the encode argv from `convert_one` (`force=True`, `*.mov.part`). The dry-run line is `-n` and the final path. The regression check should keep saying the dry-run text is unchanged, and the GUI check should say it calls `convert_one`.
- Put the README “Desktop app (Windows)” section after the Usage section and before Output layout.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- No `.git` directory. `.venv` is Python 3.11.9, Tk 8.6, and `pythonw.exe` is present. `ffmpeg` on PATH is Gyan 8.0.1 (`ffmpeg version 8.0.1-full_build-www.gyan.dev`).
- `probe` is line 215 and calls `subprocess.run` with no `stdin` or `creationflags`. `run_ffmpeg` is line 429; `Popen` uses `stdin=DEVNULL` and no `creationflags`. `convert_one` is line 517. `parse_progress_line` divides `out_time_us` by 1_000_000. `progress=end` returns `None`.
- `discover_inputs(path, recursive)` has no default for `recursive` and returns `(list[Path], int)`. `output_path_for` writes `out_dir / stem.container` when `input_root` is a file (lines 137–138), and mirrors `relative_to(root).parent` for a directory. `find_collisions` returns `dict[Path, list[Path]]`. `default_output_dir` uses `resolve()`, so a file prefill is absolute (`<parent>/dnxhr`).
- `Options` fields match the plan’s `DEFAULT_OPTIONS` construction. `build_parser()` defaults are `dnxhr_hqx`, `mov`, audio 16, `deinterlace` false, `overwrite` false, `duration` unset. `parse_args(["_"])` satisfies the required positional.
- Existing tests do not assert `Popen` or `subprocess.run` kwargs, so `creationflags` does not by itself break `unittest`. They also never call `run_ffmpeg`, so they do not prove the default `cancel=None` encode path. `test_mkdir_oserror` and `test_probe_error_strips_duplicate_path_and_empty_dir` still apply if a `None` cancel does not raise.
- README strings to replace are present: “`tqdm` is the only Python dependency” and “No installer, `pyproject.toml`, or bundled FFmpeg. No GUI.” `requirements.txt` is only `tqdm>=4.60`. `.gitignore` has `dnxhr/` and no `build/` or `dist/`. `mts_to_dnxhr_gui.py` and `scripts/` are absent.
- `samples/` currently contains `01 American Landscape.MTS`, `README.md`, and `dnxhr/01 American Landscape.mov`.
- Not run: unit tests, a real encode, `tkinterdnd2` install, or PyInstaller. The `tkinterdnd2>=0.4,<0.5` pin and `--collect-all tkinterdnd2` are still an implementation check, with the plan’s Browse-only fallback if the DLLs are missed.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- In step 1, one sentence: “If `cancel` is already set, raise `ConversionCancelled` before `mkdir`. On `ConversionCancelled` from `run_ffmpeg`, call `_remove_dir_if_empty(final_dst.parent)` and re-raise. Never treat that exception as `failed`.”
- In the `on_progress` branch: “Guard `cancel` with `is not None`. Set `returncode` from `proc.wait()` and use the existing publish check. Snap `on_progress(total, total)` only when `total` is not `None`.”
- In `collect_items`: “`ignored += skipped` from `discover_inputs`. Expected mixed-drop ignored count is 3.”
- In Finish: “Call `os.startfile` only when `out_dir.is_dir()`, inside `try/except OSError`.”
- In the disk dialog: “`askyesno(..., default='no')`, with GB = bytes / 1e9. If `free_bytes` is `None`, do not prompt.”

## Confidence
high — the blocking items were checked against `mts_to_dnxhr.py`, the tests, the README, and the local interpreter. Packaging and the `tkinterdnd2` wheel were not executed.
