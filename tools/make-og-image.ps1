<#
  生成站点默认分享图（1200x630 PNG）

  用途：分享首页或没有配图的文章到微信 / QQ / Twitter 时，卡片右侧显示的小图。
  输出：static/images/og-default.png

  用法（在 my-blog-4 目录下）：
    pwsh -NoProfile -File tools\make-og-image.ps1
  或直接双击 tools\生成分享图.bat

  改配色 / 文案：改下面 DrawString 那几行的文字，以及背景色的 RGB 值。
#>

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$outDir = Join-Path $PSScriptRoot '..\static\images'
$outDir = [System.IO.Path]::GetFullPath($outDir)
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
$outFile = Join-Path $outDir 'og-default.png'

$W = 1200
$H = 630

$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic

# ---- 背景：深青色斜向渐变 ----
$rect = New-Object System.Drawing.Rectangle 0, 0, $W, $H
$brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
  $rect,
  [System.Drawing.Color]::FromArgb(255, 15, 32, 39),
  [System.Drawing.Color]::FromArgb(255, 32, 58, 67),
  45.0
)
$g.FillRectangle($brush, $rect)

# ---- 右下角光晕，避免整块死板 ----
$glowPath = New-Object System.Drawing.Drawing2D.GraphicsPath
$glowPath.AddEllipse(760, 250, 700, 700)
$glowBrush = New-Object System.Drawing.Drawing2D.PathGradientBrush($glowPath)
$glowBrush.CenterColor = [System.Drawing.Color]::FromArgb(56, 140, 200, 170)
$glowBrush.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 140, 200, 170))
$g.FillPath($glowBrush, $glowPath)

# ---- 左侧竖线 ----
$accent = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 72, 199, 152))
$g.FillRectangle($accent, 90, 120, 6, 390)

# ---- 字体 ----
$fontBold = New-Object System.Drawing.Font('Microsoft YaHei', 62, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$fontSub = New-Object System.Drawing.Font('Microsoft YaHei', 27, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$fontTag = New-Object System.Drawing.Font('Microsoft YaHei', 22, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$fontSite = New-Object System.Drawing.Font('Microsoft YaHei', 24, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)

$white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 245, 248, 250))
$dim = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 154, 170, 178))
$soft = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 120, 200, 175))

# ---- 顶部小标签 ----
$g.DrawString('民商事诉讼 · 案例检索 · 实务笔记', $fontTag, $dim, 128, 118)

# ---- 主标题 ----
$g.DrawString('王志满律师', $fontBold, $white, 122, 176)

# ---- 副标题 ----
$g.DrawString('把办案过程写成可以复用的笔记', $fontSub, $dim, 128, 300)

# ---- 分隔线 ----
$linePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(70, 255, 255, 255)), 1.5
$g.DrawLine($linePen, 128, 400, 620, 400)

# ---- 底部域名 ----
$g.DrawString('444527.xyz', $fontSite, $soft, 128, 432)

$g.Dispose()
$bmp.Save($outFile, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

Write-Output "[OK] 已生成 $outFile"
