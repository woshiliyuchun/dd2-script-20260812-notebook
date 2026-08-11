@echo off
REM =====================================================
REM 一键启动 DD2 全局热键监听
REM 双击本文件后保持窗口开着，即可：
REM   Ctrl+F11 → 启动/重启 dd2_war_table_walk.py（任意界面都可按）
REM   Ctrl+F12 → 关闭本监听程序（不影响已启动的DD2脚本）
REM =====================================================
chcp 65001 > nul
cd /d "%~dp0"

REM 如果有 .venv 就用 .venv 的 python，否则用系统 python
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

title DD2 全局热键监听（Ctrl+F11启动脚本，Ctrl+F12退出监听）
echo =====================================================
echo DD2 全局热键监听 - 启动中...
echo 若提示「管理员权限」相关错误，请右键本文件 -^> 以管理员身份运行
echo =====================================================
"%PYTHON%" "%~dp0hotkey_listener.py"
if errorlevel 1 (
    echo.
    echo [监听异常退出] 5秒后关闭窗口...
    timeout /t 5 > nul
)
