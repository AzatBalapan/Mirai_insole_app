# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

from PyInstaller.utils.hooks import Tree

a = Analysis(
    ['main.py'],  # Replace 'main.py' with your actual script name if different
    pathex=['C:\\Users\\azatz\\Desktop\\insoles test'],
    binaries=[],
    datas=[
        Tree('static', prefix='static'),            # Include entire 'static' directory
        Tree('recordings', prefix='recordings'),    # Include entire 'recordings' directory
        ('insole_image.jpeg', '.')                  # Include 'insole_image.jpeg' in root
    ],
    hiddenimports=[
        "cv2",
        "fastapi",
        "uvicorn",
        "starlette",
        "pydantic",
        "bleak",
        "bleak.backends",
        "bleak.exc",
        "psutil",
        "webview",
        "PyQt5",          # Include if using PyQt5 backend
        # "PySide2",      # Uncomment if using PySide2 instead
        # "cefpython3"    # Uncomment if using CEF backend
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InsoleSensorApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to True to enable console for debugging
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='InsoleSensorApp'
)
