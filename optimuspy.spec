# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# Package directory — use absolute path
src_dir = Path("src").resolve()

# Collect all optimuspy submodules
optimuspy_imports = collect_submodules('optimuspy')

a = Analysis(
    [str(src_dir / 'optimuspy' / '__main__.py')],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        (str(src_dir / 'optimuspy' / 'static'), 'optimuspy/static'),
        (str(src_dir / 'optimuspy' / 'images'), 'optimuspy/images'),
    ],
    hiddenimports=optimuspy_imports + [
        'TM1py.Objects',
        'TM1py.Objects.Element',
        'TM1py.Objects.Cube',
        'TM1py.Objects.Dimension',
        'TM1py.Objects.Process',
        'TM1py.Exceptions',
        'win32timezone',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='optimuspy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
