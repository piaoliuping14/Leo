# Leo 桌宠 项目阶段总结

> 本文档面向后续接手开发的 AI / 工程师，目标是让接手者能在 10 分钟内理解项目全貌、架构约束与待办事项。
> 最后更新：2026-08-16

---

## 一、项目概述

**Leo 桌宠** 是一个用 Python 编写的 Windows 桌面宠物狮子，包含三个组成部分：

1. **桌宠本体**（`lion_desktop.py`）—— tkinter 透明窗口，狮子动画 + 多种气泡交互
2. **管理软件**（`lion_manager.py` + `manager_ui/app.html`）—— pywebview + HTML 单页应用，配置快捷指令 / 昵称 / 闲置间隔
3. **启动器**（`launcher.py` → `Leo桌宠.exe`）—— 打包入口，支持核心程序在线热更新

最新完成的功能是**音乐盒**（基于 Windows SMTC 系统媒体接口），通过桌宠主气泡的「音乐盒」按钮触发。

---

## 二、功能完成状态

### ✅ 已完成

| 模块 | 功能 | 状态 |
|------|------|------|
| 桌宠本体 | 透明窗口 / 狮子动画（摇摆、漂浮、呼吸） | ✅ |
| 桌宠本体 | 单击弹出对话气泡（暖色调圆角 + 尾巴） | ✅ |
| 桌宠本体 | 右键菜单（自定义样式，暖色方案） | ✅ |
| 桌宠本体 | 闲置气泡（定时显示文案，间隔可配） | ✅ |
| 桌宠本体 | 快捷指令气泡（3 列网格，拖拽排序） | ✅ |
| 桌宠本体 | 时间查看气泡 | ✅ |
| 桌宠本体 | 任务栏无图标（WS_EX_TOOLWINDOW） | ✅ |
| 管理软件 | 启动 / 停止 / 状态显示 | ✅ |
| 管理软件 | 快捷指令增删改查 + 拖拽排序 | ✅ |
| 管理软件 | 昵称自定义（最多 10 字） | ✅ |
| 管理软件 | 闲置间隔配置 | ✅ |
| 管理软件 | 设备绑定（配置仅本机保留） | ✅ |
| 音乐盒 | SMTC 媒体信息读取（标题/艺术家/进度/状态） | ✅ |
| 音乐盒 | 媒体控制（播放/暂停、上一曲、下一曲） | ✅ |
| 音乐盒 | 进度条（丝滑插值动画 + 防抖） | ✅ |
| 音乐盒 | 音量控制（pycaw，与 SMTC 解耦） | ✅ |
| 音乐盒 | 智能降级（无媒体源置灰、无时长显示提示） | ✅ |
| 音乐盒 | 主题可定制（music_theme.py 集中配置） | ✅ |
| 构建 | PyInstaller 打包 + 在线热更新 | ✅ |

### ⏸ 暂未实现

| 模块 | 功能 | 说明 |
|------|------|------|
| 音乐盒 | 歌词渲染 | SMTC 不提供歌词，需接入第三方歌词 API（如网易云歌词接口），暂不实现 |
| 桌宠 | 换主题功能 | 主题配置已就位（`music_theme.py` 的 `# [THEME]` 标记），UI 切换逻辑待开发 |

---

## 三、架构总览

### 模块职责

```
┌─────────────────────────────────────────────────────────┐
│  launcher.py (Leo桌宠.exe)                              │
│  - 打包入口，启动子进程                                  │
│  - 支持热更新：对比远程 version.json 的 SHA256          │
│  - 子进程通过 Leo桌宠.exe --run [module] 复用同一 exe   │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ lion_manager │ │ lion_desktop │ │lion_watchdog │
│  管理软件     │ │  桌宠主体     │ │  守护进程     │
│ (pywebview)  │ │ (tkinter)    │ │              │
└──────────────┘ └──────┬───────┘ └──────────────┘
                        │
                        ▼
                 ┌──────────────┐
                 │  music_box   │  ← SMTC 媒体控制 + pycaw 音量
                 │  (后台线程)   │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ music_theme  │  ← 主题配置（# [THEME] 标记）
                 └──────────────┘
```

### 关键类清单

| 文件 | 类 | 职责 |
|------|-----|------|
| `lion_desktop.py` | `LionPet` | 桌宠主体，管理窗口/动画/气泡/右键菜单 |
| `lion_desktop.py` | `BubbleWindow` | 通用气泡窗口（圆角 + 尾巴 + 关闭按钮） |
| `lion_desktop.py` | `IdleBubble` | 闲置气泡（定时显示文案） |
| `lion_desktop.py` | `MusicBubbleWindow` | **音乐盒气泡**（SMTC 媒体信息 + 控制界面） |
| `lion_desktop.py` | `_CanvasButton` | 无框 Canvas 按钮（用于音乐控制） |
| `lion_desktop.py` | `ContextMenu` | 自定义右键菜单 |
| `music_box.py` | `MusicController` | **音乐控制器**（后台轮询 SMTC + pycaw 音量） |
| `music_box.py` | `MediaInfo` | 媒体状态快照（线程安全只读） |
| `music_theme.py` | `MusicTheme` | **主题配置**（颜色/尺寸/字体，`# [THEME]` 标记） |

### 音乐盒数据流

```
[Windows 播放器] → SMTC → MusicController._poll_loop (后台线程, 1s 轮询)
                                        │
                                        ▼
                                _refresh() 读取会话
                                        │
                                        ▼
                                MediaInfo 快照
                                        │
                                        ▼
                          回调 _on_media_update() (在后台线程)
                                        │
                          【时间平滑锁定策略】
                          - 切歌/状态切换 → 重置锚点
                          - 稳定正向偏移 > 0.8s → 校准锚点
                          - 偏差 > 5s → 强制校准
                          - 回跳噪声 → 忽略
                                        │
                                        ▼
                                _pending_update = True
                                        │
                                        ▼
                          tick() (主线程, 每帧) 检测到 pending
                                        │
                          - 锚点 + elapsed 计算显示位置
                          - 插值平滑 pos += (target-pos)*dt*8
                                        │
                                        ▼
                                _refresh_progress() 重绘 UI
```

---

## 四、关键技术决策与原因

### 1. SMTC 而非逆向播放器

**决策**：仅使用 Windows SMTC 系统媒体接口，不针对网易云/QQ 音乐做专项适配。

**原因**：
- SMTC 是 Windows 官方标准接口，兼容所有合规播放器
- 逆向适配成本高、易失效（播放器更新即破坏）
- 网易云/QQ 音乐 PC 版需用户自行安装第三方 SMTC 插件，这是用户侧问题，不应在程序内处理

### 2. 音量控制与 SMTC 解耦

**决策**：音量控制独立使用 pycaw（Windows Core Audio API），不依赖 SMTC。

**原因**：
- SMTC 不提供音量控制接口
- pycaw 直接访问系统音量，与播放器无关
- 解耦后音量控制始终可用，即使 SMTC 无会话

### 3. 进度条「时间平滑锁定策略」

**决策**：进度显示值由 `tick()` 累加驱动（`anchor_pos + elapsed`），SMTC 回调仅在特定条件下校准锚点。

**原因**：
- SMTC 采样存在时序偏差，会出现 `43→44→43` 回跳噪声
- 直接用 SMTC 值刷新 UI 会导致进度条反复横跳
- 本地累加 + 锚点校准策略可保证进度条平稳前进，同时防止长期累积误差

**关键阈值**（定义在 `MusicBubbleWindow`）：
- `PROGRESS_DEBOUNCE = 0.8` —— SMTC 值需稳定前进超过此值才校准锚点
- `PROGRESS_MAX_DRIFT = 5.0` —— 偏差超过此值强制校准

### 4. SMTC 初始化必须在后台线程

**决策**：`_init_smtc()` 在 daemon 线程中执行 `request_async().get()`。

**原因**：winrt 的阻塞调用在主线程（STA）中会报错 `Cannot call blocking method from single-threaded apartment`。

### 5. SMTC 会话选择：`get_sessions()` 而非 `get_current_session()`

**决策**：遍历所有会话，按「正在播放 > 有标题 > 第一个」优先级选择。

**原因**：`get_current_session()` 只返回系统"当前选中"的会话，会漏掉网易云等非激活播放器。

### 6. 主题配置集中管理

**决策**：所有音乐盒 UI 的颜色/尺寸/字体集中在 `music_theme.py`，用 `# [THEME]` 标记。

**原因**：为后续「换主题」功能预留接口，换主题时只需替换配置值或加载不同主题文件，无需改动 `lion_desktop.py` 逻辑。

### 7. 进度条/音量条轨道左右内边距 = 滑块半径

**决策**：轨道从 `pad` 绘制到 `w - pad`，其中 `pad = thumb_radius`。

**原因**：避免首尾滑块被界面裁切。

### 8. 退出流程优先关闭窗口

**决策**：退出时先写退出标记 → 立即关窗 → 后台异步 kill 子进程。

**原因**：同步 `stop_pet()` 会导致明显卡顿，影响用户体验。

---

## 五、重要约束（不可违反）

### 命名与文件

- 所有 `whale` 相关命名必须改为 `lion`
- 日志文件名必须为 `lion.log`（不是 `lion_error.log`），存放在 `logs/` 目录
- 软件名称必须为 `Leo桌宠`，图标为 `app-icon.ico`

### 进程与窗口

- 子进程调用必须包含 `creationflags=subprocess.CREATE_NO_WINDOW`（防止黑窗闪烁）
- 桌宠窗口必须用 `WS_EX_TOOLWINDOW` 样式（隐藏任务栏图标）
- DPI 感知必须设为 `PER_MONITOR_AWARE`（`SetProcessDpiAwareness(2)`）
- WebView2 窗口必须 `hidden=True` 创建，`init()` 完成后通过 `page_loaded()` 回调显示
- HTML 必须包含 no-cache meta 标签

### UI 与布局

- UI 不得出现垂直滚动条；body 和主容器固定 720px 高度，`overflow:hidden`
- 昵称输入最多 10 字，输入框宽度自适应内容
- UI 元素必须视觉居中（狮子图片在框内居中、昵称文字在白色框上方居中）
- 气泡使用暖色方案：背景 `#FFF8E8`，暖灰棕边框，浅橙按钮
- 无按钮气泡（时间、音乐盒）宽度 +24px，防止关闭按钮遮挡文字
- 闲置气泡固定宽度 140-160px 以实现文字自动换行

### 音乐盒

- 仅识别向外输出 SMTC 会话的播放器，不做播放器专项适配
- 音量控制必须独立调用 Windows Core Audio API，与 SMTC 完全解耦
- 无媒体源时，音乐控件按钮必须置灰并显示「未检测到媒体源」
- SMTC 未提供时长时，进度条置灰并显示「暂未获取进度」（不是「直播模式」）
- 暂停状态下进度条完全静止；切歌失败不干扰当前进度
- 播放/暂停切换时必须重置 `_last_smtc_pos`，避免误判停滞
- 主题配置必须集中在 `music_theme.py`，用 `# [THEME]` 标记

### 配置与更新

- 默认配置（仅「启动B站」快捷指令、「小Leo」昵称、默认时间间隔）在分享/重装时恢复
- 用户配置修改仅保存在本机（设备绑定）
- `config.json` 在更新时不得被覆盖
- 核心程序（`app/` 目录）可在线更新；启动器（`Leo桌宠.exe`）很少重新打包
- 更新检查对比远程 `version.json` 与本地文件的 SHA256 哈希

---

## 六、依赖与环境

### Python 依赖（`requirements.txt`）

```
Pillow>=8.2.0
pywebview>=5.0
winrt-runtime>=2.0
winrt-Windows.Foundation>=2.0
winrt-Windows.Foundation.Collections>=2.0
winrt-Windows.Media>=2.0
winrt-Windows.Media.Control>=2.0
winrt-Windows.Storage.Streams>=2.0
pycaw>=20230407
```

### 开发模式依赖安装

winrt 和 pycaw 需安装在 `_libs` 目录并加入 `sys.path`：

```bash
pip install --target=_libs winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media winrt-Windows.Media.Control winrt-Windows.Storage.Streams pycaw
```

> **注意**：winrt 按命名空间拆分包，每个子模块需单独安装。`--target` 安装可能导致命名空间包 `__init__.py` 被覆盖，需删除并重装所有 winrt 子包。

---

## 七、构建与打包

### 构建流程

```bash
pip install pyinstaller
python build.py
```

`build.py` 执行三步：
1. PyInstaller 打包 `launcher.py` → `Leo桌宠.exe`
2. 复制核心程序到 `dist/Leo桌宠/app/`
3. 扫描 `app/` 生成 `version.json`（文件清单 + SHA256）

### 目录结构（打包后）

```
dist/Leo桌宠/
├── Leo桌宠.exe          # 启动器（EXE_DIR，存用户文件）
│   ├── config.json      # 用户配置
│   └── logs/
│       ├── lion.log
│       └── lion_clean_exit.txt
└── app/                 # 核心程序（APP_DIR，可在线更新）
    ├── lion_manager.py
    ├── lion_desktop.py
    ├── lion_watchdog.py
    ├── music_box.py
    ├── music_theme.py
    ├── manager_ui/
    ├── katong/
    ├── design/
    └── version.json
```

### 已知打包注意事项

- `build.py` 的 `APP_FILES` 已包含 `music_theme.py` 和 `music_box.py`
- `build.spec` 需包含 winrt 和 pycaw 的 hidden imports
- **修改源文件必须在 `d:\deepseek\test\` 下进行**，`dist\Leo桌宠\app\` 下的修改会被重新打包覆盖

---

## 八、调试与排错

### 日志位置

`logs/lion.log`（exe 同目录的 `logs/` 下）

### 常见问题与解决方案

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `No module named 'winrt.windows.foundation'` | winrt 子包未完整安装 | 重装所有 winrt 子包（见上文） |
| `'AudioDevice' object has no attribute 'Activate'` | pycaw 2025+ API 变更 | 使用 `AudioDevice.EndpointVolume` 属性，代码已兼容 |
| SMTC 初始化失败（STA 错误） | 主线程调用阻塞方法 | 在后台 daemon 线程执行（代码已处理） |
| 进度条 43→44→43 反复跳变 | SMTC 采样时序偏差 | 时间平滑锁定策略（已实现） |
| 网易云/QQ 音乐未识别 | 未安装第三方 SMTC 插件 | 用户侧安装插件，程序内不处理 |
| 端口 52719 占用无法重开 | `webview.start()` + `stop_pet()` 端口未释放 | 已改用异步退出 |
| 桌宠窗口黑边/坐标偏移 | DPI 不一致 | `SetProcessDpiAwareness(2)` |
| WebView2 缓存旧 HTML | 浏览器缓存 | HTML 加 no-cache meta |

### 音乐盒冒烟测试

`LionPet.__init__` 末尾有冒烟测试代码（`self._show_music_bubble()`），可用于快速验证音乐盒功能。正式发布前需注释或移除。

---

## 九、未来规划

### 短期

- [ ] 实现歌词渲染（接入第三方歌词 API，SMTC 不提供歌词）
- [ ] 开发「换主题」功能（主题配置已就位，需实现 UI 切换逻辑）
- [ ] 音乐盒气泡支持拖动跟随（目前依赖通用 BubbleWindow 的拖动逻辑）

### 中期

- [ ] 更多闲置动画（当前为摇摆/漂浮/呼吸）
- [ ] 桌宠互动反馈（点击不同部位不同反应）
- [ ] 管理软件界面主题切换

### 长期

- [ ] 跨平台支持（当前仅 Windows）
- [ ] 插件系统（允许第三方扩展功能）

---

## 十、接手者快速上手清单

1. **环境准备**
   ```bash
   git clone <repo>
   cd Leo
   pip install -r requirements.txt
   pip install --target=_libs winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media winrt-Windows.Media.Control winrt-Windows.Storage.Streams pycaw
   ```

2. **开发模式运行**
   - 桌宠：`启动狮子.bat` 或 `python lion_desktop.py`
   - 管理软件：`启动管理软件.bat` 或 `python lion_manager.py`

3. **必读文件**（按优先级）
   - `SUMMARY.md`（本文档）—— 全局认知
   - `music_theme.py` —— 主题配置，`# [THEME]` 标记
   - `music_box.py` —— SMTC + pycaw 核心逻辑
   - `lion_desktop.py` 的 `MusicBubbleWindow` 类 —— 音乐盒 UI 与防抖逻辑
   - `build.py` —— 打包流程

4. **关键约束速查**
   - 命名：`lion`（不是 `whale`）
   - 日志：`logs/lion.log`
   - 退出：先关窗后 kill 子进程
   - 修改源文件在 `d:\deepseek\test\`，不在 `dist\`
   - 配置不覆盖：`config.json` 更新时保留

5. **验证音乐盒功能**
   - 启动任意支持 SMTC 的播放器（如 Windows Media Player、Chrome 播放视频）
   - 运行桌宠，单击狮子 → 点「音乐盒」按钮
   - 检查 `logs/lion.log` 是否有「检测到媒体源」日志

---

## 十一、文件职责速查表

| 文件 | 行数（约） | 职责 |
|------|-----------|------|
| `launcher.py` | ~100 | 启动器入口，热更新逻辑 |
| `lion_manager.py` | ~500 | 管理软件后端（pywebview API） |
| `lion_desktop.py` | ~2000 | 桌宠主体（窗口/动画/气泡/音乐盒UI） |
| `lion_watchdog.py` | ~100 | 守护进程 |
| `music_box.py` | ~450 | SMTC 媒体控制 + pycaw 音量 |
| `music_theme.py` | ~90 | 音乐盒主题配置 |
| `manager_ui/app.html` | ~800 | 管理界面单页应用 |
| `build.py` | ~120 | 构建脚本 |
| `build.spec` | ~50 | PyInstaller 配置 |

---

**文档结束。如有疑问，请先查阅 `logs/lion.log` 排错，或参考「关键技术决策」章节理解设计意图。**
