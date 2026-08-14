#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  lion_watchdog.py
#  狮子桌宠守护进程：宠物异常退出时自动重启；
#  若用户主动退出（右键“退出”写了标记文件）则停止。
#  socket 单实例锁：重复双击 bat 不会起第二个 watchdog。
# ============================================================
import os
import sys
import time
import socket
import subprocess

DIR = os.path.dirname(os.path.abspath(__file__))
MARKER = os.path.join(DIR, 'lion_clean_exit.txt')
SCRIPT = os.path.join(DIR, 'lion_desktop.py')
PY = sys.executable          # bat 用 pythonw 启动本脚本，故此处为 pythonw.exe


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
        p = subprocess.Popen([PY, SCRIPT])
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
