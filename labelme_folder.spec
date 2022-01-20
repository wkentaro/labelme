# -*- mode: python -*-
# vim: ft=python

import sys


sys.setrecursionlimit(5000)  # required on Windows


a = Analysis(
    ['labelme/__main__.py'],
    pathex=['labelme'],
    binaries=[],
    datas=[
        ('labelme/config/default_config.yaml', 'labelme/config'),
        ('labelme/icons/*', 'labelme/icons'),
    ],
    hiddenimports=['yaml','termcolor','colorama'],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tflite-runtime","PyOpenGL","PyQt6"],
    noarchive = True
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.datas,
    name='labelme',
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon='labelme/icons/icon.ico',
)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               strip=False,
               upx=True,
               name='main')
