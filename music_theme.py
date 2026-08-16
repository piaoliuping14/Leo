# -*- coding: utf-8 -*-
# ============================================================
#  music_theme.py
#  音乐盒气泡主题配置
#
#  【主题系统 - 重点标记】
#  本文件集中管理音乐盒气泡的所有颜色、尺寸、字体配置。
#  后续 Leo 软件开发「换主题」功能时，只需替换以下配置值
#  或加载不同的主题文件即可，无需改动 lion_desktop.py 逻辑。
#
#  所有以 # [THEME] 标记的属性均属于主题可配置项。
# ============================================================


class MusicTheme:
    """音乐盒气泡主题。

    # [THEME] ==================== 颜色配置 ====================

    所有颜色为 RGB 元组，运行时通过 _hex() 转为 tkinter 颜色字符串。
    """

    # [THEME] 气泡
    BG       = (255, 250, 245)   # 气泡背景 - 暖白米色
    BORDER   = (232, 216, 196)   # 气泡边框 - 暖灰

    # [THEME] 文字
    TITLE_COLOR    = (90, 74, 62)      # 歌曲标题 - 暖棕
    ARTIST_COLOR   = (140, 120, 100)   # 艺术家名 - 浅棕
    TIME_COLOR     = (160, 140, 120)   # 时间显示 - 灰棕
    HINT_COLOR     = (180, 160, 140)   # 无播放源提示 - 浅灰棕

    # [THEME] 控制按钮（上一曲/播放暂停/下一曲）
    BTN_BG       = (255, 235, 215)    # 按钮底色 - 浅橙
    BTN_HOVER    = (255, 195, 140)    # 悬停色 - 橙色
    BTN_BORDER   = (232, 184, 140)    # 按钮边框
    BTN_TEXT     = (140, 80, 30)      # 按钮文字/图标
    BTN_PLAY_BG  = (255, 200, 130)    # 播放/暂停按钮特殊底色
    BTN_PLAY_HOVER = (255, 170, 80)   # 播放/暂停按钮悬停
    BTN_DISABLED = (225, 215, 205)    # 禁用色 - 无播放源时

    # [THEME] 进度条
    PROGRESS_BG     = (240, 230, 220)  # 进度条轨道背景
    PROGRESS_FILL   = (255, 180, 100)  # 已播放部分填充
    PROGRESS_THUMB  = (255, 150, 60)   # 滑块颜色
    PROGRESS_HEIGHT = 4                # 进度条高度（px）
    PROGRESS_THUMB_R = 5               # 滑块半径（px）

    # [THEME] 音量条
    VOL_BG     = (240, 230, 220)   # 音量条轨道背景
    VOL_FILL   = (200, 170, 130)   # 已有音量填充
    VOL_THUMB  = (180, 140, 90)    # 音量滑块
    VOL_HEIGHT = 3                 # 音量条高度（px）
    VOL_THUMB_R = 4                # 音量滑块半径（px）

    # [THEME] 关闭按钮
    CLOSE_COLOR = (176, 128, 96)   # × 颜色
    CLOSE_HOVER = (200, 80, 20)    # × 悬停色

    # [THEME] ==================== 尺寸配置 ====================

    BUBBLE_W = 240                 # 气泡内容区宽度（不含尾巴）
    PAD_LR   = 16                  # 左右内边距
    PAD_TOP  = 10                  # 顶部内边距
    PAD_BOT  = 12                  # 底部内边距

    # 各元素间距
    GAP_TITLE_ARTIST = 2           # 标题→艺术家
    GAP_ARTIST_PROG  = 10          # 艺术家→进度条
    GAP_PROG_TIME    = 3           # 进度条→时间
    GAP_TIME_BTNS    = 10          # 时间→控制按钮
    GAP_BTNS_VOL     = 10          # 控制按钮→音量条
    GAP_VOL_LABEL    = 4           # 音量条→音量百分比

    # 控制按钮
    BTN_SIZE   = 30                # 按钮尺寸（正方形）
    BTN_GAP    = 16                # 按钮间距
    BTN_PLAY_SIZE = 34             # 播放/暂停按钮稍大

    # [THEME] ==================== 字体配置 ====================

    TITLE_FONT  = ('Microsoft YaHei UI', 10, 'bold')
    ARTIST_FONT = ('Microsoft YaHei UI', 8)
    TIME_FONT   = ('Microsoft YaHei UI', 8)
    BTN_FONT    = ('Microsoft YaHei UI', 12)
    HINT_FONT   = ('Microsoft YaHei UI', 9)
    VOL_FONT    = ('Microsoft YaHei UI', 8)

    @staticmethod
    def _hex(rgb):
        """RGB 元组转 tkinter 颜色字符串。"""
        return '#%02x%02x%02x' % rgb
