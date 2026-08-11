# pip install mss opencv-python pyautogui pywin32 keyboard
#
# 说明：
# 1) 这段代码只实现“从城镇出生点走到 War Table，并按下 E 打开爬塔房间选择界面”这一段。
# 2) 你后续补充截图后，只需要把下方模板路径改为你自己的图片即可。
# 3) 代码中已区分【走路无光标模式】与【弹窗有光标点击模式】两套逻辑。
# 4) 使用 F12 热键即可立刻停止脚本执行。

import os
import time
import random
import cv2
import numpy as np
import mss
import pyautogui
import keyboard
import win32gui
import win32con


# ========================= 全局配置（只改这里） =========================
CONFIG = {
    "game_class": "LaunchUnrealUWindowsClient",
    "game_title": "Dungeon Defenders 2",

    # 识别模板路径（后续补图以后只改这里即可）
    "template_dir": r"D:\DD2_WestBuild\templates",
    "war_table_template": r"D:\DD2_WestBuild\templates\war_table.png",
    "e_tip_template": r"D:\DD2_WestBuild\templates\e_tip.png",

    # 识别阈值与扫描参数
    "match_threshold": 0.78,
    "scan_rotate_steps": 6,
    "scan_rotate_ms": 220,
    "forward_press_ms": 220,
    "forward_hold_ms": 500,
    "step_wait_seconds": 0.15,

    # 识别中心容差
    "center_tolerance_x": 140,
    "center_tolerance_y": 120,

    # 自动重试次数
    "max_scan_rounds": 12,

    # 退出键
    "stop_hotkey": "F12",
}

STOP_FLAG = False


# ========================= 窗口工具模块 =========================

def find_game_window():
    """查找并返回游戏窗口句柄。"""
    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
    if hwnd == 0:
        raise RuntimeError(f"未找到游戏窗口：class={CONFIG['game_class']} title={CONFIG['game_title']}")
    return hwnd


def focus_game_window(hwnd=None):
    """
    把游戏窗口切到前台，确保后续键鼠操作只作用于游戏窗口。
    这是防止误操作桌面的关键。
    """
    if hwnd is None:
        hwnd = find_game_window()

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass

    # 让游戏窗口保持顶层，避免别的窗口盖住
    try:
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
    except Exception:
        pass

    time.sleep(0.15)
    return hwnd


def get_window_rect(hwnd):
    """返回游戏窗口的屏幕矩形区域。"""
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return left, top, right - left, bottom - top
    except Exception:
        return 0, 0, 1920, 1080


def capture_game_window(hwnd):
    """使用 mss 截取游戏窗口当前画面，返回 BGR 图像。"""
    x, y, width, height = get_window_rect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("游戏窗口尺寸无效")

    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": width, "height": height}
        img = np.array(sct.grab(monitor))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


# ========================= 图像识别模块 =========================

def load_template(template_path):
    """加载模板图片。"""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板图片不存在：{template_path}")

    img = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"模板图片读取失败：{template_path}")
    return img


def find_template_center(frame_bgr, template_bgr, threshold=None):
    """
    在当前画面中寻找模板图片的位置，返回中心坐标（x, y），找不到返回 None。
    这里会做 cv2.matchTemplate 模板匹配。
    """
    if threshold is None:
        threshold = CONFIG["match_threshold"]

    result = cv2.matchTemplate(frame_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < threshold:
        return None

    th, tw = template_bgr.shape[:2]
    center_x = max_loc[0] + tw // 2
    center_y = max_loc[1] + th // 2
    return center_x, center_y, max_val


# ========================= 走路无光标模式（WASD + 视角拖拽） =========================

def safe_press(key_name, duration=0.12):
    """安全按键：先保证游戏窗口在前台，再执行按键。"""
    hwnd = find_game_window()
    focus_game_window(hwnd)
    pyautogui.keyDown(key_name)
    time.sleep(duration)
    pyautogui.keyUp(key_name)


def move_forward_once():
    """前进一步：无需系统鼠标光标，直接用 W 键走。"""
    safe_press("w", duration=CONFIG["forward_press_ms"] / 1000.0)
    time.sleep(CONFIG["step_wait_seconds"])


def rotate_view(direction, drag_px=160):
    """
    视角拖拽旋转：
    direction = -1 表示向左旋转；direction = 1 表示向右旋转。
    """
    hwnd = find_game_window()
    focus_game_window(hwnd)

    left, top, width, height = get_window_rect(hwnd)
    center_x = left + width // 2
    center_y = top + height // 2

    pyautogui.moveTo(center_x, center_y)
    time.sleep(0.05)

    # 模拟在游戏窗口内拖拽视角
    pyautogui.mouseDown(button="left")
    time.sleep(0.04)
    pyautogui.moveRel(int(drag_px * direction), 0, duration=0.14)
    pyautogui.mouseUp(button="left")
    time.sleep(CONFIG["step_wait_seconds"])


def left_scan_once():
    rotate_view(-1, drag_px=160)


def right_scan_once():
    rotate_view(1, drag_px=160)


# ========================= 弹窗有光标模式（E 提示与房间界面） =========================

def press_e_interact():
    """
    当检测到 E 提示图时，按下 E 打开爬塔房间选择界面。
    这里属于“弹窗有光标点击模式”的交互阶段。
    """
    hwnd = find_game_window()
    focus_game_window(hwnd)

    # 先保证窗口前台，避免误触桌面
    pyautogui.keyDown("e")
    time.sleep(0.08)
    pyautogui.keyUp("e")
    print("[INFO] 已按下 E，尝试打开爬塔房间选择界面")


# ========================= 自动寻路逻辑模块 =========================

def detect_war_table(hwnd):
    """在当前游戏窗口截图中识别 War Table 模板。"""
    frame = capture_game_window(hwnd)
    template = load_template(CONFIG["war_table_template"])
    return find_template_center(frame, template)


def detect_e_tip(hwnd):
    """在当前游戏窗口截图中识别 E 提示模板。"""
    frame = capture_game_window(hwnd)
    template = load_template(CONFIG["e_tip_template"])
    return find_template_center(frame, template)


def stop_now():
    """F12 热键触发的停止函数。"""
    global STOP_FLAG
    STOP_FLAG = True
    print("[INFO] 已收到 F12 停止信号，脚本即将停止")


def register_stop_hotkey():
    """注册 F12 热键，随时停止脚本。"""
    keyboard.add_hotkey(CONFIG["stop_hotkey"], stop_now)


def center_alignment(target_x, target_y, frame_w, frame_h):
    """
    调整 War Table 在画面中心附近：
    - 如果桌子偏左，就向左旋转视角
    - 如果桌子偏右，就向右旋转视角
    - 如果桌子接近中心则直走
    """
    center_x = frame_w // 2
    center_y = frame_h // 2

    dx = target_x - center_x
    dy = target_y - center_y

    # 只处理水平旋转补偿，优先保证桌子进入视野中心
    if dx < -CONFIG["center_tolerance_x"]:
        rotate_view(-1, drag_px=80)
        return "rotate_left"
    if dx > CONFIG["center_tolerance_x"]:
        rotate_view(1, drag_px=80)
        return "rotate_right"

    if abs(dy) > CONFIG["center_tolerance_y"]:
        # 如果桌子在画面上下偏差大，优先做较轻微的前进/调整
        move_forward_once()
        return "forward"

    return "approach"


def walk_to_war_table_and_press_e():
    """
    核心主逻辑：
    1) 识别桌子模板，如果出现则靠近并校正中心；
    2) 连续多次未识别到桌子时，自动左右旋转扫描视角；
    3) 找到 E 提示后，按 E 打开爬塔房间选择界面；
    4) F12 可立即中止所有键鼠动作。
    """
    global STOP_FLAG

    hwnd = find_game_window()
    focus_game_window(hwnd)

    # 开始前先给一点时间，让用户切到游戏窗口
    print("[INFO] 3 秒后开始自动寻路…")
    time.sleep(3)

    scan_round = 0
    last_action = "startup"

    while not STOP_FLAG:
        hwnd = find_game_window()
        focus_game_window(hwnd)

        # 1) 优先检测 E 提示：如果已经靠近桌子并显示 E 文字，就按 E
        e_pos = detect_e_tip(hwnd)
        if e_pos is not None:
            print("[INFO] 检测到 E 提示，准备按 E 交互")
            press_e_interact()
            return True

        # 2) 检测 War Table 桌子
        table_pos = detect_war_table(hwnd)
        if table_pos is not None:
            table_x, table_y, conf = table_pos
            frame = capture_game_window(hwnd)
            frame_h, frame_w = frame.shape[:2]
            print(f"[INFO] 检测到 War Table，置信度={conf:.3f}，坐标=({table_x}, {table_y})")

            action = center_alignment(table_x, table_y, frame_w, frame_h)
            if action == "rotate_left" or action == "rotate_right":
                last_action = action
            elif action == "approach":
                move_forward_once()
                last_action = "forward"
            else:
                move_forward_once()
                last_action = "forward"

            scan_round = 0
            time.sleep(0.15)
            continue

        # 3) 未找到桌子，自动左右旋转扫描，避免卡死
        scan_round += 1
        print(f"[INFO] 未找到 War Table，开始第 {scan_round} 轮旋转扫描")

        if scan_round % 2 == 1:
            left_scan_once()
            last_action = "scan_left"
        else:
            right_scan_once()
            last_action = "scan_right"

        # 4) 连续多轮未识别到时，短暂前进一小步再继续扫描
        if scan_round >= CONFIG["max_scan_rounds"]:
            print("[WARN] 连续多轮未识别到桌子，执行一次前进补偿后继续扫描")
            move_forward_once()
            scan_round = 0

        time.sleep(0.2)

    print("[INFO] 脚本已停止")
    return False


# ========================= 主入口 =========================

if __name__ == "__main__":
    register_stop_hotkey()

    print("=" * 70)
    print("DD2 自动寻路到 War Table 并按 E 打开界面")
    print("=" * 70)
    print("说明：")
    print("- 走路阶段：无系统鼠标光标，使用 WASD + 视角拖拽")
    print("- 弹窗阶段：有鼠标光标，需要通过按 E 打开交互界面")
    print("- 紧急停止：按 F12")
    print("- 模板路径：")
    print(f"  War Table = {CONFIG['war_table_template']}")
    print(f"  E Tip     = {CONFIG['e_tip_template']}")
    print("=" * 70)

    try:
        walk_to_war_table_and_press_e()
    except KeyboardInterrupt:
        print("[INFO] 用户中断退出")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}\n请先把桌子模板与 E 提示模板放到: {CONFIG['template_dir']}")
    except Exception as e:
        print(f"[ERROR] 脚本异常: {e}")
