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
import struct
import ctypes
import subprocess
import threading
import tkinter as tk
from PIL import Image, ImageTk

import webview

# ---------- 路径 ----------
DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(DIR, 'config.json')
WATCHDOG = os.path.join(DIR, 'lion_watchdog.py')
CLEAN_EXIT = os.path.join(DIR, 'lion_clean_exit.txt')


def _get_machine_id():
    """获取当前 Windows 机器的唯一 ID（MachineGuid）。
    用于设备绑定：区分"本机配置"与"分享/换设备首次打开"。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\Microsoft\Cryptography') as key:
            guid, _ = winreg.QueryValueEx(key, 'MachineGuid')
        return guid
    except Exception:
        return ''


def _ensure_device_config():
    """确保 config.json 中的设备相关配置与当前设备绑定。
    - config.json 不存在：不做处理
    - machine_id 缺失：首次运行，写入当前机器 ID
    - machine_id 不匹配：换设备/被分享，重置 idle_timeout=60，更新机器 ID
    - machine_id 匹配：正常使用，不做处理"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return
    cur_mid = _get_machine_id()
    saved_mid = data.get('machine_id', '')
    if not saved_mid:
        try:
            data['machine_id'] = cur_mid
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    elif cur_mid and saved_mid != cur_mid:
        try:
            data['idle_timeout'] = 60
            data['machine_id'] = cur_mid
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
HTML = os.path.join(DIR, 'manager_ui', 'app.html')
PYW = sys.executable                 # bat 用 pythonw 启动，故为 pythonw.exe
PET_PORT = 52718                     # 桌宠单实例锁端口（lion_desktop.py）
MGR_PORT = 52719                     # 管理软件单实例锁端口


class ManagerApi:
    """暴露给前端 JS 的 Python 接口（window.pywebview.api.xxx）。"""

    def __init__(self):
        self._window = None
        self._shown = False
        self._stop_splash = None        # 由 main() 注入

    def page_loaded(self):
        """前端 init() 完成后调用：显示 webview 窗口并关闭 splash。"""
        if self._shown:
            return
        self._shown = True
        if self._window:
            self._window.show()
        if self._stop_splash:
            self._stop_splash.set()

    # ---------- 宠物状态 ----------
    def get_status(self):
        """桌宠是否在运行：尝试连接其单实例锁端口。
        用 SO_LINGER(0) 发 RST 而非 FIN，避免连接堆积在宠物的
        accept 队列中导致后续检测失败。"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                     struct.pack('ii', 1, 0))
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
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['commands'] = commands
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            return False
        return True

    # ---------- 设置 ----------
    def get_settings(self):
        _ensure_device_config()            # 设备绑定校验（分享/换设备时重置间隔）
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                'idle_bubble_enabled': data.get('idle_bubble_enabled', True),
                'idle_timeout': data.get('idle_timeout', 60)
            }
        except Exception:
            return {'idle_bubble_enabled': True, 'idle_timeout': 60}

    def save_settings(self, settings):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['idle_bubble_enabled'] = settings.get('idle_bubble_enabled', True)
        data['idle_timeout'] = settings.get('idle_timeout', 60)
        data['machine_id'] = _get_machine_id()   # 绑定当前设备
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            return False
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


def show_splash(stop_event):
    """原生 tkinter 启动加载页，与 webview 窗口同尺寸同位置，完全覆盖黑屏。"""
    W, H = 440, 720                       # 与 webview 窗口一致
    sw = ctypes.windll.user32.GetSystemMetrics(0)
    sh = ctypes.windll.user32.GetSystemMetrics(1)
    x, y = (sw - W) // 2, (sh - H) // 2

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.config(bg='#faf8f5')
    root.geometry('%dx%d+%d+%d' % (W, H, x, y))

    # 狮子图片
    photo = None
    try:
        img = Image.open(os.path.join(DIR, 'manager_ui', 'assets', 'lion-pet.png'))
        img = img.resize((100, 100), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    except Exception:
        pass

    frame = tk.Frame(root, bg='#faf8f5')
    frame.pack(expand=True, fill='both')

    if photo:
        tk.Label(frame, image=photo, bg='#faf8f5').pack(pady=(120, 12))
    tk.Label(frame, text='桌面宠物', font=('Microsoft YaHei UI', 18, 'bold'),
             fg='#2d2420', bg='#faf8f5').pack(pady=(0, 32))

    # 旋转 spinner
    canvas = tk.Canvas(frame, width=36, height=36, bg='#faf8f5',
                       highlightthickness=0)
    canvas.pack(pady=(0, 8))

    status_var = tk.StringVar(value='狮子正在赶来陪你')
    tk.Label(frame, textvariable=status_var,
             font=('Microsoft YaHei UI', 10),
             fg='#8c7b6e', bg='#faf8f5').pack()

    # spinner 动画
    ang = [0]
    def spin():
        canvas.delete('all')
        canvas.create_oval(4, 4, 32, 32, outline='#f5f0ea', width=3)
        canvas.create_arc(4, 4, 32, 32, start=ang[0], extent=90,
                          style='arc', outline='#e8843c', width=3)
        ang[0] = (ang[0] + 12) % 360
        if not stop_event.is_set():
            root.after(30, spin)
    root.after(30, spin)

    # 状态文字动画
    dots = [0]
    def animate_dots():
        dots[0] = (dots[0] + 1) % 4
        status_var.set('狮子正在赶来陪你' + '.' * dots[0])
        if not stop_event.is_set():
            root.after(500, animate_dots)
    root.after(500, animate_dots)

    # 检查停止信号
    def check_stop():
        if stop_event.is_set():
            root.quit()
        else:
            root.after(100, check_stop)
    root.after(100, check_stop)

    # 兜底：5 秒后强制关闭
    root.after(5000, root.quit)

    root.mainloop()
    # mainloop 退出后在同线程销毁，避免跨线程 GC 报错
    try:
        root.destroy()
    except Exception:
        pass


def main():
    # DPI 感知：确保 tkinter splash 和 webview 窗口使用相同坐标系统
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # 管理软件单实例锁：重复启动直接退出
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(('127.0.0.1', MGR_PORT))
        lock.listen(1)
    except OSError:
        sys.exit(0)

    if not os.path.exists(HTML):
        raise FileNotFoundError('找不到管理界面: ' + HTML)

    # 启动 splash（独立线程，与 webview 同尺寸同位置，完全覆盖）
    stop_splash = threading.Event()
    threading.Thread(target=show_splash, args=(stop_splash,),
                     daemon=True).start()

    api = ManagerApi()
    api._stop_splash = stop_splash
    window = webview.create_window(
        '桌宠管理', HTML, js_api=api,
        width=440, height=720, resizable=False, min_size=(420, 600),
        background_color='#faf8f5', hidden=True)
    api._window = window

    # 兜底：若 page_loaded() 3 秒内未触发，强制显示窗口并关闭 splash
    def on_ready():
        time.sleep(3)
        if not api._shown:
            api._shown = True
            window.show()
            time.sleep(0.2)
            stop_splash.set()
    webview.start(func=on_ready)


if __name__ == '__main__':
    main()
