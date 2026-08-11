import os
import time
import random
import win32api
import win32con
import win32gui
import win32ui
import pyautogui
import cv2
import numpy as np
import ctypes
import mss
from PIL import Image

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

SCRIPT_DIR = r"D:\DD2脚本"
TEMPLATE_BACKPACK1 = os.path.join(SCRIPT_DIR, "背包1.png")
TEMPLATE_BACKPACK2 = os.path.join(SCRIPT_DIR, "背包2.png")
TEMPLATE_LEVEL10 = os.path.join(SCRIPT_DIR, "10级装备.png")
TEMPLATE_CACHE = {}
MATCH_THRESHOLD = 0.6


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
    hdc_window = win32gui.GetDC(hwnd)
    hdc_mem = win32gui.CreateCompatibleDC(hdc_window)
    hbmp = win32gui.CreateCompatibleBitmap(hdc_window, width, height)
    old_bmp = win32gui.SelectObject(hdc_mem, hbmp)
    
    win32gui.BitBlt(hdc_mem, 0, 0, width, height, hdc_window, left, top, win32con.SRCCOPY)
    
    hbmp_obj = win32ui.CreateBitmapFromHandle(hbmp)
    bmp_str = hbmp_obj.GetBitmapBits(True)
    img = np.frombuffer(bmp_str, dtype=np.uint8).reshape((height, width, 4))
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    
    win32gui.SelectObject(hdc_mem, old_bmp)
    win32gui.DeleteObject(hbmp)
    win32gui.DeleteDC(hdc_mem)
    win32gui.ReleaseDC(hwnd, hdc_window)
    
    return img


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
    time.sleep(actual)


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
    key_down("W"); time.sleep(450 / 1000.0); key_up("W")
    time.sleep(270 / 1000.0)
    key_down("Space"); time.sleep(103 / 1000.0); key_up("Space")
    time.sleep(633 / 1000.0)
    key_down("W"); time.sleep(75 / 1000.0); key_up("W")
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
    time.sleep(2079 / 1000.0)

    print("✅ 建造西方节日完成")


def capture_game_window(hwnd):
    x, y, width, height = get_window_rect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("游戏窗口尺寸无效")
    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": width, "height": height}
        img = np.array(sct.grab(monitor))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def load_template_cached(template_path):
    if template_path in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[template_path]
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板图片不存在：{template_path}")
    img = np.array(Image.open(template_path).convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    TEMPLATE_CACHE[template_path] = img
    return img


def find_template_in_region(frame_bgr, template_bgr, region=None, threshold=None, skip_positions=None, skip_radius=30):
    if threshold is None:
        threshold = MATCH_THRESHOLD
    if region is not None:
        rx0, ry0, rx1, ry1 = region
        search_frame = frame_bgr[ry0:ry1, rx0:rx1]
    else:
        search_frame = frame_bgr
        rx0, ry0 = 0, 0
    result = cv2.matchTemplate(search_frame, template_bgr, cv2.TM_CCOEFF_NORMED)
    th, tw = template_bgr.shape[:2]
    if skip_positions:
        for (sx, sy) in skip_positions:
            local_x = sx - rx0
            local_y = sy - ry0
            mask_x0 = max(0, local_x - skip_radius)
            mask_y0 = max(0, local_y - skip_radius)
            mask_x1 = min(result.shape[1], local_x + skip_radius)
            mask_y1 = min(result.shape[0], local_y + skip_radius)
            result[mask_y0:mask_y1, mask_x0:mask_x1] = -1.0
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < threshold:
        return None
    center_x = max_loc[0] + tw // 2 + rx0
    center_y = max_loc[1] + th // 2 + ry0
    return center_x, center_y, max_val


def find_template_on_screen(hwnd, template_path, threshold=None):
    frame = capture_game_window(hwnd)
    template = load_template_cached(template_path)
    win_left, win_top, _, _ = get_window_rect(hwnd)
    result = find_template_in_region(frame, template, threshold=threshold)
    if result is None:
        return None
    cx, cy, conf = result
    return win_left + cx, win_top + cy, conf


def find_template_in_backpack(hwnd, template_path, threshold=None, skip_positions=None):
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]
    template = load_template_cached(template_path)
    x0 = int(w * 0.50)
    y0 = int(h * 0.15)
    x1 = int(w * 0.95)
    y1 = int(h * 0.90)
    win_left, win_top, _, _ = get_window_rect(hwnd)
    frame_skip = None
    if skip_positions:
        frame_skip = [(sx - win_left, sy - win_top) for (sx, sy) in skip_positions]
    result = find_template_in_region(frame, template, region=(x0, y0, x1, y1), threshold=threshold, skip_positions=frame_skip)
    if result is None:
        return None
    cx, cy, conf = result
    return win_left + cx, win_top + cy, conf


def click_backpack1(hwnd):
    result = find_template_on_screen(hwnd, TEMPLATE_BACKPACK1)
    if result is None:
        print("[WARN] 未找到背包1按钮图像")
        return False
    sx, sy, conf = result
    print(f"[INFO] 找到背包1，屏幕坐标=({sx}, {sy})，置信度={conf:.3f}")
    humanized_move_to(sx, sy)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.click()
    time.sleep(random.uniform(0.8, 1.2))
    return True


def find_backpack2(hwnd):
    result = find_template_on_screen(hwnd, TEMPLATE_BACKPACK2)
    if result is None:
        result = find_template_on_screen(hwnd, TEMPLATE_BACKPACK2, threshold=0.4)
    if result is None:
        print("[WARN] 未找到背包2按钮图像")
        return None
    sx, sy, conf = result
    print(f"[INFO] 找到背包2，屏幕坐标=({sx}, {sy})，置信度={conf:.3f}")
    return sx, sy


def find_level10_equipment(hwnd, skip_positions=None):
    key_down("SHIFT")
    time.sleep(random.uniform(0.8, 1.2))
    result = find_template_in_backpack(hwnd, TEMPLATE_LEVEL10, threshold=0.5, skip_positions=skip_positions)
    if result is not None:
        sx, sy, conf = result
        print(f"[INFO] 找到 10 级装备！屏幕坐标=({sx}, {sy})，置信度={conf:.3f}")
    else:
        print("[INFO] 未找到 10 级装备")
    key_up("SHIFT")
    time.sleep(random.uniform(0.4, 0.6))
    return result


def move_level10_to_backpack2(hwnd, equip_sx, equip_sy):
    humanized_move_to(equip_sx, equip_sy)
    time.sleep(random.uniform(0.8, 1.2))
    print("[INFO] 按 L 锁住装备")
    humanized_press("L")
    time.sleep(random.uniform(0.8, 1.2))
    print("[INFO] 左键点击装备（拿起）")
    pyautogui.click(button="left")
    time.sleep(random.uniform(1.2, 1.8))
    bp2_pos = find_backpack2(hwnd)
    if bp2_pos is None:
        print("[INFO] 等待1秒后重试查找背包2...")
        time.sleep(1.0)
        bp2_pos = find_backpack2(hwnd)
    if bp2_pos is None:
        print("[WARN] 未找到背包2")
        return False
    bp2_sx, bp2_sy = bp2_pos
    humanized_move_to(bp2_sx, bp2_sy)
    time.sleep(random.uniform(0.8, 1.2))
    print("[INFO] 右键点击背包2（放入装备）")
    pyautogui.click(button="right")
    time.sleep(random.uniform(0.8, 1.2))
    win_rect = get_window_rect(hwnd)
    safe_x = win_rect[0] + win_rect[2] // 4
    safe_y = win_rect[1] + win_rect[3] // 4
    humanized_move_to(safe_x, safe_y)
    time.sleep(random.uniform(0.8, 1.2))
    return True


def sell_all_equipment(hwnd):
    print("[INFO] 按 Y 批量出售装备...")
    humanized_press("Y")
    time.sleep(random.uniform(1.6, 2.4))
    print("[INFO] 按 ENTER 确认出售...")
    humanized_press("ENTER")
    time.sleep(random.uniform(1.6, 2.4))


def sell_equipment(hwnd):
    print("💰 开始卖装备环节（含10级装备保护）...")

    for name, path in [("背包1", TEMPLATE_BACKPACK1), ("背包2", TEMPLATE_BACKPACK2),
                        ("10级装备", TEMPLATE_LEVEL10)]:
        if not os.path.exists(path):
            print(f"[ERROR] 缺少模板文件：{name} = {path}")
            return

    print("1. 按 I 打开背包...")
    humanized_press("I")
    time.sleep(3.0)

    print("2. 图像识别并点击背包1...")
    if not click_backpack1(hwnd):
        print("[ERROR] 无法找到背包1，终止")
        return
    time.sleep(2.0)

    print("3. 循环检查10级装备并移到背包2...")
    moved_count = 0
    max_rounds = 20
    skip_positions = []

    for round_idx in range(max_rounds):
        print(f"--- 第 {round_idx + 1} 轮检查 ---")
        equip_result = find_level10_equipment(hwnd, skip_positions=skip_positions)
        if equip_result is None:
            print("[INFO] 没有更多10级装备，进入出售流程")
            break

        equip_sx, equip_sy, _ = equip_result
        success = move_level10_to_backpack2(hwnd, equip_sx, equip_sy)
        if success:
            moved_count += 1
            skip_positions.append((equip_sx, equip_sy))
            print(f"[INFO] 已移动第 {moved_count} 件10级装备到背包2")
        else:
            print("[WARN] 移动失败，跳过本轮")
        time.sleep(1.0)

    print(f"共移动 {moved_count} 件10级装备到背包2")

    print("4. 出售剩余装备...")
    sell_all_equipment(hwnd)

    print("5. 按 ESC 关闭背包...")
    humanized_press("ESC")
    time.sleep(random.uniform(1.6, 2.4))

    print(f"✅ 卖装备完成，共保护 {moved_count} 件10级装备")


def main():
    print("=" * 60)
    print("  DD2 挂机脚本 - 完整版")
    print("=" * 60)
    print("")

    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd == 0:
        print("❌ 找不到游戏窗口")
        return

    print(f"✅ 找到游戏窗口: {hwnd}")
    l, t, w, h = get_window_rect(hwnd)
    cw, ch = get_client_rect(hwnd)
    print(f"窗口位置: ({l}, {t}), 尺寸: {w}x{h}")
    print(f"客户区尺寸: {cw}x{ch}")
    print("")

    print("🔄 自动切换到游戏窗口...")
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    print("倒计时 5 秒，请确保游戏窗口在前台...")
    print("")
    for i in range(5, 0, -1):
        print(f"   {i}...")
        time.sleep(1)

    print("")
    print("🚀 开始执行建造流程...")

    build_western_festival()
    time.sleep(1.0)
    sell_equipment(hwnd)
    time.sleep(1.0)
    humanized_press("0")
    time.sleep(1.0)

    print("")
    print("🔄 进入循环监测...")
    k = 1
    m = 0

    try:
        while True:
            time.sleep(3.0)

            xy = locate_image(hwnd, r"D:\DD2脚本\额外奖励.png", '额外奖励区域', confidence=0.8)
            if xy:
                print("🎁 额外奖励")
                time.sleep(3.0)
                humanized_press("ENTER")
                time.sleep(3.0)

            xy = locate_image(hwnd, r"D:\DD2脚本\replay.png", 'replay区域', confidence=0.8)
            if xy:
                print("🔄 replay")
                print(f"第{k}轮完成")
                time.sleep(3.0)
                
                client_rect = win32gui.GetClientRect(hwnd)
                cw, ch = client_rect[2], client_rect[3]
                rel_x = (0.6 + 0.68) / 2
                rel_y = (0.88 + 0.91) / 2
                client_x = int(rel_x * cw)
                client_y = int(rel_y * ch)
                screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
                
                humanized_move_to(screen_x, screen_y)
                time.sleep(random.uniform(0.8, 1.2))
                pyautogui.click()
                humanized_sleep(50.0)

                print("🚀 重新开始")
                build_western_festival()
                time.sleep(1.0)
                sell_equipment(hwnd)
                time.sleep(2.0)
                humanized_press("0")
                k += 1
            else:
                time.sleep(1.0)

                xy = locate_image(hwnd, r"D:\DD2脚本\失败重来.png", '失败重来区域', confidence=0.8)
                if xy:
                    print("💀 失败，重来")
                    time.sleep(2.0)
                    humanized_press("N")
                    time.sleep(3.0)

                    print("🔍 等待replay界面...")
                    for _ in range(20):
                        xy_replay = locate_image(hwnd, r"D:\DD2脚本\replay.png", 'replay区域', confidence=0.8)
                        if xy_replay:
                            print("✅ 找到replay按钮")
                            
                            client_rect = win32gui.GetClientRect(hwnd)
                            cw, ch = client_rect[2], client_rect[3]
                            
                            rel_x = (0.6 + 0.68) / 2
                            rel_y = (0.88 + 0.91) / 2
                            client_x = int(rel_x * cw)
                            client_y = int(rel_y * ch)
                            
                            screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
                            
                            humanized_move_to(screen_x, screen_y)
                            time.sleep(random.uniform(0.8, 1.2))
                            pyautogui.click()
                            humanized_sleep(50.0)
                            break
                        time.sleep(3.0)
                    else:
                        print("⚠️ 未找到replay按钮，继续")

                    print("🚀 重新开始")
                    build_western_festival()
                    time.sleep(2.0)
                    sell_equipment(hwnd)
                    humanized_press("0")
                    k += 1
                    m += 1

            humanized_press("0")
            print(f"第 {k} 轮, 失败: {m}")

    except KeyboardInterrupt:
        print("")
        print("👋 退出")


if __name__ == "__main__":
    main()
