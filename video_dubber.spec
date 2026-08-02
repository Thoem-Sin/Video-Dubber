import whisper
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

whisper_dir = os.path.dirname(whisper.__file__)
whisper_assets = os.path.join(whisper_dir, 'assets')

added_files = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('voices_config.py', '.'),
    ('gender_detector.py', '.'),
    ('dubbing_engine.py', '.'),
    ('font_manager.py', '.'),
    (whisper_assets, 'whisper/assets'),
] + collect_data_files('whisper') + collect_data_files('tiktoken')

a = Analysis(
    ['run_app.py'],
    pathex=['.'],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'flask',
        'edge_tts',
        'deep_translator',
        'whisper',
        'torch',
        'wave',
        'contextlib',
        'shutil',
        'asyncio',
        'tkinter',
        'tkinter.filedialog',
        'webview',
        'clr',
        'clr_loader',
        'openvoice_cli',
        'openvoice_cli.api',
        'openvoice_cli.downloader',
        'openvoice_cli.models',
        'openvoice_cli.modules',
        'openvoice_cli.attentions',
        'openvoice_cli.commons',
        'openvoice_cli.mel_processing',
        'openvoice_cli.transforms',
        'openvoice_cli.utils',
        'librosa',
        'soundfile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'notebook'],
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
    name='VideoDubberStudio',
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
    name='VideoDubberStudio',
)
