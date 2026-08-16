# -*- coding: utf-8 -*-
# ============================================================
#  music_box.py
#  基于 Windows SMTC 的媒体控制 + pycaw 音量控制
#
#  设计原则：
#  - SMTC 仅用于读取媒体信息（歌名/艺术家/进度/状态）和控制播放
#  - 音量控制独立使用 pycaw（Windows Core Audio API），与 SMTC 解耦
#  - 仅识别向外输出 SMTC 会话的播放器，不做任何播放器专项适配
#  - 网易云/QQ音乐需用户自行安装第三方插件开启 SMTC
# ============================================================
import os
import sys
import time
import threading
from ctypes import cast, POINTER

# ---------- 路径（兼容 PyInstaller 打包）----------
if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(EXE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 开发模式下，第三方依赖安装在 _libs 目录（打包后由 PyInstaller 处理）
if not getattr(sys, 'frozen', False):
    _libs_dir = os.path.join(EXE_DIR, '_libs')
    if os.path.isdir(_libs_dir) and _libs_dir not in sys.path:
        sys.path.insert(0, _libs_dir)

import logging
log = logging.getLogger('lion')


# ---------- pycaw 音量控制（与 SMTC 解耦）----------
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    _PYCAW_OK = True
except Exception:
    _PYCAW_OK = False
    log.warning('pycaw 不可用，音量控制功能将禁用')


# ---------- SMTC 媒体控制 ----------
# winrt 包安装后，导入路径为 winrt.windows.media.control
# 不同 winrt 版本 API 略有差异，此处尝试多种导入方式
_SMTC_OK = False
_MediaManager = None
_SMTC_IMPORT_ERROR = None

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _MediaManager,
    )
    _SMTC_OK = True
except Exception as _ex:
    _SMTC_IMPORT_ERROR = str(_ex)
    log.warning('winrt SMTC 导入失败: %s' % _ex)
    log.warning('请安装 winrt 依赖: pip install winrt-runtime '
                'winrt-Windows.Media.Control winrt-Windows.Storage.Streams')


# SMTC 播放状态枚举值（GlobalSystemMediaTransportControlsSessionPlaybackStatus）
#   Closed=1, Opened=2, Paused=3, Playing=4, Stopped=5
_PLAYING = 4
_PAUSED = 3


class MediaInfo:
    """媒体状态快照（线程安全只读）。"""
    __slots__ = ('available', 'title', 'artist', 'is_playing',
                 'position_sec', 'duration_sec')

    def __init__(self):
        self.available = False
        self.title = ''
        self.artist = ''
        self.is_playing = False
        self.position_sec = 0.0
        self.duration_sec = 0.0

    @property
    def progress(self):
        """进度比例 0.0-1.0。"""
        if self.duration_sec > 0:
            return min(1.0, max(0.0, self.position_sec / self.duration_sec))
        return 0.0

    def copy(self):
        m = MediaInfo()
        m.available = self.available
        m.title = self.title
        m.artist = self.artist
        m.is_playing = self.is_playing
        m.position_sec = self.position_sec
        m.duration_sec = self.duration_sec
        return m


def _fmt_time(sec):
    """秒数格式化为 M:SS。"""
    if sec <= 0:
        return '0:00'
    m = int(sec) // 60
    s = int(sec) % 60
    return '%d:%02d' % (m, s)


class MusicController:
    """音乐控制器。

    - 后台线程轮询 SMTC 获取媒体信息
    - 提供 play_pause / next / prev 控制
    - 提供 get_volume / set_volume 音量控制（pycaw，与 SMTC 解耦）
    - 无播放源时 media_info.available=False，UI 层据此隐藏/置灰控件
    """

    POLL_INTERVAL = 1.0   # 轮询间隔（秒）

    def __init__(self):
        self._manager = None
        self._session = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._media_info = MediaInfo()
        self._callbacks = []
        self._volume = None
        self._logged_source = False       # 调试：避免日志刷屏
        self._init_volume()
        if _SMTC_OK:
            self._init_smtc()
        else:
            log.warning('winrt SMTC 模块未安装，媒体控制不可用。'
                        '请执行: pip install winrt-runtime winrt-Windows.Media.Control')

    # ---------- 初始化 ----------
    def _init_volume(self):
        """初始化 pycaw 音量控制。

        pycaw 2025 新版 API：
        - GetSpeakers() 返回 AudioDevice 对象
        - 通过 AudioDevice.EndpointVolume 属性获取 IAudioEndpointVolume 接口
        旧版 API：
        - GetSpeakers() 返回 IMMDevice，需手动调用 Activate()
        此处兼容两种版本。
        """
        if not _PYCAW_OK:
            return
        try:
            device = AudioUtilities.GetSpeakers()
            if device is None:
                log.warning('音量控制初始化失败: 未找到音频输出设备')
                return
            # 优先使用新版 API（AudioDevice.EndpointVolume 属性）
            if hasattr(device, 'EndpointVolume'):
                self._volume = device.EndpointVolume
            else:
                # 旧版 API 回退：手动 Activate
                interface = device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._volume = cast(interface, POINTER(IAudioEndpointVolume))
            log.info('音量控制初始化成功')
        except Exception as ex:
            log.warning('音量控制初始化失败: %s' % ex)

    def _init_smtc(self):
        """初始化 SMTC 会话管理器。

        winrt 的 request_async().get() 是阻塞调用，在主线程（STA）中调用会报错：
        'Cannot call blocking method from single-threaded apartment'
        因此在后台线程中执行初始化。
        """
        if not _SMTC_OK:
            # winrt 模块未安装，不重试
            return
        if self._manager is not None:
            return

        def _do_init():
            try:
                mgr = _MediaManager.request_async().get()
                with self._lock:
                    self._manager = mgr
                log.info('SMTC 会话管理器初始化成功')
            except Exception as ex:
                log.warning('SMTC 初始化失败: %s' % ex)

        t = threading.Thread(target=_do_init, daemon=True)
        t.start()

    # ---------- 后台轮询 ----------
    def start(self):
        """启动后台轮询线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止轮询。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def add_callback(self, cb):
        """注册媒体状态变化回调（在轮询线程中调用）。"""
        self._callbacks.append(cb)

    def _poll_loop(self):
        """后台轮询循环。"""
        while self._running:
            try:
                self._refresh()
            except Exception as ex:
                log.warning('音乐轮询异常: %s' % ex)
            time.sleep(self.POLL_INTERVAL)

    def _refresh(self):
        """刷新媒体信息并通知回调。

        使用 get_sessions() 获取所有 SMTC 会话（而非 get_current_session()，
        后者只返回系统"当前选中"的会话，可能漏掉网易云等播放器）。
        优先选择正在播放的会话，其次选择第一个有标题的会话。
        """
        # SMTC 模块未安装 -> 直接返回，不重试
        if not _SMTC_OK:
            return

        if not self._manager:
            self._init_smtc()
            if not self._manager:
                return

        # 获取所有 SMTC 会话
        try:
            sessions = self._manager.get_sessions()
        except Exception as ex:
            log.warning('get_sessions 失败: %s' % ex)
            sessions = []

        if not sessions:
            # 无会话 -> 清空状态
            new_info = MediaInfo()
            with self._lock:
                self._session = None
                self._media_info = new_info
            for cb in self._callbacks:
                try:
                    cb(new_info.copy())
                except Exception:
                    pass
            return

        # 遍历所有会话，收集信息并选出目标会话
        # 优先级：正在播放 > 有标题 > 第一个
        best_session = None
        best_info = None
        best_score = -1

        for sess in sessions:
            info = self._read_session(sess)
            # 评分：正在播放=2，有标题=1，否则=0
            score = 0
            if info.available:
                score += 1
            if info.is_playing:
                score += 1
            if score > best_score:
                best_score = score
                best_session = sess
                best_info = info

        if best_info is None:
            best_info = MediaInfo()

        with self._lock:
            self._session = best_session
            self._media_info = best_info

        # 调试日志：首次检测到媒体源时记录
        if best_info.available and not self._logged_source:
            try:
                src = best_session.source_app_user_model_id
            except Exception:
                src = 'unknown'
            log.info('检测到媒体源: %s | %s - %s' % (src, best_info.title, best_info.artist))
            self._logged_source = True
        elif not best_info.available and self._logged_source:
            self._logged_source = False

        snapshot = best_info.copy()
        for cb in self._callbacks:
            try:
                cb(snapshot)
            except Exception:
                pass

    def _read_session(self, session):
        """读取单个 SMTC 会话的媒体信息，返回 MediaInfo 快照。"""
        info = MediaInfo()
        if not session:
            return info

        # 媒体属性（歌名/艺术家）
        try:
            props = session.try_get_media_properties_async().get()
            info.title = props.title or ''
            info.artist = props.artist or ''
        except Exception:
            pass

        # 播放状态
        try:
            playback = session.get_playback_info()
            status = playback.playback_status
            info.is_playing = (status == _PLAYING)
        except Exception:
            pass

        # 时间线（进度/总时长）
        # winrt 3.x: timeline.position / end_time 是 datetime.timedelta 对象，
        # 用 total_seconds() 获取秒数；旧版 winrt 2.x 用 .duration / 10_000_000
        try:
            timeline = session.get_timeline_properties()
            pos = timeline.position
            et = timeline.end_time
            # 优先用 timedelta.total_seconds()（winrt 3.x）
            if hasattr(pos, 'total_seconds'):
                info.position_sec = pos.total_seconds()
            elif hasattr(pos, 'duration'):
                info.position_sec = pos.duration / 10_000_000
            if hasattr(et, 'total_seconds'):
                info.duration_sec = et.total_seconds()
            elif hasattr(et, 'duration'):
                info.duration_sec = et.duration / 10_000_000
        except Exception as ex:
            log.warning('读取时间线失败: %s' % ex)

        # 有标题即视为有有效媒体源
        info.available = bool(info.title)
        return info

    # ---------- 媒体信息读取 ----------
    @property
    def media_info(self):
        """获取当前媒体信息快照（线程安全）。"""
        with self._lock:
            return self._media_info.copy()

    # ---------- 媒体控制 ----------
    def _run_async(self, func, error_msg):
        """在后台线程中执行 SMTC 异步操作（避免主线程 STA 错误）。"""
        def _do():
            try:
                with self._lock:
                    session = self._session
                if session:
                    func(session)
            except Exception as ex:
                log.warning('%s: %s' % (error_msg, ex))
        t = threading.Thread(target=_do, daemon=True)
        t.start()

    def play_pause(self):
        """播放 / 暂停切换。"""
        is_playing = self.media_info.is_playing
        def _do(session):
            if is_playing:
                session.try_pause_async().get()
            else:
                session.try_play_async().get()
        self._run_async(_do, '播放/暂停失败')

    def next_track(self):
        """下一曲。"""
        self._run_async(lambda s: s.try_skip_next_async().get(), '下一曲失败')

    def prev_track(self):
        """上一曲。"""
        self._run_async(lambda s: s.try_skip_previous_async().get(), '上一曲失败')

    def seek(self, position_sec):
        """跳转到指定播放位置（秒）。
        通过 SMTC 的 try_change_playback_position_async 实现。"""
        ticks = int(max(0.0, float(position_sec)) * 10_000_000)  # 秒 -> 100ns ticks
        self._run_async(lambda s: s.try_change_playback_position_async(ticks).get(),
                        'seek 失败')

    # ---------- 音量控制（pycaw，与 SMTC 解耦）----------
    def get_volume(self):
        """获取当前系统音量 (0.0-1.0)。"""
        if not self._volume:
            return 0.0
        try:
            return float(self._volume.GetMasterVolumeLevelScalar())
        except Exception:
            return 0.0

    def set_volume(self, level):
        """设置系统音量 (0.0-1.0)。"""
        if not self._volume:
            return
        try:
            level = max(0.0, min(1.0, float(level)))
            self._volume.SetMasterVolumeLevelScalar(level, None)
        except Exception as ex:
            log.warning('设置音量失败: %s' % ex)

    def is_muted(self):
        """是否静音。"""
        if not self._volume:
            return False
        try:
            return bool(self._volume.GetMute())
        except Exception:
            return False

    def toggle_mute(self):
        """切换静音状态。"""
        if not self._volume:
            return
        try:
            current = self._volume.GetMute()
            self._volume.SetMute(0 if current else 1, None)
        except Exception as ex:
            log.warning('切换静音失败: %s' % ex)


# 全局单例（懒加载）
_controller = None
_controller_lock = threading.Lock()


def get_controller():
    """获取全局 MusicController 单例。"""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = MusicController()
                _controller.start()
    return _controller
