#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  lion_watchdog.py
#  狮子桌宠守护进程：宠物异常退出时自动重启；
#  若用户主动退出（右键"退出"写了标记文件）或管理软件停止则不再重启。
#  socket 单实例锁：重复双击 bat 不会起第二个 watchdog。
# ============================================================
import os
import sys
import time
import socket
import subprocess

if getattr(sys, 'frozen', False):
    # 被启动器调用：用户文件放 exe 目录，核心代码在 app/ 目录
    EXE_DIR = os.path.dirname(sys.executable)
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
else:
    # 独立运行（开发模式）
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = APP_DIR
MARKER = os.path.join(EXE_DIR, 'lion_clean_exit.txt')
SCRIPT = os.path.join(APP_DIR, 'lion_desktop.py')
PY = sys.executable


def main():
    # 单实例锁：已有 watchdog 在跑 -> 安静退出
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(('127.0.0.1', 52717))
        lock.listen(1)
    except OSError:
        sys.exit(0)

    try:
        os.remove(MARKER)
    except OSError:
        pass

    while True:
        if getattr(sys, 'frozen', False):
            # 被启动器调用：用启动器 exe + --run 参数启动子进程
            p = subprocess.Popen([sys.executable, '--run', 'lion_desktop'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            p = subprocess.Popen([PY, SCRIPT],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        p.wait()
        if os.path.exists(MARKER):           # 用户主动退出 -> 不再重启
            try:
                os.remove(MARKER)
            except OSError:
                pass
            break
        time.sleep(2)                        # 崩溃后等 2s 重启


if __name__ == '__main__':
    main()
