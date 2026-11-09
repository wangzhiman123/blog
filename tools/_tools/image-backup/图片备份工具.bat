@echo off
rem 本文件保存为 GBK(936) 编码，先让控制台也切到 936，中文才不会乱码。
chcp 936 >nul
cd /d "%~dp0"
title 文章图片备份工具
setlocal enabledelayedexpansion

rem 找一个真正能用的 Python 3。
rem Windows 自带的 WindowsApps\python.exe 是 0 字节的商店占位符，
rem 能通过 where 检查，一运行就退出，所以必须真的执行一次来验证。

set "PY="

if defined PYTHON_EXE call :test_python "%PYTHON_EXE%"
if defined PY goto found

call :test_python "python"
if defined PY goto found

call :test_python "python3"
if defined PY goto found

call :test_python "py"
if defined PY goto found

rem WorkBuddy 自带的 Python（有这个就不用另外装）
if not defined PY if exist "%ProgramFiles%\WorkBuddy\resources\vendor\python\python.exe" call :test_python "%ProgramFiles%\WorkBuddy\resources\vendor\python\python.exe"
if defined PY goto found

for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if not defined PY if exist "%%~fD\python.exe" call :test_python "%%~fD\python.exe"
)
if defined PY goto found

rem 系统里常见的手动安装位置
for %%R in ("%LOCALAPPDATA%\Programs\Python" "%ProgramFiles%\Python" "C:\Python") do (
    for /d %%D in ("%%~R\Python3*") do (
        if not defined PY if exist "%%~fD\python.exe" call :test_python "%%~fD\python.exe"
    )
    for /d %%D in ("%%~R\3*") do (
        if not defined PY if exist "%%~fD\python.exe" call :test_python "%%~fD\python.exe"
    )
)
if defined PY goto found

goto no_python

rem ============================================================

:test_python
"%~1" -c "import sys;sys.exit(0 if sys.version_info[0]==3 else 1)" >nul 2>nul
if errorlevel 1 goto :eof
set "PY=%~1"
goto :eof

rem ============================================================

:no_python
cls
echo.
echo  ============================================================
echo    没有找到可用的 Python
echo  ============================================================
echo.
echo    这台电脑上只有一个 Windows 自带的「商店占位符」，
echo    它名字叫 python，但实际运行会立刻退出。
echo.
echo    办法一（推荐）：装一个 Python
echo      1. 浏览器打开  https://www.python.org/downloads/
echo      2. 点黄色大按钮  Download Python 3.x.x
echo      3. 安装界面最下面，务必勾上  Add python.exe to PATH
echo      4. 装完关掉本窗口，重新双击这个文件
echo.
echo    办法二：已经装了 Python，但没加进 PATH
echo      新建一个环境变量 PYTHON_EXE，值填 python.exe 的完整路径，
echo      然后重新双击这个文件。
echo.
echo    办法三：正在使用 WorkBuddy
echo      确认这个文件存在：
echo      %ProgramFiles%\WorkBuddy\resources\vendor\python\python.exe
echo.
pause
exit /b 1

rem ============================================================

:found
rem 切到 UTF-8，让 Python 打出来的中文和符号正常显示。
rem 这一行之后不要再写中文 echo，否则 cmd 会读错行。
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
"!PY!" "%~dp0backup_images.py" --menu %*
pause
exit /b 0
