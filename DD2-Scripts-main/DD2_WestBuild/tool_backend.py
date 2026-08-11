# 你的原图素材文件夹（原按键精灵路径，不用移动图片）
PIC_ROOT = r"F:\DD2脚本"
import cv2
import numpy as np
import time
import random
import mss
import win32gui
import win32api
import win32con
from datetime import datetime

# ===================== 全局配置（只改这里） =====================
# 你的原图素材文件夹（原按键精灵路径，不用移动图片）
PIC_ROOT = r"F:\DD2脚本"
# 随机延迟浮动区间 ms
MIN_RAND = 50
MAX_RAND = 500
# 找图默认相似度
THRESHOLD_PIC = 0.8
# 多点找色颜色容差（偏色，对应按键精灵-101010）
COLOR_TOLERANCE = 12

# 游戏全局句柄
hwnd = 0

# ===================== 虚拟键码对照表（全部你的脚本用到按键） =====================
VK = {
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "A": 0x41, "S": 0x53, "D": 0x44, "W": 0x57,
    "Shift": 0x10, "Ctrl": 0x11, "Space": 0x20, "Enter": 0x0D,
    "Esc": 0x1B, "CapsLock": 0x14,
    "F1": 0x70, "F2": 0x71, "F4": 0x73,
    "L": 0x4C, "Y": 0x59, "N": 0x4E, "P": 0x50
}

# ===================== 窗口绑定（对应 Plugin.Window.Find） =====================
def bind_window(class_name: str, win_title: str):
    global hwnd
    hwnd = win32gui.FindWindow(class_name, win_title)
    if hwnd == 0:
        print(f"【错误】未找到窗口：{win_title} 类名：{class_name}")
        return False
    print(f"窗口绑定成功，句柄：{hwnd}")
    return True

# ===================== 随机延迟（对应 Function 随机延迟） =====================
def rand_delay(base_ms: int):
    """基础延时 + 随机浮动防检测，单位毫秒"""
    add_rand = random.randint(MIN_RAND, MAX_RAND)
    total_sec = (base_ms + add_rand) / 1000
    time.sleep(total_sec)

# ===================== 时间打印函数（对应 Function 时间） =====================
def print_time():
    now = datetime.now()
    a = f"{now.month}月{now.day}日 {now.hour}时{now.minute}分"
    print(f"【时间】{a}")
    return a

# ===================== 后台按键系列（对应 Plugin.Bkgnd.Keypress / KeyDown / KeyUp） =====================
def key_down(key_name: str):
    """后台按下按键不松开"""
    key_code = VK[key_name]
    win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, key_code, 0)

def key_up(key_name: str):
    """后台弹起按键"""
    key_code = VK[key_name]
    win32api.SendMessage(hwnd, win32con.WM_KEYUP, key_code, 0)

def key_press(key_name: str, hold_ms=200):
    """按一下自动松开，对应Bkgnd.Keypress"""
    key_down(key_name)
    rand_delay(hold_ms)
    key_up(key_name)

# ===================== 前台鼠标移动+点击（MoveTo LeftClick RightClick） =====================
def move_to(screen_x: int, screen_y: int, base_delay=300):
    """屏幕绝对坐标移动鼠标（你原脚本前台MoveTo）"""
    win32api.SetCursorPos((screen_x, screen_y))
    rand_delay(base_delay)

def left_click(base_delay=300):
    """左键单击"""
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    rand_delay(base_delay//2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    rand_delay(base_delay)

def left_down():
    """左键长按按下"""
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

def left_up():
    """左键松开"""
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def right_click(base_delay=300):
    """右键单击"""
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    rand_delay(base_delay//2)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
    rand_delay(base_delay)

# ===================== 后台窗口FindPic（对应 Plugin.Bkgnd.FindPic） =====================
def get_window_rect():
    return win32gui.GetWindowRect(hwnd)

def find_pic_backend(x1, y1, x2, y2, pic_name: str, threshold=THRESHOLD_PIC):
    """
    后台窗口找图，返回 (x|y) 找不到返回 "0|0"
    x1,y1,x2,y2：窗口内相对坐标范围
    """
    win_left, win_top, win_right, win_bottom = get_window_rect()
    win_w = win_right - win_left
    win_h = win_bottom - win_top
    # 截取游戏窗口画面
    with mss.mss() as sct:
        cap_area = {"top": win_top, "left": win_left, "width": win_w, "height": win_h}
        screen_img = sct.grab(cap_area)
        screen_np = np.array(screen_img)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_BGRA2BGR)

    template_path = f"{PIC_ROOT}/{pic_name}"
    template = cv2.imread(template_path)
    if template is None:
        print(f"【素材缺失】{template_path}")
        return "0|0"
    h_t, w_t = template.shape[:2]

    # 裁剪指定区域进行匹配
    crop = screen_bgr[y1:y2, x1:x2]
    res = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)
    points = list(zip(*loc[::-1]))
    if len(points) == 0:
        return "0|0"
    px, py = points[0]
    # 返回窗口内绝对坐标
    center_x = x1 + px + w_t // 2
    center_y = y1 + py + h_t // 2
    return f"{center_x}|{center_y}"

# ===================== 多点找色 FindMultiColor（完全复刻按键精灵逻辑） =====================
def hex_to_bgr(hex_str: str):
    """按键精灵BBGGRR十六进制转opencv BGR数组"""
    r = int(hex_str[4:6], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[0:2], 16)
    return np.array([b, g, r], dtype=np.int16)

def color_match(pixel, target_bgr, tolerance):
    """判断像素颜色是否匹配（带偏色容差）"""
    diff = abs(pixel.astype(np.int16) - target_bgr)
    return np.all(diff <= tolerance)

def find_multi_color(x1, y1, x2, y2, first_color_hex, offset_color_str, dir=0):
    """
    复刻按键精灵 FindMultiColor
    :param x1,y1,x2,y2: 查找窗口内区域
    :param first_color_hex: 主色十六进制 BBGGRR
    :param offset_color_str: 偏移色字符串 "0|6|FFFFFF,5|3|FFFFFF..."
    :return: 找到返回 (窗口内X,窗口内Y)，否则 (0,0)
    """
    win_left, win_top, win_right, win_bottom = get_window_rect()
    win_w = win_right - win_left
    win_h = win_bottom - win_top
    with mss.mss() as sct:
        cap_area = {"top": win_top, "left": win_left, "width": win_w, "height": win_h}
        screen_img = sct.grab(cap_area)
        screen_np = np.array(screen_img)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_BGRA2BGR)

    crop = screen_bgr[y1:y2, x1:x2]
    main_color = hex_to_bgr(first_color_hex)
    offset_list = []
    # 解析偏移色组
    group_strs = offset_color_str.split(",")
    for g in group_strs:
        ox, oy, hex_c = g.split("|")
        offset_list.append((int(ox), int(oy), hex_to_bgr(hex_c)))

    # 遍历裁剪区域像素寻找主色
    h_crop, w_crop = crop.shape[:2]
    for y in range(h_crop):
        for x in range(w_crop):
            px = crop[y, x]
            if not color_match(px, main_color, COLOR_TOLERANCE):
                continue
            # 主色匹配，校验所有偏移点
            all_match = True
            for ox_off, oy_off, tar_c in offset_list:
                nx = x + ox_off
                ny = y + oy_off
                if 0 <= nx < w_crop and 0 <= ny < h_crop:
                    npx = crop[ny, nx]
                    if not color_match(npx, tar_c, COLOR_TOLERANCE):
                        all_match = False
                        break
                else:
                    all_match = False
                    break
            if all_match:
                # 返回窗口内全局坐标
                win_x = x1 + x
                win_y = y1 + y
                return (win_x, win_y)
    return (0, 0)