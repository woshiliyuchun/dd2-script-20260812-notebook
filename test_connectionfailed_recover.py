# -*- coding: utf-8 -*-
"""
DD2 网络连接中断 + 卡死恢复流程 独立测试脚本

测试流程（与主脚本逻辑 1:1 对齐，便于单步验证）:
  1. 切换到 DD2 游戏画面（聚焦窗口）
  2. 识别网络连接中断 connectionfailed.png（阈值 0.9）
     - 若检测到 → 走 recover_game() 卡死恢复流程
     - 若未检测到 → 每秒重试，最多检测 60 秒
     - 按 Ctrl+C 可随时手动中断

模板路径、阈值、卡死恢复流程（关游戏 → Steam 重开 → 回私人城镇）
完全复用主脚本 dd2_war_table_walk.py 中的配置与实现。
"""

import os
import sys
import time
import random
import ctypes
import subprocess
from pathlib import Path

import cv2
import numpy as np
import mss
import pyautogui
import win32api
import win32con
import win32gui
import win32process

SCRIPT_DIR = Path(r"d:\DD2脚本\dd2onslaught")
sys.path.insert(0, str(SCRIPT_DIR))

from dd2_war_table_walk import (
    CONFIG,
    FREEZE_MONITOR,
    FREEZE_SCRIPT_DIR,
    FREEZE_MATCH_THRESHOLD,
    TEMPLATE_STEAM,
    TEMPLATE_STOP,
    TEMPLATE_CONFIRM,
    TEMPLATE_START_GAME,
    TEMPLATE_PRIVATE_TAVERN,
    TEMPLATE_CANCEL,
    GAME_PROCESS_NAME,
    find_game_window,
    focus_game_window,
    capture_game_window,
    load_template,
    find_template_rect,
    check_connection_failed,
    recover_game,
)

CONNECTION_FAILED_PATH = r"D:\DD2脚本\DD2ganmedie\connectionfailed.png"
MATCH_THRESHOLD = 0.9
MAX_DETECT_RETRY = 60  # 最多检测 60 秒


def detect_connectionfailed_once():
    """单次检测：截屏 → 在游戏窗口内匹配 connectionfailed.png（阈值 0.9）。
    命中返回相似度，否则返回 None。"""
    hwnd = find_game_window()
    if not hwnd:
        print("[检测] 未找到 DD2 游戏窗口")
        return None
    frame = capture_game_window(hwnd)
    if frame is None:
        print("[检测] 截取游戏窗口失败")
        return None
    if not os.path.exists(CONNECTION_FAILED_PATH):
        print(f"[检测] 模板文件不存在: {CONNECTION_FAILED_PATH}")
        return None
    template = load_template(CONNECTION_FAILED_PATH)
    rect = find_template_rect(frame, template, threshold=MATCH_THRESHOLD)
    if rect:
        print(f"[检测] 识别到网络连接中断！位置中心=({rect['center_x']},{rect['center_y']}) 相似度={rect['max_val']:.4f}（阈值≥{MATCH_THRESHOLD}）")
        return rect["max_val"]
    return None


def main():
    print("=" * 60)
    print("DD2 网络连接中断 → 卡死恢复流程 独立测试")
    print("=" * 60)
    print(f"[配置] 模板路径: {CONNECTION_FAILED_PATH}")
    print(f"[配置] 匹配阈值: {MATCH_THRESHOLD}")
    print(f"[配置] 主脚本 CONFIG['connectionfailed_template'] = {CONFIG['connectionfailed_template']}")
    print("-" * 60)

    # ==================== 步骤1：切到 DD2 游戏画面 ====================
    print("\n[步骤1/3] 切换到 DD2 游戏画面...")
    hwnd = find_game_window()
    if not hwnd:
        print("[步骤1] ❌ 未找到 DD2 游戏窗口（可能游戏未启动或类名/标题不匹配）")
        print(f"       期待: class={CONFIG['game_class']}, title={CONFIG['game_title']}")
        return
    focus_game_window(hwnd)
    time.sleep(1)
    # 再聚焦一次，避免第一次被遮挡
    hwnd = find_game_window()
    focus_game_window(hwnd)
    time.sleep(1)
    print(f"[步骤1] ✅ DD2 游戏窗口已聚焦（句柄 {hwnd}）")

    # ==================== 步骤2：识别网络连接中断 ====================
    print(f"\n[步骤2/3] 开始识别网络连接中断 connectionfailed.png（阈值 {MATCH_THRESHOLD}），最多等待 {MAX_DETECT_RETRY} 秒")
    print("         如果画面上当前没有 connectionfailed，请在游戏里触发断网（或手工把模板放在显眼位置）后继续...")
    print("         按 Ctrl+C 可随时手动中断。")

    detected_score = None
    try:
        for attempt in range(1, MAX_DETECT_RETRY + 1):
            score = detect_connectionfailed_once()
            if score is not None:
                detected_score = score
                break
            print(f"[检测] 第 {attempt}/{MAX_DETECT_RETRY} 次：未识别到 connectionfailed（阈值 {MATCH_THRESHOLD}），1秒后重试...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[步骤2] ⚠️  用户手动中断检测")
        return

    if detected_score is None:
        print(f"\n[步骤2] ❌ {MAX_DETECT_RETRY} 秒内未识别到 connectionfailed，不执行卡死恢复流程。")
        print("         建议：用截图工具从游戏真正的断网弹窗里重新截一张 connectionfailed.png")
        print("               替换到 D:\\DD2脚本\\DD2ganmedie\\connectionfailed.png 再测试。")
        return

    print(f"[步骤2] ✅ 识别成功，相似度 {detected_score:.4f} ≥ {MATCH_THRESHOLD}")

    # 验证主脚本的 check_connection_failed 函数行为（0.9 阈值、路径正确）
    print("\n[交叉验证] 调用主脚本 check_connection_failed() 函数（阈值0.9，路径走 CONFIG）...")
    # 手动对齐 CONFIG 路径到 DD2ganmedie 目录（与主脚本最新配置保持一致）
    CONFIG["connectionfailed_template"] = CONNECTION_FAILED_PATH
    # 再调一次函数做最终确认（注意：它内部一旦命中就会直接触发 recover_game！）
    # 这里只做「只检测不恢复」的独立副本确认：先重跑一次 find_template_rect
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(CONNECTION_FAILED_PATH)
    rect = find_template_rect(frame, template, threshold=0.9)
    if rect:
        print(f"[交叉验证] ✅ 主脚本所用 find_template_rect(frame, template, 0.9) 命中，相似度={rect['max_val']:.4f}")
    else:
        print(f"[交叉验证] ⚠️  主脚本级 0.9 阈值未命中（但上方独立检测命中 {detected_score:.4f}，需要检查模板是否略有差异）")
        print("         将仍继续执行卡死恢复流程，便于验证 recover_game 自身是否能跑通。")

    # ==================== 步骤3：走卡死恢复流程 recover_game ====================
    print("\n[步骤3/3] 开始执行卡死恢复流程 recover_game()（关游戏 → Steam重开 → 回私人城镇）")
    confirm = input("         👉 请输入大写 Y 并回车确认执行恢复流程（此操作会关闭DD2再重启）: ").strip()
    if confirm != "Y":
        print("[步骤3] ⚠️  未输入 Y，跳过卡死恢复流程执行。")
        print("         若只想单独验证检测识别是否正确，现在已经验证通过。")
        return

    if FREEZE_MONITOR:
        FREEZE_MONITOR.reset()
    success = recover_game()
    if success:
        print("\n[步骤3] ✅ 卡死恢复流程执行成功，游戏已重启并回到私人城镇！")
    else:
        print("\n[步骤3] ❌ 卡死恢复流程执行失败（详见上方日志），可根据报错定位模板/Steam配置问题。")


if __name__ == "__main__":
    # 进程设置为 DPI-aware，与主脚本保持一致
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    main()
