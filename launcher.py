#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  Leo桌宠启动器 / 更新器
#  - 打包一次即固定，包含完整 Python 运行时和依赖
#  - 核心程序（lion_*.py + 资源）放在 app/ 目录，支持在线更新
#  - --run <module>  : 子进程模式，运行指定核心模块
#  - 正常启动        : 检查更新 → 运行 lion_manager
# ============================================================
import os
import sys
import json
import shutil
import hashlib
import ctypes
import subprocess
import winreg
import urllib.request

# ---------- 路径 ----------
if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
    APP_DIR = os.path.join(EXE_DIR, 'app')
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = EXE_DIR

VERSION_FILE = os.path.join(APP_DIR, 'version.json')

# 更新源 URL（为空则跳过更新检查）
# 部署时改为实际地址，如 'https://your-server.com/leo-updates'
UPDATE_URL = os.environ.get('LEO_UPDATE_URL', '')

# 构建开关：Store 版（MSIX）打包时置 1 → 跳过自更新，由微软商店分发更新
STORE_BUILD = os.environ.get('STORE_BUILD', '0') == '1'


# ---------- WebView2 Runtime 依赖检测 ----------
# pywebview 的 edgechrom 后端需要 WebView2 Runtime（Win11 自带，旧 Win10 可能缺失）。
# 缺失时弹窗引导下载 Evergreen Bootstrapper，避免黑屏报错。
_WEBVIEW2_REGKEYS = (
    r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
)
_WEBVIEW2_BOOTSTRAPPER = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'


def check_webview2():
    """检测 WebView2 Runtime 是否已安装。"""
    for key in _WEBVIEW2_REGKEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                winreg.QueryValueEx(k, 'pv')  # 有 pv 值即已安装
            return True
        except FileNotFoundError:
            continue
        except Exception:
            pass
    return False


def ensure_webview2_or_prompt():
    """缺失 WebView2 时弹窗引导下载，用户确认后打开官方下载页并退出。"""
    if check_webview2():
        return
    # MB_ICONINFORMATION(0x40) | MB_OKCANCEL(0x1)
    ret = ctypes.windll.user32.MessageBoxW(
        0,
        '本应用需要 WebView2 Runtime（Win10 旧版可能未自带）。\n'
        '点击「确定」打开微软官方下载页，安装后再次启动本应用。',
        '需要 WebView2 Runtime',
        0x40 | 0x1,
    )
    if ret == 1:  # IDOK
        subprocess.Popen(['cmd', '/c', 'start', '', _WEBVIEW2_BOOTSTRAPPER])
    sys.exit(1)


def _file_hash(path):
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _local_version():
    """读取本地版本清单。"""
    try:
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _download_file(rel_path):
    """从更新源下载单个文件到 app/ 目录。"""
    try:
        url = UPDATE_URL.rstrip('/') + '/' + rel_path.replace('\\', '/')
        dest = os.path.join(APP_DIR, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        resp = urllib.request.urlopen(url, timeout=30)
        with open(dest, 'wb') as f:
            shutil.copyfileobj(resp, f)
        return True
    except Exception:
        return False


def check_and_update():
    """检查远程版本，下载变更文件。更新失败不影响启动。"""
    if STORE_BUILD:
        return  # Store 版：由微软商店负责更新，禁止自更新
    if not UPDATE_URL:
        return
    try:
        url = UPDATE_URL.rstrip('/') + '/version.json'
        resp = urllib.request.urlopen(url, timeout=5)
        remote = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return  # 网络错误，跳过更新

    local = _local_version()
    remote_files = remote.get('files', {})
    local_files = local.get('files', {})

    updated = False
    for rel_path, info in remote_files.items():
        local_hash = local_files.get(rel_path, {}).get('hash', '')
        if info.get('hash') != local_hash:
            if _download_file(rel_path):
                updated = True

    if updated:
        try:
            with open(VERSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(remote, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def run_module(module_name):
    """在当前进程中运行核心模块。"""
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    mod = __import__(module_name)
    if hasattr(mod, 'main'):
        mod.main()


def main():
    # 子进程模式：--run <module>
    if '--run' in sys.argv:
        idx = sys.argv.index('--run')
        if idx + 1 < len(sys.argv):
            run_module(sys.argv[idx + 1])
        return

    # 正常启动：WebView2 检测 → 检查更新 → 运行管理软件
    ensure_webview2_or_prompt()
    check_and_update()
    run_module('lion_manager')


if __name__ == '__main__':
    main()
