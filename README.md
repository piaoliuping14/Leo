# Leo桌面宠物

> 简称 **Leo桌宠** —— 一个用 Python 写的桌面宠物狮子，会陪你工作、提醒你休息，还能一键打开常用网站与应用。

![icon](app-icon-lion-head.jpg)

## 功能特性

### 桌宠本体
- 透明窗口显示卡通狮子，闲时摇摆 / 漂浮 / 呼吸动画
- 单击弹出对话气泡（暖色调圆角 + 尾巴）
- 右键菜单：打开对话 / 回到右下角 / 退出（自定义样式）
- 闲置气泡：定时显示文案，可配置间隔时间
- 快捷指令：气泡内一键打开常用网站（默认「启动B站」）
- 时间查看：气泡内显示当前时间
- 任务栏无图标，不占用任务栏空间

### 管理软件
- 启动 / 停止桌宠
- 实时显示桌宠运行状态
- 快捷指令配置：增删改查 + 拖拽排序，增加需要一键打开的网站或应用，即时生效
- 昵称自定义：修改「小Leo」为任意昵称（最多 10 字）
- 闲置气泡间隔时间配置
- 设备绑定：配置修改仅本机保留，分享 / 重装自动恢复默认值

### 音乐盒（基于 Windows SMTC）
基于 Windows 系统媒体传输控制（SMTC）接口实现，**仅识别向外输出 SMTC 会话的播放器，不做任何播放器专项适配**。

- **媒体控制**：播放 / 暂停、上一曲、下一曲
- **进度展示**：实时显示歌曲播放进度与总时长，丝滑插值动画进度条
- **音量控制**：独立调用 Windows Core Audio API（pycaw），与 SMTC 完全解耦
- **媒体信息**：显示歌曲标题、艺术家、播放状态
- **智能降级**：
  - 无媒体会话时，控件置灰并显示「未检测到媒体源」
  - SMTC 未提供时长时（如部分第三方插件），进度条置灰并显示「暂未获取进度」
- **进度防抖**：采用「时间平滑锁定策略」，过滤 SMTC 采样回跳噪声（如 43→44→43 反复跳变），保证进度条平稳前进
- **兼容规则**：
  - 网易云音乐 PC 版、QQ 音乐 PC 版需用户自行安装第三方 SMTC 插件
  - 程序内部不做专项兼容处理
- **主题可定制**：所有颜色 / 尺寸 / 字体集中在 `music_theme.py`，标注 `# [THEME]`，方便后续「换主题」功能开发

## 下载使用

### 普通用户（免安装）
1. 前往 [Releases](../../releases) 下载最新版 zip
2. 解压到任意目录
3. 双击 `Leo桌宠.exe` 即可运行

> 无需安装 Python，开箱即用。

### 开发者（源码运行）
```bash
git clone https://github.com/piaoliuping14/Leo.git
cd Leo
pip install -r requirements.txt
python lion_manager.py
```

## 项目结构

```
Leo桌面宠物/
├── launcher.py            # 启动器（打包入口，支持热更新）
├── lion_manager.py        # 管理软件后端（pywebview + HTML）
├── lion_desktop.py        # 桌宠主体（tkinter 透明窗口 + 音乐盒气泡）
├── lion_watchdog.py       # 守护进程（异常退出自动重启）
├── music_box.py           # 音乐盒核心逻辑（SMTC 媒体控制 + pycaw 音量）
├── music_theme.py         # 音乐盒主题配置（# [THEME] 标记可配置项）
├── build.py               # 构建脚本（PyInstaller 打包）
├── build.spec             # PyInstaller 配置
├── manager_ui/
│   ├── app.html           # 管理界面（单页应用）
│   └── assets/            # 界面图片
├── katong/                # 桌宠狮子图片
├── design/
│   └── 文案.txt           # 闲置气泡文案
├── app-icon.ico           # 应用图标
├── app-icon-lion-head.jpg # 图标源图
├── requirements.txt       # Python 依赖
├── 启动狮子.bat           # 开发模式启动桌宠
└── 启动管理软件.bat       # 开发模式启动管理软件
```

## 运行时生成的文件

运行后会在 exe 同目录生成（不影响使用）：

```
├── config.json            # 用户配置（含设备绑定）
└── logs/
    ├── lion.log           # 运行日志
    └── lion_clean_exit.txt # 退出标记（临时文件）
```

## 自行打包

```bash
pip install pyinstaller
python build.py
```

产物输出到 `dist/Leo桌宠/`。

## 技术栈

- **Python 3.10+**
- **tkinter** —— 桌宠透明窗口与动画
- **pywebview** —— 管理软件界面（WebView2 后端）
- **Pillow** —— 图片处理与图标转换
- **PyInstaller** —— 打包为独立 exe
- **winrt** —— Windows Runtime API（SMTC 系统媒体传输控制）
- **pycaw** —— Windows Core Audio API（独立音量控制）

## 默认配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 快捷指令 | 启动B站 | 气泡内默认按钮 |
| 昵称 | 小Leo | 气泡问候语显示 |
| 闲置间隔 | 60 秒 | 闲置气泡触发时间 |
| 闲置气泡 | 开启 | 闲置时是否弹气泡 |

> 以上配置修改后仅保存在本机，分享软件或重装后恢复默认值。

## License

MIT
