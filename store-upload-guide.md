# Leo桌宠 — 上架微软商店操作指南（EXE 或 MSI 应用 路径）

> 代码层已就绪（`STORE_BUILD` 开关，commit `3206d0f`）。本文是 **EXE 路径** 上架操作。
>
> **EXE 路径 vs MSIX 路径**：
> - EXE：直接上传 `launcher.exe`（打 zip），Store 自动包装成 MSIX + 自动签名 + 自动验证。**不用 makeappx / 不用自签名 / 不用 AppxManifest.xml / 不用本地跑 WACK**。
> - MSIX：自己打包 + 签名 + WACK + manifest。完全控制但工程量大。
>
> 你的选择是 **EXE 路径**。下面按这条来。

---

## 0. 全局流程

```
注册开发者账号 → Partner Center 选「EXE 或 MSI 应用」创建应用
   → STORE_BUILD=1 构建 PyInstaller 产物
   → 把 dist/Leo桌宠/ 打成 zip（根目录是 launcher.exe）
   → （强烈建议）在 launcher 加 WebView2 Runtime 检测 + 引导
   → Partner Center 上传 zip + 截图/图标 + 定价/分级 → 提交审核
```

---

## 1. 注册开发者账号 + 创建应用

1. 打开 https://partner.microsoft.com ，用微软账号登录，注册「开发者」（一次性费用，约 ¥19 个人 / ¥299 组织）。
2. 「应用和游戏」→ 「**新產品**」→ 选 **「EXE 或 MSI 应用」**（不是游戏那两个）。
3. 完成创建，会拿到保留的**包名**（如 `12345.Leo`）和 **Publisher 字符串**。
   - EXE 路径下 Store 会自动塞这些进 manifest，**你不用手写 AppxManifest.xml**，但保留值最好记下，后续如需调试会用。

---

## 2. 构建 Store 版（STORE_BUILD=1）

PowerShell：
```powershell
$env:STORE_BUILD = "1"
python build.py
```

产物：`dist/Leo桌宠/`（含 `launcher.exe` + `app/` + `_internal/` + 一些 dll）。

> `STORE_BUILD=1` 让代码走 Store 分支（数据写 `%LOCALAPPDATA%\Leo桌宠`、跳过自更新）。**Store 包装后的安装目录也是只读**，不设必崩。

---

## 3. 打包 zip

EXE 路径要求上传一个 zip，**zip 根目录就是入口 exe**，不要嵌套一层 `Leo桌宠/`。

PowerShell：
```powershell
# 注意 -Path 用 \* 确保不嵌套外层目录
Compress-Archive -Path "dist\Leo桌宠\*" -DestinationPath "dist\Leo_x64.zip" -Force
```

或文件管理器手动 zip `dist\Leo桌宠\` 内全部内容。

产物：`Leo_x64.zip`（命名建议含版本和架构）。

---

## 4. WebView2 Runtime 引导（强烈建议加）

pywebview 的 `edgechrom` 后端需要 **WebView2 Runtime**。Win11 自带；旧 Win10 可能没有。EXE 路径下不能通过 manifest 声明依赖，必须在**应用层检测 + 引导**。

### 检测位置建议

加到 `launcher.py` 的 `main()` 开头（在 `check_and_update` 之前）或 `lion_manager.py` 启动 pywebview 之前。

### 检测 + 引导代码示例

```python
import sys
import ctypes
import subprocess
import winreg

def check_webview2():
    """检测 WebView2 Runtime 是否安装。"""
    # WebView2 Runtime 在注册表的 GUID = {F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}
    paths = [
        r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    ]
    for p in paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, p) as k:
                winreg.QueryValueEx(k, 'pv')  # 有 pv 值即已安装
            return True
        except FileNotFoundError:
            continue
        except Exception:
            pass
    return False

def ensure_webview2_or_prompt():
    """缺失 WebView2 时弹窗引导下载，用户确认后打开 Evergreen Bootstrapper。"""
    if check_webview2():
        return
    # 弹窗：MB_ICONINFORMATION(0x40) + MB_OKCANCEL(0x1)
    ret = ctypes.windll.user32.MessageBoxW(
        0,
        '本应用需要 WebView2 Runtime（Win10 旧版可能未自带）。\n'
        '点击「确定」将打开微软官方下载页，下载安装后再次启动本应用。',
        '需要 WebView2 Runtime',
        0x40 | 0x1,
    )
    if ret == 1:  # IDOK
        # Evergreen Bootstrapper 直链（微软官方）
        subprocess.Popen(['cmd', '/c', 'start', '', 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'])
    sys.exit(1)
```

调用（在 launcher.py `main()` 顶部）：
```python
ensure_webview2_or_prompt()
```

> 这段要不要我直接加到 `launcher.py`？给个回复我就动手（GitHub 版也受益——首次启动也能兜底）。

---

## 5. Partner Center 提交

1. Partner Center → 你的应用 → 「Start submission」。
2. **Packages（程序包）**：上传 `Leo_x64.zip`。
4. **Store listings（商店一览）**：
   - 名称、描述、简介、关键字
   - **应用图标**：300×300 PNG（用现有 `app-icon-lion-head.jpg` 缩放）
   - **截图**：至少 1 张，建议 1920×1080（桌宠主界面截图）
   - 系统要求、备注
5. **Pricing and availability**：免费或收费、可见市场。
6. **Age ratings**：填问卷（无 UGC/暴力/定位/网络聊天，通常 12+ 或更低）。
7. **Notes for certification**：写明「桌面桥 EXE 应用，需 WebView2 Runtime，已在首启引导安装」。
8. 提交审核（1–3 天）。

---

## 6. 本项目注意点

| 项 | 说明 |
|---|---|
| `STORE_BUILD=1` | 构建必设，否则数据写包目录只读会崩 |
| zip 根目录 | 必须直接是 `launcher.exe`，**不要嵌套** `Leo桌宠/` |
| 应用图标 | 用 `app-icon-lion-head.jpg` 缩放到 300×300 PNG |
| 截图 | 至少 1 张 1366×768+，建议 1920×1080 |
| WebView2 | 已在 launcher 加检测引导（见第 4 节） |
| 自更新 | Store 版已 `check_and_update` 首行 return，走商店更新 |
| 版本号 | Partner Center 每次提审递增版本号字段（不是代码） |

---

## 我能帮你做 / 需要你做

**需要你做**（只有你能做）：
1. 注册开发者账号 + 创建应用选「EXE 或 MSI 应用」
2. 准备截图（至少 1 张，应用主界面）
3. 拿到保留包名 / Publisher 截图给我（用于核对）

**我能帮你做**：
- 把 WebView2 检测引导代码加到 `launcher.py`（GitHub 版也受益）
- 从 `app-icon-lion-head.jpg` 生成 300×300 应用图标 PNG
- 写 `build_store.ps1` 一键脚本（设 STORE_BUILD=1 → build.py → 打包 zip）
- 帮你核对截图/图标尺寸

你给个回复，我就把上面这些落地。