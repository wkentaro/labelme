# -*- mode: python -*-


block_cipher = None


a = Analysis(['app.py'],
             pathex=['.'],
             binaries=[],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='labelme',
          debug=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=False , icon='labelme/icons/icon.icns')
app = BUNDLE(exe,
             name='labelme.app',
             icon='labelme/icons/icon.icns',
             bundle_identifier=None,
             info_plist={'NSHighResolutionCapable': 'True'})
