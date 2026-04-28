# PyInstaller spec — onefile, macOS arm64 only.
# Build: pyinstaller sysinstall.spec

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis

a = Analysis(
    ["src/sysinstall/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "plistlib",
        "sysinstall.cli.disk",
        "sysinstall.cli.usb",
        "sysinstall.cli.iso",
        "sysinstall.cli.boot",
        "sysinstall.core.platform",
        "sysinstall.core.logging",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sysinstall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",
)
