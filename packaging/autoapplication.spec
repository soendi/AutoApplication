# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Build fuer AutoApplication (onedir inkl. Vorlagen und Qt)."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # .../packaging
SRC = ROOT / "src"

datas = [
    (
        str(SRC / "autoapplication" / "data" / "templates.json"),
        "autoapplication/data",
    ),
    (
        str(SRC / "autoapplication" / "data" / "ocr-test.png"),
        "autoapplication/data",
    ),
]

OCR_MODULES = (
    "{}.windows.media.ocr",
    "{}.windows.graphics.imaging",
    "{}.windows.globalization",
    "{}.windows.storage.streams",
)

# Texterkennung nur einbinden, wenn sie auf dem Build-Rechner vorhanden ist.
ocr_imports = []
for package in ("winrt", "winsdk"):
    try:
        __import__(package)
    except Exception:
        continue
    ocr_imports.extend(module.format(package) for module in OCR_MODULES)

icon_file = ROOT / "packaging" / "autoapplication.ico"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=ocr_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "pytest",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtDesigner",
        "PySide6.QtTest",
        "PySide6.QtSql",
        "PySide6.QtNetworkAuth",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoApplication",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_file) if icon_file.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AutoApplication",
)
