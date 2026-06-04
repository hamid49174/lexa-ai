# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(__file__).resolve().parent


a = Analysis(
    [str(ROOT / 'backend' / 'pyinstaller_entry.py')],
    pathex=[],
    binaries=[],
    datas=[(str(ROOT / 'command_whitelist.json'), '.')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'backend.main', 'backend.ai_engine', 'backend.memory', 'backend.productivity', 'backend.security', 'backend.action_parser', 'backend.router_companion', 'backend.router_voice', 'backend.router_productivity', 'companion.engine', 'companion.browser', 'companion.file_tools', 'companion.media', 'companion.communication', 'companion.system_tools', 'companion.dev_tools', 'voice.tts', 'voice.stt'],
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
    name='lexa-backend',
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
    name='lexa-backend',
)
