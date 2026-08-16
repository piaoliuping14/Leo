# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  Leo桌宠 PyInstaller 打包配置（热更新架构）
#  只打包 launcher.py（启动器），包含完整 Python 运行时和依赖。
#  核心程序（lion_*.py + 资源）由 build.py 复制到 dist/Leo桌宠/app/，
#  支持在线更新，无需重新打包。
#
#  构建命令:
#    python build.py
# ============================================================

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    hiddenimports=[
        'lion_manager', 'lion_desktop', 'lion_watchdog',
        'music_theme', 'music_box',
        'webview', 'webview.platforms.edgechrom', 'webview.platforms.mshtml',
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw',
        # 音乐盒：SMTC 媒体控制（winrt）+ 音量控制（pycaw）
        'pycaw', 'pycaw.pycaw', 'comtypes',
        'winrt', 'winrt.windows.media.control',
        'winrt.windows.storage.streams',
        # WebView2 后端依赖（clr_loader 用于加载 WebView2 COM 组件）
        'clr_loader',
    ],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6',
              'django', 'matplotlib', 'numpy', 'pandas'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='Leo桌宠',
    console=False,
    icon='app-icon.ico',
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    name='Leo桌宠',
)
