#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  桌面狮子桌宠 (Python 版)
#  - 透明窗口显示狮子图片（硬遮罩，无紫边/灰边）
#  - 闲时摇摆 / 漂浮 / 呼吸动画
#  - 拖拽时倾斜 + 摇晃，松开回正
#  - 单击弹出对话气泡（圆角 + 尾巴，三按钮 + 关闭）
#  - 右键菜单：打开对话 / 回到右下角 / 退出
#  图片: katong/狮子111-no-bg.png
#
#  用法:
#     python lion_desktop.py
#     pythonw lion_desktop.py             (无控制台)
#     python lion_desktop.py --test       (冒烟测试后自动退出)
#     python lion_desktop.py --scale=0.08
# ============================================================
import os
import sys
import json
import math
import time
import random
import logging
import socket
import threading
import traceback
import subprocess
import webbrowser
import ctypes
import datetime
from ctypes import wintypes
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk, ImageDraw

# 音乐盒模块（SMTC 媒体控制 + pycaw 音量控制 + 主题配置）
from music_theme import MusicTheme
from music_box import get_controller, MediaInfo, _fmt_time

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
IMG_PATH = os.path.join(RES_DIR, 'katong', '狮子111-no-bg.png')
LOG_DIR = os.path.join(EXE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, 'lion.log')
CLEAN_EXIT = os.path.join(LOG_DIR, 'lion_clean_exit.txt')
CONFIG_PATH = os.path.join(APP_DIR, 'config.json')
QUOTES_PATH = os.path.join(RES_DIR, 'design', '文案.txt')
ICON_PATH = os.path.join(RES_DIR, 'app-icon.ico')

# ---------- 闲置气泡默认配置 ----------
IDLE_TIMEOUT = 60.0          # 闲置多少秒后触发
IDLE_BUBBLE_DURATION = 10.0  # 闲置气泡显示时长

# ---------- 快捷指令默认配置（config.json 缺失时回退）----------
DEFAULT_COMMANDS = [
    {'name': '启动B站', 'type': 'url', 'target': 'https://www.bilibili.com/', 'icon': 'play'},
]


def load_commands():
    """从 config.json 读取快捷指令；缺失或异常时回退默认列表。
    注意：空列表 [] 是合法值（用户删除了所有指令），不应回退默认。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cmds = data.get('commands')
        if cmds is not None:
            return cmds
    except Exception:
        pass
    return list(DEFAULT_COMMANDS)


def load_idle_enabled():
    """从 config.json 读取闲置气泡开关；默认开启。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('idle_bubble_enabled', True)
    except Exception:
        return True


def load_idle_timeout():
    """从 config.json 读取闲置气泡间隔秒数；默认60秒。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            v = json.load(f).get('idle_timeout', 60)
        return max(1, int(v))
    except Exception:
        return 60


def load_nickname():
    """从 config.json 读取用户昵称；默认'小Leo'。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('nickname', '小Leo')
    except Exception:
        return '小Leo'


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
        # 首次运行 -> 绑定设备
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


def load_quotes():
    """从文案.txt 读取文案列表；每行一条，去除序号前缀（支持1-3位数）。"""
    import re
    try:
        with open(QUOTES_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        quotes = []
        for line in lines:
            s = line.strip()
            if not s:
                continue
            # 去掉 "1. " / "10. " / "100. " 等序号前缀
            s = re.sub(r'^\d+\.\s*', '', s)
            quotes.append(s)
        return quotes if quotes else ['静静陪伴你...']
    except Exception:
        return ['静静陪伴你...']

# ---------- 日志 ----------
_log = logging.getLogger('lion')
_log.setLevel(logging.INFO)
if not _log.handlers:
    try:
        _fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
        _fh.setFormatter(logging.Formatter('[%(asctime)s] %(message)s',
                                           '%Y-%m-%d %H:%M:%S'))
        _log.addHandler(_fh)
    except Exception:
        pass


def log(msg):
    _log.info(msg)


# ---------- Win32 工作区（排除任务栏）----------
def working_area():
    try:
        rc = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)
        return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception:
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        return (0, 0, sw, sh)


# ---------- 图像工具 ----------
def hard_matte(img):
    """硬遮罩：alpha<128 -> 全透明(RGB 清零)，否则 alpha=255。
    消除缩放/旋转插值产生的半透明边缘，杜绝紫边/灰边。"""
    img = img.convert('RGBA')
    a = img.split()[3].point(lambda p: 255 if p >= 128 else 0)
    black = Image.new('RGBA', img.size, (0, 0, 0, 255))
    out = Image.composite(img, black, a)   # 透明处取黑，不透明处取原图色
    out.putalpha(a)                        # alpha 二值化
    return out


def binarize_alpha(img):
    """仅二值化 alpha（保留 RGB），用于气泡形状硬边缘。
    避免 transparentcolor 与抗锯齿半透明像素混色产生彩边。"""
    img = img.convert('RGBA')
    a = img.split()[3].point(lambda p: 255 if p >= 128 else 0)
    img.putalpha(a)
    return img


def render_frame(base, fw, fh, pad, angle, bob, breath):
    """渲染一帧：以底部为支点旋转 + 呼吸缩放 + bob 平移，返回 fw x fh 的 RGBA 图。
    与 PS 版变换一致：DrawImage(src,pad,pad) 后关于 (fw/2, pad+bh*0.88+bob) 旋转缩放。"""
    bw, bh = base.size
    cx = fw / 2.0
    cy = pad + bh * 0.88 + bob              # 底部支点（站立摆动双脚不动）
    s = 1.0 + breath * 0.015                # 呼吸缩放 ±1.5%
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)
    inv = 1.0 / s
    # 画布(目标) -> base(源) 的仿射映射（顺时针 angle，关于 (cx,cy) 缩放 s）
    a = ca * inv
    b = -sa * inv
    c = cx - pad - (ca * cx - sa * cy) * inv
    d = sa * inv
    e = ca * inv
    f = cy - pad - (sa * cx + ca * cy) * inv
    canvas = base.transform((fw, fh), Image.AFFINE,
                            (a, b, c, d, e, f), resample=Image.BICUBIC)
    return binarize_alpha(canvas)           # 旋转插值边缘 -> 硬边缘


# ---------- 自定义右键菜单 ----------
class ContextMenu:
    """自定义右键菜单：白底圆角 + 悬停高亮，替代系统默认 tk.Menu。"""
    BG = '#ffffff'
    FG = '#5a4a3e'
    HOVER_BG = '#fff4ec'
    HOVER_FG = '#e8843c'
    BORDER = '#e8e0d6'

    def __init__(self, parent):
        self.parent = parent
        self.top = None
        self._items = []

    def add_command(self, label, command):
        self._items.append({'label': label, 'command': command})

    def add_separator(self):
        self._items.append({'separator': True})

    def show(self, x, y):
        if self.top:
            self._close()

        self.top = tk.Toplevel(self.parent)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.config(bg=self.BORDER)

        item_h = 22
        sep_h = 6
        pad_v = 4
        w = 120

        sep_count = sum(1 for i in self._items if i.get('separator'))
        cmd_count = len(self._items) - sep_count
        h = pad_v * 2 + cmd_count * item_h + sep_count * sep_h

        # 屏幕边界检查
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        if x + w > sw - 4:
            x = sw - w - 4
        if y + h > sh - 4:
            y = sh - h - 4

        self.top.geometry('%dx%d+%d+%d' % (w, h, x, y))

        container = tk.Frame(self.top, bg=self.BG, bd=0,
                             highlightthickness=1,
                             highlightbackground=self.BORDER,
                             highlightcolor=self.BORDER)
        container.pack(fill='both', expand=True, padx=1, pady=1)

        y_pos = pad_v
        for item in self._items:
            if item.get('separator'):
                sep = tk.Frame(container, bg=self.BORDER, height=1)
                sep.place(x=14, y=y_pos + sep_h // 2, width=w - 30, height=1)
                y_pos += sep_h
            else:
                row = tk.Frame(container, bg=self.BG, cursor='hand2')
                row.place(x=4, y=y_pos, width=w - 8, height=item_h)

                label = tk.Label(row, text=item['label'],
                                 font=('Microsoft YaHei UI', 9),
                                 fg=self.FG, bg=self.BG,
                                 anchor='w', padx=12, cursor='hand2')
                label.pack(fill='both', expand=True)

                cmd = item['command']
                row.bind('<Enter>', lambda e, r=row, l=label:
                         (r.config(bg=self.HOVER_BG),
                          l.config(bg=self.HOVER_BG, fg=self.HOVER_FG)))
                row.bind('<Leave>', lambda e, r=row, l=label:
                         (r.config(bg=self.BG),
                          l.config(bg=self.BG, fg=self.FG)))

                def on_click(e, c=cmd):
                    self._close()
                    c()

                row.bind('<Button-1>', on_click)
                label.bind('<Button-1>', on_click)
                y_pos += item_h

        self.top.bind('<FocusOut>', lambda e: self._close())
        self.top.focus_set()

    def _close(self):
        if self.top:
            try:
                self.top.destroy()
            except Exception:
                pass
            self.top = None


# ---------- 对话气泡 ----------
class BubbleWindow:
    """可动态切换内容的对话气泡：set_content() 更新文本和按钮后 show() 即可。"""
    TAIL_ALLOW = 14                         # 尾巴预留宽度（整体收入窗口，不被裁切）
    KEY = 'magenta'
    BG       = (255, 250, 245)             # 暖白（米色）
    BORDER   = (232, 216, 196)             # 暖灰边框
    TEXT     = (90, 74, 62)                # 暖棕文字
    BTN_BASE = (255, 235, 215)             # 浅橙底
    BTN_HOVER= (255, 195, 140)             # 橙色悬停
    BTN_BD   = (232, 184, 140)             # 橙边框
    BTN_TX   = (140, 80, 30)               # 棕橙文字
    BTN_TXH  = (200, 80, 20)               # 深橙悬停文字

    def __init__(self, parent, on_close):
        self.on_close = on_close
        self.fade = 0.0
        self.opened = False
        self.bubble_photo = None
        self._cur_tail = None

        # 内容（由 set_content 设置）
        self.text = ''
        self.btn_labels = []
        self.on_button_click = None

        # 字体 & 布局参数
        self.font_lab = tkfont.Font(family='Microsoft YaHei UI', size=10)
        self.font_btn = tkfont.Font(family='Microsoft YaHei UI', size=9)
        self.btn_h = 28               # 基础按钮高度（单行）
        self.gap = 8                  # 按钮间水平间距
        self.row_gap = 6              # 行间距
        self.pad_lr = 14
        self.lab_top = 11
        self.lab_gap = 9
        self.bot_pad = 11
        self.cols = 3                 # 每行按钮数
        self.btn_w = 85               # 固定按钮宽度
        self.wrap_len = self.btn_w - 12   # 按钮文本换行宽度
        self.btn_heights = []         # 各按钮高度
        self.row_heights = []         # 各行高度（取该行最大值）

        # Toplevel
        self.top = tk.Toplevel(parent)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.config(bg=self.KEY)
        try:
            self.top.wm_attributes('-transparentcolor', self.KEY)
        except Exception:
            pass
        self.top.withdraw()

        self.canvas = tk.Canvas(self.top, width=10, height=10,
                                bg=self.KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.img_item = self.canvas.create_image(0, 0, anchor='nw')

        # 控件（由 _create_widgets 创建）
        self.label = None
        self.buttons = []
        self.btn_frames = []
        self.close_btn = None

        # 初始化空内容
        self._calc_layout('', [])
        self._create_widgets()

    def set_content(self, text, btn_labels, on_button_click):
        """更新气泡内容：文本、按钮标签列表、按钮点击回调。"""
        self.text = text
        self.btn_labels = btn_labels or []
        self.on_button_click = on_button_click

        # 销毁旧控件
        if self.label:
            self.label.destroy()
        for f in self.btn_frames:
            f.destroy()
        if self.close_btn:
            self.close_btn.destroy()
        self.buttons = []
        self.btn_frames = []

        # 重新计算并创建
        self._calc_layout(text, self.btn_labels)
        self._create_widgets()
        self._cur_tail = None               # 强制下次 show/position 时重建

    def _calc_layout(self, text, btn_labels):
        """根据文本和按钮列表计算气泡尺寸（三列网格布局）。"""
        lab_w = self.font_lab.measure(text) + 4              # +4px 防止末尾字符被裁切
        lab_h = self.font_lab.metrics('linespace')
        names = btn_labels or []
        n = len(names)

        # 计算每个按钮高度（文本超宽时换行）
        line_h = self.font_btn.metrics('linespace')
        self.btn_heights = []
        for name in names:
            tw = self.font_btn.measure(name)
            if tw <= self.wrap_len:
                self.btn_heights.append(self.btn_h)
            else:
                lines = max(1, math.ceil(tw / self.wrap_len))
                self.btn_heights.append(self.btn_h + (lines - 1) * line_h)

        # 计算每行高度（取该行最大值）
        self.row_heights = []
        for i in range(0, n, self.cols):
            row = self.btn_heights[i:i + self.cols]
            self.row_heights.append(max(row) if row else self.btn_h)

        # 气泡宽度
        cols_in_use = min(self.cols, n) if n > 0 else 0
        btn_row_w = cols_in_use * self.btn_w + max(0, cols_in_use - 1) * self.gap
        if n > 0:
            self.bw = max(lab_w + 2 * self.pad_lr, btn_row_w + 2 * self.pad_lr, 160)
        else:
            self.bw = max(lab_w + 2 * self.pad_lr + 24, 160)  # +24 给关闭按钮留空间

        # 气泡高度
        if n > 0:
            total_btn_h = sum(self.row_heights) + max(0, len(self.row_heights) - 1) * self.row_gap
            self.bh = self.lab_top + lab_h + self.lab_gap + total_btn_h + self.bot_pad
        else:
            self.bh = self.lab_top + lab_h + 20
        self.btn_y = self.lab_top + lab_h + self.lab_gap

    def _create_widgets(self):
        """根据当前内容创建标签、按钮、关闭按钮。"""
        self.label = tk.Label(self.top, text=self.text, font=self.font_lab,
                              fg=self._hex(self.TEXT), bg=self._hex(self.BG),
                              relief='flat', bd=0, highlightthickness=0)

        for i, label in enumerate(self.btn_labels):
            f = tk.Frame(self.top, bg=self._hex(self.BTN_BD), bd=0)
            b = tk.Button(f, text=label, font=self.font_btn,
                          fg=self._hex(self.BTN_TX), bg=self._hex(self.BTN_BASE),
                          activebackground=self._hex(self.BTN_HOVER),
                          activeforeground=self._hex(self.BTN_TXH),
                          relief='flat', bd=0, highlightthickness=0,
                          padx=6, pady=4, cursor='hand2',
                          wraplength=self.wrap_len, justify='center')
            b.pack(fill='both', expand=True, padx=1, pady=1)
            b.bind('<Enter>', lambda e, bb=b, idx=i: self._hover(bb, idx, True))
            b.bind('<Leave>', lambda e, bb=b, idx=i: self._hover(bb, idx, False))
            b.config(command=lambda idx=i: self._click(idx))
            self.buttons.append(b)
            self.btn_frames.append(f)

        self.close_btn = tk.Button(self.top, text='×',
                                   font=('Microsoft YaHei UI', 9, 'bold'),
                                   fg='#b08060', bg=self._hex(self.BG),
                                   activebackground='#fff0e0',
                                   relief='flat', bd=0, highlightthickness=0,
                                   cursor='hand2', command=self._close)

    @staticmethod
    def _hex(rgb):
        return '#%02x%02x%02x' % rgb

    def _hover(self, btn, idx, enter):
        if enter:
            btn.config(bg=self._hex(self.BTN_HOVER), fg=self._hex(self.BTN_TXH))
        else:
            btn.config(bg=self._hex(self.BTN_BASE), fg=self._hex(self.BTN_TX))

    def _make_bubble_img(self, tail_right):
        """生成气泡图：圆角矩形 + 侧边尾巴，抗锯齿绘制后二值化 alpha 成硬边缘。"""
        bw, bh = self.bw, self.bh
        tail = self.TAIL_ALLOW
        win_w = bw + tail + 1
        img = Image.new('RGBA', (win_w, bh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        bx = 0 if tail_right else tail
        r = 10
        d.rounded_rectangle([bx, 0, bx + bw - 1, bh - 1], radius=r,
                            fill=self.BG, outline=self.BORDER, width=1)
        ty1 = bh - 34; ty2 = bh - 20; tmy = bh - 27   # 尾巴在侧边中下部
        if tail_right:
            apex = bx + bw + tail - 1                   # 尾尖抵窗口右内边
            d.polygon([(bx + bw - 1, ty1), (apex, tmy), (bx + bw - 1, ty2)],
                      fill=self.BG)
            d.line([(bx + bw - 1, ty1), (apex, tmy), (bx + bw - 1, ty2)],
                   fill=self.BORDER, width=1)
        else:
            apex = bx - tail + 1                         # 尾尖抵窗口左内边
            d.polygon([(bx, ty1), (apex, tmy), (bx, ty2)], fill=self.BG)
            d.line([(bx, ty1), (apex, tmy), (bx, ty2)],
                   fill=self.BORDER, width=1)
        return binarize_alpha(img), win_w

    def _apply(self, tail_right):
        img, win_w = self._make_bubble_img(tail_right)
        self.bubble_photo = ImageTk.PhotoImage(img)
        self.canvas.config(width=win_w, height=self.bh)
        self.canvas.itemconfig(self.img_item, image=self.bubble_photo)
        body_x = 0 if tail_right else self.TAIL_ALLOW
        self.label.place(x=body_x + self.pad_lr, y=self.lab_top)

        # 三列网格布局
        n = len(self.btn_frames)
        cols_in_use = min(self.cols, n)
        btn_row_w = cols_in_use * self.btn_w + max(0, cols_in_use - 1) * self.gap
        x0 = body_x + (self.bw - btn_row_w) // 2

        y = self.btn_y
        for row_idx in range(len(self.row_heights)):
            row_h = self.row_heights[row_idx]
            for col_idx in range(self.cols):
                bi = row_idx * self.cols + col_idx
                if bi >= n:
                    break
                x = x0 + col_idx * (self.btn_w + self.gap)
                self.btn_frames[bi].place(x=x, y=y, width=self.btn_w, height=row_h)
            y += row_h + self.row_gap

        self.close_btn.place(x=body_x + self.bw - 23, y=4, width=18, height=18)

    def _place_at(self, pet_x, pet_y, pet_fw, pet_fh):
        wa = working_area()
        win_w = self.bw + self.TAIL_ALLOW + 1
        tail_right = True
        bx = int(pet_x) - win_w - 10
        if bx < 8:                              # 左边放不下 -> 尾巴转向右
            bx = int(pet_x) + pet_fw + 10
            tail_right = False
        by = int(max(8, min(wa[3] - self.bh - 8,
                            pet_y + pet_fh * 0.55 - self.bh / 2.0)))
        if tail_right != self._cur_tail:        # 仅方向变化时重建气泡图
            self._apply(tail_right)
            self._cur_tail = tail_right
        self.top.geometry('%dx%d+%d+%d' % (win_w, self.bh, bx, by))

    def show(self, pet_x, pet_y, pet_fw, pet_fh):
        self.opened = True
        self.fade = 0.0
        self._cur_tail = None                   # 强制重建
        self._place_at(pet_x, pet_y, pet_fw, pet_fh)
        self.top.attributes('-alpha', 0.0)
        self.top.deiconify()

    def position(self, pet_x, pet_y, pet_fw, pet_fh):
        if not self.opened:
            return
        self._place_at(pet_x, pet_y, pet_fw, pet_fh)

    def tick(self, dt):
        if self.opened:
            self.fade += dt * 6.0
            try:
                self.top.attributes('-alpha', min(1.0, self.fade))
            except Exception:
                pass

    def close(self):
        self.opened = False
        self.fade = 0.0
        try:
            self.top.attributes('-alpha', 0.0)
            self.top.withdraw()
        except Exception:
            pass
        try:
            self.on_close()
        except Exception:
            pass

    def _click(self, idx):
        try:
            if self.on_button_click:
                self.on_button_click(idx)
        except Exception as ex:
            log('btn click error: %s' % ex)

    def _close(self):
        self.close()


# ---------- 闲置气泡 ----------
class IdleBubble:
    """闲置气泡：比正常气泡小、显示在桌宠上方、半透明、无关闭按钮。"""
    KEY = 'magenta'
    BG       = (252, 252, 254)
    BORDER   = (214, 221, 234)
    TEXT     = (80, 90, 110)
    BW       = 150                    # 固定宽度，文字自动换行
    PAD_LR   = 10
    PAD_TB   = 8

    def __init__(self, parent):
        self.opened = False
        self.fade = 0.0
        self.bubble_photo = None
        self._cur_tail = None
        self._cur_text = ''
        self._cur_wrapped = []
        self._cur_tail_bottom = True
        self._cur_bw = self.BW            # 当前气泡宽度（可能因文案自适应加宽）

        self.font = tkfont.Font(family='Microsoft YaHei UI', size=8)

        self.top = tk.Toplevel(parent)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.config(bg=self.KEY)
        try:
            self.top.wm_attributes('-transparentcolor', self.KEY)
        except Exception:
            pass
        self.top.withdraw()

        self.canvas = tk.Canvas(self.top, width=10, height=10,
                                bg=self.KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.img_item = self.canvas.create_image(0, 0, anchor='nw')
        self.label = None

    @staticmethod
    def _hex(rgb):
        return '#%02x%02x%02x' % rgb

    def _calc_height(self, text):
        """根据文字宽度计算换行后的高度。
        若最后一行只有句号或1-2字+句号，自动加宽气泡让整段文案显示为一行。"""
        import textwrap
        import re
        line_h = self.font.metrics('linespace')
        wrapped = textwrap.wrap(text, width=12)   # 约每行 12 个中文字符

        # 检测：换行后多于1行，且最后一行只有"。"或1-2字+"。" -> 尝试合并为一行
        if len(wrapped) >= 2 and re.match(r'^.{0,2}。$', wrapped[-1]):
            text_w = self.font.measure(text)
            needed_bw = text_w + 2 * self.PAD_LR
            # 限制最大宽度，不超过工作区宽度的80%
            wa = working_area()
            max_bw = min(320, int((wa[2] - wa[0]) * 0.8))
            if needed_bw <= max_bw:
                self._cur_bw = needed_bw
                return line_h + 2 * self.PAD_TB, [text]

        self._cur_bw = self.BW
        return len(wrapped) * line_h + 2 * self.PAD_TB, wrapped

    def _make_bubble_img(self, bh, tail_bottom=True):
        """生成圆角矩形气泡图。
        tail_bottom=True  -> 底部小三角指向下方（气泡在桌宠上方时用）
        tail_bottom=False -> 顶部小三角指向上方（气泡在桌宠下方时用）"""
        bw = self._cur_bw
        tail = 10
        win_w = bw + 2
        img = Image.new('RGBA', (win_w, bh + tail), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = 8
        cx = bw // 2
        if tail_bottom:
            # 圆角矩形在上方，底部三角指向下方
            d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=r,
                                fill=self.BG, outline=self.BORDER, width=1)
            d.polygon([(cx - 5, bh - 1), (cx, bh + tail - 1), (cx + 5, bh - 1)],
                      fill=self.BG)
            d.line([(cx - 5, bh - 1), (cx, bh + tail - 1)], fill=self.BORDER, width=1)
            d.line([(cx + 5, bh - 1), (cx, bh + tail - 1)], fill=self.BORDER, width=1)
        else:
            # 顶部三角指向上方，圆角矩形在下方
            d.polygon([(cx - 5, tail), (cx, 0), (cx + 5, tail)],
                      fill=self.BG)
            d.rounded_rectangle([0, tail, bw - 1, bh + tail - 1], radius=r,
                                fill=self.BG, outline=self.BORDER, width=1)
            d.line([(cx - 5, tail), (cx, 0)], fill=self.BORDER, width=1)
            d.line([(cx + 5, tail), (cx, 0)], fill=self.BORDER, width=1)
        return binarize_alpha(img), win_w, bh + tail

    def _apply(self, text, wrapped, tail_bottom=True):
        bh, _ = self._calc_height(text)
        img, win_w, full_h = self._make_bubble_img(bh, tail_bottom)
        self.bubble_photo = ImageTk.PhotoImage(img)
        self.canvas.config(width=win_w, height=full_h)
        self.canvas.itemconfig(self.img_item, image=self.bubble_photo)

        if self.label:
            self.label.destroy()
        self.label = tk.Label(self.top, text='\n'.join(wrapped), font=self.font,
                              fg=self._hex(self.TEXT), bg=self._hex(self.BG),
                              relief='flat', bd=0, highlightthickness=0,
                              justify='center')
        # 尾巴在顶部时，圆角矩形向下偏移 tail 像素，label 跟随偏移
        label_y = self.PAD_TB if tail_bottom else 10 + self.PAD_TB
        self.label.place(x=1, y=label_y, width=self._cur_bw - 2,
                         height=bh - 2 * self.PAD_TB)

    def _compute_pos(self, pet_x, pet_y, pet_fw, pet_fh, full_h):
        """计算气泡位置和尾巴方向。
        上方放得下 -> 气泡在上方、尾巴朝下；放不下 -> 气泡在下方、尾巴朝上。"""
        wa = working_area()
        win_w = self._cur_bw + 2
        by_top = int(pet_y - full_h - 4)
        if by_top >= wa[1] + 4:
            tail_bottom = True
            by = by_top
        else:
            tail_bottom = False
            by = int(pet_y + pet_fh + 4)
        bx = int(pet_x + pet_fw / 2 - win_w / 2)
        bx = max(wa[0] + 4, min(wa[2] - win_w - 4, bx))
        by = max(wa[1] + 4, min(wa[3] - full_h - 4, by))
        return bx, by, tail_bottom

    def show(self, text, pet_x, pet_y, pet_fw, pet_fh):
        bh, wrapped = self._calc_height(text)
        self._cur_text = text
        self._cur_wrapped = wrapped

        win_w = self._cur_bw + 2
        full_h = bh + 10
        bx, by, tail_bottom = self._compute_pos(pet_x, pet_y, pet_fw, pet_fh, full_h)
        self._cur_tail_bottom = tail_bottom

        self._apply(text, wrapped, tail_bottom)
        self.top.geometry('%dx%d+%d+%d' % (win_w, full_h, bx, by))

        self.opened = True
        self.fade = 0.0
        self.top.attributes('-alpha', 0.0)
        self.top.deiconify()

    def position(self, pet_x, pet_y, pet_fw, pet_fh):
        """桌宠移动时同步更新闲置气泡位置（方向变化时重建气泡图）。"""
        if not self.opened:
            return
        bh, _ = self._calc_height(self._cur_text)
        win_w = self._cur_bw + 2
        full_h = bh + 10
        bx, by, tail_bottom = self._compute_pos(pet_x, pet_y, pet_fw, pet_fh, full_h)
        # 尾巴方向变化 -> 重建气泡图和 label 位置
        if tail_bottom != self._cur_tail_bottom:
            self._cur_tail_bottom = tail_bottom
            self._apply(self._cur_text, self._cur_wrapped, tail_bottom)
        self.top.geometry('%dx%d+%d+%d' % (win_w, full_h, bx, by))

    def tick(self, dt):
        if self.opened:
            self.fade += dt * 5.0
            try:
                self.top.attributes('-alpha', min(0.88, self.fade))
            except Exception:
                pass

    def close(self):
        self.opened = False
        self.fade = 0.0
        try:
            self.top.attributes('-alpha', 0.0)
            self.top.withdraw()
        except Exception:
            pass


# ---------- 音乐盒气泡 ----------
class _CanvasButton:
    """Canvas 自绘按钮：完全无边框，外观由主题配置控制。

    【主题系统 - 重点标记】
    按钮颜色、尺寸均从 MusicTheme 读取，支持自定义。
    用 Canvas 绘制圆形背景 + 文字，彻底消除 tk.Button 的系统主题边框。
    提供 config(text=, state=, command=) 和 place() 接口，兼容原 tk.Button 用法。
    """

    def __init__(self, parent, text, size, font, theme, is_play=False):
        self._t = theme
        self._text = text
        self._size = size
        self._font = font
        self._is_play = is_play
        self._enabled = True
        self._command = None
        self._hovered = False

        self.canvas = tk.Canvas(parent, width=size, height=size,
                                bg=theme._hex(theme.BG),
                                highlightthickness=0, bd=0)
        self.canvas.bind('<Enter>', self._on_enter)
        self.canvas.bind('<Leave>', self._on_leave)
        self.canvas.bind('<Button-1>', self._on_click)
        self._draw()

    def _cur_bg(self):
        """当前背景色（考虑悬停/禁用/播放按钮状态）。"""
        t = self._t
        if not self._enabled:
            return t.BTN_DISABLED
        if self._is_play:
            return t.BTN_PLAY_HOVER if self._hovered else t.BTN_PLAY_BG
        return t.BTN_HOVER if self._hovered else t.BTN_BG

    def _draw(self):
        """重绘按钮。"""
        c = self.canvas
        t = self._t
        c.delete('btn')
        bg = self._cur_bg()
        # 圆形背景
        c.create_oval(0, 0, self._size, self._size,
                      fill=t._hex(bg), outline='', tags='btn')
        # 文字/图标
        tc = t._hex(t.BTN_TEXT) if self._enabled else t._hex(t.HINT_COLOR)
        c.create_text(self._size // 2, self._size // 2,
                      text=self._text, font=self._font,
                      fill=tc, tags='btn')

    def _on_enter(self, e):
        self._hovered = True
        self._draw()

    def _on_leave(self, e):
        self._hovered = False
        self._draw()

    def _on_click(self, e):
        if self._enabled and self._command:
            self._command()

    def config(self, **kw):
        """兼容 tk.Button 的 config 接口。"""
        if 'text' in kw:
            self._text = kw['text']
        if 'state' in kw:
            self._enabled = (kw['state'] == 'normal')
        if 'command' in kw:
            self._command = kw['command']
        self._draw()

    def place(self, **kw):
        self.canvas.place(**kw)


class MusicBubbleWindow:
    """音乐盒气泡：基于 Windows SMTC 显示媒体信息和控制界面。

    【主题系统 - 重点标记】
    所有颜色、尺寸、字体均从 MusicTheme 读取。
    后续开发「换主题」功能时，只需替换 music_theme.py 中的配置值，
    或加载不同的主题文件即可，无需改动本类逻辑。

    支持自定义的元素：
    - 进度条：轨道/填充/滑块 颜色和尺寸（PROGRESS_*）
    - 控制按钮：上一曲/播放暂停/下一曲 颜色和尺寸（BTN_*）
    - 音量条：轨道/填充/滑块 颜色和尺寸（VOL_*）
    - 文字：标题/艺术家/时间/提示 字体和颜色（*_FONT / *_COLOR）
    """

    TAIL_ALLOW = 14
    KEY = 'magenta'

    def __init__(self, parent, on_close):
        self.on_close = on_close
        self.fade = 0.0
        self.opened = False
        self.bubble_photo = None
        self._cur_tail = None

        # 控制器（全局单例，后台线程轮询 SMTC）
        self._controller = get_controller()
        self._controller.add_callback(self._on_media_update)

        # 状态（_media_info 由后台回调更新，_pending_update 标记需刷新 UI）
        self._media_info = MediaInfo()
        self._pending_update = False
        self._volume = self._controller.get_volume()
        self._muted = self._controller.is_muted()
        self._dragging_progress = False
        self._dragging_volume = False
        # 进度防抖与平滑锁定策略：
        # - tick 累加驱动显示值持续前进（不受 SMTC 采样时序偏差影响）
        # - SMTC 回调仅在以下情况校准锚点：
        #   1. 切歌（标题变化）
        #   2. 播放状态切换
        #   3. SMTC 值稳定正向偏移超过阈值（seek 前进）
        #   4. 偏差过大时强制校准（防止长期累积误差）
        # - 回跳噪声（43→44→43）完全忽略，显示值不跳回
        self._last_title = ''
        self._anchor_pos = 0.0          # tick 累加基准位置
        self._anchor_time = 0.0         # 基准时间戳（monotonic）
        self._last_playing = False      # 上次播放状态（检测状态切换）

        # 跑马灯状态：超长标题向左循环滚动，短标题居中静止
        self._marquee_text = ''         # 当前标题文本（用于检测变化）
        self._marquee_active = False    # 是否正在滚动
        self._marquee_text_w = 0        # 标题文字像素宽度
        self._marquee_offset = 0.0      # 文字 x 偏移（负=向左）
        self._marquee_phase = 0         # 0=开头停留 1=向左滚动 2=末尾停留
        self._marquee_timer = 0.0       # 当前阶段计时器

        # 字体（从主题配置创建）
        self.font_title = self._make_font(MusicTheme.TITLE_FONT)
        self.font_artist = self._make_font(MusicTheme.ARTIST_FONT)
        self.font_time = self._make_font(MusicTheme.TIME_FONT)
        self.font_btn = self._make_font(MusicTheme.BTN_FONT)
        self.font_hint = self._make_font(MusicTheme.HINT_FONT)
        self.font_vol = self._make_font(MusicTheme.VOL_FONT)

        # Toplevel 窗口
        self.top = tk.Toplevel(parent)
        self.top.overrideredirect(True)
        self.top.attributes('-topmost', True)
        self.top.config(bg=self.KEY)
        try:
            self.top.wm_attributes('-transparentcolor', self.KEY)
        except Exception:
            pass
        self.top.withdraw()

        self.canvas = tk.Canvas(self.top, width=10, height=10,
                                bg=self.KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.img_item = self.canvas.create_image(0, 0, anchor='nw')

        # 控件引用
        self.title_canvas = None
        self.title_text_id = None
        self.artist_label = None
        self.time_cur_label = None
        self.time_dur_label = None
        self.prev_btn = None
        self.play_btn = None
        self.next_btn = None
        self.close_btn = None
        self.vol_label = None
        self.progress_canvas = None
        self.volume_canvas = None

        # 计算布局并创建控件
        self._calc_layout()
        self._create_widgets()
        self._apply_bubble(True)

    @staticmethod
    def _make_font(spec):
        """从主题字体配置创建 tkfont.Font。"""
        family = spec[0]
        size = spec[1]
        weight = spec[2] if len(spec) > 2 else 'normal'
        return tkfont.Font(family=family, size=size, weight=weight)

    def _calc_layout(self):
        """计算气泡尺寸和各元素 Y 坐标。"""
        t = MusicTheme
        self.bw = t.BUBBLE_W

        self.title_h = self.font_title.metrics('linespace')
        title_h = self.title_h
        artist_h = self.font_artist.metrics('linespace')
        time_h = self.font_time.metrics('linespace')
        vol_h = self.font_vol.metrics('linespace')

        y = t.PAD_TOP
        self.title_y = y
        y += title_h + t.GAP_TITLE_ARTIST
        self.artist_y = y
        y += artist_h + t.GAP_ARTIST_PROG
        self.progress_y = y
        # 进度条 Canvas 高度 = 进度条高度 + 2*滑块半径（给滑块留空间）
        self.progress_canvas_h = t.PROGRESS_HEIGHT + 2 * t.PROGRESS_THUMB_R
        y += self.progress_canvas_h + t.GAP_PROG_TIME
        self.time_y = y
        y += time_h + t.GAP_TIME_BTNS
        self.btn_y = y
        y += t.BTN_PLAY_SIZE + t.GAP_BTNS_VOL
        self.volume_y = y
        self.volume_canvas_h = t.VOL_HEIGHT + 2 * t.VOL_THUMB_R
        y += self.volume_canvas_h + t.GAP_VOL_LABEL
        self.vol_label_y = y
        y += vol_h + t.PAD_BOT

        self.bh = y

    def _create_widgets(self):
        """创建所有控件。"""
        t = MusicTheme

        # 标题（Canvas 容器，裁剪超长文本并支持跑马灯滚动）
        self.title_canvas = tk.Canvas(self.top, width=10, height=self.title_h,
                                      bg=t._hex(t.BG), highlightthickness=0, bd=0)
        self.title_text_id = self.title_canvas.create_text(
            0, self.title_h // 2, text='未检测到媒体源',
            font=self.font_title, fill=t._hex(t.TITLE_COLOR), anchor='w')

        # 艺术家
        self.artist_label = tk.Label(self.top, text='请打开支持 SMTC 的播放器',
                                     font=self.font_artist,
                                     fg=t._hex(t.ARTIST_COLOR),
                                     bg=t._hex(t.BG),
                                     relief='flat', bd=0, highlightthickness=0)

        # 进度条 Canvas
        prog_w = self.bw - 2 * t.PAD_LR
        self.progress_canvas = tk.Canvas(self.top,
                                         width=prog_w,
                                         height=self.progress_canvas_h,
                                         bg=t._hex(t.BG),
                                         highlightthickness=0, bd=0)
        self.progress_canvas.bind('<ButtonPress-1>', self._on_progress_down)
        self.progress_canvas.bind('<B1-Motion>', self._on_progress_drag)
        self.progress_canvas.bind('<ButtonRelease-1>', self._on_progress_up)

        # 时间（当前 / 总时长）
        self.time_cur_label = tk.Label(self.top, text='0:00',
                                       font=self.font_time,
                                       fg=t._hex(t.TIME_COLOR),
                                       bg=t._hex(t.BG),
                                       relief='flat', bd=0, highlightthickness=0)
        self.time_dur_label = tk.Label(self.top, text='0:00',
                                       font=self.font_time,
                                       fg=t._hex(t.TIME_COLOR),
                                       bg=t._hex(t.BG),
                                       relief='flat', bd=0, highlightthickness=0)

        # 控制按钮
        self.prev_btn = self._make_btn('⏮', t.BTN_SIZE, play=False)
        self.play_btn = self._make_btn('▶', t.BTN_PLAY_SIZE, play=True)
        self.next_btn = self._make_btn('⏭', t.BTN_SIZE, play=False)

        self.prev_btn.config(command=self._on_prev)
        self.play_btn.config(command=self._on_play_pause)
        self.next_btn.config(command=self._on_next)

        # 音量条 Canvas
        self.volume_canvas = tk.Canvas(self.top,
                                       width=self.bw - 2 * t.PAD_LR,
                                       height=self.volume_canvas_h,
                                       bg=t._hex(t.BG),
                                       highlightthickness=0, bd=0)
        self.volume_canvas.bind('<ButtonPress-1>', self._on_volume_down)
        self.volume_canvas.bind('<B1-Motion>', self._on_volume_drag)
        self.volume_canvas.bind('<ButtonRelease-1>', self._on_volume_up)

        # 音量百分比
        self.vol_label = tk.Label(self.top, text='',
                                  font=self.font_vol,
                                  fg=t._hex(t.TIME_COLOR),
                                  bg=t._hex(t.BG),
                                  relief='flat', bd=0, highlightthickness=0)

        # 关闭按钮
        self.close_btn = tk.Button(self.top, text='×',
                                   font=('Microsoft YaHei UI', 9, 'bold'),
                                   fg=t._hex(t.CLOSE_COLOR),
                                   bg=t._hex(t.BG),
                                   activebackground='#fff0e0',
                                   relief='flat', bd=0, highlightthickness=0,
                                   cursor='hand2', command=self._close)

    def _make_btn(self, text, size, play=False):
        """创建控制按钮（Canvas 自绘，完全无边框）。

        【主题系统】按钮颜色从 MusicTheme 读取，支持自定义。
        """
        return _CanvasButton(self.top, text, size, self.font_btn,
                             MusicTheme, is_play=play)

    def _make_bubble_img(self, tail_right):
        """生成气泡背景图：圆角矩形 + 侧边尾巴。"""
        t = MusicTheme
        bw, bh = self.bw, self.bh
        tail = self.TAIL_ALLOW
        win_w = bw + tail + 1
        img = Image.new('RGBA', (win_w, bh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        bx = 0 if tail_right else tail
        r = 10
        d.rounded_rectangle([bx, 0, bx + bw - 1, bh - 1], radius=r,
                            fill=t.BG, outline=t.BORDER, width=1)
        ty1 = bh - 34; ty2 = bh - 20; tmy = bh - 27
        if tail_right:
            apex = bx + bw + tail - 1
            d.polygon([(bx + bw - 1, ty1), (apex, tmy), (bx + bw - 1, ty2)],
                      fill=t.BG)
            d.line([(bx + bw - 1, ty1), (apex, tmy), (bx + bw - 1, ty2)],
                   fill=t.BORDER, width=1)
        else:
            apex = bx - tail + 1
            d.polygon([(bx, ty1), (apex, tmy), (bx, ty2)], fill=t.BG)
            d.line([(bx, ty1), (apex, tmy), (bx, ty2)],
                   fill=t.BORDER, width=1)
        return binarize_alpha(img), win_w

    def _apply_bubble(self, tail_right):
        """应用气泡背景图并放置所有控件。"""
        t = MusicTheme
        img, win_w = self._make_bubble_img(tail_right)
        self.bubble_photo = ImageTk.PhotoImage(img)
        self.canvas.config(width=win_w, height=self.bh)
        self.canvas.itemconfig(self.img_item, image=self.bubble_photo)

        body_x = 0 if tail_right else self.TAIL_ALLOW
        content_w = self.bw - 2 * t.PAD_LR

        # 标题（Canvas 容器，裁剪超长文本）
        self.title_canvas.place(x=body_x + t.PAD_LR, y=self.title_y,
                                width=content_w)

        # 艺术家（居中）
        self.artist_label.place(x=body_x + t.PAD_LR, y=self.artist_y,
                                width=content_w)

        # 进度条
        self.progress_canvas.place(x=body_x + t.PAD_LR, y=self.progress_y,
                                   width=content_w)

        # 时间（左对齐当前时间，右对齐总时长）
        self.time_cur_label.place(x=body_x + t.PAD_LR, y=self.time_y,
                                  anchor='nw')
        self.time_dur_label.place(x=body_x + self.bw - t.PAD_LR, y=self.time_y,
                                  anchor='ne')

        # 控制按钮（居中排列，播放/暂停按钮稍大，垂直居中对齐）
        btn_total_w = t.BTN_SIZE + t.BTN_GAP + t.BTN_PLAY_SIZE + t.BTN_GAP + t.BTN_SIZE
        btn_x0 = body_x + (self.bw - btn_total_w) // 2
        # 小按钮垂直居中于大按钮
        small_offset = (t.BTN_PLAY_SIZE - t.BTN_SIZE) // 2
        self.prev_btn.place(x=btn_x0, y=self.btn_y + small_offset,
                            width=t.BTN_SIZE, height=t.BTN_SIZE)
        self.play_btn.place(x=btn_x0 + t.BTN_SIZE + t.BTN_GAP, y=self.btn_y,
                            width=t.BTN_PLAY_SIZE, height=t.BTN_PLAY_SIZE)
        self.next_btn.place(x=btn_x0 + t.BTN_SIZE + t.BTN_GAP + t.BTN_PLAY_SIZE + t.BTN_GAP,
                            y=self.btn_y + small_offset,
                            width=t.BTN_SIZE, height=t.BTN_SIZE)

        # 音量条
        self.volume_canvas.place(x=body_x + t.PAD_LR, y=self.volume_y,
                                 width=content_w)

        # 音量百分比（居中）
        self.vol_label.place(x=body_x + self.bw // 2, y=self.vol_label_y,
                             anchor='n')

        # 关闭按钮
        self.close_btn.place(x=body_x + self.bw - 23, y=4,
                             width=18, height=18)

    def _place_at(self, pet_x, pet_y, pet_fw, pet_fh):
        """计算并设置气泡位置。"""
        wa = working_area()
        win_w = self.bw + self.TAIL_ALLOW + 1
        tail_right = True
        bx = int(pet_x) - win_w - 10
        if bx < 8:
            bx = int(pet_x) + pet_fw + 10
            tail_right = False
        by = int(max(8, min(wa[3] - self.bh - 8,
                            pet_y + pet_fh * 0.55 - self.bh / 2.0)))
        if tail_right != self._cur_tail:
            self._apply_bubble(tail_right)
            self._cur_tail = tail_right
        self.top.geometry('%dx%d+%d+%d' % (win_w, self.bh, bx, by))

    def show(self, pet_x, pet_y, pet_fw, pet_fh):
        """显示气泡。"""
        self.opened = True
        self.fade = 0.0
        self._cur_tail = None
        # 初始读取音量
        self._volume = self._controller.get_volume()
        self._muted = self._controller.is_muted()
        self._place_at(pet_x, pet_y, pet_fw, pet_fh)
        self._refresh_ui()
        self.top.attributes('-alpha', 0.0)
        self.top.deiconify()

    def position(self, pet_x, pet_y, pet_fw, pet_fh):
        """桌宠移动时同步气泡位置。"""
        if not self.opened:
            return
        self._place_at(pet_x, pet_y, pet_fw, pet_fh)

    def tick(self, dt):
        """每帧调用：淡入动画 + 刷新 UI（主线程安全）。"""
        if not self.opened:
            return
        self.fade += dt * 6.0
        try:
            self.top.attributes('-alpha', min(1.0, self.fade))
        except Exception:
            pass
        # 如果有待处理的媒体更新，刷新整个 UI
        if self._pending_update:
            self._pending_update = False
            self._refresh_ui()
        else:
            # 进度更新：仅播放中累加时间差，暂停时固定不变
            # 拖动中或无时长时不更新
            m = self._media_info
            if (m.available and m.duration_sec > 0
                    and not self._dragging_progress and self._anchor_time > 0):
                if m.is_playing:
                    elapsed = time.monotonic() - self._anchor_time
                    m.position_sec = min(m.duration_sec, self._anchor_pos + elapsed)
                else:
                    m.position_sec = self._anchor_pos
            self._refresh_progress()
            self._refresh_volume()
        # 跑马灯动画（每帧更新，与媒体回调无关）
        self._tick_marquee(dt)

    def close(self):
        """关闭气泡。"""
        self.opened = False
        self.fade = 0.0
        try:
            self.top.attributes('-alpha', 0.0)
            self.top.withdraw()
        except Exception:
            pass
        try:
            self.on_close()
        except Exception:
            pass

    def _close(self):
        self.close()

    # ---------- 媒体信息回调（后台线程调用）----------
    # 防抖阈值：SMTC 值需稳定前进超过此值才校准锚点
    PROGRESS_DEBOUNCE = 0.8       # 秒
    # 最大允许偏差：超过此值强制校准（防止长期累积误差）
    PROGRESS_MAX_DRIFT = 5.0      # 秒

    def _on_media_update(self, media_info):
        """媒体信息更新回调（在 MusicController 后台线程中调用）。

        时间平滑锁定策略：
        - 显示值由 tick 累加驱动（anchor_pos + elapsed），持续平稳前进
        - SMTC 回调仅在以下情况校准锚点：
          1. 切歌（标题变化）：重置为新位置
          2. 播放状态切换：以当前显示位置为新锚点
          3. SMTC 值 > 显示值 + 阈值：稳定正向偏移，接受校准
          4. SMTC 值 < 显示值 - 最大偏差：累积误差过大，强制校准
        - 其他情况（包括回跳噪声 43→44→43）：完全忽略，不刷新 UI
        """
        cur_title = media_info.title or ''
        cur_pos = media_info.position_sec
        now = time.monotonic()

        # 计算当前显示位置（基于锚点 + 时间差）
        if self._anchor_time > 0:
            elapsed = now - self._anchor_time
            if self._last_playing:
                current_display = self._anchor_pos + elapsed
            else:
                current_display = self._anchor_pos
        else:
            current_display = cur_pos

        # 1. 切歌检测：标题变化 → 新歌，重置锚点
        if cur_title and cur_title != self._last_title:
            self._last_title = cur_title
            self._anchor_pos = cur_pos
            self._anchor_time = now
            self._last_playing = media_info.is_playing

        # 2. 播放状态切换：以当前显示位置为新锚点（保持显示连续）
        elif media_info.is_playing != self._last_playing:
            self._last_playing = media_info.is_playing
            self._anchor_pos = current_display
            self._anchor_time = now

        # 3. 暂停状态：不更新锚点（完全静止，tick 中 is_playing=False 不累加）
        elif not media_info.is_playing:
            pass

        # 4. 播放中：时间平滑锁定
        else:
            diff = cur_pos - current_display
            if diff > self.PROGRESS_DEBOUNCE:
                # 稳定正向偏移（如 seek 前进）：接受校准
                self._anchor_pos = cur_pos
                self._anchor_time = now
            elif diff < -self.PROGRESS_MAX_DRIFT:
                # 偏差过大（显示值领先太多）：强制校准回 SMTC 值
                self._anchor_pos = cur_pos
                self._anchor_time = now
            # 其他情况（回跳噪声、小幅波动）：忽略，依赖 tick 累加

        # 同步显示位置到 media_info（tick 会继续在此基础上累加）
        if media_info.is_playing and media_info.duration_sec > 0:
            elapsed = now - self._anchor_time
            media_info.position_sec = min(media_info.duration_sec,
                                          self._anchor_pos + elapsed)
        else:
            media_info.position_sec = self._anchor_pos

        self._media_info = media_info
        self._pending_update = True

    # ---------- UI 刷新 ----------
    def _refresh_ui(self):
        """刷新整个 UI（主线程）。"""
        m = self._media_info

        if m.available:
            # 有媒体源
            self._update_title(m.title or '未知歌曲')
            self.artist_label.config(text=m.artist or '未知艺术家')
            icon = '⏸' if m.is_playing else '▶'
            self.play_btn.config(text=icon, state='normal')
            self.prev_btn.config(state='normal')
            self.next_btn.config(state='normal')
        else:
            # 无媒体源 -> 置灰控件
            self._update_title('未检测到媒体源')
            self.artist_label.config(text='请打开支持 SMTC 的播放器')
            self.play_btn.config(text='▶', state='disabled')
            self.prev_btn.config(state='disabled')
            self.next_btn.config(state='disabled')

        self._refresh_progress()
        self._refresh_volume()

    # ---------- 跑马灯 ----------
    # 滚动速度 px/s、停留时间 秒、末尾间距 px
    MARQUEE_SPEED = 32
    MARQUEE_HOLD = 1.0
    MARQUEE_GAP = 20

    def _update_title(self, text):
        """更新标题显示：超长标题启动跑马灯滚动，短标题居中静止。

        标题未变化时不重置跑马灯状态，避免每秒回调打断滚动动画。
        """
        if text == self._marquee_text:
            return
        self._marquee_text = text
        t = MusicTheme
        canvas_w = self.bw - 2 * t.PAD_LR
        self.title_canvas.itemconfig(self.title_text_id, text=text)
        text_w = self.font_title.measure(text)
        if text_w > canvas_w:
            # 超长标题：左对齐 + 跑马灯
            self._marquee_active = True
            self._marquee_text_w = text_w
            self._marquee_offset = 0.0
            self._marquee_phase = 0
            self._marquee_timer = 0.0
            self.title_canvas.itemconfig(self.title_text_id, anchor='w')
            self.title_canvas.coords(self.title_text_id,
                                     0, self.title_h // 2)
        else:
            # 短标题：居中静止
            self._marquee_active = False
            self.title_canvas.itemconfig(self.title_text_id, anchor='center')
            self.title_canvas.coords(self.title_text_id,
                                     canvas_w // 2, self.title_h // 2)

    def _tick_marquee(self, dt):
        """跑马灯动画：超长标题向左循环滚动（开头停留→滚动→末尾停留→重置）。"""
        if not self._marquee_active:
            return
        canvas_w = self.bw - 2 * MusicTheme.PAD_LR
        scroll_dist = self._marquee_text_w + self.MARQUEE_GAP - canvas_w
        if scroll_dist <= 0:
            return
        if self._marquee_phase == 0:          # 开头停留
            self._marquee_timer += dt
            if self._marquee_timer >= self.MARQUEE_HOLD:
                self._marquee_phase = 1
                self._marquee_timer = 0.0
        elif self._marquee_phase == 1:        # 向左滚动
            self._marquee_offset -= self.MARQUEE_SPEED * dt
            if self._marquee_offset <= -scroll_dist:
                self._marquee_offset = -scroll_dist
                self._marquee_phase = 2
                self._marquee_timer = 0.0
        elif self._marquee_phase == 2:        # 末尾停留
            self._marquee_timer += dt
            if self._marquee_timer >= self.MARQUEE_HOLD:
                self._marquee_offset = 0.0
                self._marquee_phase = 0
                self._marquee_timer = 0.0
        self.title_canvas.coords(self.title_text_id,
                                 self._marquee_offset, self.title_h // 2)

    def _refresh_progress(self):
        """刷新进度条和时间显示。

        当播放器不提供时长（duration_sec == 0，如网易云部分 SMTC 插件）时，
        进度条置灰不可拖动，时间区显示"直播模式"。
        """
        m = self._media_info
        if m.available and m.duration_sec > 0:
            # 正常模式：有总时长
            self.time_cur_label.config(text=_fmt_time(m.position_sec))
            self.time_dur_label.config(text=_fmt_time(m.duration_sec))
        elif m.available:
            # 有媒体源但无时长（网易云 SMTC 插件限制）
            self.time_cur_label.config(text='暂未获取进度')
            self.time_dur_label.config(text='')
        else:
            self.time_cur_label.config(text='0:00')
            self.time_dur_label.config(text='0:00')
        self._draw_progress()

    def _refresh_volume(self):
        """刷新音量条。"""
        if not self._dragging_volume:
            self._volume = self._controller.get_volume()
            self._muted = self._controller.is_muted()
        self._draw_volume()
        pct = int(round(self._volume * 100))
        if self._muted:
            self.vol_label.config(text='🔇 %d%%' % pct)
        else:
            self.vol_label.config(text='🔊 %d%%' % pct)

    def _draw_progress(self):
        """绘制进度条。

        【主题系统】进度条颜色和尺寸从 MusicTheme 读取，支持自定义。
        左右内边距 = 滑块半径，确保首尾滑块不被裁切。
        无时长（duration_sec == 0）时进度条置灰，不显示滑块。
        """
        t = MusicTheme
        c = self.progress_canvas
        c.delete('progress')
        w = c.winfo_width()
        if w <= 1:
            w = self.bw - 2 * t.PAD_LR
        h = self.progress_canvas_h

        # 左右内边距 = 滑块半径，确保滑块在首尾位置不被裁切
        pad = t.PROGRESS_THUMB_R
        track_x0 = pad
        track_x1 = w - pad
        track_w = track_x1 - track_x0

        # 轨道（垂直居中）
        track_y = (h - t.PROGRESS_HEIGHT) // 2

        m = self._media_info
        has_duration = m.available and m.duration_sec > 0

        if has_duration:
            # 正常模式：有总时长
            track_color = t.PROGRESS_BG
            fill_color = t.PROGRESS_FILL
            thumb_color = t.PROGRESS_THUMB
            ratio = m.progress
        else:
            # 无时长模式：置灰，不显示填充和滑块
            track_color = t.HINT_COLOR
            fill_color = None
            thumb_color = None
            ratio = 0.0

        # 轨道
        c.create_rectangle(track_x0, track_y, track_x1, track_y + t.PROGRESS_HEIGHT,
                           fill=t._hex(track_color), outline='', tags='progress')

        # 填充（仅有时长时）
        if fill_color:
            fill_w = int(track_w * ratio)
            if fill_w > 0:
                c.create_rectangle(track_x0, track_y, track_x0 + fill_w,
                                   track_y + t.PROGRESS_HEIGHT,
                                   fill=t._hex(fill_color), outline='', tags='progress')

            # 滑块
            thumb_x = track_x0 + fill_w
            thumb_y = h // 2
            c.create_oval(thumb_x - t.PROGRESS_THUMB_R, thumb_y - t.PROGRESS_THUMB_R,
                          thumb_x + t.PROGRESS_THUMB_R, thumb_y + t.PROGRESS_THUMB_R,
                          fill=t._hex(thumb_color), outline='', tags='progress')

    def _draw_volume(self):
        """绘制音量条。

        【主题系统】音量条颜色和尺寸从 MusicTheme 读取，支持自定义。
        左右内边距 = 滑块半径，确保首尾滑块不被裁切。
        """
        t = MusicTheme
        c = self.volume_canvas
        c.delete('volume')
        w = c.winfo_width()
        if w <= 1:
            w = self.bw - 2 * t.PAD_LR
        h = self.volume_canvas_h

        # 左右内边距 = 滑块半径，确保滑块在首尾位置不被裁切
        pad = t.VOL_THUMB_R
        track_x0 = pad
        track_x1 = w - pad
        track_w = track_x1 - track_x0

        # 轨道
        track_y = (h - t.VOL_HEIGHT) // 2
        c.create_rectangle(track_x0, track_y, track_x1, track_y + t.VOL_HEIGHT,
                           fill=t._hex(t.VOL_BG), outline='', tags='volume')

        # 填充
        vol = self._volume if not self._muted else 0.0
        fill_w = int(track_w * vol)
        if fill_w > 0:
            c.create_rectangle(track_x0, track_y, track_x0 + fill_w,
                               track_y + t.VOL_HEIGHT,
                               fill=t._hex(t.VOL_FILL), outline='', tags='volume')

        # 滑块
        thumb_x = track_x0 + fill_w
        thumb_y = h // 2
        c.create_oval(thumb_x - t.VOL_THUMB_R, thumb_y - t.VOL_THUMB_R,
                      thumb_x + t.VOL_THUMB_R, thumb_y + t.VOL_THUMB_R,
                      fill=t._hex(t.VOL_THUMB), outline='', tags='volume')

    # ---------- 进度条交互 ----------
    def _on_progress_down(self, e):
        if not self._media_info.available or self._media_info.duration_sec <= 0:
            return
        self._dragging_progress = True
        self._seek_to(e.x)

    def _on_progress_drag(self, e):
        if self._dragging_progress:
            self._seek_to(e.x)

    def _on_progress_up(self, e):
        if self._dragging_progress:
            self._dragging_progress = False
            self._seek_to(e.x)

    def _seek_to(self, x):
        """拖动进度条到指定位置（考虑左右内边距）。"""
        c = self.progress_canvas
        w = c.winfo_width()
        if w <= 1:
            return
        pad = MusicTheme.PROGRESS_THUMB_R
        track_w = w - 2 * pad
        if track_w <= 0:
            return
        ratio = max(0.0, min(1.0, (x - pad) / track_w))
        new_pos = ratio * self._media_info.duration_sec
        # 立即更新显示，同步锚点（以新位置为锚点）
        self._media_info.position_sec = new_pos
        self._anchor_pos = new_pos
        self._anchor_time = time.monotonic()
        self._refresh_progress()
        # 实际 seek（通过 SMTC）
        self._controller.seek(new_pos)

    # ---------- 音量条交互 ----------
    def _on_volume_down(self, e):
        self._dragging_volume = True
        self._set_volume_to(e.x)

    def _on_volume_drag(self, e):
        if self._dragging_volume:
            self._set_volume_to(e.x)

    def _on_volume_up(self, e):
        if self._dragging_volume:
            self._dragging_volume = False
            self._set_volume_to(e.x)

    def _set_volume_to(self, x):
        """拖动音量条到指定位置（考虑左右内边距）。"""
        c = self.volume_canvas
        w = c.winfo_width()
        if w <= 1:
            return
        pad = MusicTheme.VOL_THUMB_R
        track_w = w - 2 * pad
        if track_w <= 0:
            return
        vol = max(0.0, min(1.0, (x - pad) / track_w))
        self._volume = vol
        self._controller.set_volume(vol)
        # 如果之前是静音状态，拖动音量时自动取消静音
        if self._muted and vol > 0:
            self._controller.toggle_mute()
            self._muted = False
        self._refresh_volume()

    # ---------- 媒体控制 ----------
    def _on_play_pause(self):
        self._controller.play_pause()
        # 立即更新图标和播放状态（不等下次回调）
        if self._media_info.available:
            self._media_info.is_playing = not self._media_info.is_playing
            icon = '⏸' if self._media_info.is_playing else '▶'
            self.play_btn.config(text=icon)
            # 同步锚点：以当前显示位置为新锚点，重置时间戳
            # - 播放→暂停：tick 中 pos = _anchor_pos（冻结）
            # - 暂停→播放：tick 中 pos = _anchor_pos + elapsed（继续前进）
            self._anchor_pos = self._media_info.position_sec
            self._anchor_time = time.monotonic()
            self._last_playing = self._media_info.is_playing

    def _on_next(self):
        self._controller.next_track()

    def _on_prev(self):
        self._controller.prev_track()


# ---------- 桌宠主体 ----------
class LionPet:
    PAD = 26                                   # 四周留白（容纳摇摆/弹跳不裁切）
    KEY = 'magenta'                            # 透明键（已确认图中无此色）

    def __init__(self, scale=0.07,
                 bubble_text=None):
        self.scale = scale
        self.nickname = load_nickname()
        self.bubble_text = bubble_text or ('Hello，' + self.nickname + '，有什么可以帮您的？')
        if not os.path.exists(IMG_PATH):
            raise FileNotFoundError('找不到图片文件: ' + IMG_PATH)
        src = Image.open(IMG_PATH)
        self.base_w = max(1, int(src.width * scale))
        self.base_h = max(1, int(src.height * scale))
        base = src.resize((self.base_w, self.base_h), Image.BICUBIC)
        self.base = hard_matte(base)
        self.fw = self.base_w + 2 * self.PAD
        self.fh = self.base_h + 2 * self.PAD
        log('startup: lion (py), base=%dx%d, hard matte, no purple edges'
            % (self.base_w, self.base_h))

        # 动画状态
        self.t = 0.0
        self.bob = 0.0
        self.angle = 0.0
        self.lean = 0.0
        self.lean_target = 0.0
        self.breath = 0.0
        self.wag_phase = 0.0
        self.wag_freq = 3.0
        self.dragging = False
        self.down = False
        self.base_x = 0
        self.base_y = 0
        self.down_sx = 0
        self.down_sy = 0
        self.last_sx = 0
        self.last_sy = 0
        self.hop_t = 0.0
        self.x = 0
        self.y = 0
        self.drag_logged = False
        self.bubble_open = False

        # 闲置气泡状态
        _ensure_device_config()            # 设备绑定校验（分享/换设备时重置间隔）
        self.idle_enabled = load_idle_enabled()
        self.idle_timeout = load_idle_timeout()
        self.idle_timer = 0.0
        self.idle_bubble_timer = 0.0
        self.quotes = load_quotes()
        self._config_check_timer = 0.0

        # 主窗口（无边框 / 置顶 / 不在任务栏 / magenta 透明键）
        self.root = tk.Tk()
        self.root.title('Leo桌宠')
        try:
            if os.path.exists(ICON_PATH):
                self.root.iconbitmap(ICON_PATH)
        except Exception:
            pass
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.config(bg=self.KEY)
        try:
            self.root.wm_attributes('-transparentcolor', self.KEY)
        except Exception:
            pass

        self.canvas = tk.Canvas(self.root, width=self.fw, height=self.fh,
                                bg=self.KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.photo = ImageTk.PhotoImage(Image.new('RGBA', (self.fw, self.fh)))
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)

        # 初始位置：右下角
        wa = working_area()
        self.x = wa[2] - self.fw - 20
        self.y = wa[3] - self.fh - 16
        self.root.geometry('%dx%d+%d+%d' % (self.fw, self.fh,
                                            int(self.x), int(self.y)))
        # 隐藏任务栏图标（设为工具窗口样式）
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                                ex | WS_EX_TOOLWINDOW)
        except Exception:
            pass

        # 事件
        self.canvas.bind('<ButtonPress-1>', self._on_down)
        self.canvas.bind('<B1-Motion>', self._on_move)
        self.canvas.bind('<ButtonRelease-1>', self._on_up)
        self.root.bind('<Button-3>', self._on_rclick)

        # 快捷指令 & 气泡
        self.commands = load_commands()
        self.bubble = BubbleWindow(self.root, self._on_bubble_closed)
        self.idle_bubble = IdleBubble(self.root)
        self.music_bubble = MusicBubbleWindow(self.root, self._on_music_bubble_closed)
        self.music_bubble_open = False

        # 右键菜单（自定义样式）
        self.menu = ContextMenu(self.root)
        self.menu.add_command('打开对话', self._toggle_bubble)
        self.menu.add_command('回到右下角', self._reset_pos)
        self.menu.add_separator()
        self.menu.add_command('退出', self._quit)

        self._last_key = None
        self._render()
        self._last_tick = time.perf_counter()
        self.root.after(33, self._tick)

    # ---------- 鼠标 ----------
    def _on_down(self, e):
        self.down = True
        self.dragging = False
        self.base_x = self.x
        self.base_y = self.y
        self.down_sx = e.x_root
        self.down_sy = e.y_root
        self.last_sx = e.x_root
        self.last_sy = e.y_root

    def _on_move(self, e):
        if not self.down:
            return
        # 用屏幕坐标计算位移：窗体跟随后相对坐标会被"拉回"，屏幕坐标无此自反馈
        dx = e.x_root - self.down_sx
        dy = e.y_root - self.down_sy
        if not self.dragging and math.hypot(dx, dy) > 5:   # >5px 判为拖动
            self.dragging = True
            self.wag_phase = 0.0
        if self.dragging:
            wa = working_area()
            self.x = max(4, min(wa[2] - self.fw - 4, self.base_x + dx))
            self.y = max(4, min(wa[3] - self.fh - 4, self.base_y + dy))
            lx = e.x_root - self.last_sx
            ly = e.y_root - self.last_sy
            self.lean_target = max(-5.0, min(5.0, lx * 0.8))
            spd = math.hypot(lx, ly)
            self.wag_freq = max(1.2, min(2.4, 1.2 + spd * 0.01))
            if not self.drag_logged:
                self.drag_logged = True
                log('drag: freq=%.2fHz, amp=1.6deg' % self.wag_freq)
            self.last_sx = e.x_root
            self.last_sy = e.y_root
            self.root.geometry('+%d+%d' % (int(self.x), int(self.y)))
            if self.bubble_open:
                self.bubble.position(self.x, self.y, self.fw, self.fh)
            if self.music_bubble_open:
                self.music_bubble.position(self.x, self.y, self.fw, self.fh)
            if self.idle_bubble.opened:
                self.idle_bubble.position(self.x, self.y, self.fw, self.fh)

    def _on_up(self, e):
        if not self.down:
            return
        was_drag = self.dragging
        self.down = False
        self.dragging = False
        self.lean = 0.0
        self.lean_target = 0.0
        self.drag_logged = False
        if not was_drag:                       # 未拖动 = 单击 -> 切换气泡
            self._toggle_bubble()

    def _on_rclick(self, e):
        self.menu.show(e.x_root, e.y_root)

    # ---------- 气泡 ----------
    def _on_bubble_closed(self):
        """气泡关闭时同步状态（由 × 按钮或按钮回调触发）。
        注意：交互行为不重置闲置计时，闲置气泡按自身节奏运行。"""
        self.bubble_open = False

    def _on_music_bubble_closed(self):
        """音乐盒气泡关闭时同步状态。"""
        self.music_bubble_open = False

    # ---------- 闲置气泡 ----------
    def _toggle_bubble(self):
        if self.music_bubble_open:
            self.music_bubble.close()
        elif self.bubble_open:
            self.bubble.close()
        else:
            self._show_main_bubble()

    def _show_main_bubble(self):
        """主气泡：问候语 + 快捷指令 / 音乐盒 / 时间 三按钮。"""
        self.bubble.set_content(
            self.bubble_text,
            ['快捷指令', '音乐盒', '时间'],
            self._on_main_btn_click)
        self.bubble_open = True
        self.hop_t = 0.35                  # 开心一跳
        self.bubble.show(self.x, self.y, self.fw, self.fh)

    def _on_main_btn_click(self, idx):
        """主气泡按钮：关闭当前气泡，切换到对应子气泡。"""
        self.bubble.close()
        if idx == 0:
            self._show_commands_bubble()
        elif idx == 1:
            self._show_music_bubble()
        elif idx == 2:
            self._show_time_bubble()

    def _show_commands_bubble(self):
        """快捷指令子气泡：展示 config.json 中的指令列表。"""
        self.commands = load_commands()               # 每次打开重新读取，确保最新
        if not self.commands:
            # 所有指令被删除 → 显示提示，不展示按钮
            self.bubble.set_content('请从配置当中添加指令~', [], None)
        else:
            cmd_names = [c.get('name', '') for c in self.commands]
            self.bubble.set_content('小主人，您要打开什么呀？', cmd_names, self._on_cmd_btn_click)
        self.bubble_open = True
        self.bubble.show(self.x, self.y, self.fw, self.fh)

    def _on_cmd_btn_click(self, idx):
        """快捷指令子气泡按钮：关闭气泡并执行对应指令。"""
        self.bubble.close()
        self._execute_command(idx)

    def _show_music_bubble(self):
        """音乐盒气泡：基于 SMTC 显示媒体信息和控制界面。"""
        self.music_bubble_open = True
        self.hop_t = 0.35                  # 开心一跳
        self.music_bubble.show(self.x, self.y, self.fw, self.fh)

    def _show_time_bubble(self):
        """时间子气泡：显示当前日期和时间。"""
        now = datetime.datetime.now()
        weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][now.weekday()]
        time_str = now.strftime('%Y年%m月%d日 %H:%M') + ' ' + weekday
        self.bubble.set_content(time_str, [], None)
        self.bubble_open = True
        self.bubble.show(self.x, self.y, self.fw, self.fh)

    def _execute_command(self, idx):
        """执行快捷指令（app/url/file 三种类型）。"""
        if idx < 0 or idx >= len(self.commands):
            return
        cmd = self.commands[idx]
        t = cmd.get('type', '')
        target = cmd.get('target', '')
        if t == 'app':                        # MSIX 应用（AUMID）
            self._launch_app(target)
        elif t == 'url':                      # 网址
            try:
                webbrowser.open(target)
            except Exception as ex:
                log('open url failed: %s' % ex)
        elif t == 'file':                     # 本地文件 / 程序
            try:
                os.startfile(target)
            except Exception:
                try:
                    subprocess.Popen([target])
                except Exception as ex:
                    log('open file failed: %s' % ex)

    @staticmethod
    def _launch_app(aumid):
        if not aumid:
            return
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, 'open', 'shell:AppsFolder\\' + aumid, None, None, 1)
        except Exception as ex:
            log('launch %s failed: %s' % (aumid, ex))

    # ---------- 菜单 ----------
    def _reset_pos(self):
        wa = working_area()
        self.x = wa[2] - self.fw - 20
        self.y = wa[3] - self.fh - 16
        self.root.geometry('+%d+%d' % (int(self.x), int(self.y)))
        if self.bubble_open:
            self.bubble.position(self.x, self.y, self.fw, self.fh)
        if self.music_bubble_open:
            self.music_bubble.position(self.x, self.y, self.fw, self.fh)
        if self.idle_bubble.opened:
            self.idle_bubble.position(self.x, self.y, self.fw, self.fh)

    def _quit(self):
        try:
            with open(CLEAN_EXIT, 'w') as f:
                f.write('ok')
        except Exception:
            pass
        try:
            self.bubble.close()
        except Exception:
            pass
        try:
            self.music_bubble.close()
        except Exception:
            pass
        try:
            self.idle_bubble.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- 动画 ----------
    def _render(self):
        key = '%.3f|%.3f|%.3f' % (self.angle, self.bob, self.breath)
        if key != self._last_key:              # 帧缓存：值未变不重建
            frame = render_frame(self.base, self.fw, self.fh, self.PAD,
                                 self.angle, self.bob, self.breath)
            self.photo.paste(frame)
            self._last_key = key

    def _step(self, dt):
        self.t += dt
        if self.dragging:
            # 拖拽：平滑摇晃（幅度小频率低，不抖动）+ 方向倾斜
            self.lean += (self.lean_target - self.lean) * 0.25
            self.wag_phase += self.wag_freq * dt
            self.angle = math.sin(self.wag_phase * 2 * math.pi) * 1.6 + self.lean
            self.bob = 0
            self.breath = math.sin(self.t * 2 * math.pi / 2.6) * 0.6
        else:
            # 闲时：轻微漂浮 + 缓慢摇摆 + 呼吸
            self.angle = math.sin(self.t * 2 * math.pi / 2.4) * 2.2
            self.bob = math.sin(self.t * 2 * math.pi / 3.0) * 3
            self.breath = math.sin(self.t * 2 * math.pi / 2.6) * 0.6
        if self.hop_t > 0:
            self.hop_t -= dt
            self.bob += math.sin(math.pi * (1 - self.hop_t / 0.35)) * 12
        self._render()
        if self.bubble_open:
            self.bubble.tick(dt)
        if self.music_bubble_open:
            self.music_bubble.tick(dt)

        # 配置热更新：每2秒轮询 config.json，检测开关、间隔、昵称是否被管理软件修改
        self._config_check_timer += dt
        if self._config_check_timer >= 2.0:
            self._config_check_timer = 0.0
            new_enabled = load_idle_enabled()
            new_timeout = load_idle_timeout()
            new_nick = load_nickname()
            if new_enabled != self.idle_enabled or new_timeout != self.idle_timeout:
                self.idle_enabled = new_enabled
                self.idle_timeout = new_timeout
                # 配置变更 -> 立即重置倒计时
                self.idle_timer = 0.0
                self.idle_bubble_timer = 0.0
                # 开关关闭时，关闭正在显示的闲置气泡
                if not self.idle_enabled and self.idle_bubble.opened:
                    self.idle_bubble.close()
            if new_nick != self.nickname:
                self.nickname = new_nick
                self.bubble_text = 'Hello，' + self.nickname + '，有什么可以帮您的？'

        # 闲置气泡逻辑
        if self.idle_enabled:
            if self.idle_bubble.opened:
                # 闲置气泡显示中：计时 10 秒后自动关闭并重新开始
                self.idle_bubble.tick(dt)
                self.idle_bubble_timer += dt
                if self.idle_bubble_timer >= IDLE_BUBBLE_DURATION:
                    self.idle_bubble.close()
                    self.idle_bubble_timer = 0.0
                    self.idle_timer = 0.0
            else:
                # 闲置计时：按配置间隔触发
                self.idle_timer += dt
                if self.idle_timer >= self.idle_timeout:
                    quote = random.choice(self.quotes)
                    self.idle_bubble.show(quote, self.x, self.y, self.fw, self.fh)
                    self.idle_bubble_timer = 0.0

    def _tick(self):
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        # 限制单帧最大步长，防止窗口被挂起后恢复时产生超大 dt
        if dt > 0.1:
            dt = 0.1
        self._step(dt)
        self.root.after(33, self._tick)

    def run(self):
        self.root.mainloop()

    def smoke_test(self):
        log('smoke test start')
        for _ in range(8):
            self._step(0.033)
            self.root.update()
        self._show_main_bubble()
        for _ in range(6):
            self._step(0.033)
            self.root.update()
        self.bubble.close()
        # 音乐盒气泡冒烟测试
        self._show_music_bubble()
        for _ in range(6):
            self._step(0.033)
            self.root.update()
        self.music_bubble.close()
        self._quit()
        print('TEST OK')


# ---------- 单实例锁 ----------
def acquire_lock(port=52718):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
        s.listen(5)                        # backlog 留余量，避免状态检测连接被拒
        return s
    except OSError:
        return None


# ---------- 命令端口（供管理软件通知桌宠自行退出，避免 PowerShell 杀进程慢）----------
CMD_PORT = 52720

def start_cmd_server(pet):
    """后台线程：监听命令端口，收到 'quit' 时让桌宠自行退出。
    与右键菜单退出走相同的快速路径（root.destroy 瞬间完成）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', CMD_PORT))
        s.listen(1)
        s.settimeout(0.5)
    except OSError:
        return                             # 端口已被占用（极少见），放弃
    def worker():
        while True:
            try:
                conn, _ = s.accept()
                try:
                    data = conn.recv(16).strip().lower()
                    if data == b'quit':
                        pet._quit()        # 触发与右键退出相同的路径
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except Exception:
                break
    threading.Thread(target=worker, daemon=True).start()


def _drain_lock_socket(sock):
    """后台线程：持续 accept() 锁端口上的连接并立即关闭。
    防止管理软件的 get_status() 轮询连接堆积在 accept 队列中，
    导致 backlog 满后新连接被拒、状态误判为"未在线"。"""
    import threading
    def worker():
        while True:
            try:
                conn, _ = sock.accept()
                try:
                    conn.close()
                except Exception:
                    pass
            except Exception:
                break
    t = threading.Thread(target=worker, daemon=True)
    t.start()


def main():
    test = False
    scale = 0.07
    for a in sys.argv[1:]:
        if a == '--test':
            test = True
        elif a.startswith('--scale='):
            try:
                scale = float(a.split('=', 1)[1])
            except Exception:
                pass
    _lock = acquire_lock()                     # 必须持有引用，否则 socket 被 GC 后端口关闭
    if _lock is None:                          # 已有实例在跑 -> 退出
        sys.exit(0)
    _drain_lock_socket(_lock)                  # 消费 accept 队列，防止 backlog 满导致状态误判
    try:
        pet = LionPet(scale=scale)
        start_cmd_server(pet)                  # 启动命令端口，供管理软件通知退出
        if test:
            pet.smoke_test()
        else:
            pet.run()
    except Exception:
        log('启动失败: ' + traceback.format_exc())
        try:
            ctypes.windll.user32.MessageBoxW(
                0, '狮子助手启动失败，详见 lion.log', '错误', 0x10)
        except Exception:
            pass


if __name__ == '__main__':
    main()
