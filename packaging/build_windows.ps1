# Baut AutoApplication fuer Windows: Programmordner + Setup-EXE (Inno Setup).
# Aufruf in PowerShell:  powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Push-Location $root
try {
    Write-Host "== Abhaengigkeiten installieren =="
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.txt pyinstaller pillow

    $version = & $python -c "import sys; sys.path.insert(0, 'src'); from autoapplication import APP_VERSION; print(APP_VERSION)"
    Write-Host "== AutoApplication $version bauen =="

    if (-not (Test-Path "packaging\autoapplication.ico")) {
        Write-Host "== Symbol erzeugen =="
        & $python packaging\make_icon.py
    }

    & $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\autoapplication.spec

    Write-Host "== Selbsttest der gebauten Anwendung =="
    # GUI-Anwendung: nicht einfach aufrufen, sondern auf das Prozessende warten.
    $tested = Start-Process -FilePath "dist\AutoApplication\AutoApplication.exe" `
        -ArgumentList "--self-test" -Wait -PassThru -NoNewWindow
    if ($tested.ExitCode -ne 0) {
        throw "Selbsttest fehlgeschlagen (Exit-Code $($tested.ExitCode))"
    }

    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $iscc) {
        Write-Host "== Installer erstellen =="
        & $iscc "/DAppVersion=$version" "packaging\installer.iss"
        Write-Host "Fertig: dist\AutoApplication-$version-Setup.exe"
    }
    else {
        Write-Warning "Inno Setup 6 nicht gefunden. Programmordner liegt in dist\AutoApplication."
        Write-Warning "Installer: ISCC.exe installieren (https://jrsoftware.org/isdl.php) und Skript erneut ausfuehren."
    }
}
finally {
    Pop-Location
}
