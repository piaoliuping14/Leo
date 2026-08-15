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
import logging
import socket
import traceback
import subprocess
import webbrowser
import ctypes
import datetime
from ctypes import wintypes
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk, ImageDraw

# ---------- 路径 ----------
DIR = os.path.dirname(os.path.abspath(__file__))
IMG_PATH = os.path.join(DIR, 'katong', '狮子111-no-bg.png')
LOG_PATH = os.path.join(DIR, 'lion.log')
CLEAN_EXIT = os.path.join(DIR, 'lion_clean_exit.txt')
CONFIG_PATH = os.path.join(DIR, 'config.json')

# ---------- 快捷指令默认配置（config.json 缺失时回退）----------
DEFAULT_COMMANDS = [
    {'name': '启动Claude',  'type': 'app', 'target': 'Claude_pzs8sxrjxfjjc!Claude',     'icon': 'sparkles'},
    {'name': '启动ChatGPT', 'type': 'app', 'target': 'OpenAI.Codex_2p2nqsd0c76g0!App', 'icon': 'message-circle'},
    {'name': '启动B站',      'type': 'url', 'target': 'https://www.bilibili.com/',       'icon': 'play'},
]


def load_commands():
    """从 config.json 读取快捷指令；缺失或异常时回退默认列表。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cmds = data.get('commands')
        if cmds:
            return cmds
    except Exception:
        pass
    return list(DEFAULT_COMMANDS)

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


# ---------- 对话气泡 ----------
class BubbleWindow:
    """可动态切换内容的对话气泡：set_content() 更新文本和按钮后 show() 即可。"""
    TAIL_ALLOW = 14                         # 尾巴预留宽度（整体收入窗口，不被裁切）
    KEY = 'magenta'
    BG       = (252, 252, 254)              # 极浅冷白
    BORDER   = (214, 221, 234)
    TEXT     = (34, 48, 70)
    BTN_BASE = (244, 246, 251)
    BTN_HOVER= (224, 234, 252)
    BTN_BD   = (204, 214, 233)
    BTN_TX   = (46, 64, 92)
    BTN_TXH  = (26, 86, 170)

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
        self.bw = max(lab_w + 2 * self.pad_lr, btn_row_w + 2 * self.pad_lr, 160)

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
                                   fg='#965c5c', bg=self._hex(self.BG),
                                   activebackground='#f7e2e2',
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


# ---------- 桌宠主体 ----------
class LionPet:
    PAD = 26                                   # 四周留白（容纳摇摆/弹跳不裁切）
    KEY = 'magenta'                            # 透明键（已确认图中无此色）

    def __init__(self, scale=0.07,
                 bubble_text='Hello，Fangjizhong，有什么可以帮您的？'):
        self.scale = scale
        self.bubble_text = bubble_text
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

        # 主窗口（无边框 / 置顶 / 不在任务栏 / magenta 透明键）
        self.root = tk.Tk()
        self.root.title('Desktop Lion')
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

        # 事件
        self.canvas.bind('<ButtonPress-1>', self._on_down)
        self.canvas.bind('<B1-Motion>', self._on_move)
        self.canvas.bind('<ButtonRelease-1>', self._on_up)
        self.root.bind('<Button-3>', self._on_rclick)

        # 快捷指令 & 气泡
        self.commands = load_commands()
        self.bubble = BubbleWindow(self.root, self._on_bubble_closed)

        # 右键菜单
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label='打开对话', command=self._toggle_bubble)
        self.menu.add_command(label='回到右下角', command=self._reset_pos)
        self.menu.add_command(label='退出', command=self._quit)

        self._last_key = None
        self._render()
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
        self.menu.tk_popup(e.x_root, e.y_root)

    # ---------- 气泡 ----------
    def _on_bubble_closed(self):
        """气泡关闭时同步状态（由 × 按钮或按钮回调触发）。"""
        self.bubble_open = False

    def _toggle_bubble(self):
        if self.bubble_open:
            self.bubble.close()
        else:
            self._show_main_bubble()

    def _show_main_bubble(self):
        """主气泡：问候语 + 快捷指令 / 天气 / 时间 三按钮。"""
        self.bubble.set_content(
            self.bubble_text,
            ['快捷指令', '天气', '时间'],
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
            self._show_weather_bubble()
        elif idx == 2:
            self._show_time_bubble()

    def _show_commands_bubble(self):
        """快捷指令子气泡：展示 config.json 中的指令列表。"""
        self.commands = load_commands()               # 每次打开重新读取，确保最新
        cmd_names = [c.get('name', '') for c in self.commands]
        self.bubble.set_content('小主人，您要打开什么呀？', cmd_names, self._on_cmd_btn_click)
        self.bubble_open = True
        self.bubble.show(self.x, self.y, self.fw, self.fh)

    def _on_cmd_btn_click(self, idx):
        """快捷指令子气泡按钮：关闭气泡并执行对应指令。"""
        self.bubble.close()
        self._execute_command(idx)

    def _show_weather_bubble(self):
        """天气子气泡：显示天气信息（暂为占位，后续可接入 API）。"""
        self.bubble.set_content('天气服务暂未接入，敬请期待', [], None)
        self.bubble_open = True
        self.bubble.show(self.x, self.y, self.fw, self.fh)

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

    def _tick(self):
        self._step(0.033)
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
    try:
        pet = LionPet(scale=scale)
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
