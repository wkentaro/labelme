# -*- mode: python -*-
# vim: ft=python


block_cipher = None


a = Analysis(
    ['labelme/app.py'],
    pathex=['labelme'],
    binaries=[],
    datas=[
        ('labelme/config/default_config.yaml', 'labelme/config'),
        ('labelme/icons/*', 'labelme/icons'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=['winhook.py'],
    excludes=['matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    #a.binaries,
    #a.zipfiles,
    #a.datas,
    name='labelme',
    debug=False,
    strip=False,
	exclude_binaries=True,
    upx=True,
    #runtime_tmpdir=None,
    console=False,
    icon='labelme/icons/icon.ico',
)
#app = BUNDLE(
#    exe,
#    name='labelme.app',
#    icon='labelme/icons/icon.icns',
#    bundle_identifier=None,
#    info_plist={'NSHighResolutionCapable': 'True'},
#)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='labelme')