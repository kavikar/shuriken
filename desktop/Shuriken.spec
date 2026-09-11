# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['shuriken.py'],
    pathex=[],
    binaries=[],
    # Menu tools are bundled from their canonical home under projects/menu/.
    # They used to be vendored into desktop/servers/, which silently drifted out
    # of sync with the originals — bundle from the source of truth instead.
    datas=[
        ('app', 'app'),
        ('../projects/menu/analyzer', 'servers/menu_delta_analyzer'),
        ('../projects/menu/mapper', 'servers/menu_mapping_validator'),
        ('../projects/menu/findUnmapped', 'servers/find_unmapped'),
    ],
    hiddenimports=['app', 'app.main', 'app.config', 'app.helpers', 'app.views', 'app.views.otp', 'app.views.menu_delta', 'app.views.unmapped', 'app.views.find_unmapped'],
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
    name='Shuriken',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='Shuriken',
)
