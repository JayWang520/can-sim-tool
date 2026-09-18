# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
from app.build_info import APP_VERSION, VERSION_TUPLE

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileDescription', 'CAN Test Workbench'),
        StringStruct('FileVersion', APP_VERSION),
        StringStruct('ProductName', 'CAN Sim Tool'),
        StringStruct('ProductVersion', APP_VERSION),
        StringStruct('OriginalFilename', 'CanSimTool.exe'),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)

hiddenimports = ['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on']
hiddenimports += collect_submodules('can.interfaces')
hiddenimports += collect_submodules('cantools')


a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[('web/app.js', 'web'), ('web/i18n.js', 'web'), ('web/analysis.js', 'web'), ('web/index.html', 'web'), ('web/style.css', 'web'),
           ('web/icon.svg', 'web'), ('web/icon.ico', 'web'),
           ('scenarios', 'scenarios'), ('dbcs', 'dbcs'), ('presets', 'presets')],
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
    name='CanSimTool',
    icon='web/icon.ico',
    version=version_info,
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
    name='CanSimTool',
)
