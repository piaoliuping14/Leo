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

    # 正常启动：检查更新 → 运行管理软件
    check_and_update()
    run_module('lion_manager')


if __name__ == '__main__':
    main()
