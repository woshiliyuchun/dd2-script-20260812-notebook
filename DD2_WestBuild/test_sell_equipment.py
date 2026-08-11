import os
import time
import win32gui
import win32api
import win32con
import pyautogui
import cv2
import numpy as np
import mss
from PIL import Image

GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"

SCRIPT_DIR = r"D:\DD2脚本"
TEMPLATE_BACKPACK1 = os.path.join(SCRIPT_DIR, "\u80cc\u53051.png")
TEMPLATE_BACKPACK2 = os.path.join(SCRIPT_DIR, "\u80cc\u53052.png")
TEMPLATE_LEVEL10 = os.path.join(SCRIPT_DIR, "10\u7ea7\u88c5\u5907.png")

TEMPLATE_CACHE = {}
MATCH_THRESHOLD = 0.6


def get_window_rect(hwnd):
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (left, top, right - left, bottom - top)
    except:
        return (0, 0, 1920, 1080)


def get_client_rect(hwnd):
    try:
        rect = win32gui.GetClientRect(hwnd)
        return (rect[2], rect[3])
    except:
        return (1920, 1080)


def client_to_screen(hwnd, x, y):
    try:
        return win32gui.ClientToScreen(hwnd, (int(x), int(y)))
    except:
        return (int(x), int(y))


def relative_to_screen(hwnd, rel_x, rel_y):
    w, h = get_client_rect(hwnd)
    return client_to_screen(hwnd, rel_x * w, rel_y * h)


def click_relative(hwnd, rel_x, rel_y, clicks=1):
    x, y = relative_to_screen(hwnd, rel_x, rel_y)
    print(f"点击位置: ({x}, {y})")
    pyautogui.moveTo(x, y)
    pyautogui.click(clicks=clicks)


def key_down(key):
    if isinstance(key, str):
        upper = key.upper()
        if upper == "SPACE":
            vk = win32con.VK_SPACE
        elif upper == "ENTER":
            vk = win32con.VK_RETURN
        elif upper == "ESC":
            vk = win32con.VK_ESCAPE
        elif upper == "SHIFT":
            vk = win32con.VK_LSHIFT
        elif upper == "L":
            vk = ord("L")
        else:
            vk = ord(upper)
    else:
        vk = key
    win32api.keybd_event(vk, win32api.MapVirtualKey(vk, 0), 0, 0)


def key_up(key):
    if isinstance(key, str):
        upper = key.upper()
        if upper == "SPACE":
            vk = win32con.VK_SPACE
        elif upper == "ENTER":
            vk = win32con.VK_RETURN
        elif upper == "ESC":
            vk = win32con.VK_ESCAPE
        elif upper == "SHIFT":
            vk = win32con.VK_LSHIFT
        elif upper == "L":
            vk = ord("L")
        else:
            vk = ord(upper)
    else:
        vk = key
    win32api.keybd_event(vk, win32api.MapVirtualKey(vk, 0), win32con.KEYEVENTF_KEYUP, 0)


def load_template(template_path):
    if template_path in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[template_path]
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板图片不存在：{template_path}")
    img = np.array(Image.open(template_path).convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    TEMPLATE_CACHE[template_path] = img
    return img


def capture_game_window(hwnd):
    x, y, width, height = get_window_rect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("游戏窗口尺寸无效")
    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": width, "height": height}
        img = np.array(sct.grab(monitor))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


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
    # 屏蔽已处理过的位置
    if skip_positions:
        for (sx, sy) in skip_positions:
            # 将屏幕坐标转换为帧内搜索区域坐标
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
    template = load_template(template_path)
    win_left, win_top, _, _ = get_window_rect(hwnd)
    result = find_template_in_region(frame, template, threshold=threshold)
    if result is None:
        return None
    cx, cy, conf = result
    return win_left + cx, win_top + cy, conf


def find_template_in_backpack(hwnd, template_path, threshold=None, skip_positions=None):
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]
    template = load_template(template_path)
    x0 = int(w * 0.50)
    y0 = int(h * 0.15)
    x1 = int(w * 0.95)
    y1 = int(h * 0.90)
    win_left, win_top, _, _ = get_window_rect(hwnd)
    # 将屏幕坐标转换为帧坐标用于屏蔽
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
    pyautogui.moveTo(sx, sy, duration=0.1)
    pyautogui.click()
    time.sleep(1.0)
    return True


def find_backpack2(hwnd):
    result = find_template_on_screen(hwnd, TEMPLATE_BACKPACK2)
    if result is None:
        # 降低阈值重试
        result = find_template_on_screen(hwnd, TEMPLATE_BACKPACK2, threshold=0.4)
    if result is None:
        print("[WARN] 未找到背包2按钮图像")
        return None
    sx, sy, conf = result
    print(f"[INFO] 找到背包2，屏幕坐标=({sx}, {sy})，置信度={conf:.3f}")
    return sx, sy


def find_level10_equipment(hwnd, skip_positions=None):
    key_down("SHIFT")
    time.sleep(1.0)
    result = find_template_in_backpack(hwnd, TEMPLATE_LEVEL10, threshold=0.5, skip_positions=skip_positions)
    if result is not None:
        sx, sy, conf = result
        print(f"[INFO] 找到 10 级装备！屏幕坐标=({sx}, {sy})，置信度={conf:.3f}")
    else:
        print("[INFO] 未找到 10 级装备")
    key_up("SHIFT")
    time.sleep(0.5)
    return result


def move_level10_to_backpack2(hwnd, equip_sx, equip_sy):
    # 先移动鼠标到装备位置，让鼠标离开背包2
    pyautogui.moveTo(equip_sx, equip_sy, duration=0.1)
    time.sleep(1.0)
    print("[INFO] 按 L 锁住装备")
    key_down("L"); time.sleep(0.1); key_up("L")
    time.sleep(1.0)
    print("[INFO] 左键点击装备（拿起）")
    pyautogui.click(button="left")
    time.sleep(1.0)
    # 鼠标已离开背包2，现在查找背包2位置
    time.sleep(0.5)  # 等待游戏UI更新
    bp2_pos = find_backpack2(hwnd)
    if bp2_pos is None:
        # 等待更久再重试
        print("[INFO] 等待1秒后重试查找背包2...")
        time.sleep(1.0)
        bp2_pos = find_backpack2(hwnd)
    if bp2_pos is None:
        print("[WARN] 未找到背包2")
        return False
    bp2_sx, bp2_sy = bp2_pos
    pyautogui.moveTo(bp2_sx, bp2_sy, duration=0.1)
    time.sleep(1.0)
    print("[INFO] 右键点击背包2（放入装备）")
    pyautogui.click(button="right")
    time.sleep(1.0)
    # 移动后将鼠标移到安全位置，避免悬停影响下次检测
    win_rect = get_window_rect(hwnd)
    safe_x = win_rect[0] + win_rect[2] // 4
    safe_y = win_rect[1] + win_rect[3] // 4
    pyautogui.moveTo(safe_x, safe_y, duration=0.1)
    time.sleep(1.0)
    return True


def sell_all_equipment(hwnd):
    print("[INFO] 按 Y 批量出售装备...")
    key_down("Y"); time.sleep(0.1); key_up("Y")
    time.sleep(2.0)
    print("[INFO] 按 ENTER 确认出售...")
    key_down("ENTER"); time.sleep(0.1); key_up("ENTER")
    time.sleep(2.0)


def main():
    print("=" * 60)
    print("  DD2 卖装备（含10级装备保护）")
    print("=" * 60)
    print()

    for name, path in [("\u80cc\u53051", TEMPLATE_BACKPACK1), ("\u80cc\u53052", TEMPLATE_BACKPACK2),
                        ("10\u7ea7\u88c5\u5907", TEMPLATE_LEVEL10)]:
        if not os.path.exists(path):
            print(f"[ERROR] 缺少模板文件：{name} = {path}")
            return

    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd == 0:
        print("找不到游戏窗口")
        return

    print(f"找到游戏窗口: {hwnd}")
    l, t, w, h = get_window_rect(hwnd)
    print(f"窗口尺寸: {w}x{h}")
    print()

    print("倒计时 3 秒...")
    for i in range(3, 0, -1):
        print(f"   {i}...")
        time.sleep(1)

    print()
    print("1. 按 I 打开背包...")
    key_down("I"); time.sleep(0.1); key_up("I")
    time.sleep(3.0)

    print("2. 图像识别并点击背包1...")
    if not click_backpack1(hwnd):
        print("[ERROR] 无法找到背包1，终止")
        return
    time.sleep(2.0)

    print("3. 循环检查10级装备并移到背包2...")
    moved_count = 0
    max_rounds = 20
    skip_positions = []  # 记录已处理过的位置，避免重复匹配

    for round_idx in range(max_rounds):
        print(f"--- 第 {round_idx + 1} 轮检查 ---")

        # 每轮开始时按 SHIFT 查找10级装备
        equip_result = find_level10_equipment(hwnd, skip_positions=skip_positions)
        if equip_result is None:
            print("[INFO] 没有更多10级装备，进入出售流程")
            break

        equip_sx, equip_sy, _ = equip_result

        # 移动鼠标到装备位置，锁定拾取后再查找背包2
        success = move_level10_to_backpack2(hwnd, equip_sx, equip_sy)
        if success:
            moved_count += 1
            skip_positions.append((equip_sx, equip_sy))  # 记录已处理位置
            print(f"[INFO] 已移动第 {moved_count} 件10级装备到背包2")
        else:
            print("[WARN] 移动失败，跳过本轮")
        time.sleep(1.0)

    print(f"共移动 {moved_count} 件10级装备到背包2")

    print()
    print("4. 出售剩余装备...")
    sell_all_equipment(hwnd)

    print("5. 按 ESC 关闭背包...")
    key_down("ESC"); time.sleep(0.1); key_up("ESC")
    time.sleep(2.0)

    print()
    print(f"完成，共保护 {moved_count} 件10级装备")


if __name__ == "__main__":
    main()
