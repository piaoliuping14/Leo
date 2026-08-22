#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  桌宠管理软件 (Python 版)
#  - 管理主页：启动宠物 / 显示宠物运行状态
#  - 快捷指令配置：增删改查，保存到 config.json（桌宠读取）
#  - 关闭窗口（×）同时退出桌宠
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
import shutil
import subprocess
import threading
import tempfile
import zipfile
import urllib.request
import tkinter as tk
from PIL import Image, ImageTk

import webview

# ---------- 路径 ----------
if getattr(sys, 'frozen', False):
    # 被启动器调用：用户文件放 exe 目录，资源放核心代码目录（app/）
    EXE_DIR = os.path.dirname(sys.executable)
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = APP_DIR
else:
    # 独立运行（开发模式）
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = APP_DIR
    EXE_DIR = APP_DIR
# 构建开关：Store 版（MSIX）打包时置 1。
# Store 版安装目录只读，用户可写数据改到 %LOCALAPPDATA%/Leo桌宠；
# GitHub/直接下载版（默认）仍写 exe 同目录，保持便携与老用户配置不丢。
STORE_BUILD = os.environ.get('STORE_BUILD', '0') == '1'
if STORE_BUILD:
    _DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Leo桌宠')
    os.makedirs(_DATA_DIR, exist_ok=True)
else:
    _DATA_DIR = None  # 用 EXE_DIR/APP_DIR 原逻辑（便携）
CONFIG_PATH = os.path.join(_DATA_DIR or APP_DIR, 'config.json')
LOG_DIR = os.path.join(_DATA_DIR or EXE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
CLEAN_EXIT = os.path.join(LOG_DIR, 'lion_clean_exit.txt')
WATCHDOG = os.path.join(APP_DIR, 'lion_watchdog.py')   # 开发模式用

# 快捷指令默认配置（与 lion_desktop.py 保持一致）
DEFAULT_COMMANDS = [
    {'name': '启动B站', 'type': 'url', 'target': 'https://www.bilibili.com/', 'icon': 'play'},
]


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
    - config.json 不存在：首次运行，创建默认配置（含默认指令 + 机器 ID 绑定）
    - machine_id 缺失：首次运行，写入当前机器 ID
    - machine_id 不匹配：换设备/被分享，重置 commands、idle_timeout=60、nickname=小Leo，更新机器 ID
    - machine_id 匹配：正常使用，不做处理"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        # config.json 不存在 → 首次运行，创建默认配置
        try:
            data = {
                'commands': list(DEFAULT_COMMANDS),
                'idle_bubble_enabled': True,
                'idle_timeout': 60,
                'nickname': '小Leo',
                'machine_id': _get_machine_id()
            }
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
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
        # 设备不匹配（分享/换设备）-> 重置 commands、idle_timeout、nickname
        try:
            data['commands'] = list(DEFAULT_COMMANDS)
            data['idle_timeout'] = 60
            data['nickname'] = '小Leo'
            data['machine_id'] = cur_mid
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
HTML = os.path.join(RES_DIR, 'manager_ui', 'app.html')
ICON_PATH = os.path.join(RES_DIR, 'app-icon.ico')
PYW = sys.executable                 # bat 用 pythonw 启动，故为 pythonw.exe
PET_PORT = 52718                     # 桌宠单实例锁端口（lion_desktop.py）
MGR_PORT = 52719                     # 管理软件单实例锁端口
CMD_PORT = 52720                     # 桌宠命令端口（通知自行退出，避免 PowerShell 杀进程慢）

# ---------- 版本更新 ----------
GITHUB_REPO = 'piaoliuping14/Leo'
GITHUB_API_LATEST = 'https://api.github.com/repos/%s/releases/latest' % GITHUB_REPO
VERSION_FILE = os.path.join(APP_DIR, 'version.json')


def _local_version():
    """读取本地版本号。打包产物读 version.json；开发模式读 build.py 的 VERSION。"""
    try:
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            v = str(json.load(f).get('version', ''))
        if v:
            return v
    except Exception:
        pass
    if not getattr(sys, 'frozen', False):
        try:
            import build
            v = str(getattr(build, 'VERSION', ''))
            if v:
                return v
        except Exception:
            pass
    return '0.0'


def _parse_version(s):
    """把 'v1.2' / '1.2.0' 解析成 (major, minor, patch) 数字元组；失败返回 (0,0,0)。"""
    try:
        nums = []
        for part in ''.join(
                c if c.isdigit() or c == '.' else ' ' for c in str(s)).split():
            nums.extend(int(n) for n in part.split('.') if n)
        nums = nums[:3]
        nums += [0] * (3 - len(nums))
        return tuple(nums)
    except Exception:
        return (0, 0, 0)


def _fetch_latest_release():
    """请求 GitHub Releases 最新版。返回 dict 或 None（网络异常）。"""
    try:
        req = urllib.request.Request(GITHUB_API_LATEST, headers={'User-Agent': 'Leo'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        assets = data.get('assets') or []
        return {
            'tag_name': str(data.get('tag_name', '')),
            'body': str(data.get('body') or ''),
            'zip_url': assets[0]['browser_download_url'] if assets else '',
        }
    except Exception:
        return None


def _unblock_downloaded_files():
    """解除打包目录下文件的 MOTW（Mark of the Web）标记。
    从网上下载 zip 解压后，Windows 会阻止加载这些 DLL，
    导致 pythonnet 报 'Failed to resolve Python.Runtime.Loader.Initialize'。"""
    try:
        base = EXE_DIR if getattr(sys, 'frozen', False) else APP_DIR
        internal = os.path.join(base, '_internal')
        if not os.path.isdir(internal):
            return
        for root, dirs, files in os.walk(internal):
            for name in files:
                # 删除 Zone.Identifier 备用数据流（即 MOTW 标记）
                ctypes.windll.kernel32.DeleteFileW(
                    os.path.join(root, name) + ':Zone.Identifier')
    except Exception:
        pass


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
            if getattr(sys, 'frozen', False):
                # 被启动器调用：用启动器 exe + --run 参数启动子进程
                subprocess.Popen([sys.executable, '--run', 'lion_watchdog'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:
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
        # 优先通过命令端口通知桌宠自行退出（毫秒级，与右键退出同路径）
        # 桌宠退出后 watchdog 检测到 clean_exit 会自行退出，无需强杀
        if self._send_quit_to_pet():
            return True
        # 命令端口失败（旧版桌宠）→ 回退到 PowerShell 多轮强杀
        for _ in range(3):
            self._kill_lion_force()
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
                cmds = json.load(f).get('commands')
                if cmds is not None:
                    return cmds
        except Exception:
            pass
        return list(DEFAULT_COMMANDS)

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
                'idle_timeout': data.get('idle_timeout', 60),
                'nickname': data.get('nickname', '小Leo')
            }
        except Exception:
            return {'idle_bubble_enabled': True, 'idle_timeout': 60, 'nickname': '小Leo'}

    def save_settings(self, settings):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['idle_bubble_enabled'] = settings.get('idle_bubble_enabled', True)
        data['idle_timeout'] = settings.get('idle_timeout', 60)
        data['nickname'] = settings.get('nickname', '小Leo')
        data['machine_id'] = _get_machine_id()   # 绑定当前设备
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            return False
        return True

    # ---------- 版本更新 ----------
    def check_update(self):
        """对比远程 Releases 与本地版本。网络失败返回 ok:False（前端静默处理）。"""
        if STORE_BUILD:
            # Store 版：由微软商店负责更新，不查 GitHub
            v = _local_version()
            return {'ok': True, 'has_update': False, 'store': True,
                    'current': v, 'latest': v, 'notes': '', 'zip_url': ''}
        release = _fetch_latest_release()
        if not release or not release['tag_name']:
            return {'ok': False, 'has_update': False, 'error': '网络不可用'}
        current = _local_version()
        has_update = _parse_version(release['tag_name']) > _parse_version(current)
        return {
            'ok': True,
            'has_update': has_update,
            'current': current,
            'latest': release['tag_name'],
            'notes': release['body'][:2000],
            'zip_url': release['zip_url'],
        }

    def apply_update(self):
        """后台线程下载最新 zip 并覆盖 app/ 目录。完成后通过 JS 回调通知前端。"""
        if STORE_BUILD:
            return False  # Store 版禁止自更新（安装目录只读 + 商店政策）
        try:
            threading.Thread(target=self._do_apply_update, daemon=True).start()
        except Exception:
            return False
        return True

    def _do_apply_update(self):
        """在后台线程执行：下载 → 解压覆盖 → 回调前端。"""
        result = {'ok': False, 'msg': '未知错误'}
        try:
            release = _fetch_latest_release()
            if not release or not release['zip_url']:
                result = {'ok': False, 'msg': '无法获取下载地址'}
            else:
                zip_path = os.path.join(tempfile.gettempdir(), 'leo_update.zip')
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
                req = urllib.request.Request(release['zip_url'],
                                             headers={'User-Agent': 'Leo'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with open(zip_path, 'wb') as f:
                        shutil.copyfileobj(resp, f)
                updated = 0
                with zipfile.ZipFile(zip_path) as zf:
                    for name in zf.namelist():
                        # zip 内条目形如 Leo桌宠/app/...，取 app/ 之后的部分
                        marker = '/app/'
                        idx = name.find(marker)
                        if idx < 0 or name.endswith('/'):
                            continue
                        rel = name[idx + len(marker):]
                        dest = os.path.join(APP_DIR, rel)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(name) as src, open(dest, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                        updated += 1
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
                result = {'ok': True, 'msg': '更新完成，共更新 %d 个文件' % updated}
        except Exception as e:
            result = {'ok': False, 'msg': '更新失败：%s' % e}
        # 回调前端（pywebview 需在主线程执行）
        try:
            if self._window:
                self._window.evaluate_js(
                    'window.onUpdateApplied(%s)' % json.dumps(result))
        except Exception:
            pass

    # ---------- 进程清理 ----------
    def _send_quit_to_pet(self):
        """通过命令端口通知桌宠自行退出（瞬间完成，与右键退出同路径）。
        成功返回 True，失败返回 False。"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(('127.0.0.1', CMD_PORT))
            s.sendall(b'quit\n')
            s.close()
            return True
        except Exception:
            return False

    def _kill_lion_force(self):
        """PowerShell 强杀桌宠和守护进程（命令端口失败时的兜底）。"""
        try:
            subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "Get-CimInstance Win32_Process -Filter "
                 "\"Name='pythonw.exe' OR Name='python.exe' "
                 "OR Name='Leo桌宠.exe'\" | "
                 "Where-Object { $_.CommandLine -like '*lion_desktop*' "
                 "-or $_.CommandLine -like '*lion_watchdog*' } | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                 "-ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass

    def _kill_lion(self):
        # 写 clean_exit：让 watchdog 检测到桌宠退出后不再重启并自行退出
        try:
            with open(CLEAN_EXIT, 'w') as f:
                f.write('ok')
        except Exception:
            pass
        # 优先通过命令端口通知桌宠自行退出（毫秒级，与右键退出相同路径）
        # 桌宠退出后 watchdog 检测到 clean_exit 会自行退出，无需强杀
        if self._send_quit_to_pet():
            return
        # 命令端口失败（旧版桌宠或未启动）→ 回退到 PowerShell 强杀
        self._kill_lion_force()


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
        img = Image.open(os.path.join(RES_DIR, 'manager_ui', 'assets', 'lion-pet.png'))
        img = img.resize((100, 100), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    except Exception:
        pass

    frame = tk.Frame(root, bg='#faf8f5')
    frame.pack(expand=True, fill='both')

    if photo:
        tk.Label(frame, image=photo, bg='#faf8f5').pack(pady=(120, 12))
    tk.Label(frame, text='Leo桌宠', font=('Microsoft YaHei UI', 18, 'bold'),
             fg='#2d2420', bg='#faf8f5').pack(pady=(0, 32))

    # 旋转 spinner
    canvas = tk.Canvas(frame, width=36, height=36, bg='#faf8f5',
                       highlightthickness=0)
    canvas.pack(pady=(0, 8))

    status_var = tk.StringVar(value='Leo正在赶来陪你')
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
        status_var.set('Leo正在赶来陪你' + '.' * dots[0])
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
    _unblock_downloaded_files()
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
        'Leo桌宠', HTML, js_api=api,
        width=440, height=720, resizable=False, min_size=(420, 600),
        background_color='#faf8f5', hidden=True)
    api._window = window

    # 关闭窗口（×）时：只写退出标记（即时），不阻塞窗口关闭
    def on_closing():
        try:
            with open(CLEAN_EXIT, 'w') as f:
                f.write('ok')
        except Exception:
            pass
    window.events.closing += on_closing

    # 兜底：若 page_loaded() 3 秒内未触发，强制显示窗口并关闭 splash
    def on_ready():
        time.sleep(3)
        if not api._shown:
            api._shown = True
            window.show()
            time.sleep(0.2)
            stop_splash.set()
    # 使用 EdgeChromium（WebView2）后端；依赖 pythonnet + .NET Framework 4.7.2+
    try:
        webview.start(gui='edgechrom', func=on_ready)
    except Exception as ex:
        err = str(ex)
        if 'Python.Runtime' in err or 'Loader' in err or 'clr' in err.lower():
            hint = ('程序依赖的 .NET 运行时加载失败。\n\n'
                    '最常见原因：从网上下载的 zip 解压后，文件被 Windows 安全策略阻止。\n'
                    '解决方法：右键软件所在文件夹 → 属性 → 勾选"解除阻止"，\n'
                    '或用 PowerShell（管理员）执行：\n'
                    'Get-ChildItem -Path "软件路径" -Recurse -File | Unblock-File\n'
                    '若仍失败，请安装 .NET Framework 4.8 运行时。')
        else:
            hint = ('可能未安装 WebView2 Runtime。\n'
                    '下载：`https://developer.microsoft.com/microsoft-edge/webview2/\n`'
                    '（Windows 11 自带，Windows 10 多数已预装）\n\n'
                    '也可能是文件被 Windows 安全策略阻止，请尝试解除阻止。')
        try:
            ctypes.windll.user32.MessageBoxW(
                0, 'Leo桌宠启动失败。\n\n' + hint +
                '\n\n详细错误：' + err, 'Leo桌宠 - 启动失败', 0x10)
        except Exception:
            pass
        return
    # 窗口已关闭，清理桌宠和守护进程（用户无感知，不阻塞 UI）
    try:
        api._kill_lion()
    except Exception:
        pass


if __name__ == '__main__':
    main()
