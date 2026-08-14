# ============================================================
#  桌面小助手 (Desktop Pet)
#  显示在桌面上的悬浮宠物（狮子）：可拖拽（拖拽时摇摆）、
#  单击弹出聊天气泡。
#  图片: katong/lion_crop.png (由 狮子.png flood-fill 抠图得到，见 process_lion.ps1)
#
#  用法:
#     powershell -NoProfile -ExecutionPolicy Bypass -File lion_desktop.ps1
#   或直接双击 启动狮子.bat
# ============================================================
param(
  [double]$Scale = 0.07,            # 显示缩放（狮子 1833x1731，0.07 ≈ 128x121）
  [string]$BubbleText = 'Hello，Fangjizhong，有什么可以帮您的？',
  [switch]$Test                     # 冒烟测试：创建界面后自动退出
)
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# 界面线程上的任何异常只写入日志，不再弹出"未处理异常"对话框
try {
  [System.Windows.Forms.Application]::SetUnhandledExceptionMode([System.Windows.Forms.UnhandledExceptionMode]::CatchException)
  [System.Windows.Forms.Application]::Add_ThreadException({
    param($s, $e)
    try { Write-Log ("UI线程异常: " + $e.Exception.ToString()) } catch {}
  })
} catch {}

$script:Dir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$script:ImgPath = Join-Path $script:Dir 'katong\lion_crop.png'
$script:LogPath = Join-Path $script:Dir 'lion_error.log'

function Write-Log($msg) {
  try { Add-Content -Path $script:LogPath -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg) -Encoding UTF8 } catch {}
}

try {

  # ---------- C# 辅助: 双缓冲窗体 + 旋转渲染器（消除绘制闪烁与紫边） ----------
  $csharp = @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public class LionForm : System.Windows.Forms.Form {
    public LionForm() {
        this.SetStyle(
            System.Windows.Forms.ControlStyles.OptimizedDoubleBuffer |
            System.Windows.Forms.ControlStyles.AllPaintingInWmPaint |
            System.Windows.Forms.ControlStyles.UserPaint |
            System.Windows.Forms.ControlStyles.ResizeRedraw, true);
        this.UpdateStyles();
    }
}

public static class LionRenderer
{
    // 在窗体大小的画布上绘制角色（狮子），然后逐像素处理：
    // 边缘混色按黑色背景反推（见下方循环），并把 alpha 硬化成 0/255。
    // 旋转支点在底部中心：站立角色左右摆动时双脚不动，更像活物。
    public static Bitmap Render(Bitmap src, int w, int h, int pad, float angle, float bob, float breath)
    {
        Bitmap bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
        using (Graphics g = Graphics.FromImage(bmp))
        {
            // 透明（黑）画布：边缘插值把狮子与黑色混合，且 GDI+ 存的是"直通 alpha"
            // （边缘像素保留前景色 + 部分透明度）。下方再把 alpha 硬化成硬遮罩即可。
            // 切忌用洋红清屏——那会让边缘与洋红合成出紫色毛边（旧版 bug）。
            g.Clear(Color.Transparent);
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            float cx = w / 2f;
            float cy = pad + src.Height * (1f - 0.12f) + bob;   // 底部支点
            float s = 1f + breath * 0.015f;                     // 呼吸缩放（±1.5%）
            g.TranslateTransform(cx, cy);
            g.RotateTransform(angle);
            g.ScaleTransform(s, s);
            g.TranslateTransform(-cx, -cy);
            g.DrawImage(src, pad, pad, src.Width, src.Height);
        }

        Rectangle rect = new Rectangle(0, 0, w, h);
        BitmapData bd = bmp.LockBits(rect, ImageLockMode.ReadWrite, PixelFormat.Format32bppArgb);
        byte[] px = new byte[w * h * 4];
        Marshal.Copy(bd.Scan0, px, 0, px.Length);
        // 硬遮罩：alpha<128 -> 全透明(RGB 清零)；否则保留"已是直通"的前景色，alpha 置 255。
        // 不要做反预乘除法：Format32bppArgb 存的是直通颜色，边缘像素颜色本就正确，
        // 除法反而会把边缘洗白。这样得到 0/255 硬遮罩，无紫边/灰边。
        for (int i = 0; i < px.Length; i += 4)
        {
            int a = px[i + 3];
            if (a < 128) { px[i] = 0; px[i + 1] = 0; px[i + 2] = 0; px[i + 3] = 0; }
            else { px[i + 3] = 255; }
        }
        Marshal.Copy(px, 0, bd.Scan0, px.Length);
        bmp.UnlockBits(bd);
        return bmp;
    }
}
'@
  Add-Type -TypeDefinition $csharp -ReferencedAssemblies System.Windows.Forms, System.Drawing

  # ---------- 加载狮子图片并缩放到显示尺寸 ----------
  if (-not (Test-Path $script:ImgPath)) { throw "找不到图片文件: $($script:ImgPath)" }
  $src = [System.Drawing.Image]::FromFile($script:ImgPath)
  $baseW = [int]($src.Width * $Scale)
  $baseH = [int]($src.Height * $Scale)
  $base = [System.Drawing.Bitmap]::new($baseW, $baseH, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($base)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.DrawImage($src, 0, 0, $baseW, $baseH)
  $g.Dispose()
  $src.Dispose()

  # 缩放插值在边缘产生半透明像素（直通 alpha，颜色已是正确的前景色）。
  # 硬化为硬遮罩：alpha<128 -> 透明(RGB 清零)，否则保留颜色并把 alpha 置 255。
  # 不要做反预乘除法（Format32bppArgb 存的是直通颜色，除法会把边缘洗白）。
  $rectB = [System.Drawing.Rectangle]::new(0, 0, $baseW, $baseH)
  $bdB = $base.LockBits($rectB, [System.Drawing.Imaging.ImageLockMode]::ReadWrite, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $lenB = $baseW * $baseH * 4
  $pxB = New-Object byte[] $lenB
  [System.Runtime.InteropServices.Marshal]::Copy($bdB.Scan0, $pxB, 0, $lenB)
  for ($ib = 0; $ib -lt $lenB; $ib += 4) {
    $aB = $pxB[$ib + 3]
    if ($aB -lt 128) {
      $pxB[$ib] = 0; $pxB[$ib + 1] = 0; $pxB[$ib + 2] = 0; $pxB[$ib + 3] = 0
    } else {
      $pxB[$ib + 3] = 255
    }
  }
  [System.Runtime.InteropServices.Marshal]::Copy($pxB, 0, $bdB.Scan0, $lenB)
  $base.UnlockBits($bdB)
  Write-Log ("startup: lion v4, base=" + $baseW + "x" + $baseH + ", hard matte, no purple edges")

  $Pad = 26                                  # 四周留白（容纳摇摆/弹跳不裁切）
  $script:FW = $baseW + 2 * $Pad
  $script:FH = $baseH + 2 * $Pad
  $key = [System.Drawing.Color]::Magenta     # 透明键（已确认图中无此颜色）

  # ---------- 狮子窗体 ----------
  $lionForm = New-Object LionForm
  $lionForm.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
  $lionForm.StartPosition   = [System.Windows.Forms.FormStartPosition]::Manual
  $lionForm.ShowInTaskbar   = $false
  $lionForm.TopMost         = $true
  $lionForm.BackColor       = $key
  $lionForm.TransparencyKey = $key
  $lionForm.Size            = [System.Drawing.Size]::new($script:FW, $script:FH)

  # ---------- 动画状态 ----------
  $script:Time = 0.0
  $script:Bob = 0.0; $script:Angle = 0.0; $script:Lean = 0.0; $script:LeanTarget = 0.0
  $script:Breath = 0.0
  $script:WagPhase = 0.0; $script:WagFreq = 3.0
  $script:Dragging = $false; $script:Down = $false
  $script:BaseX = 0; $script:BaseY = 0
  $script:DownScreenX = 0; $script:DownScreenY = 0
  $script:LastScreenX = 0; $script:LastScreenY = 0
  $script:HopT = 0.0
  $script:X = 0; $script:Y = 0
  $script:BubbleOpen = $false; $script:Fade = 0.0
  $script:DragLogged = $false

  $wa0 = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  $script:X = $wa0.Width  - $script:FW - 20
  $script:Y = $wa0.Height - $script:FH - 16

  # ---------- 绘制：旋转支点在角色底部（站立摆动像活物） ----------
  # 渲染器每次渲染一帧到画布再贴上窗体，顺带反推边缘混色；帧缓存避免无谓重建。
  $script:LastFrameKey = ''
  $script:LastFrame = $null
  $lionForm.Add_Paint({
    param($s, $e)
    $k = $script:Angle.ToString('0.000') + '|' + $script:Bob.ToString('0.000') + '|' + $script:Breath.ToString('0.000')
    if ($k -ne $script:LastFrameKey -or $null -eq $script:LastFrame) {
      if ($null -ne $script:LastFrame) { $script:LastFrame.Dispose() }
      $script:LastFrame = [LionRenderer]::Render($base, $script:FW, $script:FH, $Pad, [single]$script:Angle, [single]$script:Bob, [single]$script:Breath)
      $script:LastFrameKey = $k
    }
    $e.Graphics.Clear($key)
    # 1:1 整数 blit + NearestNeighbor：硬遮罩边缘不会与洋红透明键混色插值，杜绝紫边
    $e.Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $e.Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $e.Graphics.DrawImage($script:LastFrame, 0, 0)
  })

  # ---------- 鼠标：按下 -> 拖动 / 点击 ----------
  $lionForm.Add_MouseDown({
    param($s, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
      $script:Down = $true
      $script:Dragging = $false
      $script:BaseX = $script:X; $script:BaseY = $script:Y
      $pt = $lionForm.PointToScreen([System.Drawing.Point]::new($e.X, $e.Y))
      $script:DownScreenX = $pt.X; $script:DownScreenY = $pt.Y
      $script:LastScreenX = $pt.X; $script:LastScreenY = $pt.Y
      $lionForm.Capture = $true
      $lionForm.Cursor = [System.Windows.Forms.Cursors]::SizeAll
    }
  })
  $lionForm.Add_MouseMove({
    param($s, $e)
    if (-not $script:Down) { return }
    # 用屏幕坐标计算位移：窗体跟随鼠标移动后，相对窗体坐标会被"拉回"，
    # 造成 dx/dy 低估甚至反向（拖动抖动/跟不上的根因）。屏幕坐标无此自反馈。
    $scr = $lionForm.PointToScreen([System.Drawing.Point]::new($e.X, $e.Y))
    $dx = $scr.X - $script:DownScreenX
    $dy = $scr.Y - $script:DownScreenY
    # 超过 5px 视为拖动而不是点击
    if (-not $script:Dragging -and [math]::Sqrt($dx * $dx + $dy * $dy) -gt 5) {
      $script:Dragging = $true
      $script:WagPhase = 0.0
    }
    if ($script:Dragging) {
      $waM = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
      $script:X = [math]::Max(4, [math]::Min($waM.Width  - $script:FW - 4, $script:BaseX + $dx))
      $script:Y = [math]::Max(4, [math]::Min($waM.Height - $script:FH - 4, $script:BaseY + $dy))
      # 动态倾斜：平滑跟随移动方向；摇晃频率随速度轻微变化（幅度小、不抖动）
      $lx = $scr.X - $script:LastScreenX; $ly = $scr.Y - $script:LastScreenY
      $script:LeanTarget = [math]::Max(-5.0, [math]::Min(5.0, $lx * 0.8))
      $spd = [math]::Sqrt($lx * $lx + $ly * $ly)
      $script:WagFreq = [math]::Max(1.2, [math]::Min(2.4, 1.2 + $spd * 0.01))
      if (-not $script:DragLogged) {
        $script:DragLogged = $true
        Write-Log ("drag: freq=" + [math]::Round($script:WagFreq, 2) + "Hz, amp=1.6deg")
      }
      $script:LastScreenX = $scr.X; $script:LastScreenY = $scr.Y
      $lionForm.Location = [System.Drawing.Point]::new([int]$script:X, [int]$script:Y)
      if ($script:BubbleOpen) { Position-Bubble }
    }
  })
  $lionForm.Add_MouseUp({
    param($s, $e)
    if ($e.Button -ne [System.Windows.Forms.MouseButtons]::Left) { return }
    if (-not $script:Down) { return }
    $wasDrag = $script:Dragging
    $script:Down = $false
    $script:Dragging = $false
    $script:Lean = 0.0
    $script:LeanTarget = 0.0
    $script:DragLogged = $false
    $lionForm.Capture = $false
    $lionForm.Cursor = [System.Windows.Forms.Cursors]::Default
    if (-not $wasDrag) { Toggle-Bubble }   # 未拖动 = 单击 -> 聊天气泡
  })

  # ---------- 聊天气泡 ----------
  $bubble = New-Object System.Windows.Forms.Form
  $bubble.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
  $bubble.ShowInTaskbar = $false
  $bubble.TopMost = $true
  $bubble.BackColor = [System.Drawing.Color]::FromArgb(252, 252, 254)   # 极浅冷白，比纯白更柔和
  $bubble.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual

  # 气泡/按钮配色（全部 script 作用域，供事件回调读取）
  $script:BubBg     = $bubble.BackColor
  $script:BubBorder = [System.Drawing.Color]::FromArgb(214, 221, 234)
  $script:BubText   = [System.Drawing.Color]::FromArgb(34, 48, 70)
  $script:BtnFont   = [System.Drawing.Font]::new('Microsoft YaHei UI', 8.5)
  $script:BtnTexts  = @('启动Claude', '启动ChatGPT', '启动B站')
  $script:BtnHover  = @($false, $false, $false)
  $script:Buttons   = @()
  $script:TailAllow = 14                 # 气泡尾巴预留宽度：尾巴整体收入窗口，杜绝被边界裁切
  $script:BtnBase   = [System.Drawing.Color]::FromArgb(244, 246, 251)
  $script:BtnHoverBg= [System.Drawing.Color]::FromArgb(224, 234, 252)
  $script:BtnBorder = [System.Drawing.Color]::FromArgb(204, 214, 233)
  $script:BtnTextC  = [System.Drawing.Color]::FromArgb(46, 64, 92)
  $script:BtnTextHv = [System.Drawing.Color]::FromArgb(26, 86, 170)
  $script:CloseHover = $false
  $script:CloseFont = [System.Drawing.Font]::new('Microsoft YaHei UI', 9, [System.Drawing.FontStyle]::Bold)

  $lab = New-Object System.Windows.Forms.Label
  $lab.Text = $BubbleText
  $lab.Font = [System.Drawing.Font]::new('Microsoft YaHei UI', 9.5)
  $lab.ForeColor = $script:BubText
  $lab.BackColor = $script:BubBg
  $lab.AutoSize = $true
  # 不设 MaximumSize：文字单行显示不折行；气泡宽度随内容自适应
  $psize = $lab.PreferredSize

  # 圆角矩形路径工具
  function New-RoundedPath($x, $y, $w, $h, $r) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = 2 * $r
    $path.AddArc($x, $y, $d, $d, 180, 90)
    $path.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $path.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $path.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
  }

  # 气泡外形路径：圆角矩形 + 侧边尾巴，整体收入窗口内（Region 与描边共用同一路径）。
  # bodyX 随尾巴方向变化：尾巴在右时 bodyX=0；尾巴在左时 bodyX=TailAllow，给左侧尾巴留位。
  function New-BubblePath {
    param([bool]$tailRight)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $bx = if ($tailRight) { 0 } else { $script:TailAllow }
    $by = 0
    $w = $bw; $h = $bh
    $r = 10; $d = 2 * $r
    $ty1 = $h - 34; $ty2 = $h - 20; $tmy = $h - 27   # 尾巴在侧边中下部（底缘内缩 20px）
    if ($tailRight) {
      $apex = $bx + $w + $script:TailAllow - 1        # 尾尖抵达窗口右内边（不超出）
      $path.AddArc($bx, $by, $d, $d, 180, 90)
      $path.AddLine(($bx + $r), $by, ($bx + $w - $r), $by)
      $path.AddArc(($bx + $w - $d), $by, $d, $d, 270, 90)
      $path.AddLine(($bx + $w), ($by + $r), ($bx + $w), $ty1)
      $path.AddLine(($bx + $w), $ty1, $apex, $tmy)
      $path.AddLine($apex, $tmy, ($bx + $w), $ty2)
      $path.AddLine(($bx + $w), $ty2, ($bx + $w), ($by + $h - $r))
      $path.AddArc(($bx + $w - $d), ($by + $h - $d), $d, $d, 0, 90)
      $path.AddLine(($bx + $w - $r), ($by + $h), ($bx + $r), ($by + $h))
      $path.AddArc($bx, ($by + $h - $d), $d, $d, 90, 90)
      $path.AddLine($bx, ($by + $h - $r), $bx, ($by + $r))
      $path.CloseFigure()
    } else {
      $apex = $bx - $script:TailAllow + 1             # 尾尖抵达窗口左内边（不超出）
      $path.AddArc($bx, $by, $d, $d, 180, 90)
      $path.AddLine(($bx + $r), $by, ($bx + $w - $r), $by)
      $path.AddArc(($bx + $w - $d), $by, $d, $d, 270, 90)
      $path.AddLine(($bx + $w), ($by + $r), ($bx + $w), ($by + $h - $r))
      $path.AddArc(($bx + $w - $d), ($by + $h - $d), $d, $d, 0, 90)
      $path.AddLine(($bx + $w - $r), ($by + $h), ($bx + $r), ($by + $h))
      $path.AddArc($bx, ($by + $h - $d), $d, $d, 90, 90)
      $path.AddLine($bx, ($by + $h - $r), $bx, $ty2)
      $path.AddLine($bx, $ty2, $apex, $tmy)
      $path.AddLine($apex, $tmy, $bx, $ty1)
      $path.AddLine($bx, $ty1, $bx, ($by + $r))
      $path.CloseFigure()
    }
    return $path
  }

  # 三个动作按钮（横排，自绘圆角抗锯齿）: 启动Claude / 启动ChatGPT / 启动B站
  $maxW = 0
  foreach ($bn in $script:BtnTexts) {
    $tw = [System.Windows.Forms.TextRenderer]::MeasureText($bn, $script:BtnFont).Width
    if ($tw -gt $maxW) { $maxW = $tw }
  }
  $btnH = 28
  $btnW = $maxW + 24
  $gap  = 8
  $padLR = 14
  $labTop = 11
  $labGap = 9
  $botPad = 11
  $btnRowW = 3 * $btnW + 2 * $gap
  $bw = [math]::Max([int]($psize.Width + 2 * $padLR), [int]($btnRowW + 2 * $padLR))
  $bh = $labTop + $psize.Height + $labGap + $btnH + $botPad
  $bubble.ClientSize = [System.Drawing.Size]::new($bw, $bh)
  $lab.Location = [System.Drawing.Point]::new($padLR, $labTop)
  $bubble.Controls.Add($lab)

  $btnY = $labTop + $psize.Height + $labGap
  $x0 = [int](($bw - $btnRowW) / 2)        # 按钮行居中
  for ($bi = 0; $bi -lt 3; $bi++) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = ''                            # 文字自绘，避免与默认渲染重叠
    $b.Font = $script:BtnFont
    $b.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $b.FlatAppearance.BorderSize = 0
    # 默认背景与气泡同色，使默认矩形渲染"隐形"，只露出自绘的圆角形状
    $b.FlatAppearance.MouseOverBackColor = $script:BubBg
    $b.FlatAppearance.MouseDownBackColor = $script:BubBg
    $b.BackColor = $script:BubBg
    $b.UseVisualStyleBackColor = $false
    $b.Size = [System.Drawing.Size]::new($btnW, $btnH)
    $b.Location = [System.Drawing.Point]::new([int]($x0 + $bi * ($btnW + $gap)), $btnY)
    $b.Cursor = [System.Windows.Forms.Cursors]::Hand
    $b.Tag = $bi
    $script:Buttons += $b
    $b.Add_MouseEnter({ param($s, $e); $script:BtnHover[[int]$s.Tag] = $true; $s.Invalidate() })
    $b.Add_MouseLeave({ param($s, $e); $script:BtnHover[[int]$s.Tag] = $false; $s.Invalidate() })
    $b.Add_Paint({
      param($s, $e)
      $idx = [int]$s.Tag
      $rect = New-Object System.Drawing.Rectangle 1, 1, ($s.Width - 2), ($s.Height - 2)
      $path = New-RoundedPath $rect.X $rect.Y $rect.Width $rect.Height 8
      $e.Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
      $fill = if ($script:BtnHover[$idx]) { $script:BtnHoverBg } else { $script:BtnBase }
      $br = New-Object System.Drawing.SolidBrush $fill
      $e.Graphics.FillPath($br, $path); $br.Dispose()
      $pen = New-Object System.Drawing.Pen($script:BtnBorder, 1)
      $e.Graphics.DrawPath($pen, $path); $pen.Dispose()
      $path.Dispose()
      $tc = if ($script:BtnHover[$idx]) { $script:BtnTextHv } else { $script:BtnTextC }
      $tbr = New-Object System.Drawing.SolidBrush $tc
      $sf = New-Object System.Drawing.StringFormat
      $sf.Alignment = [System.Drawing.StringAlignment]::Center
      $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
      $e.Graphics.DrawString($script:BtnTexts[$idx], $script:BtnFont, $tbr, [System.Drawing.RectangleF]::new(0, 0, $s.Width, $s.Height), $sf)
      $tbr.Dispose(); $sf.Dispose()
    })
    $b.Add_Click({
      param($s2, $e2)
      switch ($s2.Tag) {
        0 {
          # 启动 Claude 桌面版（MSIX 应用，通过 AUMID 启动）
          try {
            $com = New-Object -ComObject Shell.Application
            $com.Namespace('shell:AppsFolder').ParseName('Claude_pzs8sxrjxfjjc!Claude').InvokeVerb('open')
          } catch { Start-Process powershell -ArgumentList '-NoExit', '-Command', 'claude' }
        }
        1 {
          # 启动 ChatGPT 桌面版
          try {
            $com = New-Object -ComObject Shell.Application
            $com.Namespace('shell:AppsFolder').ParseName('OpenAI.Codex_2p2nqsd0c76g0!App').InvokeVerb('open')
          } catch { Start-Process 'https://chatgpt.com' }
        }
        2 {
          $edge = "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe"
          try {
            if (Test-Path $edge) { Start-Process $edge -ArgumentList 'https://www.bilibili.com/' }
            else {
              $edge2 = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction SilentlyContinue
              if ($edge2) { Start-Process $edge2.'(default)' -ArgumentList 'https://www.bilibili.com/' }
              else { Start-Process 'https://www.bilibili.com/' }
            }
          } catch { Start-Process 'https://www.bilibili.com/' }
        }
      }
      # 点击按钮启动后，关闭气泡
      try { Close-Bubble } catch {}
    })
    $bubble.Controls.Add($b)
  }

  # 关闭按钮（自绘圆形，悬停浅红）
  $btnClose = New-Object System.Windows.Forms.Button
  $btnClose.Text = ''
  $btnClose.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $btnClose.FlatAppearance.BorderSize = 0
  $btnClose.FlatAppearance.MouseOverBackColor = $script:BubBg
  $btnClose.FlatAppearance.MouseDownBackColor = $script:BubBg
  $btnClose.BackColor = $script:BubBg
  $btnClose.UseVisualStyleBackColor = $false
  $btnClose.Size = [System.Drawing.Size]::new(18, 18)
  $btnClose.Location = [System.Drawing.Point]::new($bw - 23, 4)
  $btnClose.Cursor = [System.Windows.Forms.Cursors]::Hand
  $btnClose.Add_MouseEnter({ param($s, $e); $script:CloseHover = $true; $s.Invalidate() })
  $btnClose.Add_MouseLeave({ param($s, $e); $script:CloseHover = $false; $s.Invalidate() })
  $btnClose.Add_Paint({
    param($s, $e)
    $rect = New-Object System.Drawing.Rectangle 1, 1, ($s.Width - 2), ($s.Height - 2)
    $e.Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $fill = if ($script:CloseHover) { [System.Drawing.Color]::FromArgb(247, 226, 226) } else { $script:BubBg }
    $br = New-Object System.Drawing.SolidBrush $fill
    $e.Graphics.FillEllipse($br, $rect); $br.Dispose()
    $penC = if ($script:CloseHover) { [System.Drawing.Color]::FromArgb(224, 180, 180) } else { [System.Drawing.Color]::FromArgb(212, 218, 230) }
    $pen = New-Object System.Drawing.Pen($penC, 1)
    $e.Graphics.DrawEllipse($pen, $rect); $pen.Dispose()
    $tbr = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(150, 92, 92))
    $sf = New-Object System.Drawing.StringFormat
    $sf.Alignment = [System.Drawing.StringAlignment]::Center
    $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
    $e.Graphics.DrawString([string][char]0x00D7, $script:CloseFont, $tbr, [System.Drawing.RectangleF]::new(0, 0, $s.Width, $s.Height), $sf)
    $tbr.Dispose(); $sf.Dispose()
  })
  $btnClose.Add_Click({ Close-Bubble })
  $bubble.Controls.Add($btnClose)

  # 气泡边框：沿"圆角矩形 + 尾巴"同一路径描 1px 细边，与 Region 完全重合、无错位
  $script:BubbleTailRight = $true
  $bubble.Add_Paint({
    param($s, $e)
    $e.Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $path = New-BubblePath $script:BubbleTailRight
    $pen = New-Object System.Drawing.Pen($script:BubBorder, 1)
    $e.Graphics.DrawPath($pen, $path); $pen.Dispose(); $path.Dispose()
  })

  # ---------- 气泡工具函数 ----------
  function Set-BubbleRegion {
    param([bool]$tailRight)
    $script:BubbleTailRight = $tailRight
    # 尾巴整体收入窗口：窗口比气泡主体宽 TailAllow+1，主体随尾巴方向左右偏移
    # (+1px 余量：尾巴在左时主体右边框不贴到窗口外沿，避免被裁掉 1px)
    $bodyX = if ($tailRight) { 0 } else { $script:TailAllow }
    $winW = $bw + $script:TailAllow + 1
    $bubble.ClientSize = [System.Drawing.Size]::new($winW, $bh)
    # 尾巴在左时，标签/按钮/关闭键整体右移 TailAllow，保持相对主体位置不变
    $lab.Location = [System.Drawing.Point]::new(($bodyX + $padLR), $labTop)
    for ($i = 0; $i -lt $script:Buttons.Count; $i++) {
      $script:Buttons[$i].Location = [System.Drawing.Point]::new(($bodyX + $x0 + $i * ($btnW + $gap)), $btnY)
    }
    $btnClose.Location = [System.Drawing.Point]::new(($bodyX + $bw - 23), 4)
    # Region = 圆角矩形 + 尾巴（同一路径），全部位于窗口内，尾巴不再被边界裁切
    $path = New-BubblePath $tailRight
    $bubble.Region = [System.Drawing.Region]::new($path)
    $path.Dispose()
    $bubble.Invalidate()
  }

  function Position-Bubble {
    $waP = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $winW = $bw + $script:TailAllow + 1
    $tailRight = $true
    $bx = [int]$script:X - $winW - 10
    if ($bx -lt 8) { $bx = [int]$script:X + $script:FW + 10; $tailRight = $false }
    $by = [int]([math]::Max(8.0, [math]::Min($waP.Height - $bh - 8.0, $script:Y + $script:FH * 0.55 - $bh / 2.0)))
    Set-BubbleRegion $tailRight
    $bubble.Location = [System.Drawing.Point]::new($bx, $by)
  }

  function Open-Bubble {
    $script:BubbleOpen = $true
    $script:Fade = 0.0
    $script:HopT = 0.35          # 开心一跳
    Position-Bubble
    $bubble.Opacity = 0
    $bubble.Show()
  }

  function Close-Bubble {
    $script:BubbleOpen = $false
    $script:Fade = 0.0
    $bubble.Opacity = 0
    $bubble.Hide()
  }

  function Toggle-Bubble {
    if ($script:BubbleOpen) { Close-Bubble } else { Open-Bubble }
  }

  # ---------- 动画主循环 ----------
  function Step-Tick {
    $dt = 0.033
    $script:Time += $dt
    if ($script:Dragging) {
      # 拖拽：平滑摇晃（幅度小、频率低，不抖动）+ 方向倾斜
      $script:Lean += ($script:LeanTarget - $script:Lean) * 0.25
      $script:WagPhase += $script:WagFreq * $dt
      $script:Angle = [math]::Sin($script:WagPhase * 2 * [math]::PI) * 1.6 + $script:Lean
      $script:Bob = 0
      $script:Breath = [math]::Sin($script:Time * 2 * [math]::PI / 2.6) * 0.6
    } else {
      # 闲时：轻微漂浮 + 缓慢摇摆 + 呼吸
      $script:Angle = [math]::Sin($script:Time * 2 * [math]::PI / 2.4) * 2.2
      $script:Bob = [math]::Sin($script:Time * 2 * [math]::PI / 3.0) * 3
      $script:Breath = [math]::Sin($script:Time * 2 * [math]::PI / 2.6) * 0.6
    }
    if ($script:HopT -gt 0) {
      $script:HopT -= $dt
      $script:Bob += [math]::Sin([math]::PI * (1 - $script:HopT / 0.35)) * 12
    }
    if ($script:BubbleOpen -and $bubble.Opacity -lt 1.0) {
      $script:Fade += $dt * 6.0
      $bubble.Opacity = [math]::Min(1.0, $script:Fade)
    }
    $lionForm.Invalidate()
  }

  # ---------- 右键菜单 ----------
  $menu = New-Object System.Windows.Forms.ContextMenuStrip
  $mOpen = $menu.Items.Add('打开对话')
  $mOpen.Add_Click({ Toggle-Bubble })
  $mReset = $menu.Items.Add('回到右下角')
  $mReset.Add_Click({
    $waR = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $script:X = $waR.Width - $script:FW - 20
    $script:Y = $waR.Height - $script:FH - 16
    $lionForm.Location = [System.Drawing.Point]::new([int]$script:X, [int]$script:Y)
    if ($script:BubbleOpen) { Position-Bubble }
  })
  $mQuit = $menu.Items.Add('退出')
  $mQuit.Add_Click({ Stop-Lion })
  $lionForm.ContextMenuStrip = $menu

  function Stop-Lion {
    # 用户主动退出时写标记，守护进程据此不再自动重启
    try { Set-Content -Path (Join-Path $script:Dir 'lion_clean_exit.txt') -Value 'ok' -Encoding ASCII } catch {}
    try { $timer.Stop() } catch {}
    try { $bubble.Dispose() } catch {}
    try { $lionForm.Dispose() } catch {}
    try { [System.Windows.Forms.Application]::Exit() } catch {}
  }

  $timer = New-Object System.Windows.Forms.Timer
  $timer.Interval = 33
  $timer.Add_Tick({ Step-Tick })

  # ---------- 启动 ----------
  $lionForm.Location = [System.Drawing.Point]::new([int]$script:X, [int]$script:Y)
  $lionForm.Show()

  if ($Test) {
    # 冒烟测试：跑几帧、开合一次气泡后自动退出
    for ($i = 0; $i -lt 8; $i++) {
      Step-Tick
      [System.Windows.Forms.Application]::DoEvents()
      Start-Sleep -Milliseconds 30
    }
    Open-Bubble
    for ($i = 0; $i -lt 6; $i++) {
      Step-Tick
      [System.Windows.Forms.Application]::DoEvents()
      Start-Sleep -Milliseconds 30
    }
    Close-Bubble
    Stop-Lion
    'TEST OK'
  } else {
    $timer.Start()
    [System.Windows.Forms.Application]::Run($lionForm)
  }

} catch {
  $err = $_.Exception.ToString()
  $err += "`nLINE: " + $_.InvocationInfo.ScriptName + ":" + $_.InvocationInfo.ScriptLineNumber + " -> " + $_.InvocationInfo.Line.Trim()
  Write-Log $err
  try { [System.Windows.Forms.MessageBox]::Show("狮子助手启动失败：`n$err", '错误', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null } catch {}
}
