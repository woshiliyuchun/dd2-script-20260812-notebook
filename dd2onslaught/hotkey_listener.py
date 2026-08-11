# -*- coding: utf-8 -*-
"""
DD2 全局热键监听器（常驻后台）
==============================
功能：
  - 在 Windows 任意界面（包括游戏界面、桌面等）按 Ctrl + F11  →  启动/重启 dd2_war_table_walk.py
  - 在任意界面按 Ctrl + F12                                      →  退出本监听程序（不影响已启动的脚本，要停止脚本请在脚本控制台按 F12）
  - 若 Ctrl+F11 按下去时脚本已经在跑 → 自动 terminate 上一个，再启动新的（保证始终只有一个在跑，避免键鼠操作冲突）

依赖：
  pip install keyboard
  （和 dd2_war_table_walk.py 共用同一个 .venv 环境即可）

运行方式：
  1) 在 Trae 里打开本文件，按「运行」启动；或者双击配套的 start_hotkey_listener.bat
  2) 保持这个监听程序一直开着（可以最小化），然后你在任何界面按 Ctrl+F11 都会自动启动 DD2 脚本
  3) 以后想开了，只要监听还在跑，就不用切 Trae 点运行了

注意：
  - keyboard 库需要管理员权限才能注册全局热键。如果监听启动后按键没反应，请以管理员方式重新开本监听。
  - 本监听本身不做任何键鼠操作，只负责启动/停止 dd2_war_table_walk.py 子进程。
  - DD2 脚本启动后会新开一个独立的 cmd 窗口显示运行日志，按 F12 可在那个窗口里立即停止脚本。
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path

try:
    import keyboard
except ImportError:
    print("[错误] 缺少 keyboard 依赖，请运行：.venv\\Scripts\\python.exe -m pip install keyboard")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = SCRIPT_DIR / ".venv" / "Scripts" / "python.exe"
TARGET_SCRIPT = SCRIPT_DIR / "dd2_war_table_walk.py"

# Windows 下让子脚本新开一个独立控制台窗口，方便看日志/按 F12 停止
CREATE_NEW_CONSOLE = 0x00000010

# 子进程句柄（Ctrl+F11 重复按时用来先 kill 上一个）
_current_proc = None
_listener_stop = False


def _kill_previous():
    """关掉上一次 Ctrl+F11 启动的脚本进程（如果还在跑），避免两个脚本冲突。"""
    global _current_proc
    if _current_proc is None:
        return
    try:
        if _current_proc.poll() is None:
            print("[监听] 上一个DD2脚本进程仍在运行，先终止…")
            try:
                # 先温柔关，2秒不死再硬杀
                _current_proc.terminate()
                try:
                    _current_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _current_proc.kill()
                    _current_proc.wait(timeout=2)
            except Exception as exc:
                print(f"[监听] 终止上一个进程遇到异常，忽略: {exc}")
    finally:
        _current_proc = None


def launch_dd2_script():
    """按 Ctrl+F11 时的回调：启动 dd2_war_table_walk.py，保证全局只跑一个。"""
    global _current_proc

    print("\n========================================")
    print("[监听] 收到 Ctrl+F11，启动 DD2 自动脚本…")
    print("========================================")

    if not VENV_PYTHON.exists():
        print(f"[错误] 找不到 .venv Python 解释器: {VENV_PYTHON}")
        return
    if not TARGET_SCRIPT.exists():
        print(f"[错误] 找不到目标脚本: {TARGET_SCRIPT}")
        return

    # 先清掉上一次残留
    _kill_previous()

    try:
        proc = subprocess.Popen(
            [str(VENV_PYTHON), str(TARGET_SCRIPT)],
            cwd=str(SCRIPT_DIR),
            creationflags=CREATE_NEW_CONSOLE,
        )
        _current_proc = proc
        print(f"[监听] DD2脚本已启动，新窗口PID={proc.pid}，会显示运行日志。按 F12 可在那个窗口停止脚本。")
        print(f"[监听] 若要重新启动脚本（例如改完代码后），再按一次 Ctrl+F11 即可，旧的会自动关掉。")
    except Exception as exc:
        print(f"[错误] 启动DD2脚本失败: {exc}")


def stop_listener():
    """按 Ctrl+F12 退出全局热键监听程序本身。"""
    global _listener_stop
    print("\n[监听] 收到 Ctrl+F12，退出全局热键监听…")
    _listener_stop = True


def main():
    if not VENV_PYTHON.exists():
        print(f"[WARN] .venv Python 解释器不存在：{VENV_PYTHON}，请先创建虚拟环境并安装依赖。")
    if not TARGET_SCRIPT.exists():
        print(f"[WARN] 目标脚本不存在：{TARGET_SCRIPT}")

    # 注册两个全局热键（任意界面都生效）
    try:
        keyboard.add_hotkey("ctrl+f11", launch_dd2_script)
        keyboard.add_hotkey("ctrl+f12", stop_listener)
    except Exception as exc:
        print(f"[错误] 注册全局热键失败({exc})。请尝试用「管理员方式」运行本监听程序。")
        sys.exit(1)

    print("=" * 70)
    print("DD2 全局热键监听器已启动（常驻后台）")
    print("=" * 70)
    print("快捷键：")
    print("  Ctrl + F11   →  启动/重启 DD2 自动脚本（dd2_war_table_walk.py）")
    print("                  重复按会先停掉上一次启动的，再开新的")
    print("  Ctrl + F12   →  退出本监听程序（不会影响正在跑的DD2脚本）")
    print("")
    print("说明：")
    print("  · 在任何界面（游戏/桌面/浏览器/Trae）按 Ctrl+F11 都会触发，不用切回 Trae")
    print("  · DD2 脚本启动后会新开一个 cmd 窗口，脚本运行日志会在那个窗口显示")
    print("  · 在DD2脚本的窗口按 F12 可立即停止当前脚本（或再按一次 Ctrl+F11 重启）")
    print("  · 若按快捷键无反应，请【右键 → 以管理员方式运行】本监听")
    print("=" * 70)
    print("[监听] 等待快捷键…（按 Ctrl+F12 退出）")

    # 空转等待；keyboard 库在后台线程跑监听，这里只要不退出进程就行
    try:
        while not _listener_stop:
            # 顺带每5秒检查一下子进程是否还活着，死了就清句柄避免下次判断误判
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[监听] Ctrl+C 中断，退出监听")

    # 退出前清理一下（不关子进程，用户可能还要继续跑DD2脚本）
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    print("[监听] 已退出。")


if __name__ == "__main__":
    main()
