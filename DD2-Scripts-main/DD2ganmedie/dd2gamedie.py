import os
import time
import random
import win32api
import win32con
import win32gui
import win32process
import pyautogui
import cv2
import numpy as np
import mss
import subprocess

# ========dw============ 配置 ====================
GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"
GAME_PROCESS_NAME = "DD2"

SCRIPT_DIR = r"F:\DD2脚本\DD2ganmedie"
TEMPLATE_STOP = os.path.join(SCRIPT_DIR, "停止.png")
TEMPLATE_CONFIRM = os.path.join(SCRIPT_DIR, "确认.png")
TEMPLATE_START_GAME = os.path.join(SCRIPT_DIR, "开始游戏.png")
TEMPLATE_STEAM = os.path.join(SCRIPT_DIR, "steam.png")
TEMPLATE_PRIVATE_TAVERN = os.path.join(SCRIPT_DIR, "私人城镇.png")
TEMPLATE_DISCONNECT = os.path.join(SCRIPT_DIR, "断开连接.png")

MATCH_THRESHOLD = 0.7
FREEZE_BLACK_RATIO = 0.95
FREEZE_DARK_THRESHOLD = 30
FREEZE_DURATION = 70  # 秒，超过1分钟判定为卡死
STATIC_SIMILARITY = 0.97  # 画面相似度高于此值视为无变化
STATIC_CHECK_INTERVAL = 10  # 秒，每隔多久对比一次画面
DISCONNECT_DURATION = 10  # 秒，断开连接提示持续多久判定卡死


# ==================== 工具函数 ====================
def find_window():
    """查找DD2游戏窗口句柄"""
    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd == 0:
        return None
    return hwnd


def get_screen():
    """截取全屏画面（BGR格式）"""
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def load_template(template_path):
    """加载模板图片（支持中文路径）"""
    try:
        img_data = np.fromfile(template_path, dtype=np.uint8)
        template = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
        return template
    except Exception as e:
        print(f"[错误] 加载模板图片失败: {template_path}, {e}")
        return None


def find_image_on_screen(template_path, threshold=MATCH_THRESHOLD, region=None):
    """
    在全屏或指定区域内查找模板图片
    返回: (center_x, center_y) 或 None
    """
    template = load_template(template_path)
    if template is None:
        print(f"[错误] 无法加载模板图片: {template_path}")
        return None

    screen = get_screen()
    if region:
        x1, y1, x2, y2 = region
        screen = screen[y1:y2, x1:x2]
        offset_x, offset_y = x1, y1
    else:
        offset_x, offset_y = 0, 0

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        th, tw = template.shape[:2]
        cx = offset_x + max_loc[0] + tw // 2
        cy = offset_y + max_loc[1] + th // 2
        return (cx, cy, max_val)
    return None


def click_at(x, y, delay=0.3):
    """移动鼠标到指定位置并左键点击"""
    pyautogui.moveTo(x, y, duration=0.2)
    time.sleep(delay)
    pyautogui.click(x, y)
    time.sleep(0.5)


def press_win_key():
    """按下Win键打开开始菜单"""
    VK_LWIN = 0x5B
    win32api.keybd_event(VK_LWIN, 0, 0, 0)
    time.sleep(0.15)
    win32api.keybd_event(VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(1.5)


# ==================== 核心功能 ====================
def is_game_frozen():
    """
    检测DD2游戏是否卡死，三种判定方式：
    1. 黑屏超过1分钟
    2. 画面长时间基本无变化超过1分钟
    3. 出现"Connection timed out"断开连接提示超过10秒
    返回: True=卡死, False=正常
    """
    hwnd = find_window()
    if hwnd is None:
        print("[检测] 未找到DD2游戏窗口，游戏未运行")
        return False

    print("[检测] 开始检测游戏是否卡死...")
    black_start_time = None
    static_start_time = None
    disconnect_start_time = None
    last_screen_small = None
    check_count = 0

    while True:
        screen = get_screen()
        h, w = screen.shape[:2]
        now = time.time()

        # ========== 检测1：黑屏 ==========
        sample_count = 100
        dark_count = 0
        for i in range(sample_count):
            y = random.randint(0, h - 1)
            x = random.randint(0, w - 1)
            pixel = screen[y, x]
            brightness = int(pixel[0]) + int(pixel[1]) + int(pixel[2])
            if brightness < FREEZE_DARK_THRESHOLD * 3:
                dark_count += 1

        black_ratio = dark_count / sample_count
        is_black = black_ratio >= FREEZE_BLACK_RATIO

        if is_black:
            if black_start_time is None:
                black_start_time = now
                print(f"[检测] 检测到黑屏（黑屏比例: {black_ratio:.0%}），开始计时...")
            else:
                elapsed = now - black_start_time
                print(f"[检测] 黑屏持续 {elapsed:.0f} 秒...")
                if elapsed >= FREEZE_DURATION:
                    print(f"[检测] 黑屏已超过 {FREEZE_DURATION} 秒，判定游戏卡死！")
                    return True
        else:
            if black_start_time is not None:
                print(f"[检测] 画面恢复正常，重置黑屏计时器")
            black_start_time = None

        # ========== 检测2：画面长时间无变化 ==========
        # 将画面缩小后对比，提高效率并忽略微小差异
        small_screen = cv2.resize(screen, (320, 180))

        if last_screen_small is not None:
            diff = cv2.absdiff(last_screen_small, small_screen)
            mean_diff = np.mean(diff)
            similarity = 1.0 - (mean_diff / 255.0)

            if similarity >= STATIC_SIMILARITY:
                if static_start_time is None:
                    static_start_time = now
                    print(f"[检测] 画面基本无变化（相似度: {similarity:.4f}），开始计时...")
                else:
                    elapsed = now - static_start_time
                    print(f"[检测] 画面静止持续 {elapsed:.0f} 秒（相似度: {similarity:.4f}）...")
                    if elapsed >= FREEZE_DURATION:
                        print(f"[检测] 画面静止已超过 {FREEZE_DURATION} 秒，判定游戏卡死！")
                        return True
            else:
                if static_start_time is not None:
                    print(f"[检测] 画面有变化，重置静止计时器")
                static_start_time = None

        last_screen_small = small_screen

        # ========== 检测3：断开连接提示 ==========
        disconnect_pos = find_image_on_screen(TEMPLATE_DISCONNECT, threshold=0.7)
        if disconnect_pos:
            if disconnect_start_time is None:
                disconnect_start_time = now
                print(f"[检测] 检测到'Connection timed out'提示，开始计时...")
            else:
                elapsed = now - disconnect_start_time
                print(f"[检测] 断开连接提示持续 {elapsed:.0f} 秒...")
                if elapsed >= DISCONNECT_DURATION:
                    print(f"[检测] 断开连接提示已超过 {DISCONNECT_DURATION} 秒，判定游戏卡死！")
                    return True
        else:
            if disconnect_start_time is not None:
                print(f"[检测] 断开连接提示消失，重置计时器")
            disconnect_start_time = None

        check_count += 1

        time.sleep(5)


def close_dd2_game():
    """关闭DD2游戏窗口和进程"""
    print("[恢复] 正在关闭DD2游戏...")

    hwnd = find_window()
    if hwnd:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            print("[恢复] 已发送关闭消息")
            time.sleep(3)
        except Exception as e:
            print(f"[恢复] 发送关闭消息失败: {e}")

    # 强制结束进程（如果窗口还在）
    hwnd = find_window()
    if hwnd:
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            handle = win32api.OpenProcess(1, False, pid)
            win32api.TerminateProcess(handle, 0)
            win32api.CloseHandle(handle)
            print(f"[恢复] 已强制结束进程 PID={pid}")
            time.sleep(2)
        except Exception as e:
            print(f"[恢复] 强制结束进程失败: {e}")

    # 也通过任务管理器方式确保进程结束
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{GAME_PROCESS_NAME}.exe"],
            capture_output=True, timeout=10
        )
        print(f"[恢复] 已执行 taskkill 确保进程结束")
    except Exception:
        pass

    time.sleep(2)
    print("[恢复] DD2游戏已关闭")


def recover_game():
    """完整的游戏恢复流程"""
    print("=" * 50)
    print("[恢复] 开始执行游戏恢复流程")
    print("=" * 50)

    # 第1步：关闭DD2游戏窗口
    close_dd2_game()

    # 第2步：按Win键打开开始菜单
    print("[恢复] 按下Win键打开开始菜单...")
    press_win_key()

    # 第3步：在屏幕左半边找Steam图标并点击
    print("[恢复] 在屏幕左半边查找Steam图标...")
    screen_w = pyautogui.size()[0]
    left_region = (0, 0, screen_w // 2, pyautogui.size()[1])

    steam_pos = None
    for attempt in range(15):
        steam_pos = find_image_on_screen(TEMPLATE_STEAM, threshold=0.6, region=left_region)
        if steam_pos:
            print(f"[恢复] 找到Steam图标，位置: ({steam_pos[0]}, {steam_pos[1]})")
            click_at(steam_pos[0], steam_pos[1], delay=0.5)
            break
        print(f"[恢复] 未找到Steam图标，重试 {attempt + 1}/15...")
        time.sleep(1)

    if not steam_pos:
        print("[错误] 多次尝试后仍未找到Steam图标，恢复流程中止")
        return False

    time.sleep(3)

    # 第4步：找"停止"按钮并点击
    print("[恢复] 查找'停止'按钮...")
    stop_pos = None
    for attempt in range(20):
        stop_pos = find_image_on_screen(TEMPLATE_STOP, threshold=MATCH_THRESHOLD)
        if stop_pos:
            print(f"[恢复] 找到'停止'按钮，位置: ({stop_pos[0]}, {stop_pos[1]})")
            click_at(stop_pos[0], stop_pos[1], delay=0.5)
            break
        print(f"[恢复] 未找到'停止'按钮，重试 {attempt + 1}/20...")
        time.sleep(1.5)

    if not stop_pos:
        print("[错误] 未找到'停止'按钮，恢复流程中止")
        return False

    time.sleep(2)

    # 第5步：找"确认"按钮并点击
    print("[恢复] 查找'确认'按钮...")
    confirm_pos = None
    for attempt in range(15):
        confirm_pos = find_image_on_screen(TEMPLATE_CONFIRM, threshold=MATCH_THRESHOLD)
        if confirm_pos:
            print(f"[恢复] 找到'确认'按钮，位置: ({confirm_pos[0]}, {confirm_pos[1]})")
            click_at(confirm_pos[0], confirm_pos[1], delay=0.5)
            break
        print(f"[恢复] 未找到'确认'按钮，重试 {attempt + 1}/15...")
        time.sleep(1.5)

    if not confirm_pos:
        print("[错误] 未找到'确认'按钮，恢复流程中止")
        return False

    time.sleep(3)

    # 第6步：等待"开始游戏"按钮出现并点击
    print("[恢复] 等待'开始游戏'按钮出现...")
    start_pos = None
    for attempt in range(30):
        start_pos = find_image_on_screen(TEMPLATE_START_GAME, threshold=MATCH_THRESHOLD)
        if start_pos:
            print(f"[恢复] 找到'开始游戏'按钮，位置: ({start_pos[0]}, {start_pos[1]})")
            click_at(start_pos[0], start_pos[1], delay=0.5)
            break
        print(f"[恢复] 未找到'开始游戏'按钮，重试 {attempt + 1}/30...")
        time.sleep(2)

    if not start_pos:
        print("[错误] 未找到'开始游戏'按钮，恢复流程中止")
        return False

    # 第7步：等待DD2游戏窗口出现并绑定句柄
    print("[恢复] 等待DD2游戏窗口出现...")
    hwnd = None
    for attempt in range(60):
        hwnd = find_window()
        if hwnd:
            print(f"[恢复] DD2游戏窗口已出现，句柄: {hwnd}")
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(3)
            break
        print(f"[恢复] 等待游戏窗口... {attempt + 1}/60")
        time.sleep(5)

    if not hwnd:
        print("[错误] 等待超时，DD2游戏窗口未出现")
        return False

    # 第8步：左键点击游戏画面中间位置，直到找到"私人城镇"按钮
    print("[恢复] 点击游戏画面中间，等待'私人城镇'按钮出现...")
    game_rect = win32gui.GetWindowRect(hwnd)
    center_x = (game_rect[0] + game_rect[2]) // 2
    center_y = (game_rect[1] + game_rect[3]) // 2

    tavern_pos = None
    for attempt in range(30):
        # 左键点击游戏画面中间
        click_at(center_x, center_y, delay=1.0)
        print(f"[恢复] 点击游戏画面中间 ({center_x}, {center_y})，第 {attempt + 1} 次")

        # 查找"私人城镇"按钮
        tavern_pos = find_image_on_screen(TEMPLATE_PRIVATE_TAVERN, threshold=0.6)
        if tavern_pos:
            print(f"[恢复] 找到'私人城镇'按钮，位置: ({tavern_pos[0]}, {tavern_pos[1]})")
            click_at(tavern_pos[0], tavern_pos[1], delay=0.5)
            break

        time.sleep(2)

    if not tavern_pos:
        print("[警告] 未找到'私人城镇'按钮，但游戏已成功重启")

    # 第9步：等待1分钟
    print("[恢复] 等待1分钟...")
    for i in range(60, 0, -1):
        if i % 10 == 0:
            print(f"[恢复] 剩余 {i} 秒...")
        time.sleep(1)

    print("=" * 50)
    print("[恢复] 游戏恢复流程完成！")
    print("=" * 50)
    return True


# ==================== 主函数 ====================
def main():
    """主入口：检测游戏是否卡死，如果是则执行恢复流程"""
    print("=" * 50)
    print("DD2 游戏卡死检测与自动恢复工具")
    print("=" * 50)

    frozen = is_game_frozen()

    if frozen:
        print("\n[主程序] 检测到游戏卡死，开始自动恢复...")
        success = recover_game()
        if success:
            print("\n[主程序] 游戏恢复成功！")
        else:
            print("\n[主程序] 游戏恢复失败，请手动处理。")
    else:
        print("\n[主程序] 游戏运行正常，无需恢复。")


if __name__ == "__main__":
    main()
