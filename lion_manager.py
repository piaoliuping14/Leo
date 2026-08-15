#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  桌宠管理软件 (Python 版)
#  - 管理主页：启动宠物 / 显示宠物运行状态
#  - 快捷指令配置：增删改查，保存到 config.json（桌宠读取）
#  - 关闭窗口（×）仅退出管理软件，桌宠继续运行（右键桌宠可退出）
#  基于 pywebview + HTML，复用 design/pet-manager.design 的 UI 设计稿。
#
#  用法:
#     python lion_manager.py
#     pythonw lion_manager.py        (无控制台)
# ============================================================
import os
import sys
import json
import time
import socket
import subprocess

import webview

# ---------- 路径 ----------
DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(DIR, 'config.json')
WATCHDOG = os.path.join(DIR, 'lion_watchdog.py')
CLEAN_EXIT = os.path.join(DIR, 'lion_clean_exit.txt')
HTML = os.path.join(DIR, 'manager_ui', 'app.html')
PYW = sys.executable                 # bat 用 pythonw 启动，故为 pythonw.exe
PET_PORT = 52718                     # 桌宠单实例锁端口（lion_desktop.py）
MGR_PORT = 52719                     # 管理软件单实例锁端口


class ManagerApi:
    """暴露给前端 JS 的 Python 接口（window.pywebview.api.xxx）。"""

    def __init__(self):
        self._window = None

    # ---------- 宠物状态 ----------
    def get_status(self):
        """桌宠是否在运行：尝试连接其单实例锁端口。"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            s.connect(('127.0.0.1', PET_PORT))
            s.close()
            return True
        except OSError:
            try:
                s.close()
            except Exception:
                pass
            return False

    # ---------- 启动 / 退出 ----------
    def start_pet(self):
        if self.get_status():
            return True
        try:
            try:
                os.remove(CLEAN_EXIT)          # 清掉旧标记，允许 watchdog 正常工作
            except OSError:
                pass
            subprocess.Popen([PYW, WATCHDOG],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            return False

    def stop_pet(self):
        # 写 clean_exit：让 watchdog 检测到桌宠退出后不再自动重启
        try:
            with open(CLEAN_EXIT, 'w') as f:
                f.write('ok')
        except Exception:
            pass
        # 多轮杀进程，防止 watchdog 抢先重启桌宠
        for _ in range(3):
            self._kill_lion()
            time.sleep(0.4)
        return True

    # ---------- 已安装应用枚举 ----------
    def list_apps(self):
        """枚举系统已安装应用（开始菜单），返回 [{name,type,target,icon}]。
        type='app'  -> MSIX/UWP 应用，target 为 AUMID（shell:AppsFolder 启动）；
        type='file' -> 传统程序，target 为 .exe/.lnk 路径（os.startfile 启动）。
        供前端"从已安装应用选择"使用，免去用户手填 AUMID。"""
        # PS 脚本：Get-StartApps 取开始菜单全部应用；对 {GUID}\rest 形式的
        # Known Folder 路径用 SHGetKnownFolderPath 解析为真实路径，否则 os.startfile 打不开。
        ps = r'''[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -Namespace Win32 -Name KF -MemberDefinition '
[DllImport("shell32.dll", CharSet=CharSet.Unicode)]
public static extern int SHGetKnownFolderPath([MarshalAs(UnmanagedType.LPStruct)] Guid rfid, uint dwFlags, IntPtr hToken, out IntPtr pszPath);
public static string Resolve(Guid g) {
  IntPtr ptr = IntPtr.Zero;
  try { SHGetKnownFolderPath(g, 0, IntPtr.Zero, out ptr); return System.Runtime.InteropServices.Marshal.PtrToStringUni(ptr); }
  finally { if (ptr != IntPtr.Zero) System.Runtime.InteropServices.Marshal.FreeCoTaskMem(ptr); }
}'
Get-StartApps | ForEach-Object {
  $id = $_.AppID
  if ($id -match '^\{[^}]+\}\\(.*)$') {
    $parts = $id -split '\\',2
    try { $base = [Win32.KF]::Resolve([Guid]$parts[0]) } catch { $base = $null }
    if ($base) { $id = Join-Path $base $parts[1] }
  }
  [PSCustomObject]@{ Name=$_.Name; AppID=$id }
} | ConvertTo-Json -Compress'''
        try:
            r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                               capture_output=True, timeout=20,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            items = json.loads(r.stdout.decode('utf-8'))
            if isinstance(items, dict):          # 单条记录时 PS 返回 dict
                items = [items]
            out = []
            for it in items:
                name = (it.get('Name') or '').strip()
                appid = (it.get('AppID') or '').strip()
                if not name or not appid:
                    continue
                t = 'file' if '\\' in appid else 'app'
                out.append({'name': name, 'type': t,
                            'target': appid, 'icon': 'monitor'})
            return out
        except Exception:
            return []

    # ---------- 快捷指令配置 ----------
    def get_commands(self):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f).get('commands', [])
        except Exception:
            return []

    def save_commands(self, commands):
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump({'commands': commands}, f,
                          ensure_ascii=False, indent=2)
        except Exception:
            return False
        # 桌宠在跑则重启，使新配置即时生效
        if self.get_status():
            self.stop_pet()
            time.sleep(1)
            self.start_pet()
        return True

    # ---------- 进程清理 ----------
    def _kill_lion(self):
        try:
            subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "Get-CimInstance Win32_Process -Filter "
                 "\"Name='pythonw.exe' OR Name='python.exe'\" | "
                 "Where-Object { $_.CommandLine -like '*lion_desktop.py*' "
                 "-or $_.CommandLine -like '*lion_watchdog.py*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                 "-ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass


def main():
    # 管理软件单实例锁：重复启动直接退出
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(('127.0.0.1', MGR_PORT))
        lock.listen(1)
    except OSError:
        sys.exit(0)

    if not os.path.exists(HTML):
        raise FileNotFoundError('找不到管理界面: ' + HTML)

    api = ManagerApi()
    window = webview.create_window(
        '桌宠管理', HTML, js_api=api,
        width=440, height=720, resizable=False, min_size=(420, 600))
    api._window = window
    webview.start()


if __name__ == '__main__':
    main()
