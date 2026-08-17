#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  Leo桌宠构建脚本
#  1. PyInstaller 打包启动器（launcher.py → Leo桌宠.exe）
#  2. 复制核心程序到 dist/Leo桌宠/app/（可在线更新）
#  3. 生成 version.json（文件清单 + SHA256）
#
#  用法: python build.py
# ============================================================
import os
import sys
import json
import shutil
import hashlib
import subprocess

# ---------- 配置 ----------
DIST_NAME = 'Leo桌宠'
DIST_DIR = os.path.join('dist', DIST_NAME)
APP_DIR = os.path.join(DIST_DIR, 'app')
VERSION = '1.3'

# 需要复制到 app/ 的文件（相对项目根目录）
APP_FILES = [
    'lion_manager.py',
    'lion_desktop.py',
    'lion_watchdog.py',
    'music_theme.py',
    'music_box.py',
    'app-icon.ico',
]

# 需要复制到 app/ 的目录
APP_DIRS = [
    'manager_ui',
    'katong',
    'design',
]


def run_pyinstaller():
    """调用 PyInstaller 打包启动器。"""
    print('[1/3] PyInstaller 打包启动器...')
    env = os.environ.copy()
    env['PYTHONPATH'] = os.path.abspath('_libs') + os.pathsep + env.get('PYTHONPATH', '')
    subprocess.run(
        [sys.executable, '-m', 'PyInstaller', 'build.spec', '--noconfirm', '--clean'],
        env=env, check=True,
    )


def copy_app_files():
    """复制核心程序到 dist/Leo桌宠/app/。"""
    print('[2/3] 复制核心程序到 app/...')
    # 清理旧目录
    if os.path.exists(APP_DIR):
        shutil.rmtree(APP_DIR)
    os.makedirs(APP_DIR)

    # 复制文件
    for f in APP_FILES:
        src = os.path.join('.', f)
        if os.path.exists(src):
            shutil.copy2(src, APP_DIR)

    # 复制目录
    for d in APP_DIRS:
        src = os.path.join('.', d)
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(APP_DIR, d), dirs_exist_ok=True)

    # 移除不需要的 design 文件（只保留 文案.txt）
    design_dir = os.path.join(APP_DIR, 'design')
    if os.path.exists(design_dir):
        for item in os.listdir(design_dir):
            if item != '文案.txt':
                path = os.path.join(design_dir, item)
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)


def gen_version():
    """扫描 app/ 目录生成 version.json。"""
    print('[3/3] 生成 version.json...')
    files = {}
    for root, dirs, filenames in os.walk(APP_DIR):
        for fname in filenames:
            if fname == 'version.json':
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, APP_DIR).replace('\\', '/')
            with open(fpath, 'rb') as f:
                h = hashlib.sha256(f.read()).hexdigest()
            files[rel] = {'hash': h, 'size': os.path.getsize(fpath)}

    version = {'version': VERSION, 'files': files}
    with open(os.path.join(APP_DIR, 'version.json'), 'w', encoding='utf-8') as f:
        json.dump(version, f, ensure_ascii=False, indent=2)

    print(f'  版本: {VERSION}')
    print(f'  文件数: {len(files)}')


def main():
    run_pyinstaller()
    copy_app_files()
    gen_version()
    print(f'\n构建完成！输出目录: {DIST_DIR}')
    print(f'  启动器: {DIST_DIR}/Leo桌宠.exe')
    print(f'  核心程序: {DIST_DIR}/app/')


if __name__ == '__main__':
    main()
