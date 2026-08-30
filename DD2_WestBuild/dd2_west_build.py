import os
import sys
import time
import random
import threading
from pathlib import Path
import win32api
import win32con
import win32gui
import pyautogui
import cv2
import numpy as np
from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from dd2onslaught import dd2_war_table_walk as war_table

GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

COORD_CONFIG = {
    '背包按钮': (0.810, 0.156),
}

REGION_CONFIG = {
    '额外奖励区域': (0.35, 0.3, 0.8, 1.2),
    'replay区域': (0.6, 0.88, 0.68, 0.91),
    '失败重来区域': (0.48, 0.77, 0.5, 0.8),
}

SCRIPT_DIR = str(PROJECT_DIR)
WEST_BUILD_DIR = Path(__file__).resolve().parent
TEMPLATE_EXTRA_REWARD = os.path.join(SCRIPT_DIR, "额外奖励.png")
TEMPLATE_REPLAY = os.path.join(SCRIPT_DIR, "replay.png")
TEMPLATE_FAILURE_RETRY = os.path.join(SCRIPT_DIR, "失败重来.png")
TEMPLATE_WILD_WEST = str(WEST_BUILD_DIR / "picture" / "wildwest.png")
TEMPLATE_WILD_WEST_STAGE = str(WEST_BUILD_DIR / "picture" / "wildwest-1.png")
TEMPLATE_CHAOS1_BEGIN = str(WEST_BUILD_DIR / "picture" / "chaos1_begin.png")
TEMPLATE_BROWSE = str(PROJECT_DIR / "dd2onslaught" / "picture" / "BROWSE.png")
TEMPLATE_CREATE = str(WEST_BUILD_DIR / "picture" / "create.png")
TEMPLATE_PRIVATE_GAME = str(WEST_BUILD_DIR / "picture" / "privitegame.png")
TEMPLATE_GO_BEGIN = str(WEST_BUILD_DIR / "picture" / "go_begin.png")
TEMPLATE_CORE = str(WEST_BUILD_DIR / "picture" / "core.png")
TEMPLATE_CONNECTION_FAILED = str(PROJECT_DIR / "DD2ganmedie" / "connectionfailed.png")
TEMPLATE_CACHE = {}
MAP_MATCH_THRESHOLD = 0.7
CONNECTION_FAILED_THRESHOLD = 0.9
NETWORK_CHECK_INTERVAL_SECONDS = 60.0
NO_SETTLEMENT_TIMEOUT_SECONDS = 30.0 * 60.0

CAPTURE_LOCK = threading.RLock()
RECOVERY_REQUEST = threading.Event()
WINDOW_GUARD_ACTIVE = threading.Event()
SETTLEMENT_WATCH_ACTIVE = threading.Event()
WATCHDOG_STOP = threading.Event()
STATE_LOCK = threading.Lock()
LAST_SETTLEMENT_TIME = None
RECOVERY_REASON = None


class RecoveryRequested(RuntimeError):
    """Raised in the foreground flow when the watchdog requests a restart."""


def request_recovery(reason):
    global RECOVERY_REASON
    with STATE_LOCK:
        if RECOVERY_REQUEST.is_set():
            return
        RECOVERY_REASON = reason
        RECOVERY_REQUEST.set()
    print(f"[卡死检测] {reason}，准备执行卡死恢复流程")


def clear_recovery_request():
    global RECOVERY_REASON
    with STATE_LOCK:
        RECOVERY_REASON = None
        RECOVERY_REQUEST.clear()


def raise_if_recovery_requested():
    if RECOVERY_REQUEST.is_set():
        with STATE_LOCK:
            reason = RECOVERY_REASON or "收到卡死恢复请求"
        raise RecoveryRequested(reason)


def mark_settlement_seen(source):
    global LAST_SETTLEMENT_TIME
    with STATE_LOCK:
        LAST_SETTLEMENT_TIME = time.monotonic()
    print(f"[卡死检测] 已识别结算画面（{source}），重置30分钟计时")


def start_settlement_watch():
    global LAST_SETTLEMENT_TIME
    with STATE_LOCK:
        LAST_SETTLEMENT_TIME = time.monotonic()
    SETTLEMENT_WATCH_ACTIVE.set()


def stop_settlement_watch():
    SETTLEMENT_WATCH_ACTIVE.clear()


def seconds_since_last_settlement(now=None):
    if now is None:
        now = time.monotonic()
    with STATE_LOCK:
        last_seen = LAST_SETTLEMENT_TIME
    if last_seen is None:
        return 0.0
    return max(0.0, now - last_seen)


def get_window_rect(hwnd):
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (left, top, right - left, bottom - top)
    except:
        return (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)


def get_client_rect(hwnd):
    try:
        rect = win32gui.GetClientRect(hwnd)
        return (rect[2], rect[3])
    except:
        return (1920, 1080)


def get_client_rect_for_recognition(hwnd):
    return (1600, 900)


def capture_client_region(hwnd, left, top, width, height):
    with CAPTURE_LOCK:
        return war_table.capture_client_region(hwnd, left, top, width, height)


def client_to_screen(hwnd, x, y):
    try:
        return win32gui.ClientToScreen(hwnd, (int(x), int(y)))
    except:
        return (int(x), int(y))


def relative_to_screen(hwnd, rel_x, rel_y):
    w, h = get_client_rect(hwnd)
    client_x = int(rel_x * w)
    client_y = int(rel_y * h)

    try:
        win_left, win_top, win_right, win_bottom = win32gui.GetWindowRect(hwnd)
        client_rect = win32gui.GetClientRect(hwnd)

        frame_left = (win_right - win_left) - client_rect[2]
        frame_top = (win_bottom - win_top) - client_rect[3]

        screen_x = win_left + frame_left + client_x
        screen_y = win_top + frame_top + client_y
        return (screen_x, screen_y)
    except:
        return client_to_screen(hwnd, client_x, client_y)


def key_down(key):
    raise_if_recovery_requested()
    if isinstance(key, str):
        if key.upper() == 'SPACE':
            vk = win32con.VK_SPACE
        elif key.upper() == 'CAPSLOCK':
            vk = win32con.VK_CAPITAL
        elif key.startswith('F') and len(key) == 2 and key[1].isdigit():
            fn = int(key[1])
            vk = win32con.VK_F1 + fn - 1
        elif key.upper() == 'SHIFT':
            vk = win32con.VK_SHIFT
        elif key.upper() == 'CTRL':
            vk = win32con.VK_CONTROL
        elif key.upper() == 'ENTER':
            vk = win32con.VK_RETURN
        elif key.upper() == 'ESC':
            vk = win32con.VK_ESCAPE
        else:
            vk = ord(key.upper())
    else:
        vk = key
    win32api.keybd_event(vk, win32api.MapVirtualKey(vk, 0), 0, 0)


def key_up(key):
    if isinstance(key, str):
        if key.upper() == 'SPACE':
            vk = win32con.VK_SPACE
        elif key.upper() == 'CAPSLOCK':
            vk = win32con.VK_CAPITAL
        elif key.startswith('F') and len(key) == 2 and key[1].isdigit():
            fn = int(key[1])
            vk = win32con.VK_F1 + fn - 1
        elif key.upper() == 'SHIFT':
            vk = win32con.VK_SHIFT
        elif key.upper() == 'CTRL':
            vk = win32con.VK_CONTROL
        elif key.upper() == 'ENTER':
            vk = win32con.VK_RETURN
        elif key.upper() == 'ESC':
            vk = win32con.VK_ESCAPE
        else:
            vk = ord(key.upper())
    else:
        vk = key
    win32api.keybd_event(vk, win32api.MapVirtualKey(vk, 0), win32con.KEYEVENTF_KEYUP, 0)


def release_all_inputs():
    """Release any key or mouse button that a recovery interrupted."""
    keys = (
        "W", "A", "S", "D", "P", "L", "I", "Y", "E", "Q", "N",
        "0", "5", "6", "7", "8", "F1", "F2", "F4",
        "SHIFT", "CTRL", "CAPSLOCK", "SPACE", "ENTER", "ESC",
    )
    for key in keys:
        try:
            key_up(key)
        except Exception:
            pass
    for button in ("left", "right"):
        try:
            pyautogui.mouseUp(button=button)
        except Exception:
            pass



# ========================= 反作弊人性化输入工具 =========================
# 所有键鼠操作加入随机扰动，模拟真人操作节奏，避免固定周期被检测
# 注意：build_western_festival() 是录制宏，不做任何改动

def humanized_press(key, base_hold=0.1):
    """模拟真人按键：按住时长在 base_hold ±40% 之间随机。"""
    hold = base_hold * random.uniform(0.6, 1.4)
    key_down(key)
    time.sleep(hold)
    key_up(key)


def humanized_move_to(x, y):
    """模拟真人鼠标移动：速度在 0.15~0.45 秒之间随机，带缓动效果。"""
    duration = random.uniform(0.15, 0.45)
    pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeOutQuad)


def humanized_sleep(base_seconds):
    """在基础等待时间上加入 ±20% 的随机抖动。"""
    if base_seconds <= 0:
        return
    jitter = base_seconds * random.uniform(-0.2, 0.2)
    actual = max(0.05, base_seconds + jitter)
    deadline = time.monotonic() + actual
    while time.monotonic() < deadline:
        raise_if_recovery_requested()
        time.sleep(min(0.5, deadline - time.monotonic()))


def load_image(image_path):
    try:
        from PIL import Image
        img = Image.open(image_path).convert('RGB')
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"❌ 加载图片失败: {e}")
        return None


def locate_image(hwnd, image_path, region_name, confidence=0.7):
    try:
        template = load_image(image_path)
        if template is None:
            print(f"❌ 无法加载图片: {image_path}")
            return None
        print(f"📌 模板图片尺寸: {template.shape[1]}x{template.shape[0]}")

        region = REGION_CONFIG.get(region_name)
        if region is None:
            print(f"❌ 未知区域: {region_name}")
            return None

        cw, ch = get_client_rect_for_recognition(hwnd)
        print(f"📌 当前客户区尺寸: {cw}x{ch}")

        left = int(region[0] * cw)
        top = int(region[1] * ch)
        right = int(region[2] * cw)
        bottom = int(region[3] * ch)
        width = right - left
        height = bottom - top

        print(f"📌 区域({region_name}): ({region[0]:.3f}, {region[1]:.3f}) - ({region[2]:.3f}, {region[3]:.3f}), 尺寸: {width}x{height}")

        img = capture_client_region(hwnd, left, top, width, height)
        print(f"📌 截图尺寸: {img.shape[1]}x{img.shape[0]}")

        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        print(f"图像识别: {region_name}, 相似度={max_val:.4f}, 阈值={confidence}")

        if max_val >= confidence:
            th, tw = template.shape[:2]
            center_x = left + max_loc[0] + tw // 2
            center_y = top + max_loc[1] + th // 2
            return (center_x, center_y)
        return None
    except Exception as e:
        print(f"❌ 图像识别失败: {e}")
        return None


def click_relative(hwnd, rel_x, rel_y, clicks=1):
    x, y = relative_to_screen(hwnd, rel_x, rel_y)
    humanized_move_to(x, y)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.click(clicks=clicks)


def build_western_festival():
    print("🚜 开始建造西方节日...")

    time.sleep(177 / 1000.0)
    time.sleep(1188 / 1000.0)
    key_down("0"); time.sleep(89 / 1000.0); key_up("0")
    time.sleep(1597 / 1000.0)
    key_down("W"); time.sleep(480 / 1000.0); key_up("W")
    time.sleep(270 / 1000.0)
    key_down("Space"); time.sleep(103 / 1000.0); key_up("Space")
    time.sleep(633 / 1000.0)
    key_down("W"); time.sleep(85 / 1000.0); key_up("W")
    time.sleep(575 / 1000.0)
    key_down("W"); time.sleep(105 / 1000.0); key_up("W")
    time.sleep(1488 / 1000.0)
    key_down("5"); time.sleep(131 / 1000.0); key_up("5")
    time.sleep(103 / 1000.0)
    key_down("S"); time.sleep(354 / 1000.0); key_up("S")
    time.sleep(1000 / 1000.0)
    pyautogui.click()
    time.sleep(201 / 1000.0)
    key_down("W"); time.sleep(508 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(501 / 1000.0)
    time.sleep(33 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(33 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(26 / 1000.0)
    time.sleep(28 / 1000.0)
    key_up("W"); time.sleep(8 / 1000.0)
    key_down("A"); time.sleep(27 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(36 / 1000.0)
    time.sleep(26 / 1000.0)
    key_down("A"); time.sleep(36 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(26 / 1000.0)
    time.sleep(37 / 1000.0)
    key_down("A"); time.sleep(26 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(35 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(36 / 1000.0)
    key_down("A"); time.sleep(20 / 1000.0)
    key_down("W"); time.sleep(26 / 1000.0)
    key_up("A"); time.sleep(16 / 1000.0)
    key_down("A"); time.sleep(41 / 1000.0)
    key_up("A"); time.sleep(20 / 1000.0)
    key_up("W"); time.sleep(400 / 1000.0)
    pyautogui.click()
    time.sleep(500 / 1000.0)
    key_down("F2"); time.sleep(50 / 1000.0); key_up("F2")
    time.sleep(1140 / 1000.0)
    key_down("7"); time.sleep(112 / 1000.0); key_up("7")
    time.sleep(520 / 1000.0)
    key_down("D"); time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(284 / 1000.0)
    key_up("D"); time.sleep(133 / 1000.0)
    key_up("S"); time.sleep(327 / 1000.0)
    key_down("S"); time.sleep(84 / 1000.0); key_up("S")
    time.sleep(332 / 1000.0)
    pyautogui.click()
    time.sleep(180 / 1000.0)
    key_down("D"); time.sleep(28 / 1000.0)
    key_down("W"); time.sleep(508 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("W"); time.sleep(30 / 1000.0)
    time.sleep(32 / 1000.0)
    key_down("W"); time.sleep(28 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("W"); time.sleep(34 / 1000.0)
    time.sleep(30 / 1000.0)
    key_down("W"); time.sleep(26 / 1000.0)
    time.sleep(36 / 1000.0)
    key_down("W"); time.sleep(26 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("W"); time.sleep(34 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("W"); time.sleep(27 / 1000.0)
    time.sleep(14 / 1000.0)
    key_up("W"); time.sleep(264 / 1000.0)
    key_down("S"); time.sleep(98 / 1000.0)
    key_up("D"); time.sleep(117 / 1000.0)
    key_up("S"); time.sleep(57 / 1000.0)
    key_down("S"); time.sleep(61 / 1000.0)
    key_down("A"); time.sleep(15 / 1000.0)
    key_up("S"); time.sleep(54 / 1000.0)
    key_up("A"); time.sleep(389 / 1000.0)
    pyautogui.click()

    time.sleep(756 / 1000.0)
    key_down("D"); time.sleep(113 / 1000.0)
    key_down("S"); time.sleep(415 / 1000.0)
    key_up("D"); time.sleep(92 / 1000.0)
    key_down("S"); time.sleep(34 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(28 / 1000.0)
    time.sleep(6 / 1000.0)
    key_up("S"); time.sleep(265 / 1000.0)
    key_down("S"); time.sleep(353 / 1000.0); key_up("S")
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(90 / 1000.0); key_up("A")
    time.sleep(534 / 1000.0)
    pyautogui.click()
    time.sleep(124 / 1000.0)
    key_down("D"); time.sleep(209 / 1000.0)
    key_down("S"); time.sleep(173 / 1000.0)
    key_up("D"); time.sleep(56 / 1000.0)
    key_down("D"); time.sleep(264 / 1000.0); key_up("D")
    time.sleep(125 / 1000.0)
    key_up("S"); time.sleep(153 / 1000.0)
    key_down("S"); time.sleep(62 / 1000.0); key_up("S")
    time.sleep(313 / 1000.0)
    pyautogui.click()
    time.sleep(172 / 1000.0)
    key_down("A"); time.sleep(42 / 1000.0)
    key_down("W"); time.sleep(292 / 1000.0)
    key_up("A"); time.sleep(215 / 1000.0)
    key_down("W"); time.sleep(28 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("W"); time.sleep(35 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("W"); time.sleep(22 / 1000.0)
    key_up("W"); time.sleep(173 / 1000.0)
    key_down("8"); time.sleep(90 / 1000.0); key_up("8")

    time.sleep(1049 / 1000.0)
    key_down("W"); time.sleep(56 / 1000.0)
    key_down("A"); time.sleep(195 / 1000.0)
    key_up("A"); time.sleep(227 / 1000.0)
    key_down("D"); time.sleep(146 / 1000.0); key_up("D")
    time.sleep(160 / 1000.0)
    key_up("W"); time.sleep(259 / 1000.0)
    key_down("W"); time.sleep(76 / 1000.0); key_up("W")
    time.sleep(166 / 1000.0)
    key_down("D"); time.sleep(104 / 1000.0); key_up("D")
    time.sleep(639 / 1000.0)
    key_down("A"); time.sleep(21 / 1000.0)
    key_down("W"); time.sleep(83 / 1000.0)
    key_up("A"); time.sleep(7 / 1000.0)
    key_up("W"); time.sleep(390 / 1000.0)
    pyautogui.click()

    time.sleep(292 / 1000.0)
    key_down("S"); time.sleep(256 / 1000.0)
    key_down("D"); time.sleep(507 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("D"); time.sleep(34 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("D"); time.sleep(33 / 1000.0)
    time.sleep(30 / 1000.0)
    key_down("D"); time.sleep(36 / 1000.0)
    time.sleep(26 / 1000.0)
    key_down("D"); time.sleep(29 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("D"); time.sleep(29 / 1000.0)
    time.sleep(1 / 1000.0)
    key_up("S"); time.sleep(27 / 1000.0)
    key_down("D"); time.sleep(33 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("D"); time.sleep(27 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("D"); time.sleep(28 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("D"); time.sleep(35 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("D"); time.sleep(21 / 1000.0)
    key_down("S"); time.sleep(507 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(27 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("S"); time.sleep(28 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(34 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(35 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(28 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("S"); time.sleep(27 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("S"); time.sleep(30 / 1000.0)
    time.sleep(32 / 1000.0)
    key_down("S"); time.sleep(29 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("S"); time.sleep(27 / 1000.0)
    time.sleep(30 / 1000.0)
    key_down("S"); time.sleep(32 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("S"); time.sleep(34 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("S"); time.sleep(26 / 1000.0)
    time.sleep(36 / 1000.0)
    key_down("S"); time.sleep(6 / 1000.0)
    key_up("D"); time.sleep(15 / 1000.0)
    key_up("S"); time.sleep(347 / 1000.0)
    key_down("7"); time.sleep(89 / 1000.0); key_up("7")
    time.sleep(370 / 1000.0)
    pyautogui.click()
    time.sleep(145 / 1000.0)
    key_down("S"); time.sleep(7 / 1000.0)
    key_down("D"); time.sleep(506 / 1000.0)
    time.sleep(31 / 1000.0)
    key_down("D"); time.sleep(32 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("D"); time.sleep(27 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("D"); time.sleep(30 / 1000.0)
    time.sleep(26 / 1000.0)
    key_down("D"); time.sleep(8 / 1000.0)
    key_up("D"); time.sleep(13 / 1000.0)
    key_up("S"); time.sleep(424 / 1000.0)
    pyautogui.click()
    time.sleep(56 / 1000.0)
    key_down("D"); time.sleep(418 / 1000.0)
    key_down("S"); time.sleep(442 / 1000.0)
    key_up("S"); time.sleep(50 / 1000.0)
    key_up("D"); time.sleep(236 / 1000.0)
    key_down("D"); time.sleep(21 / 1000.0)
    key_down("W"); time.sleep(194 / 1000.0)
    key_up("W"); time.sleep(167 / 1000.0)
    key_down("S"); time.sleep(145 / 1000.0)
    key_up("D"); time.sleep(306 / 1000.0)
    key_up("S"); time.sleep(480 / 1000.0)
    key_down("S"); time.sleep(62 / 1000.0)
    key_down("D"); time.sleep(181 / 1000.0)
    key_up("D"); time.sleep(28 / 1000.0)
    key_up("S"); time.sleep(76 / 1000.0)
    pyautogui.click()
    time.sleep(132 / 1000.0)
    key_down("D"); time.sleep(132 / 1000.0)
    key_down("W"); time.sleep(131 / 1000.0)
    key_up("W"); time.sleep(154 / 1000.0)
    key_down("S"); time.sleep(507 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("S"); time.sleep(15 / 1000.0)
    key_up("D"); time.sleep(19 / 1000.0)
    key_down("S"); time.sleep(28 / 1000.0)
    time.sleep(1 / 1000.0)
    key_up("S"); time.sleep(301 / 1000.0)
    pyautogui.click()
    time.sleep(400 / 1000.0)
    key_down("F4"); time.sleep(50 / 1000.0); key_up("F4")
    time.sleep(1100 / 1000.0)
    key_down("5"); time.sleep(89 / 1000.0); key_up("5")

    time.sleep(744 / 1000.0)
    key_down("D"); time.sleep(229 / 1000.0); key_up("D")
    time.sleep(230 / 1000.0)
    pyautogui.click()

    time.sleep(216 / 1000.0)
    key_down("A"); time.sleep(507 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(27 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    key_down("W"); time.sleep(353 / 1000.0)
    key_up("W"); time.sleep(287 / 1000.0)
    key_up("A"); time.sleep(338 / 1000.0)
    pyautogui.click()

    time.sleep(451 / 1000.0)
    key_down("F1"); time.sleep(140 / 1000.0); key_up("F1")
    time.sleep(687 / 1000.0)
    key_down("6"); time.sleep(77 / 1000.0); key_up("6")
    time.sleep(361 / 1000.0)
    key_down("D"); time.sleep(131 / 1000.0)
    key_down("W"); time.sleep(118 / 1000.0)
    key_up("D"); time.sleep(35 / 1000.0)
    key_up("W"); time.sleep(154 / 1000.0)
    pyautogui.click()
    time.sleep(162 / 1000.0)
    key_down("D"); time.sleep(379 / 1000.0); key_up("D")
    time.sleep(84 / 1000.0)
    pyautogui.click()
    time.sleep(146 / 1000.0)
    key_down("D"); time.sleep(457 / 1000.0); key_up("D")
    time.sleep(43 / 1000.0)
    pyautogui.click()
    time.sleep(132 / 1000.0)
    key_down("D"); time.sleep(508 / 1000.0)
    time.sleep(27 / 1000.0)
    key_up("D"); time.sleep(104 / 1000.0)
    pyautogui.click()
    time.sleep(84 / 1000.0)
    key_down("D"); time.sleep(194 / 1000.0)
    key_down("S"); time.sleep(299 / 1000.0)
    key_up("D"); time.sleep(6 / 1000.0)
    key_up("S"); time.sleep(160 / 1000.0)
    pyautogui.click()
    time.sleep(216 / 1000.0)
    key_down("D"); time.sleep(42 / 1000.0)
    key_down("W"); time.sleep(208 / 1000.0)
    key_up("W"); time.sleep(118 / 1000.0)
    key_up("D"); time.sleep(42 / 1000.0)
    key_down("A"); time.sleep(473 / 1000.0)
    key_down("S"); time.sleep(47 / 1000.0)
    key_up("A"); time.sleep(328 / 1000.0)
    key_up("S"); time.sleep(235 / 1000.0)
    pyautogui.click()
    time.sleep(535 / 1000.0)
    key_down("CTRL"); time.sleep(326 / 1000.0)
    key_down("P"); time.sleep(75 / 1000.0)
    key_up("P"); time.sleep(105 / 1000.0)
    key_up("CTRL"); time.sleep(7993 / 1000.0)
    key_down("W"); time.sleep(423 / 1000.0); key_up("W")
    time.sleep(306 / 1000.0)
    key_down("Space"); time.sleep(90 / 1000.0); key_up("Space")
    time.sleep(556 / 1000.0)
    key_down("W"); time.sleep(70 / 1000.0); key_up("W")
    time.sleep(478 / 1000.0)
    key_down("W"); time.sleep(111 / 1000.0); key_up("W")
    time.sleep(1375 / 1000.0)
    key_down("6"); time.sleep(118 / 1000.0); key_up("6")
    time.sleep(175 / 1000.0)
    key_down("S"); time.sleep(270 / 1000.0)
    key_down("A"); time.sleep(333 / 1000.0)
    key_up("S"); time.sleep(111 / 1000.0)
    key_up("A"); time.sleep(252 / 1000.0)
    key_down("W"); time.sleep(56 / 1000.0)
    key_down("A"); time.sleep(262 / 1000.0)
    key_up("W"); time.sleep(236 / 1000.0)
    key_up("A"); time.sleep(181 / 1000.0)
    key_down("S"); time.sleep(76 / 1000.0)
    key_down("A"); time.sleep(62 / 1000.0)
    key_up("S"); time.sleep(22 / 1000.0)
    key_up("A"); time.sleep(165 / 1000.0)
    key_down("A"); time.sleep(320 / 1000.0); key_up("A")
    time.sleep(356 / 1000.0)
    pyautogui.click()
    time.sleep(81 / 1000.0)
    key_down("A"); time.sleep(22 / 1000.0)
    key_down("S"); time.sleep(339 / 1000.0)
    key_up("S"); time.sleep(22 / 1000.0)
    key_up("A"); time.sleep(207 / 1000.0)
    pyautogui.click()
    time.sleep(174 / 1000.0)
    key_down("S"); time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(153 / 1000.0)
    key_up("A"); time.sleep(138 / 1000.0)
    key_up("S"); time.sleep(356 / 1000.0)
    pyautogui.click()
    time.sleep(451 / 1000.0)
    key_down("A"); time.sleep(160 / 1000.0); key_up("A")
    time.sleep(1000 / 1000.0)
    key_down("F2"); time.sleep(132 / 1000.0); key_up("F2")
    time.sleep(1111 / 1000.0)
    key_down("7"); time.sleep(506 / 1000.0); key_up("7")
    time.sleep(506 / 1000.0)
    key_down("A"); time.sleep(508 / 1000.0)
    time.sleep(26 / 1000.0)
    key_down("A"); time.sleep(35 / 1000.0)
    time.sleep(20 / 1000.0)
    key_up("A"); time.sleep(500 / 1000.0)
    pyautogui.click()
    time.sleep(445 / 1000.0)
    key_down("D"); time.sleep(42 / 1000.0)
    key_down("S"); time.sleep(277 / 1000.0)
    key_up("D"); time.sleep(49 / 1000.0)
    key_up("S"); time.sleep(847 / 1000.0)
    key_down("D"); time.sleep(160 / 1000.0); key_up("D")
    time.sleep(146 / 1000.0)
    pyautogui.click()
    time.sleep(1100 / 1000.0)
    key_down("F4"); time.sleep(50 / 1000.0); key_up("F4")
    time.sleep(1200 / 1000.0)
    key_down("5"); time.sleep(50 / 1000.0); key_up("5")

    time.sleep(90 / 1000.0)
    key_down("A"); time.sleep(194 / 1000.0)
    key_down("S"); time.sleep(249 / 1000.0)
    key_up("A"); time.sleep(56 / 1000.0)
    key_up("S"); time.sleep(617 / 1000.0)
    pyautogui.click()

    time.sleep(100 / 1000.0)
    key_down("D"); time.sleep(132 / 1000.0)
    key_down("W"); time.sleep(314 / 1000.0)
    key_up("W"); time.sleep(207 / 1000.0)
    key_up("D"); time.sleep(628 / 1000.0)
    pyautogui.click()

    time.sleep(200 / 1000.0)
    key_down("A"); time.sleep(208 / 1000.0)
    key_down("W"); time.sleep(48 / 1000.0)
    key_up("A"); time.sleep(460 / 1000.0)
    key_down("W"); time.sleep(28 / 1000.0)
    time.sleep(33 / 1000.0)
    key_down("W"); time.sleep(30 / 1000.0)
    time.sleep(26 / 1000.0)
    key_down("W"); time.sleep(34 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("W"); time.sleep(28 / 1000.0)
    time.sleep(36 / 1000.0)
    key_down("W"); time.sleep(26 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("W"); time.sleep(27 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("W"); time.sleep(35 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("W"); time.sleep(27 / 1000.0)
    time.sleep(35 / 1000.0)
    pyautogui.click()

    key_down("W"); time.sleep(27 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("W"); time.sleep(36 / 1000.0)
    time.sleep(1 / 1000.0)
    key_up("W"); time.sleep(276 / 1000.0)
    key_down("W"); time.sleep(105 / 1000.0); key_up("W")
    time.sleep(27 / 1000.0)
    pyautogui.click()
    time.sleep(34 / 1000.0)
    key_down("W"); time.sleep(501 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("W"); time.sleep(29 / 1000.0)
    time.sleep(19 / 1000.0)
    key_down("A"); time.sleep(506 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(34 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(34 / 1000.0)
    time.sleep(2 / 1000.0)
    key_up("A"); time.sleep(172 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    key_up("W"); time.sleep(479 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(35 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(36 / 1000.0)
    key_down("A"); time.sleep(7 / 1000.0)
    key_down("W"); time.sleep(355 / 1000.0)
    key_up("W"); time.sleep(416 / 1000.0)
    key_down("W"); time.sleep(47 / 1000.0); key_up("W")
    time.sleep(70 / 1000.0)
    key_up("A"); time.sleep(147 / 1000.0)
    pyautogui.click()
    time.sleep(56 / 1000.0)
    key_down("W"); time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(230 / 1000.0)
    key_up("W"); time.sleep(91 / 1000.0)
    key_down("W"); time.sleep(26 / 1000.0); key_up("W")
    time.sleep(576 / 1000.0)
    key_down("W"); time.sleep(105 / 1000.0); key_up("W")
    time.sleep(70 / 1000.0)
    key_up("A"); time.sleep(332 / 1000.0)
    pyautogui.click()
    time.sleep(14 / 1000.0)
    key_down("W"); time.sleep(69 / 1000.0)
    key_down("A"); time.sleep(292 / 1000.0)
    key_up("W"); time.sleep(215 / 1000.0)
    key_down("A"); time.sleep(27 / 1000.0)
    time.sleep(31 / 1000.0)
    key_down("A"); time.sleep(32 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(33 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    time.sleep(33 / 1000.0)
    key_down("A"); time.sleep(30 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(19 / 1000.0)
    key_up("A"); time.sleep(981 / 1000.0)
    pyautogui.click()
    time.sleep(308 / 1000.0)
    key_down("F1"); time.sleep(137 / 1000.0); key_up("F1")
    time.sleep(1715 / 1000.0)
    time.sleep(168 / 1000.0)
    key_down("6"); time.sleep(124 / 1000.0); key_up("6")
    time.sleep(306 / 1000.0)
    pyautogui.click()
    time.sleep(758 / 1000.0)
    key_down("CapsLock"); time.sleep(260 / 1000.0); key_up("CapsLock")
    time.sleep(647 / 1000.0)
    key_down("D"); time.sleep(257 / 1000.0); key_up("D")
    time.sleep(90 / 1000.0)
    pyautogui.click()
    time.sleep(112 / 1000.0)
    key_down("D"); time.sleep(402 / 1000.0); key_up("D")
    time.sleep(334 / 1000.0)
    pyautogui.click()
    time.sleep(114 / 1000.0)
    key_down("D"); time.sleep(400 / 1000.0); key_up("D")
    time.sleep(77 / 1000.0)
    pyautogui.click()
    time.sleep(500 / 1000.0)
    key_down("F2"); time.sleep(50 / 1000.0); key_up("F2")
    time.sleep(1182 / 1000.0)
    key_down("7"); time.sleep(50 / 1000.0); key_up("7")
    time.sleep(361 / 1000.0)
    key_down("D"); time.sleep(195 / 1000.0); key_up("D")
    time.sleep(333 / 1000.0)
    pyautogui.click()
    time.sleep(84 / 1000.0)
    key_down("A"); time.sleep(507 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(34 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(27 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(27 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(35 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(1 / 1000.0)
    key_down("S"); time.sleep(103 / 1000.0)
    key_up("A"); time.sleep(27 / 1000.0)
    key_up("S"); time.sleep(307 / 1000.0)
    pyautogui.click()
    time.sleep(376 / 1000.0)
    key_down("A"); time.sleep(478 / 1000.0)
    pyautogui.mouseDown(); time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    time.sleep(13 / 1000.0)
    pyautogui.mouseUp(); time.sleep(14 / 1000.0)
    key_down("A"); time.sleep(34 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    time.sleep(34 / 1000.0)
    key_down("A"); time.sleep(27 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(27 / 1000.0)
    key_down("A"); time.sleep(35 / 1000.0)
    time.sleep(29 / 1000.0)
    key_down("A"); time.sleep(29 / 1000.0)
    pyautogui.mouseDown(); time.sleep(1 / 1000.0)
    key_down("A"); time.sleep(32 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(6 / 1000.0)
    pyautogui.mouseUp(); time.sleep(21 / 1000.0)
    key_down("A"); time.sleep(35 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("A"); time.sleep(28 / 1000.0)
    time.sleep(35 / 1000.0)
    key_down("A"); time.sleep(21 / 1000.0)
    key_down("S"); time.sleep(200 / 1000.0)
    pyautogui.mouseDown(); time.sleep(28 / 1000.0)
    key_up("A"); time.sleep(62 / 1000.0)
    pyautogui.mouseUp(); time.sleep(216 / 1000.0)
    key_down("S"); time.sleep(34 / 1000.0)
    time.sleep(28 / 1000.0)
    key_down("S"); time.sleep(28 / 1000.0)
    key_up("S"); time.sleep(2 / 1000.0)
    pyautogui.click()
    time.sleep(126 / 1000.0)
    key_down("D"); time.sleep(165 / 1000.0)
    key_down("W"); time.sleep(70 / 1000.0)
    pyautogui.click()
    time.sleep(347 / 1000.0)
    key_down("W"); time.sleep(28 / 1000.0)
    time.sleep(35 / 1000.0)
    pyautogui.mouseDown(); time.sleep(2 / 1000.0)
    key_down("W"); time.sleep(25 / 1000.0)
    time.sleep(36 / 1000.0)
    key_down("W"); time.sleep(13 / 1000.0)
    key_up("W"); time.sleep(23 / 1000.0)
    pyautogui.mouseUp(); time.sleep(393 / 1000.0)
    pyautogui.click()
    time.sleep(147 / 1000.0)
    key_down("W"); time.sleep(160 / 1000.0); key_up("W")
    time.sleep(249 / 1000.0)
    pyautogui.click()
    time.sleep(202 / 1000.0)
    key_down("W"); time.sleep(145 / 1000.0)
    pyautogui.click()
    time.sleep(34 / 1000.0)
    key_up("W"); time.sleep(244 / 1000.0)
    pyautogui.click()
    time.sleep(286 / 1000.0)
    key_down("W"); time.sleep(62 / 1000.0)
    pyautogui.click()
    time.sleep(374 / 1000.0)
    pyautogui.mouseDown(); time.sleep(7 / 1000.0)
    key_down("W"); time.sleep(34 / 1000.0)
    time.sleep(7 / 1000.0)
    key_up("W"); time.sleep(23 / 1000.0)
    pyautogui.mouseUp(); time.sleep(2 / 1000.0)
    key_up("D"); time.sleep(2830 / 1000.0)
    key_down("F4"); time.sleep(152 / 1000.0); key_up("F4")

    print("✅ 建造西方节日完成")


def capture_game_window(hwnd):
    with CAPTURE_LOCK:
        return war_table.capture_game_window(hwnd)


def load_template_cached(template_path):
    if template_path in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[template_path]
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板图片不存在：{template_path}")
    img = np.array(Image.open(template_path).convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    TEMPLATE_CACHE[template_path] = img
    return img


def interruptible_sleep(seconds):
    """Sleep in short slices so recovery requests are handled promptly."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        raise_if_recovery_requested()
        time.sleep(min(0.5, deadline - time.monotonic()))


def find_game_window_or_none():
    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    return hwnd or None


def focus_game_window(hwnd):
    if not hwnd or not win32gui.IsWindow(hwnd):
        raise RecoveryRequested("DD2游戏窗口已经消失")
    war_table.focus_game_window(hwnd)
    return hwnd


def find_template_match(hwnd, template_path, threshold=MAP_MATCH_THRESHOLD,
                        right_half=False):
    """Find a template in the game window and return screen/frame coordinates."""
    frame = capture_game_window(hwnd)
    frame_h, frame_w = frame.shape[:2]
    offset_x = frame_w // 2 if right_half else 0
    search_frame = frame[:, offset_x:] if right_half else frame
    template = load_template_cached(template_path)
    rect = war_table.find_template_rect(
        search_frame,
        template,
        threshold=threshold,
    )
    if rect is None:
        return None

    frame_x = rect["center_x"] + offset_x
    frame_y = rect["center_y"]
    win_left, win_top, _, _ = get_window_rect(hwnd)
    return {
        "screen_x": win_left + frame_x,
        "screen_y": win_top + frame_y,
        "frame_x": frame_x,
        "frame_y": frame_y,
        "frame_width": frame_w,
        "frame_height": frame_h,
        "confidence": rect["max_val"],
    }


def wait_for_template(hwnd, template_path, label, timeout_seconds,
                      threshold=MAP_MATCH_THRESHOLD, right_half=False,
                      retry_seconds=1.0):
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while time.monotonic() < deadline:
        raise_if_recovery_requested()
        if not find_game_window_or_none():
            raise RecoveryRequested(f"等待{label}时DD2游戏窗口消失")
        attempt += 1
        match = find_template_match(
            hwnd,
            template_path,
            threshold=threshold,
            right_half=right_half,
        )
        if match is not None:
            print(
                f"[选图] 找到{label}，置信度={match['confidence']:.3f}，"
                f"坐标=({match['screen_x']}, {match['screen_y']})"
            )
            return match
        if attempt == 1 or attempt % 10 == 0:
            elapsed = timeout_seconds - max(0.0, deadline - time.monotonic())
            print(f"[选图] 尚未找到{label}，已等待 {elapsed:.0f} 秒")
        interruptible_sleep(retry_seconds)
    return None


def click_match(match, clicks=1):
    humanized_move_to(match["screen_x"], match["screen_y"])
    time.sleep(random.uniform(0.1, 0.25))
    pyautogui.click(clicks=clicks, interval=0.2)


def walk_to_war_table_without_open(hwnd):
    """Reach the War Table and stop when E-tip is visible, without pressing E."""
    print("[寻路] 开始识别 War Table，并移动到 E-tip 可见的位置")
    focus_game_window(hwnd)
    deadline = time.monotonic() + 180.0
    scan_round = 0

    while time.monotonic() < deadline:
        raise_if_recovery_requested()
        if not find_game_window_or_none():
            raise RecoveryRequested("寻找War Table时游戏窗口消失")

        table = war_table.detect_war_table(hwnd)
        if table is not None:
            print(
                f"[寻路] 找到 War Table，置信度={table[2]:.3f}，"
                "先连续按 4 次 W 靠近"
            )
            for _ in range(4):
                raise_if_recovery_requested()
                war_table.move_forward_once()
                interruptible_sleep(0.4)

            print("[寻路] 4 次 W 完成，停顿 0.5 秒后识别 E-tip")
            interruptible_sleep(0.5)
            e_tip = war_table.detect_e_tip(hwnd)
            if e_tip is not None:
                print(
                    f"[寻路] 已识别 E-tip，置信度={e_tip[2]:.3f}；"
                    "已到达 War Table 交互位置"
                )
                return True

            print("[寻路] 尚未识别到 E-tip，改为每前进 1 次识别一次")
            for walk_step in range(1, 11):
                raise_if_recovery_requested()
                if not find_game_window_or_none():
                    raise RecoveryRequested("寻找E-tip时游戏窗口消失")
                war_table.move_forward_once()
                interruptible_sleep(0.5)
                e_tip = war_table.detect_e_tip(hwnd)
                if e_tip is not None:
                    print(
                        f"[寻路] 继续前进 {walk_step} 次后识别到 E-tip，"
                        f"置信度={e_tip[2]:.3f}"
                    )
                    return True
            raise RecoveryRequested("连续前进10次仍未识别到E-tip")

        scan_round += 1
        print(f"[寻路] 未找到 War Table，第 {scan_round} 次扫描")
        if scan_round % 2:
            war_table.left_scan_once()
        else:
            war_table.right_scan_once()
        if scan_round >= 6:
            war_table.move_forward_once()
            scan_round = 0

        interruptible_sleep(0.3)

    raise RecoveryRequested("180秒内未能走到War Table的E-tip位置")


def select_wild_west_map(hwnd):
    """Open the War Table and create a Chaos 1 Wild West game."""
    print("[选图] War Table 前置流程完成，按 E 打开 War Table")
    humanized_press("E")
    interruptible_sleep(random.uniform(2.0, 3.0))
    print("[选图] 按 Q 打开地图选择")
    humanized_press("Q")
    interruptible_sleep(random.uniform(2.0, 3.0))
    print("[选图] 按 E 确认进入地图列表")
    humanized_press("E")
    interruptible_sleep(2.0)

    wild_west = wait_for_template(
        hwnd, TEMPLATE_WILD_WEST, "wildwest", 60.0
    )
    if wild_west is None:
        raise RecoveryRequested("60秒内未找到wildwest")
    click_match(wild_west)
    interruptible_sleep(2.0)

    stage = wait_for_template(
        hwnd, TEMPLATE_WILD_WEST_STAGE, "wildwest-1", 60.0
    )
    if stage is None:
        raise RecoveryRequested("60秒内未找到wildwest-1")
    stage["screen_y"] -= int(stage["frame_height"] * 0.03)
    print("[选图] 点击 wildwest-1 正上方游戏高度3%的位置")
    click_match(stage)
    interruptible_sleep(2.0)

    chaos1 = wait_for_template(
        hwnd,
        TEMPLATE_CHAOS1_BEGIN,
        "chaos1_begin",
        60.0,
        right_half=True,
    )
    if chaos1 is None:
        raise RecoveryRequested("60秒内未在游戏右半侧找到chaos1_begin")
    chaos1["screen_x"] += int(chaos1["frame_width"] * 0.065)
    print("[选图] 点击 chaos1_begin 右侧游戏宽度6.5%的位置，共7次，每次间隔1-2秒")
    for click_index in range(7):
        click_match(chaos1)
        if click_index < 6:
            interruptible_sleep(random.uniform(1.0, 2.0))
    interruptible_sleep(2.0)

    for template_path, label in (
        (TEMPLATE_BROWSE, "BROWSE"),
        (TEMPLATE_CREATE, "create"),
    ):
        match = wait_for_template(hwnd, template_path, label, 60.0)
        if match is None:
            raise RecoveryRequested(f"60秒内未找到{label}")
        click_match(match)
        interruptible_sleep(2.0)

    private_game = find_template_match(hwnd, TEMPLATE_PRIVATE_GAME)
    if private_game is not None:
        print(
            f"[选图] 找到privitegame，置信度="
            f"{private_game['confidence']:.3f}，点击一次"
        )
        click_match(private_game)
    else:
        print("[选图] 未找到privitegame，直接继续识别go_begin")

    go_begin = wait_for_template(
        hwnd,
        TEMPLATE_GO_BEGIN,
        "go_begin",
        60.0,
    )
    if go_begin is None:
        raise RecoveryRequested("60秒内未找到go_begin")
    click_match(go_begin)
    interruptible_sleep(2.0)

    print("[进图] 已点击 go_begin，等待 core 出现")
    core = wait_for_template(hwnd, TEMPLATE_CORE, "core", 240.0)
    if core is None:
        raise RecoveryRequested("240秒内未识别到core，地图未正常进入")
    print("[进图] 已识别 core，正式进入西方世界")
    return True


def prepare_and_enter_wild_west(hwnd):
    focus_game_window(hwnd)
    walk_to_war_table_without_open(hwnd)
    select_wild_west_map(hwnd)


def wait_for_private_tavern_and_war_table(hwnd):
    """After login, enter Private Tavern and wait until War Table is visible."""
    focus_game_window(hwnd)
    win_left, win_top, width, height = get_window_rect(hwnd)
    center_x = win_left + width // 2
    center_y = win_top + height // 2

    print("[恢复] 等待并点击私人城镇")
    tavern_clicked = False
    for attempt in range(30):
        if not find_game_window_or_none():
            return False
        try:
            if war_table.detect_war_table(hwnd) is not None:
                print("[恢复] 已经位于私人城堡并识别到 War Table")
                return True
        except Exception:
            pass

        war_table._click_at(center_x, center_y, delay=1.0)
        tavern_pos = war_table._find_image_on_screen(
            war_table.TEMPLATE_PRIVATE_TAVERN,
            threshold=0.6,
        )
        if tavern_pos:
            print(
                f"[恢复] 找到私人城镇，位置="
                f"({tavern_pos[0]}, {tavern_pos[1]})"
            )
            war_table._click_at(tavern_pos[0], tavern_pos[1], delay=0.5)
            tavern_clicked = True
            break
        print(f"[恢复] 未找到私人城镇，重试 {attempt + 1}/30")
        time.sleep(2.0)

    if not tavern_clicked:
        print("[恢复] 未点击到私人城镇，恢复本轮失败")
        return False

    print("[恢复] 等待私人城堡加载并识别 War Table")
    for attempt in range(36):
        if not find_game_window_or_none():
            return False
        try:
            table = war_table.detect_war_table(hwnd)
        except Exception as exc:
            print(f"[恢复] War Table检测暂时失败: {exc}")
            table = None
        if table is not None:
            print(
                f"[恢复] 已进入私人城堡，War Table置信度={table[2]:.3f}"
            )
            return True
        print(f"[恢复] 尚未识别到 War Table，重试 {attempt + 1}/36")
        time.sleep(5.0)
    return False


def restart_game_to_private_tavern():
    """Run the shared freeze restart flow and return in Private Tavern."""
    stop_settlement_watch()
    WINDOW_GUARD_ACTIVE.clear()
    release_all_inputs()
    print("[恢复] 执行卡死流程：关闭DD2并通过Steam重新启动")
    war_table.close_dd2_game()
    clear_recovery_request()
    war_table.STOP_FLAG = False
    hwnd = war_table._launch_game_via_steam_until_window("[West恢复]")
    if not hwnd:
        return None

    WINDOW_GUARD_ACTIVE.set()
    if not wait_for_private_tavern_and_war_table(hwnd):
        return None
    return hwnd


def watchdog_loop():
    """Monitor crashes, network failure, and 30 minutes without settlement."""
    next_network_check = time.monotonic()
    while not WATCHDOG_STOP.is_set() and not war_table.STOP_FLAG:
        now = time.monotonic()

        if WINDOW_GUARD_ACTIVE.is_set():
            hwnd = find_game_window_or_none()
            if not hwnd:
                request_recovery("DD2游戏窗口消失或游戏闪退")
            elif now >= next_network_check:
                next_network_check = now + NETWORK_CHECK_INTERVAL_SECONDS
                try:
                    match = find_template_match(
                        hwnd,
                        TEMPLATE_CONNECTION_FAILED,
                        threshold=CONNECTION_FAILED_THRESHOLD,
                    )
                    if match is not None:
                        request_recovery(
                            "检测到网络连接中断 connectionfailed.png"
                        )
                except Exception as exc:
                    print(f"[网络检测] 本次截图失败，60秒后重试: {exc}")
        else:
            next_network_check = now

        if SETTLEMENT_WATCH_ACTIVE.is_set():
            idle_seconds = seconds_since_last_settlement(now)
            if idle_seconds >= NO_SETTLEMENT_TIMEOUT_SECONDS:
                request_recovery(
                    f"连续 {idle_seconds / 60:.1f} 分钟未识别到结算画面"
                )

        WATCHDOG_STOP.wait(0.5)


def start_watchdog():
    thread = threading.Thread(
        target=watchdog_loop,
        name="west-build-watchdog",
        daemon=True,
    )
    thread.start()
    return thread


def click_replay_button(hwnd):
    client_rect = win32gui.GetClientRect(hwnd)
    client_width, client_height = client_rect[2], client_rect[3]
    rel_x = (0.6 + 0.68) / 2
    rel_y = (0.88 + 0.91) / 2
    client_x = int(rel_x * client_width)
    client_y = int(rel_y * client_height)
    screen_x, screen_y = win32gui.ClientToScreen(
        hwnd,
        (client_x, client_y),
    )
    humanized_move_to(screen_x, screen_y)
    time.sleep(random.uniform(0.8, 1.2))
    pyautogui.click()


def wait_for_core_after_replay(hwnd):
    interruptible_sleep(5.0)
    core = wait_for_template(hwnd, TEMPLATE_CORE, "core", 240.0)
    if core is None:
        raise RecoveryRequested("Replay后240秒内未识别到core")
    print("[循环] Replay后已识别core，开始下一轮")


def run_current_round(hwnd):
    print("🚀 开始执行建造流程...")
    build_western_festival()
    raise_if_recovery_requested()
    print("[卖装备] 已按 F4 切换人物，等待2秒后开始卖装备")
    interruptible_sleep(2.0)
    war_table.sell_equipment()
    raise_if_recovery_requested()
    print("[战斗] 卖装备完成，按 0 正式开始")
    interruptible_sleep(1.0)
    humanized_press("0")
    interruptible_sleep(1.0)


def run_gameplay_loop(hwnd, stats):
    start_settlement_watch()
    run_current_round(hwnd)
    print("🔄 进入结算/replay循环监测...")

    while True:
        raise_if_recovery_requested()
        if not find_game_window_or_none():
            raise RecoveryRequested("地图循环中DD2游戏窗口消失")
        interruptible_sleep(3.0)

        extra_reward = locate_image(
            hwnd,
            TEMPLATE_EXTRA_REWARD,
            '额外奖励区域',
            confidence=0.8,
        )
        if extra_reward:
            mark_settlement_seen("额外奖励")
            print("🎁 额外奖励")
            interruptible_sleep(3.0)
            humanized_press("ENTER")
            interruptible_sleep(3.0)

        replay = locate_image(
            hwnd,
            TEMPLATE_REPLAY,
            'replay区域',
            confidence=0.8,
        )
        if replay:
            mark_settlement_seen("replay")
            print(f"🔄 replay，第{stats['round']}轮完成")
            interruptible_sleep(3.0)
            click_replay_button(hwnd)
            wait_for_core_after_replay(hwnd)
            run_current_round(hwnd)
            stats["round"] += 1
        else:
            interruptible_sleep(1.0)
            failure = locate_image(
                hwnd,
                TEMPLATE_FAILURE_RETRY,
                '失败重来区域',
                confidence=0.8,
            )
            if failure:
                mark_settlement_seen("失败重来")
                print("💀 失败，重来")
                interruptible_sleep(2.0)
                humanized_press("N")
                interruptible_sleep(3.0)

                print("🔍 等待replay界面...")
                replay_found = False
                for _ in range(20):
                    raise_if_recovery_requested()
                    replay = locate_image(
                        hwnd,
                        TEMPLATE_REPLAY,
                        'replay区域',
                        confidence=0.8,
                    )
                    if replay:
                        mark_settlement_seen("失败后的replay")
                        print("✅ 找到replay按钮")
                        click_replay_button(hwnd)
                        replay_found = True
                        break
                    interruptible_sleep(3.0)
                if not replay_found:
                    raise RecoveryRequested("失败后60秒内未找到replay按钮")

                wait_for_core_after_replay(hwnd)
                run_current_round(hwnd)
                stats["round"] += 1
                stats["failures"] += 1

        humanized_press("0")
        print(
            f"第 {stats['round']} 轮, "
            f"失败: {stats['failures']}"
        )


def main():
    print("=" * 66)
    print("  DD2 西方世界建造脚本 - 自动启动、进图与卡死恢复版")
    print("=" * 66)
    print("- 有游戏窗口：直接寻找 War Table")
    print("- 无游戏窗口：执行 Steam 卡死恢复并进入私人城堡")
    print("- 每轮建造宏结束并按 F4 后，执行无限爬塔卖装备流程")
    print("- 网络中断：每60秒识别 connectionfailed.png")
    print("- 30分钟未识别结算画面：自动重启")
    print("- F12：立即停止脚本")

    required_templates = (
        war_table.CONFIG["backpack1_template"],
        war_table.CONFIG["backpack2_template"],
        war_table.CONFIG["level10_equipment_template"],
        TEMPLATE_EXTRA_REWARD,
        TEMPLATE_REPLAY,
        TEMPLATE_FAILURE_RETRY,
        TEMPLATE_WILD_WEST,
        TEMPLATE_WILD_WEST_STAGE,
        TEMPLATE_CHAOS1_BEGIN,
        TEMPLATE_BROWSE,
        TEMPLATE_CREATE,
        TEMPLATE_PRIVATE_GAME,
        TEMPLATE_GO_BEGIN,
        TEMPLATE_CORE,
        TEMPLATE_CONNECTION_FAILED,
    )
    missing_templates = [
        path for path in required_templates if not os.path.exists(path)
    ]
    if missing_templates:
        print("[ERROR] 以下模板文件不存在：")
        for path in missing_templates:
            print(f"  {path}")
        return

    war_table.STOP_FLAG = False
    war_table.register_stop_hotkey()
    war_table.enable_system_keep_awake()
    start_watchdog()

    stats = {"round": 1, "failures": 0}
    recovery_required = find_game_window_or_none() is None
    if recovery_required:
        print("[启动] 未检测到DD2窗口，按一次卡死流程处理")
    else:
        print("[启动] 已检测到DD2窗口，直接进入War Table流程")

    try:
        while not war_table.STOP_FLAG:
            stop_settlement_watch()

            try:
                if recovery_required:
                    hwnd = restart_game_to_private_tavern()
                    if not hwnd:
                        print("[恢复] 本次恢复失败，10秒后继续重试")
                        time.sleep(10.0)
                        continue
                    recovery_required = False
                else:
                    clear_recovery_request()
                    hwnd = find_game_window_or_none()
                    if not hwnd:
                        raise RecoveryRequested(
                            "启动或循环阶段未检测到DD2游戏窗口"
                        )
                    WINDOW_GUARD_ACTIVE.set()
                    focus_game_window(hwnd)

                l, t, w, h = get_window_rect(hwnd)
                print(
                    f"[启动] 游戏窗口句柄={hwnd}，"
                    f"位置=({l}, {t})，尺寸={w}x{h}"
                )
                prepare_and_enter_wild_west(hwnd)
                run_gameplay_loop(hwnd, stats)

            except RecoveryRequested as exc:
                stop_settlement_watch()
                WINDOW_GUARD_ACTIVE.clear()
                release_all_inputs()
                print(f"[卡死检测] 主流程中断：{exc}")
                recovery_required = True
            except Exception as exc:
                stop_settlement_watch()
                WINDOW_GUARD_ACTIVE.clear()
                release_all_inputs()
                print(f"[ERROR] 主流程异常，转入卡死恢复：{exc}")
                recovery_required = True

    except KeyboardInterrupt:
        print("\n[INFO] 收到 Ctrl+C，脚本停止")
    finally:
        WATCHDOG_STOP.set()
        stop_settlement_watch()
        WINDOW_GUARD_ACTIVE.clear()
        release_all_inputs()
        war_table.disable_system_keep_awake()


if __name__ == "__main__":
    main()
