# Feedback: Simple drop-and-convert GUI for MTS → DNxHR

*Loop signal: satisfied*

*Plan: [simple-export-gui-claude-2026-11-07.md](simple-export-gui-claude-2026-11-07.md) · Reviewer: grok · 2026-11-07*

## Verdict
solid-with-nits — the round-1 contradictions are fixed against `mts_to_dnxhr.py`, and the plan is safe to implement as written.

## Summary
The wrapper still calls `convert_one` instead of scraping ffmpeg, and the product choices stay fixed. Cancel-before-`mkdir`, the `cancel is not None` guard, `ignored += skipped`, and opening the export folder only when it still exists now match the control flow and the tests that require them. What remains is clarification around drops during a run, when the export directory is created, and `progress=end` lines. None of that changes the encode argv or blocks implementation.

## Blocking
None.

## Non-blocking
Should improve; plan can proceed if explicitly deferred.

- **A disabled drop zone still accepts `<<Drop>>`.** `state=disabled` does not unregister tkinterdnd2. The plan already ignores Delete while running because row updates use list indexes, and Remove/Clear are disabled, but the drop zone and Treeview stay registered. Appending a row does not shift earlier indexes; the new row is also not in the snapshotted batch, so it stays Waiting. Say the `<<Drop>>` handlers return immediately while a batch is running.
- **`mkdir` runs before the name-clash abort.** Convert creates the export directory, then `plan_outputs` / `find_collisions`. `main()` returns 2 at the collision check (lines 779–782) before `_encode_all`, so the CLI creates nothing. Checklist 8 says a clash writes nothing. Move `mkdir` to after the clash dialog and after the disk-space prompt is accepted. A rejected run then leaves the disk untouched.
- **`progress=end` parses to `None`.** `parse_progress_line` returns `None` for that key (lines 249–262), and the tqdm loop continues (lines 465–466). The hook fake includes `progress=end\n`, while the expected callbacks are only `(0.5, total)`, `(1.0, total)`, then `(total, total)`. The callback is typed `(float, Optional[float])`. Say the `on_progress` branch uses the same `continue`, so a `None` parse is not forwarded into `seconds / total`.

## Nits
Wording, structure, minor clarity.

- Set the busy cursor back to `""` in a `finally`. The add flow only shows `root.config(cursor="watch")`.
- Keep `from __future__ import annotations` as the first statement. The devnull guard belongs after the stdlib imports and before `import mts_to_dnxhr` and `import tkinter`.
- Use "No .MTS/.M2TS files found in what you added." only when both the new-clip count and the ignored count are 0. Checklists 2 and 9 still need the Ignored sentence when nothing new was added.
- The `log=list.append` success case needs `on_progress` (or a tqdm patch). Otherwise `run_ffmpeg` still draws a bar and the stderr capture is not empty. The skipped-exists case never reaches `run_ffmpeg`.

## Spot-checks
What was verified in the repo (paths, symbols, commands). Note anything that could not be checked.

- Round-1 cancel-before-`mkdir`: `convert_one` returns "skipped" at lines 525–527, `mkdir` is at 529, and the `run_ffmpeg` try is 550–561. `except Exception` at 558–561 returns `"failed"`. The plan raises `ConversionCancelled` after the exists-check and before `mkdir`, and handles a later cancel on that try before `OSError` / `Exception`. `_remove_dir_if_empty` is `rmdir` (lines 365–369), so a cancelled sole file removes an empty export directory. Checklist 5 and the Finish `is_dir()` guard agree.
- Round-1 `cancel is None`: the plan writes `cancel is not None and cancel.is_set()` on the `on_progress` branch only. `except Exception` in `run_ffmpeg` (lines 494–497) stops ffmpeg, unlinks the `.part`, and re-raises, so an `AttributeError` there would still fail the encode.
- Round-1 skip count: `discover_inputs` returns `(list[Path], int)` and increments `skipped` only for non-input files (lines 88–111). `collect_items` adds that integer. The mixed-drop expected count of 3 matches one loose `.txt`, one missing path, and one `.CPI`. `samples/` on disk is the clip, `README.md`, and `dnxhr\01 American Landscape.mov`, so a folder drop ignores 2 files when that gitignored `.mov` is present. Checklist 2 says that.
- `probe` (line 215) calls `subprocess.run` with no `stdin` or `creationflags`. `run_ffmpeg` (line 429) uses `stdin=DEVNULL` and no `creationflags`. `Popen` is only in `run_ffmpeg`. Existing tests do not assert those kwargs. `test_mkdir_oserror` and `test_probe_error_strips_duplicate_path_and_empty_dir` still pass if a default `cancel=None` does not raise. They never call `run_ffmpeg`.
- `Options` fields match `DEFAULT_OPTIONS`. Parser defaults are `dnxhr_hqx`, `mov`, audio 16, deinterlace off, overwrite off, duration unset. `YADIF` is `yadif=mode=send_frame:...` (line 35). `build_command` adds it only when deinterlace is set and info is missing or interlaced (lines 304–305). README line 57 and the interlaced section confirm `--deinterlace` stays at `30000/1001` with the same frame count. Checklist 7 matches that, not a 59.94p conversion.
- `output_path_for` writes `out_dir / stem.container` when the root is a file (lines 137–138) and mirrors `relative_to(root).parent` for a directory. `find_collisions` is case-insensitive on Windows. `default_output_dir` uses `resolve()`, so a file prefill is `<parent>/dnxhr`.
- `.venv` is Python 3.11.9, Tk 8.6. `ffmpeg version 8.0.1-full_build-www.gyan.dev` is on PATH. No `.git` directory. `mts_to_dnxhr_gui.py` and `scripts/` are absent. `requirements.txt` is only `tqdm>=4.60`. `.gitignore` has `dnxhr/` and no `build/` or `dist/`.
- README strings to edit are present: "`tqdm` is the only Python dependency" (Requirements), "There is no free-space check before encoding." (Profiles, line 48), and "No installer, `pyproject.toml`, or bundled FFmpeg. No GUI." (Limitations). Usage is section-heading line 60 and Output layout is line 103, so the new section slot is real.
- Not run: `unittest`, a real encode, `tkinterdnd2` install, or PyInstaller. The `tkinterdnd2>=0.4,<0.5` pin and `--collect-all tkinterdnd2` stay implementation checks, with the plan’s Browse-only fallback if the DLLs are missed.

## Suggested steals / strengtheners
Concrete additions the author should fold into the plan (not a competing rewrite).

- In the convert-click disable list: "`<<Drop>>` handlers return without adding rows while running."
- In that same click flow: "`mkdir` the export folder only after the name-clash check passes and the disk warning is not declined."
- In the `on_progress` branch: "If `parse_progress_line` returns `None`, continue, as the tqdm loop does."

## Confidence
high — the closed blockers and the remaining notes were checked against `mts_to_dnxhr.py`, the tests, the README, and the files currently in `samples/`. Packaging and the `tkinterdnd2` wheel were not executed.
