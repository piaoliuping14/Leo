# 快捷指令模块改动说明（交付文档 / 供其他 AI 快速理解）

> 仓库：Leo 桌宠（Windows 桌宠 + 管理软件，pywebview + Python）
> 覆盖改动：① 快捷指令初始化逻辑优化 + 拖拽重排序　② 快捷指令配置页 UI 布局修复
> 关键文件：`lion_manager.py`、`lion_desktop.py`、`manager_ui/app.html`
> 阅读方式：先看 0 / 3，需要改代码再回看 1 / 2 的函数定位。

---

## 0. TL;DR（30 秒速览）

- **初始化**：首次运行自动写入含「启动B站」的默认指令；用 Windows `MachineGuid` 做设备绑定，换机/被分享时重置指令；用户清空得到空列表 `[]` 是**合法值**，不再回退默认。
- **空指令态**：桌宠气泡显示「请从配置当中添加指令~」，**不展示也不执行**任何指令按钮。
- **拖拽**：从「自由拖拽」改为「列表内重排序」——实时显示插入位置指示线，拖拽被限制在列表区域内，仅落点变化才写回 `save_commands`。
- **UI 修复**：pywebview 窗口高 720 含标题栏，但页面硬编码 `height:720px`，底部约 30px 被裁，配置页贴底的「取消/保存」按钮显示不全。修复为按真实客户区高度（`100%`），并取消表单「固定底部」，改为列表区与表单区各自独立滚动，表单区 `max-height:60%` 超高才滚（约 4:6 分栏）。

---

## 1. 改动一：快捷指令初始化逻辑 + 拖拽重排序

### 1.1 默认指令与设备绑定
- 默认指令常量（两处必须保持一致）：
  - `lion_manager.py:46` `DEFAULT_COMMANDS = [{'name':'启动B站','type':'url','target':'https://www.bilibili.com/','icon':'play'}]`
  - `lion_desktop.py:66` 同样的 `DEFAULT_COMMANDS`（桌宠侧回退用）。
- 设备绑定入口 `_ensure_device_config()`（`lion_manager.py:64`）：
  - `config.json` 不存在 → 首次运行，创建配置（默认指令 + `idle_bubble_enabled=True` + `idle_timeout=60` + `nickname='小Leo'` + `machine_id=<MachineGuid>`）。
  - `machine_id` 缺失 → 补写当前机器 ID。
  - `machine_id` 不匹配（换设备/被分享）→ **重置** `commands`/`idle_timeout=60`/`nickname='小Leo'`，更新 `machine_id`。
  - `machine_id` 匹配 → 不处理。
- 「默认指令仅首次生成」由以上逻辑保证：之后用户增删的指令会被持久化，**不会**因重开再被默认指令覆盖（设备不变时）。

### 1.2 空指令处理（关键边界）
- `load_commands()`（`lion_desktop.py:71`）：读取 `config.json` 的 `commands`；若字段为 `None` 或文件异常才回退默认。**空列表 `[]` 直接返回，不回退**——这是「清空全部指令」与「首次运行」的区别。
- 气泡展示 `_show_commands_bubble()`（`lion_desktop.py:1880`）：
  - `not self.commands`（空）→ `bubble.set_content('请从配置当中添加指令~', [], None)`，**无按钮、不执行**。
  - 非空 → 列出指令名，按钮回调 `_on_cmd_btn_click` → `_execute_command(idx)`。

### 1.3 拖拽：自由拖 → 列表内重排序
- 实现位于 `manager_ui/app.html` 的 `<script>`（`startDrag` / `onDragMove` / `onDragEnd`）：
  - 仅由条目左侧 grip 手柄（`[data-grip]`）发起 `mousedown`，点击条目其余区域进入编辑。
  - 拖动时创建 **ghost 克隆**跟随鼠标；插入位置用一条 `drag-indicator`（3px 主色线）**实时预览**。
  - **限制在列表区域内**：ghost 的 top 被夹在 `listRect.top ~ listRect.bottom - ghostH` 之间（`onDragMove`）。
  - 落点：`onDragEnd` 中仅当 `targetIdx !== idx`（顺序真的变化）才 `commands.splice` 重排并 `save_commands`，避免无谓写盘与重渲染闪烁。

---

## 2. 改动二：快捷指令配置页 UI 布局修复

### 2.1 根因
- `lion_manager.py:468` 创建窗口 `webview.create_window(..., width=440, height=720)`，该 `720` 是**含 Windows 标题栏**的总高，Webview 真实客户区 ≈ 689px。
- 但 `manager_ui/app.html` 多处硬编码 `height:720px`，且 `body { overflow:hidden }`，导致底部约 30px 被裁。
- 主页/设置页内容靠上或居中"侥幸"无碍；唯独快捷指令页的表单被 `flex` 的 `shrink-0` 钉在 720px 列最底部，取消/保存按钮正好落在被裁区 → 显示不全。

### 2.2 修复方案（仅改 `manager_ui/app.html`，逻辑不动）
- 让布局贴合真实客户区：新增 `html, body { height: 100%; }`，并把 5 处 `720px` 改为 `100%`（`body`、`#view-home`、主页内容容器、`.view-scroll`、`#view-commands.active`）。
- 取消表单「固定底部」思路：
  - 新增 CSS `.form-region { max-height: 60%; overflow-y: auto; overflow-x: hidden; }`（`app.html` 约 `:86`）。
  - 表单 wrapper 去掉 `shrink-0`，挂上 `form-region` 类（`app.html` 约 `:178`）——表单不再钉底，随内容流排列；**仅当内容超过 60% 时才在内部滚动**。
  - 列表区 `.cmd-scroll` 保持 `flex:1` 不变 → 表单占满 60% 上限时，列表自然剩约 40%，近似 4:6；两区各自独立滚动、互不联动。
- 表单底部留白 `pb-6 pt-2` → `pb-8 pt-3`（底部安全区 24→32px，更透气）。

### 2.3 已知小坑（非本次 bug，供维护者留意）
- 表单自然高度约 470px > 60% 上限（≈413px），打开表单时其内部会有一道**小幅滚动条**，取消/保存可能需要轻滚一下才完全露出。可调大 `.form-region` 的 `60%`（如 `70%`）缓解。
- `config.json` 中某 app 指令 `target:"QuarkClouddrive_..."` 缺 `!App` 后缀，`_launch_app` 按 AUMID 解析会**静默失败**（点了没反应）。属另一潜在 bug，本次未改。

---

## 3. 涉及文件清单

| 文件 | 改动点 |
|---|---|
| `lion_manager.py` | `DEFAULT_COMMANDS`(:46)、`_ensure_device_config`(:64 设备绑定/重置)、`get_commands`/`save_commands`(:256/:266) |
| `lion_desktop.py` | `DEFAULT_COMMANDS`(:66)、`load_commands`(:71 空列表合法)、`_show_commands_bubble`(:1880 空态提示) |
| `manager_ui/app.html` | `html,body{height:100%}` + 5 处 `720px→100%`、`.form-region` 样式、表单 wrapper 去 `shrink-0`、`startDrag/onDragMove/onDragEnd` 列表内重排序 |

---

## 4. 提交信息（git commit）

**主题（一行）**
```
feat(ui): 优化快捷指令初始化与拖拽重排，并修复配置页底部按钮被遮挡
```

**正文**
```
快捷指令初始化与拖拽（lion_manager.py / lion_desktop.py）：
- 首次运行自动生成含「启动B站」的默认指令；基于 MachineGuid 设备绑定，
  换设备/被分享时重置指令；空列表 [] 为合法值，不再回退默认
- 空指令时气泡显示「请从配置当中添加指令~」且不展示/执行任何按钮
- 拖拽由自由拖拽改为列表内重排序：实时预览插入位置、限制在列表区域内，
  仅落点变化才写回 save_commands

快捷指令配置页 UI 修复（manager_ui/app.html）：
- 根因：pywebview 窗口高 720 含标题栏，但页面硬编码 height:720px 且 body
  overflow:hidden，底部约 30px 被裁，贴底按钮显示不全
- 页面改按真实客户区高度（html,body 及视图 height:100%）
- 取消表单「固定底部」，列表区与表单区各自独立滚动；表单区 max-height:60%
  超高才滚，上下约 4:6 分栏；底部留白 pb-6 pt-2 → pb-8 pt-3
```

**提交建议**：仅 `git add` 上述三个文件（勿带 `build/`、`dist/`、`__pycache__/`、`.workbuddy/`）。

---

## 5. 给后续 AI / 维护者的快速定位提示

- 改默认指令 → 同步改 `lion_manager.py:46` 与 `lion_desktop.py:66` 两处 `DEFAULT_COMMANDS`。
- 改「空指令提示文案」→ `lion_desktop.py:1885` 字符串。
- 改拖拽手感（手柄、指示线、约束）→ `app.html` 的 `startDrag`/`onDragMove`/`onDragEnd`。
- 改配置页分栏比例/底部留白 → `app.html` 的 `.form-region` 与表单 wrapper 的 `pb-8 pt-3`。
- 再出现「底部被裁」类问题 → 优先检查是否有新加的 `height:720px` 或新的 `overflow:hidden` 固定区。
