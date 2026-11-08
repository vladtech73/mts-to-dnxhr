$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "Missing $py. Create .venv and install requirements-build.txt."
    exit 1
}
$ico = Join-Path $root 'assets\app.ico'
if (-not (Test-Path -LiteralPath $ico)) {
    Write-Error "Missing assets\app.ico. Run scripts\make_icon.py first."
    exit 1
}
Push-Location $root
try {
    & $py -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name "MTS-to-DNxHR" `
        --icon $ico `
        --add-data "$ico;assets" `
        --collect-all tkinterdnd2 `
        --specpath build --workpath build --distpath dist `
        mts_to_dnxhr_gui.py
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
Write-Output (Join-Path $root 'dist\MTS-to-DNxHR.exe')
