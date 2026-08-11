# -*- coding: utf-8 -*-
r"""
DD2 视角重置专项（鼠标专项）独立测试脚本
==========================================
本文件把 dd2_war_table_walk.py 中【楼层>320 时触发的鼠标/视角专项整套操作】
单独拎出来做成独立可运行的测试，不用等到楼层达到条件，直接运行就能执行全套：
    1) 视角左转 45°（相对鼠标事件，缓慢移动防作弊）
    2) 盲按 4 次 W（W 期间不再识别 e-reset），之后直接盲按 E
    3) 按 E 后等 2 秒
    4) 缓慢点击游戏相对位置 (0.65, 0.75)
    5) 每秒按 1 次 Enter，共 3 次
    6) 等待 20 秒，然后（可选）执行卡死关游戏+重启

本脚本所有辅助函数（窗口查找/聚焦、游戏截图、缓慢移动鼠标等）
与 wartable 文件中使用的实现完全一致，保证专项行为和正式流程里一模一样。
仅独立出来方便直接测试专项流程，不涉及寻路/找War/楼层判断等其他逻辑。

使用方式：
  1) 切到游戏界面，保证已经在私人城堡/城镇里（可以先自己走两歩确认有角色）
  2) 在 Trae 运行本脚本，或在 cmd 里运行：
         .venv\\Scripts\\python.exe test_view_reset_specialty.py
  3) 脚本会自动切回游戏并执行全套鼠标/视角专项操作，看日志输出观察每歩效果
"""

import os
import sys
import time
import ctypes
import random
from pathlib import Path

import cv2
import numpy as np
import mss
import pyautogui
import win32api
import win32con
import win32gui
import win32ui

SCRIPT_DIR = Path(__file__).resolve().parent
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ========================= 基础工具（与 wartable 文件保持一致） =========================

GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"
E_RESET_TEMPLATE = str(SCRIPT_DIR / "picture" / "e-reset.png")
RESET_CONFIRM_TEMPLATE = str(SCRIPT_DIR / "picture" / "resetconfirm.png")
MATCH_THRESHOLD = 0.66


def humanized_sleep(base_seconds):
    """在 base_seconds 基础上 ±30% 随机抖动的 sleep，避免固定周期反作弊。"""
    jitter = base_seconds * random.uniform(-0.30, 0.30)
    time.sleep(max(0.05, base_seconds + jitter))


def humanized_press(key, duration=0.08):
    """模拟人类按键：按下→随机抖动时长→抬起。"""
    pyautogui.keyDown(key)
    time.sleep(max(0.02, duration * random.uniform(0.75, 1.25)))
    pyautogui.keyUp(key)
    humanized_sleep(0.10)


def safe_press(key, duration=0.25):
    """较长按压的安全按键（用于 W/S/A/D）。"""
    pyautogui.keyDown(key)
    time.sleep(duration)
    pyautogui.keyUp(key)
    time.sleep(0.05)


def find_game_window():
    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if not hwnd:
        hwnd = win32gui.FindWindow(None, GAME_TITLE)
    return hwnd


def focus_game_window(hwnd=None):
    if hwnd is None:
        hwnd = find_game_window()
    if not hwnd:
        return
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(
            ctypes.windll.kernel32.GetCurrentProcessId()
        )
    except Exception:
        pass
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.2)
        # —— 每次聚焦后自动把窗口移到屏幕左上角，避免遮挡脚本输出
        try:
            _, _, w, h = get_window_rect(hwnd)
            if w <= 0: w = 2000
            if h <= 0: h = 1100
            win32gui.SetWindowPos(hwnd, 0, 0, 0, w, h,
                                  win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW)
        except Exception:
            pass
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    except Exception:
        pass


def get_window_rect(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return left, top, right - left, bottom - top


def capture_game_window(hwnd):
    """用 mss 捕获游戏窗口，避免黑边黑色区域。"""
    if not hwnd:
        return None
    left, top, w, h = get_window_rect(hwnd)
    if w <= 0 or h <= 0:
        return None
    # 只取客户区（去掉标题栏）效果更好；这里直接抓整个窗口，与 wartable 保持一致
    monitor = {"left": left, "top": top, "width": w, "height": h}
    with mss.mss() as sct:
        shot = sct.grab(monitor)
        frame = np.array(shot, dtype=np.uint8)[:, :, :3]
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    return frame_bgr


def load_template(path):
    """读取灰度模板图片，不存在返回 None。"""
    if not path or not os.path.exists(path):
        return None
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    return img


def find_template_rect(frame, template, threshold=0.80, region=None):
    """
    在 frame 中搜索 template，返回：
        {left, top, right, bottom, center_x, center_y, max_val}
    没找到返回 None。region 若给出为 (fx0, fy0, fx1, fy1) 相对坐标(0~1)。
    """
    if frame is None or template is None:
        return None
    fh, fw = frame.shape[:2]
    th, tw = template.shape[:2]
    x0 = y0 = 0
    x1, y1 = fw, fh
    if region:
        fx0, fy0, fx1, fy1 = region
        x0, y0 = int(fx0 * fw), int(fy0 * fh)
        x1, y1 = max(x0 + 1, int(fx1 * fw)), max(y0 + 1, int(fy1 * fh))
        if (x1 - x0) < tw or (y1 - y0) < th:
            return None
        frame = frame[y0:y1, x0:x1]
    if frame.shape[0] < th or frame.shape[1] < tw:
        return None
    try:
        gray_f = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(gray_f, gray_t, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
    except Exception:
        return None
    if max_val < threshold:
        return None
    ml, mt = max_loc
    left = x0 + ml
    top = y0 + mt
    right = left + tw
    bottom = top + th
    return {
        "left": left, "top": top, "right": right, "bottom": bottom,
        "center_x": left + tw // 2, "center_y": top + th // 2,
        "max_val": float(max_val),
    }


# ========================= 视角专项相关：鼠标缓慢移动 + 相对旋转 =========================

def _slow_move_to(target_x, target_y, steps=20):
    """把系统鼠标缓慢移动到屏幕(target_x, target_y)，分20歩防作弊。"""
    try:
        start_x, start_y = win32api.GetCursorPos()
    except Exception:
        start_x, start_y = target_x, target_y
    for i in range(steps):
        if i == steps - 1:
            nx, ny = target_x, target_y
        else:
            t = (i + 1) / steps
            jitter_x = random.uniform(-0.5, 0.5)
            jitter_y = random.uniform(-0.5, 0.5)
            nx = int(start_x + (target_x - start_x) * t + jitter_x)
            ny = int(start_y + (target_y - start_y) * t + jitter_y)
        ctypes.windll.user32.SetCursorPos(nx, ny)
        time.sleep(0.012)


def _slow_click_at(target_x, target_y, clicks=1):
    """缓慢移到目标→按下→抬起→重复。"""
    _slow_move_to(target_x, target_y)
    for _ in range(clicks):
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # LMOUSE down
        time.sleep(random.uniform(0.04, 0.08))
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # LMOUSE up
        time.sleep(random.uniform(0.10, 0.20))


def _rotate_view_left_for_reset(degrees=45, duration=1.0):
    """
    使用相对鼠标事件把视角向左转指定角度（与 wartable 里完全一样）。
    - 先确保鼠标在游戏窗口内部
    - 使用 MOUSEEVENTF_MOVE (0x0001) 发相对移动事件，分多次缓慢移动，避免作弊检测
    """
    hwnd = find_game_window()
    focus_game_window(hwnd)
    if not hwnd:
        print("[专项-错误] 找不到游戏窗口")
        return
    left, top, w, h = get_window_rect(hwnd)
    # 先把鼠标放到窗口中央，避免在窗口边缘发相对移动没效果
    cx = left + w // 2
    cy = top + h // 2
    _slow_move_to(cx, cy)
    time.sleep(0.05)
    # 与 wartable 里校准一致：degrees × 2.17（之前用户反复校准后的转动幅度）
    total_dx = -int(w * degrees * 2.17 / 180)
    steps = 50
    step_dx = int(total_dx / steps)
    for i in range(steps):
        # 最后一步把余数吃掉，保证总角度精准
        if i == steps - 1:
            dx = total_dx - step_dx * (steps - 1)
        else:
            dx = step_dx + random.randint(-1, 1)
        ctypes.windll.user32.mouse_event(0x0001, dx, 0, 0, 0)
        time.sleep(duration / steps)
    print(f"[专项] 视角左转 {degrees}° 完成（相对像素总位移={total_dx}）")


def _check_e_reset_present():
    """在整个游戏窗口内找 e-reset.png，找到返回 True 并输出日志。"""
    template_path = E_RESET_TEMPLATE
    if not os.path.exists(template_path):
        print(f"[专项-警告] e-reset 模板不存在：{template_path}")
        return False
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    if frame is None:
        return False
    template = load_template(template_path)
    if template is None:
        return False
    rect = find_template_rect(frame, template, threshold=0.80)
    if rect:
        print(f"[专项] 识别到 e-reset，相似度={rect['max_val']:.4f}")
        return True
    # 没识别到时也输出一下最佳匹配度，方便排查
    try:
        gray_f = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(gray_f, gray_t, cv2.TM_CCOEFF_NORMED)
        _, best, _, _ = cv2.minMaxLoc(res)
        print(f"[专项] 暂未识别到 e-reset（全图最佳匹配={best:.4f}，阈值=0.80）")
    except Exception:
        print("[专项] 暂未识别到 e-reset")
    return False


# ========================= 专项整套流程入口（与 wartable 中 perform_view_reset_and_restart 完全一致） =========================

def run_view_reset_specialty_without_restart():
    r"""执行【视角左转→4次W（不识别e-reset）→盲按E→等2秒→点(0.65,0.75)→识别resetconfirm点击（找不到回退Enter×3）→等20秒】整套，不含关游戏重启。"""
    hwnd = find_game_window()
    if not hwnd:
        print("[专项-错误] 未找到游戏窗口，请先打开DD2并进入私人城堡")
        return False
    focus_game_window(hwnd)
    print("=" * 70)
    print("[专项] 开始执行视角/鼠标专项整套流程…")
    print("=" * 70)

    # 1. 视角左转 45°
    print("\n[专项] 1/6 视角左转 45°…")
    _rotate_view_left_for_reset(45, duration=1.0)

    # 2. 盲按 4 次 W（W 期间不再识别 e-reset，只走路），然后直接盲按 E
    print("\n[专项] 2/6 盲按 4 次 W（不识别e-reset），之后盲按 E…")
    for i in range(4):
        print(f"[专项]  第 {i+1}/4 次盲按 W…")
        safe_press("w", duration=0.3)
        time.sleep(1.0)
    # 4 次 W 走完后，直接盲按 E（不再检测 e-reset 图标）
    print("[专项]   4 次 W 完成，盲按 E…")
    humanized_press("e")
    e_pressed = True

    # 3. 按 E 后等 2 秒
    print("\n[专项] 3/6 盲按 E 完成，等 2 秒…")
    time.sleep(2.0)

    # 4. 缓慢点击相对 (0.65, 0.75)
    print("\n[专项] 4/6 点击游戏相对位置 (0.65, 0.75)…")
    left, top, w, h = get_window_rect(hwnd)
    sx = left + int(w * 0.65)
    sy = top + int(h * 0.75)
    print(f"[专项]  窗口左上角=({left},{top})  尺寸=({w}x{h})  目标屏幕坐标=({sx},{sy})")
    _slow_click_at(sx, sy)

    # 5. 识别 resetconfirm.png 并点击；找不到回退每秒1次 Enter×3
    print("\n[专项] 5/6 识别 resetconfirm.png 并点击（找不到回退按 Enter）…")
    confirm_clicked = False
    for confirm_try in range(3):
        found_rect = None
        if os.path.exists(RESET_CONFIRM_TEMPLATE):
            frame_cf = capture_game_window(hwnd)
            tmpl_cf = load_template(RESET_CONFIRM_TEMPLATE)
            found_rect = find_template_rect(frame_cf, tmpl_cf, threshold=MATCH_THRESHOLD)
        if found_rect is not None:
            tx = found_rect["center_x"] + left
            ty = found_rect["center_y"] + top
            print(f"[专项]   第 {confirm_try+1}/3 次识别到 resetconfirm，相似度={found_rect['max_val']:.4f}，坐标=({tx},{ty})")
            _slow_click_at(tx, ty)
            confirm_clicked = True
            break
        else:
            print(f"[专项]   第 {confirm_try+1}/3 次未识别到 resetconfirm，回退按 Enter")
            humanized_press("enter")
        if confirm_try < 2:
            time.sleep(1.0)
    if confirm_clicked:
        print("[专项]   resetconfirm 识别并点击完成")
    else:
        print("[专项]   3次均未识别到 resetconfirm，已按 Enter 3 次回退")

    # 6. 等 20 秒（这一步之后 wartable 会关游戏重启；本测试脚本只等待，不关游戏）
    print("\n[专项] 6/6 重置确认后，等待 20 秒（观察游戏是否按预期反应）…")
    for i in range(20):
        time.sleep(1.0)
        if (i + 1) % 5 == 0:
            print(f"[专项]   已等待 {i+1} / 20 秒…")

    print("\n" + "=" * 70)
    print("[专项] 整套视角/鼠标专项流程执行完成。")
    print("=" * 70)
    print("[专项] 说明：此测试脚本不会执行关游戏+重启；正式流程下 wartable 会在这一步之后调用 recover_game 重启。")
    return True


if __name__ == "__main__":
    print("=" * 70)
    print("DD2 视角/鼠标专项 独立测试")
    print("=" * 70)
    print("提示：请先切到游戏界面并进入私人城堡，准备好后脚本会自动切到游戏并执行。")
    print("倒计时 3 秒后开始，如需停止请直接关掉本窗口…")
    for i in range(3, 0, -1):
        print(f"  {i} ...")
        time.sleep(1)
    try:
        run_view_reset_specialty_without_restart()
    except KeyboardInterrupt:
        print("\n[专项] Ctrl+C 中断")
        sys.exit(0)
