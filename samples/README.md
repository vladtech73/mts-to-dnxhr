# Samples

Drop one or more `.MTS` or `.M2TS` clips in this folder to try the converter locally.

Media is gitignored. Do not commit `.MTS`, `.M2TS`, `.mov`, or `.mxf` files.

The opt-in smoke test uses the first `.mts` or `.m2ts` file it finds here (non-recursive):

```powershell
$env:MTS_SMOKE='1'; python -m unittest -v
```

Without `MTS_SMOKE=1`, `python -m unittest -v` skips that encode and does not need a sample or FFmpeg.
