# -*- mode: python ; coding: utf-8 -*-

import importlib.machinery
import os
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).parents[1]
backend_root = repo_root / "backend"

import tiktoken
import tiktoken_ext

tiktoken_ext_path = list(tiktoken_ext.__path__)[0]
tiktoken_path = os.path.dirname(tiktoken.__file__)
ext_suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
tiktoken_so = os.path.join(tiktoken_path, "_tiktoken" + ext_suffix)


a = Analysis(
    [str(backend_root / "app" / "packaged_launcher.py")],
    pathex=[str(backend_root)],
    binaries=[],
    datas=[
        (tiktoken_ext_path, "tiktoken_ext"),
        (tiktoken_so, "tiktoken"),
        (str(backend_root / "app" / "execution" / "prompts"), "app/execution/prompts"),
    ],
    hiddenimports=[
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_asyncio"],
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
    name="reflexion-backend",
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="reflexion-backend",
)
