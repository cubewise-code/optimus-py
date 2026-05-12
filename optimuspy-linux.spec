# -*- mode: python ; coding: utf-8 -*-
# Linux build: --onedir layout. Avoids PyInstaller --onefile extracting to /tmp,
# which fails on hardened RHEL hosts where /tmp is mounted noexec.
# UPX disabled to avoid SELinux execmod denials on the bundled .so files.

hiddenimports = ['seaborn', 'execution_mode', 'executors', 'results']

a = Analysis(
    ['optimuspy.py'],
    pathex=[],
    binaries=[],
    datas=[('execution_mode.py', '.'), ('executors.py', '.'), ('results.py', '.')],
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='optimuspy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='optimuspy',
)
