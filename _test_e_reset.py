# -*- coding: utf-8 -*-
"""
测试 e-reset 转生流程：从视角左转 → 盲走4步W → 盲按E → 点击(0.65,0.75) → 识别resetconfirm → 等待20秒
不包含关闭/重启游戏步骤（步骤7 recover_game 跳过）。

使用方法：
  1. 确保游戏窗口在前台、角色站在 War Table 旁边
  2. 运行本脚本，3 秒倒计时后自动开始
  3. F12 可随时中止
"""

import sys
import os
import time

# 添加主脚本路径，导入所需函数
SCRIPT_DIR = r"D:\DD2脚本\dd2onslaught"
sys.path.insert(0, SCRIPT_DIR)

from dd2_war_table_walk import (
    find_game_window,
    focus_game_window,
    capture_game_window,
    load_template,
    find_template_rect,
    humanized_press,
    humanized_sleep,
    safe_press,
    _slow_click_at,
    _rotate_view_left_for_reset,
    _check_e_reset_present,
    CONFIG,
)
import win32gui
import keyboard

# F12 停止热键
STOP_FLAG = False

def _on_f12():
    global STOP_FLAG
    STOP_FLAG = True
    print("\n[F12] 收到停止信号，正在退出…")

keyboard.on_press_key("F12", lambda _: _on_f12())


def test_e_reset_flow():
    """测试 e-reset 转生流程（不含关闭/重启游戏）。"""

    # ===== 0. 切换到游戏窗口并等待 =====
    hwnd = find_game_window()
    if not hwnd:
        print("[ERROR] 未找到游戏窗口，请先启动游戏")
        return

    focus_game_window(hwnd)
    humanized_sleep(0.5)
    print("[测试] 已切换到游戏窗口")

    # 3 秒倒计时
    for i in range(3, 0, -1):
        print(f"[测试] {i} 秒后开始执行转生流程…")
        time.sleep(1)

    if STOP_FLAG:
        print("[测试] 已中止")
        return

    # ===== 1. 视角左转 30° =====
    print("[测试] 1/6 视角左转 30°…")
    try:
        _rotate_view_left_for_reset(30, duration=1.0)
    except Exception as e:
        print(f"[测试] 视角左转异常，跳过: {e}")

    if STOP_FLAG:
        print("[测试] 已中止")
        return

    # ===== 2. 盲按 4 次 W =====
    print("[测试] 2/6 盲按 4 次 W…")
    for i in range(4):
        if STOP_FLAG:
            print("[测试] 已中止")
            return
        print(f"[测试]   第 {i+1}/4 次盲按 W…")
        try:
            safe_press("w", duration=0.3)
        except Exception:
            pass
        time.sleep(1.0)

    # ===== 3. 盲按 E =====
    print("[测试] 3/6 4 次 W 完成，盲按 E…")
    try:
        humanized_press("e")
    except Exception:
        pass

    # ===== 4. 等 2 秒后点击相对 (0.65, 0.75) =====
    print("[测试] 4/6 等待 2 秒后点击 (0.65, 0.75)…")
    time.sleep(2.0)

    if STOP_FLAG:
        print("[测试] 已中止")
        return

    try:
        game_rect = win32gui.GetWindowRect(hwnd)
        sx = game_rect[0] + int((game_rect[2] - game_rect[0]) * 0.65)
        sy = game_rect[1] + int((game_rect[3] - game_rect[1]) * 0.75)
        print(f"[测试]   点击屏幕坐标=({sx}, {sy})")
        _slow_click_at(sx, sy)
    except Exception as e:
        print(f"[测试] 点击(0.65,0.75)异常，跳过: {e}")

    # ===== 5. 识别 resetconfirm.png 并点击（3次失败回退 Enter）=====
    print("[测试] 5/6 识别 resetconfirm.png 并点击（3次失败回退 Enter）…")
    confirm_template_path = CONFIG.get("resetconfirm_template")
    confirm_clicked = False

    for confirm_try in range(3):
        if STOP_FLAG:
            print("[测试] 已中止")
            return

        found_rect = None
        if confirm_template_path and os.path.exists(confirm_template_path):
            try:
                frame_cf = capture_game_window(hwnd)
                tmpl_cf = load_template(confirm_template_path)
                found_rect = find_template_rect(frame_cf, tmpl_cf, threshold=0.7)
            except Exception as e:
                print(f"[测试]   resetconfirm 识别异常（尝试{confirm_try+1}/3），回退 Enter: {e}")
                found_rect = None
        else:
            print(f"[测试]   resetconfirm 模板不存在: {confirm_template_path}")

        if found_rect is not None:
            g_left, g_top, _, _ = win32gui.GetWindowRect(hwnd)
            tx = g_left + int(found_rect["center_x"])
            ty = g_top + int(found_rect["center_y"])
            print(f"[测试]   第 {confirm_try+1}/3 次识别到 resetconfirm，相似度={found_rect['max_val']:.4f}，点击=({tx},{ty})")
            try:
                _slow_click_at(tx, ty)
                confirm_clicked = True
            except Exception as e:
                print(f"[测试]   resetconfirm 点击异常，回退 Enter: {e}")
            break
        else:
            print(f"[测试]   第 {confirm_try+1}/3 次未识别到 resetconfirm，回退按 Enter")
            try:
                humanized_press("enter")
            except Exception:
                pass

        if confirm_try < 2:
            time.sleep(1.0)

    if confirm_clicked:
        print("[测试]   resetconfirm 识别并点击完成")
    else:
        print("[测试]   3 次均未识别到 resetconfirm（或异常），继续等待")

    # ===== 6. 等待 20 秒（不关闭/重启游戏）=====
    print("[测试] 6/6 等待 20 秒…")
    for i in range(20):
        if STOP_FLAG:
            break
        time.sleep(1)

    print("[测试] e-reset 转生流程测试完成！")


if __name__ == "__main__":
    print("=" * 50)
    print("  DD2 e-reset 转生流程测试")
    print("  F12 随时中止")
    print("=" * 50)
    test_e_reset_flow()
