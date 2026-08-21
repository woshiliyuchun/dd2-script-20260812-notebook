# pip install mss opencv-python pyautogui pywin32 keyboard pillow pytesseract
#
# DD2 自动爬塔脚本 — 完整流程：
# 0) 每轮开始前先卖装备：按 I 打开背包 → 找背包1 → 识别 10 级装备移到背包2 → 按 Y 卖出剩余 → 关闭背包
# 1) 从城镇出生点自动寻路到 War Table，按下 E 打开界面
# 2) 进入 Onslaught 界面，OCR 识别 Selected Floor 当前楼层数字
# 3) 扫描房间列表（Floor + CHAMPION SCORE 双列 OCR），找到 Floor >= 当前层数且 SCORE == 0 的房间，双击进入
# 4) 进入房间后每 10 秒按 2/0 准备 + 随机长按方向键 1 秒，直到出现 finish game 结算界面
# 5) 点击 To Tavern 返回城堡，等待 30 秒后开始下一轮
# 6) 如果列表中找不到目标房间，点击 REFRESH 后每 4 秒检测一次，最多等 20 秒
#
# 异常处理：
# - 卡死检测：黑屏超 6 分钟、画面静止超 20 分钟或 Connection timed out 超 10 秒 → 自动关闭并重启游戏
# - 游戏失败：检测到 gamefailed.png → 按 N 键继续
# - 被踢出房间：检测到 bekick.png → 点击 kickok → 点击私人城镇 → 等 30 秒重新开始
# - F12 热键随时停止脚本

import os
import re
import time
import ctypes
import random
import subprocess
from pathlib import Path
import cv2
import numpy as np
import mss
import pyautogui
import keyboard
import pytesseract
import win32api
import win32con
import win32gui
import win32process
import win32ui
from pytesseract import Output
import ctypes.wintypes

# ========================= DPI 感知（兼容 1K/2K 不同缩放） =========================
# 让进程成为 DPI-aware，避免 Win32 API 返回被虚拟化的坐标
try:
    # Windows 10+：Per-Monitor DPI Aware V2（最完善）
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        # 降级：System DPI Aware（Win7/8 兼容）
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def get_system_dpi_scale():
    """获取系统 DPI 缩放比例，例如 125% 缩放返回 1.25，100% 返回 1.0。"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        LOGPIXELSX = 88
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        # Windows 默认基准 DPI = 96（对应 100%）
        return round(dpi / 96.0, 4)
    except Exception:
        return 1.0

def get_monitor_dpi_from_window(hwnd):
    """根据窗口所在显示器获取对应 DPI 缩放（优先使用，比系统级更准）。"""
    try:
        import win32api
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        hmonitor = win32api.MonitorFromPoint((cx, cy), 2)  # MONITOR_DEFAULTTONEAREST
        MDT_EFFECTIVE_DPI = 0
        dpi_x = ctypes.wintypes.UINT()
        dpi_y = ctypes.wintypes.UINT()
        ctypes.windll.shcore.GetDpiForMonitor(
            hmonitor, MDT_EFFECTIVE_DPI,
            ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        return round(dpi_x.value / 96.0, 4)
    except Exception:
        return get_system_dpi_scale()

SCRIPT_DIR = Path(__file__).resolve().parent
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_EXE):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE


# ========================= 全局配置（只改这里） =========================
CONFIG = {
    "game_class": "LaunchUnrealUWindowsClient",
    "game_title": "Dungeon Defenders 2",

    # 识别模板路径（后续补图以后只改这里即可）
    # 这里默认使用脚本所在目录下的 picture 文件夹，避免硬编码到某一台电脑的绝对路径。
    "template_dir": str(SCRIPT_DIR / "picture"),
    "war_table_templates": [
        str(SCRIPT_DIR / "picture" / "wartable1.png"),
        str(SCRIPT_DIR / "picture" / "wartable2.png"),
        str(SCRIPT_DIR / "picture" / "wartable3.png"),
        str(SCRIPT_DIR / "picture" / "wartable4.png"),
        str(SCRIPT_DIR / "picture" / "wartable5.png"),
    ],
    "e_tip_template": str(SCRIPT_DIR / "picture" / "e_tip.png"),
    "e_tip2_template": str(SCRIPT_DIR / "picture" / "e_tip2.png"),
    "e_tip3_template": str(SCRIPT_DIR / "picture" / "e_tip3.png"),
    "onslaught_template": str(SCRIPT_DIR / "picture" / "ONSLAUGHT.png"),
    "browse_template": str(SCRIPT_DIR / "picture" / "BROWSE.png"),
    "selected_floor_template": str(SCRIPT_DIR / "picture" / "Selected Floor.png"),
    "room_list_template": str(SCRIPT_DIR / "picture" / "room list.png"),
    "refresh_template": str(SCRIPT_DIR / "picture" / "REFRESH.png"),
    "finish_game_template": str(SCRIPT_DIR / "picture" / "finish game.png"),
    "to_tavern_template": str(SCRIPT_DIR / "picture" / "To Tavern.png"),
    "game_failed_template": str(SCRIPT_DIR / "picture" / "gamefailed.png"),
    "bekick_template": str(SCRIPT_DIR / "picture" / "bekick.png"),
    "bekick2_template": str(SCRIPT_DIR / "picture" / "bekick2.png"),
    "bekick3_template": str(SCRIPT_DIR / "picture" / "bekick3.png"),
    "roomfull_template": str(SCRIPT_DIR / "picture" / "roomfull.png"),
    "roomfull_9001_template": r"D:\DD2脚本\dd2onslaught\picture\9001roomfull.png",
    "roomfull_9001_v2_template": r"D:\DD2脚本\dd2onslaught\picture\9001roomfullv2.png",
    "kickok_template": str(SCRIPT_DIR / "picture" / "kickok.png"),
    "private_tavern_template": str(SCRIPT_DIR / "picture" / "PRIVATETAVERN.png"),
    "ready_template": str(SCRIPT_DIR / "picture" / "ready.png"),
    "nomana_template": str(SCRIPT_DIR / "picture" / "nomana.png"),
    "failure_retry_template": r"D:\DD2脚本\失败重来.png",

    # 卖装备相关模板路径（位于 D:\DD2脚本\ 目录下）
    "backpack1_template": r"D:\DD2脚本\背包1.png",
    "backpack2_template": r"D:\DD2脚本\背包2.png",
    "level10_equipment_template": r"D:\DD2脚本\10级装备.png",

    # 换装/分屏/chaos 相关模板
    "e_reset_template": str(SCRIPT_DIR / "picture" / "e-reset.png"),
    "auto_equip_gear_template": str(SCRIPT_DIR / "picture" / "autoequipgear.png"),
    "defaults_template": str(SCRIPT_DIR / "picture" / "defaults.png"),
    "chaos9_template": str(SCRIPT_DIR / "picture" / "chaos9.png"),
    "chaos10_template": str(SCRIPT_DIR / "picture" / "chaos10.png"),
    "chaos11_template": str(SCRIPT_DIR / "picture" / "chaos11.png"),
    "chaos8_template": str(SCRIPT_DIR / "picture" / "chaos8.png"),
    "chaos9_room_template": str(SCRIPT_DIR / "picture" / "chaos9room.png"),
    "chaos91011_room_template": str(SCRIPT_DIR / "picture" / "chaos91011room.png"),
    "resetconfirm_template": str(SCRIPT_DIR / "picture" / "resetconfirm.png"),
    "setfaild_template": str(SCRIPT_DIR / "picture" / "setfaild.png"),
    "connectionfailed_template": r"D:\DD2脚本\DD2ganmedie\connectionfailed.png",

    # 识别阈值与扫描参数
    # 这里把阈值放低一点，避免你补的模板图与实际游戏中的字体/角度略有差异时直接失配。
    "match_threshold": 0.66,
    "e_tip_threshold": 0.9,
    "scan_rotate_steps": 6,
    "scan_rotate_ms": 220,
    "forward_press_ms": 320,
    "forward_hold_ms": 500,
    "step_wait_seconds": 0.12,
    "strafe_press_ms": 120,

    # 识别中心容差
    "center_tolerance_x": 140,
    "center_tolerance_y": 120,

    # 自动重试次数
    "max_scan_rounds": 5,

    # 退出键
    "stop_hotkey": "F12",
}

# ========================= 全局状态变量 =========================
STOP_FLAG = False          # F12 热键触发后设为 True，所有循环检测此标志退出
TEMPLATE_CACHE = {}        # 模板图片缓存，避免重复读盘
REFRESH_CLICK_POINT = None # REFRESH 按钮的屏幕坐标缓存（首次模板匹配后缓存，后续直接点击）
FREEZE_MONITOR = None      # 全局卡死监视器，主入口初始化

# 楼层判断与换装流程的状态标记
SKIP_FLOOR_CHECK_THIS_ROUND = False   # 本次找合适房间前跳过楼层<300判断（gear低后进入房间时）
LAST_ROUND_HAD_GEAR_CHECK = False     # 上一轮是否做过换装判断（用于重置跳过标记）
# 原 NEED_RESET_AFTER_ROUND 标记已废弃（改为直接卡死重启 + 识别到War Table后执行视角专项），留空兼容旧代码
NEED_RESET_AFTER_ROUND = False        # 保留变量名，不再使用
LAST_COMPLETED_FLOOR = None           # 上一次完整打完的Selected Floor数字，用于判断是否>320
NEED_VIEW_RESET_BEFORE_NEXT_WAR = False  # True 时：下一次 walk_to_war_table 识别到War Table之后、按E之前，执行视角专项→再卡死重启
LAST_PLAYER_READY_TIME = None         # 最近一次检测到队友准备（绿色对钩）的时间戳，用于40分钟无准备卡死重启（全流程适用）
ROOMFULL_9001_TRIGGERED = False       # 双击房间后1分钟内检测到9001roomfull时标记为True，跳过run_room_progression_loop直接重新识别e-tip
NO_PLAYER_READY_TIMEOUT_MINUTES = 40.0
NO_PLAYER_READY_TIMEOUT_SECONDS = NO_PLAYER_READY_TIMEOUT_MINUTES * 60

# ========================= 卡死检测配置（来自 dd2gamedie.py） =========================
# 模板路径：卡死恢复流程中需要用到的图像（关闭游戏、Steam 重启等）
GAME_PROCESS_NAME = "DD2"
FREEZE_SCRIPT_DIR = r"D:\DD2脚本\DD2ganmedie"
TEMPLATE_STOP = os.path.join(FREEZE_SCRIPT_DIR, "停止.png")
TEMPLATE_CONFIRM = os.path.join(FREEZE_SCRIPT_DIR, "确认.png")
TEMPLATE_START_GAME = os.path.join(FREEZE_SCRIPT_DIR, "开始游戏.png")
TEMPLATE_GAME_END = os.path.join(FREEZE_SCRIPT_DIR, "gameend.png")
TEMPLATE_STEAM = os.path.join(FREEZE_SCRIPT_DIR, "steam.png")
TEMPLATE_PRIVATE_TAVERN = os.path.join(FREEZE_SCRIPT_DIR, "私人城镇.png")
TEMPLATE_DISCONNECT = os.path.join(FREEZE_SCRIPT_DIR, "断开连接.png")
TEMPLATE_CANCEL = os.path.join(FREEZE_SCRIPT_DIR, "取消.png")

FREEZE_MATCH_THRESHOLD = 0.7
FREEZE_BLACK_RATIO = 0.95
FREEZE_DARK_THRESHOLD = 30
FREEZE_DURATION = 360         # 秒，黑屏超过此时长判定卡死（6分钟）
STATIC_FREEZE_DURATION = 1200 # 秒，画面连续静止超过此时长判定卡死（20分钟）
STATIC_SIMILARITY = 0.97      # 画面相似度高于此值视为无变化
DISCONNECT_DURATION = 10      # 秒，断开连接提示持续多久判定卡死

# Windows 运行状态：脚本运行期间阻止系统自动睡眠、息屏和由空闲触发的锁屏。
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def enable_system_keep_awake():
    """保持系统和显示器唤醒，避免自动锁屏导致游戏截图失败。"""
    result = ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    )
    if result:
        print("[INFO] 已启用防睡眠/防息屏，脚本运行期间系统将保持唤醒")
        return True
    print("[WARN] 启用防睡眠/防息屏失败，锁屏后截图可能暂时不可用")
    return False


def disable_system_keep_awake():
    """恢复 Windows 默认电源管理行为。"""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


# ========================= 卡死检测与恢复模块 =========================

class GameFreezeMonitor:
    """游戏卡死监视器，每次调用 check() 做单次采样，跨调用累积状态。
    三种判定方式：
    1. 黑屏超过 FREEZE_DURATION 秒
    2. 画面长时间基本无变化超过 STATIC_FREEZE_DURATION 秒
    3. 出现断开连接提示超过 DISCONNECT_DURATION 秒
    """

    def __init__(self):
        self.black_start_time = None
        self.static_start_time = None
        self.disconnect_start_time = None
        self.last_screen_small = None

    def reset(self):
        """重置所有状态"""
        self.black_start_time = None
        self.static_start_time = None
        self.disconnect_start_time = None
        self.last_screen_small = None

    def check(self):
        """做一次采样检查，返回 True 表示判定游戏卡死。"""
        hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
        if hwnd == 0:
            print("[卡死检测] 未找到游戏窗口")
            return True  # 窗口不存在，视为卡死

        now = time.time()

        # 截取全屏
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screen = cv2.cvtColor(
                    np.array(sct.grab(monitor)), cv2.COLOR_BGRA2BGR
                )
        except Exception as e:
            # 锁屏期间没有有效采样，不能把这段时间计入连续黑屏/静止时长。
            self.reset()
            print(f"[卡死检测] 截屏失败，已暂停并重置画面计时: {e}")
            return False

        h, w = screen.shape[:2]

        # ---- 检测1：黑屏 ----
        sample_count = 100
        dark_count = 0
        for _ in range(sample_count):
            y = random.randint(0, h - 1)
            x = random.randint(0, w - 1)
            pixel = screen[y, x]
            brightness = int(pixel[0]) + int(pixel[1]) + int(pixel[2])
            if brightness < FREEZE_DARK_THRESHOLD * 3:
                dark_count += 1

        black_ratio = dark_count / sample_count
        is_black = black_ratio >= FREEZE_BLACK_RATIO

        if is_black:
            if self.black_start_time is None:
                self.black_start_time = now
                print(f"[卡死检测] 检测到黑屏（比例: {black_ratio:.0%}），开始计时...")
            else:
                elapsed = now - self.black_start_time
                print(f"[卡死检测] 检测到黑屏（比例: {black_ratio:.0%}），已持续 {elapsed:.1f} 秒...")
                if elapsed >= FREEZE_DURATION:
                    print(f"[卡死检测] 黑屏已超过 {FREEZE_DURATION} 秒，判定游戏卡死！")
                    return True
        else:
            if self.black_start_time is not None:
                print("[卡死检测] 画面恢复正常，重置黑屏计时器")
            self.black_start_time = None

        # ---- 检测2：画面静止 ----
        small_screen = cv2.resize(screen, (320, 180))
        if self.last_screen_small is not None:
            diff = cv2.absdiff(self.last_screen_small, small_screen)
            mean_diff = np.mean(diff)
            similarity = 1.0 - (mean_diff / 255.0)

            if similarity >= STATIC_SIMILARITY:
                if self.static_start_time is None:
                    self.static_start_time = now
                    print(f"[卡死检测] 画面基本无变化（相似度: {similarity:.4f}），开始计时...")
                else:
                    elapsed = now - self.static_start_time
                    print(f"[卡死检测] 画面基本无变化（相似度: {similarity:.4f}），已持续 {elapsed:.1f} 秒...")
                    if elapsed >= STATIC_FREEZE_DURATION:
                        print(f"[卡死检测] 画面静止已超过 {STATIC_FREEZE_DURATION} 秒，判定游戏卡死！")
                        return True
                    if elapsed >= 100:
                        disconnect_pos = _find_image_on_screen(TEMPLATE_DISCONNECT, threshold=0.7)
                        if disconnect_pos:
                            print("[卡死检测] 画面静止超100秒，检测到断开连接提示，开始恢复...")
                            self.disconnect_start_time = now - DISCONNECT_DURATION - 1
                            return True
            else:
                if self.static_start_time is not None:
                    pass  # 画面有变化，重置
                self.static_start_time = None

        self.last_screen_small = small_screen

        # ---- 检测3：断开连接提示 ----
        disconnect_pos = _find_image_on_screen(TEMPLATE_DISCONNECT, threshold=0.7)
        if disconnect_pos:
            if self.disconnect_start_time is None:
                self.disconnect_start_time = now
                print("[卡死检测] 检测到断开连接提示，开始计时...")
            else:
                elapsed = now - self.disconnect_start_time
                print(f"[卡死检测] 检测到断开连接提示，已持续 {elapsed:.1f} 秒...")
                if elapsed >= DISCONNECT_DURATION:
                    print(f"[卡死检测] 断开连接提示已超过 {DISCONNECT_DURATION} 秒，判定游戏卡死！")
                    return True
        else:
            self.disconnect_start_time = None

        return False


def check_disconnect_quick():
    """快速检测断开连接提示，检测到后立即触发卡死恢复流程。
    用于进入房间后立即检测断连，不用等 10 秒计时。"""
    if not os.path.exists(TEMPLATE_DISCONNECT):
        return False
    disconnect_pos = _find_image_on_screen(TEMPLATE_DISCONNECT, threshold=0.7)
    if disconnect_pos:
        print("[INFO] 检测到断开连接提示，触发卡死恢复流程")
        if FREEZE_MONITOR:
            # 强制设置断开开始时间为 10 秒前，让卡死恢复立即触发
            FREEZE_MONITOR.disconnect_start_time = time.time() - DISCONNECT_DURATION - 1
            check_and_recover_if_frozen(FREEZE_MONITOR)
        return True
    return False


def check_connection_failed():
    """检测 connectionfailed.png（网络连接断开），检测到后立即执行卡死恢复流程。"""
    if not os.path.exists(CONFIG["connectionfailed_template"]):
        return False
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(CONFIG["connectionfailed_template"])
    rect = find_template_rect(frame, template, threshold=0.9)
    if rect:
        print("[INFO] 检测到网络连接断开（connectionfailed），触发卡死恢复流程")
        if FREEZE_MONITOR:
            FREEZE_MONITOR.reset()
        recover_game()
        return True
    return False


def _find_image_on_screen(template_path, threshold=FREEZE_MATCH_THRESHOLD, region=None):
    """在全屏或指定区域内查找模板图片，返回 (cx, cy, max_val) 或 None。

    当单尺度匹配失败时，自动尝试多尺度匹配（0.5x~2.0x），
    以适应不同分辨率/DPI 缩放下的模板匹配。
    """
    try:
        img_data = np.fromfile(template_path, dtype=np.uint8)
        template = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
        if template is None:
            return None
    except Exception:
        return None

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        screen = cv2.cvtColor(np.array(sct.grab(monitor)), cv2.COLOR_BGRA2BGR)

    if region:
        x1, y1, x2, y2 = region
        screen = screen[y1:y2, x1:x2]
        offset_x, offset_y = x1, y1
    else:
        offset_x, offset_y = 0, 0

    sh, sw = screen.shape[:2]
    tth, twt = template.shape[:2]

    # 先尝试 1.0x 原始尺度
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        cx = offset_x + max_loc[0] + twt // 2
        cy = offset_y + max_loc[1] + tth // 2
        return (cx, cy, max_val)

    # 单尺度失败，尝试多尺度
    scales = [s for s in [0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]
              if int(twt * s) <= sw and int(tth * s) <= sh]

    best_score = max_val
    best_cx, best_cy = None, None

    for scale in scales:
        scaled = cv2.resize(template, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA)
        s_tth, s_twt = scaled.shape[:2]
        result = cv2.matchTemplate(screen, scaled, cv2.TM_CCOEFF_NORMED)
        _, s_max_val, _, s_max_loc = cv2.minMaxLoc(result)

        if s_max_val > best_score:
            best_score = s_max_val
            best_cx = offset_x + s_max_loc[0] + s_twt // 2
            best_cy = offset_y + s_max_loc[1] + s_tth // 2

    if best_score >= threshold and best_cx is not None:
        return (best_cx, best_cy, best_score)

    return None


# ========================= 反作弊人性化输入工具 =========================
# 所有键鼠操作加入随机扰动，模拟真人操作节奏，避免固定周期被检测

def humanized_sleep(base_seconds):
    """在基础等待时间上加入 ±30% 的随机抖动，模拟真人不精确的时间感。"""
    if base_seconds <= 0:
        return
    jitter = base_seconds * random.uniform(-0.3, 0.3)
    actual = max(0.05, base_seconds + jitter)
    time.sleep(actual)


def humanized_press(key):
    """模拟真人按键：按下后随机保持 50~180ms 再松开，然后随机等 30~120ms。"""
    pyautogui.keyDown(key)
    time.sleep(random.uniform(0.05, 0.18))
    pyautogui.keyUp(key)
    time.sleep(random.uniform(0.03, 0.12))


def humanized_move_to(x, y):
    """模拟真人鼠标移动：速度在 0.15~0.45 秒之间随机，路径略带波动。"""
    duration = random.uniform(0.15, 0.45)
    # 使用 pyautogui 的 easeOutQuad 缓动，模拟真人减速效果
    pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeOutQuad)


def _click_at(x, y, delay=0.3):
    """移动鼠标到指定位置并左键点击（已加入人性化扰动）"""
    humanized_move_to(x, y)
    time.sleep(delay * random.uniform(0.8, 1.2))
    pyautogui.click(x, y)
    time.sleep(random.uniform(0.3, 0.7))


def _press_win_key():
    """按下Win键打开开始菜单"""
    VK_LWIN = 0x5B
    win32api.keybd_event(VK_LWIN, 0, 0, 0)
    time.sleep(0.15)
    win32api.keybd_event(VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(1.5)


def close_dd2_game():
    """关闭DD2游戏窗口和进程"""
    print("[恢复] 正在关闭DD2游戏...")

    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
    if hwnd:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            print("[恢复] 已发送关闭消息")
            time.sleep(3)
        except Exception as e:
            print(f"[恢复] 发送关闭消息失败: {e}")

    # 强制结束进程
    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
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

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{GAME_PROCESS_NAME}.exe"],
            capture_output=True, timeout=10
        )
        print("[恢复] 已执行 taskkill 确保进程结束")
    except Exception:
        pass

    time.sleep(2)
    print("[恢复] DD2游戏已关闭")


def recover_game():
    """完整的游戏恢复流程：关闭游戏 → Steam重启 → 等待进入游戏"""
    global REFRESH_CLICK_POINT

    print("=" * 50)
    print("[恢复] 开始执行游戏恢复流程")
    print("=" * 50)

    # 第1步：关闭DD2游戏
    close_dd2_game()

    # 第2步：按Win键打开开始菜单
    print("[恢复] 按下Win键打开开始菜单...")
    _press_win_key()

    # 第3步：在屏幕左半边找Steam图标并点击
    print("[恢复] 在屏幕左半边查找Steam图标...")
    screen_w = pyautogui.size()[0]
    left_region = (0, 0, screen_w // 2, pyautogui.size()[1])

    steam_pos = None
    for attempt in range(15):
        steam_pos = _find_image_on_screen(TEMPLATE_STEAM, threshold=0.6, region=left_region)
        if steam_pos:
            print(f"[恢复] 找到Steam图标，位置: ({steam_pos[0]}, {steam_pos[1]})")
            _click_at(steam_pos[0], steam_pos[1], delay=0.5)
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
        stop_pos = _find_image_on_screen(TEMPLATE_STOP, threshold=FREEZE_MATCH_THRESHOLD)
        if stop_pos:
            print(f"[恢复] 找到'停止'按钮，位置: ({stop_pos[0]}, {stop_pos[1]})")
            _click_at(stop_pos[0], stop_pos[1], delay=0.5)
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
        confirm_pos = _find_image_on_screen(TEMPLATE_CONFIRM, threshold=FREEZE_MATCH_THRESHOLD)
        if confirm_pos:
            print(f"[恢复] 找到'确认'按钮，位置: ({confirm_pos[0]}, {confirm_pos[1]})")
            _click_at(confirm_pos[0], confirm_pos[1], delay=0.5)
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
    game_end_clicked = False
    for attempt in range(30):
        start_pos = _find_image_on_screen(TEMPLATE_START_GAME, threshold=FREEZE_MATCH_THRESHOLD)
        if start_pos:
            print(f"[恢复] 找到'开始游戏'按钮，位置: ({start_pos[0]}, {start_pos[1]})")
            _click_at(start_pos[0], start_pos[1], delay=0.5)
            break
        if attempt >= 9 and not game_end_clicked:
            game_end_pos = _find_image_on_screen(TEMPLATE_GAME_END, threshold=FREEZE_MATCH_THRESHOLD)
            if game_end_pos:
                print(f"[恢复] 连续10次未找到'开始游戏'，检测到 gameend，点击位置: ({game_end_pos[0]}, {game_end_pos[1]})")
                _click_at(game_end_pos[0], game_end_pos[1], delay=0.5)
                game_end_clicked = True
                time.sleep(2)
                continue
        print(f"[恢复] 未找到'开始游戏'按钮，重试 {attempt + 1}/30...")
        time.sleep(2)

    if not start_pos:
        print("[错误] 未找到'开始游戏'按钮，恢复流程中止")
        return False

    # 第7步：等待DD2游戏窗口出现，如果超时则重新通过 Steam 启动
    print("[恢复] 等待DD2游戏窗口出现...")
    hwnd = None
    for attempt in range(60):
        hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
        if hwnd:
            print(f"[恢复] DD2游戏窗口已出现，句柄: {hwnd}")
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(3)
            break
        print(f"[恢复] 等待游戏窗口... {attempt + 1}/60")
        time.sleep(5)

    if not hwnd:
        # 窗口未出现，当作游戏启动失败，先检测是否出现 setfaild.png（取消登录弹窗）
        print("[恢复] 等待超时，游戏窗口未出现...")

        # 检测 setfaild.png，如果出现则点击
        setfaild_pos = None
        for attempt in range(10):
            setfaild_pos = _find_image_on_screen(CONFIG["setfaild_template"], threshold=FREEZE_MATCH_THRESHOLD)
            if setfaild_pos:
                print(f"[恢复] 检测到 setfaild（取消登录弹窗），点击关闭")
                _click_at(setfaild_pos[0], setfaild_pos[1], delay=0.5)
                time.sleep(2)
                break
            time.sleep(1)

        # 重新走 Steam 启动流程
        print("[恢复] 重新通过 Steam 启动...")

        # 按 Win 键打开开始菜单
        _press_win_key()

        # 在屏幕左半边找 Steam 图标并点击
        screen_w = pyautogui.size()[0]
        left_region = (0, 0, screen_w // 2, pyautogui.size()[1])
        steam_pos = None
        for attempt in range(15):
            steam_pos = _find_image_on_screen(TEMPLATE_STEAM, threshold=0.6, region=left_region)
            if steam_pos:
                print(f"[恢复] 找到Steam图标，位置: ({steam_pos[0]}, {steam_pos[1]})")
                _click_at(steam_pos[0], steam_pos[1], delay=0.5)
                break
            print(f"[恢复] 未找到Steam图标，重试 {attempt + 1}/15...")
            time.sleep(1)

        if not steam_pos:
            print("[错误] 未找到Steam图标，恢复流程中止")
            return False

        time.sleep(3)

        # 先找"取消"按钮（如果有），点击取消当前操作
        cancel_pos = None
        for attempt in range(10):
            cancel_pos = _find_image_on_screen(TEMPLATE_CANCEL, threshold=FREEZE_MATCH_THRESHOLD)
            if cancel_pos:
                print(f"[恢复] 找到'取消'按钮，点击取消")
                _click_at(cancel_pos[0], cancel_pos[1], delay=0.5)
                time.sleep(2)
                break
            # 取消按钮可能不存在，不报错，继续找开始游戏
            time.sleep(1)

        # 找"开始游戏"按钮并点击
        print("[恢复] 查找'开始游戏'按钮...")
        start_pos = None
        game_end_clicked = False
        for attempt in range(30):
            start_pos = _find_image_on_screen(TEMPLATE_START_GAME, threshold=FREEZE_MATCH_THRESHOLD)
            if start_pos:
                print(f"[恢复] 找到'开始游戏'按钮，位置: ({start_pos[0]}, {start_pos[1]})")
                _click_at(start_pos[0], start_pos[1], delay=0.5)
                break
            if attempt >= 9 and not game_end_clicked:
                game_end_pos = _find_image_on_screen(TEMPLATE_GAME_END, threshold=FREEZE_MATCH_THRESHOLD)
                if game_end_pos:
                    print(f"[恢复] 连续10次未找到'开始游戏'，检测到 gameend，点击位置: ({game_end_pos[0]}, {game_end_pos[1]})")
                    _click_at(game_end_pos[0], game_end_pos[1], delay=0.5)
                    game_end_clicked = True
                    time.sleep(2)
                    continue
            print(f"[恢复] 未找到'开始游戏'按钮，重试 {attempt + 1}/30...")
            time.sleep(2)

        if not start_pos:
            print("[错误] 未找到'开始游戏'按钮，恢复流程中止")
            return False

        # 再次等待游戏窗口出现
        print("[恢复] 再次等待DD2游戏窗口出现...")
        for attempt in range(60):
            hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
            if hwnd:
                print(f"[恢复] DD2游戏窗口已出现，句柄: {hwnd}")
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(3)
                break
            print(f"[恢复] 等待游戏窗口... {attempt + 1}/60")
            time.sleep(5)

        if not hwnd:
            # 窗口未出现，先检测是否出现 setfaild.png（取消登录弹窗）
            print("[恢复] 再次等待超时，游戏窗口未出现...")

            # 检测 setfaild.png，如果出现则点击
            setfaild_pos = None
            for attempt in range(10):
                setfaild_pos = _find_image_on_screen(CONFIG["setfaild_template"], threshold=FREEZE_MATCH_THRESHOLD)
                if setfaild_pos:
                    print(f"[恢复] 检测到 setfaild（取消登录弹窗），点击关闭")
                    _click_at(setfaild_pos[0], setfaild_pos[1], delay=0.5)
                    time.sleep(2)
                    break
                time.sleep(1)

            print("[错误] 再次等待超时，DD2游戏窗口仍未出现，恢复流程中止")
            return False

    # 第8步：点击游戏画面中间，直到找到"私人城镇"按钮
    print("[恢复] 点击游戏画面中间，等待'私人城镇'按钮出现...")
    game_rect = win32gui.GetWindowRect(hwnd)
    center_x = (game_rect[0] + game_rect[2]) // 2
    center_y = (game_rect[1] + game_rect[3]) // 2

    tavern_pos = None
    for attempt in range(30):
        _click_at(center_x, center_y, delay=1.0)
        print(f"[恢复] 点击游戏画面中间 ({center_x}, {center_y})，第 {attempt + 1} 次")

        tavern_pos = _find_image_on_screen(TEMPLATE_PRIVATE_TAVERN, threshold=0.6)
        if tavern_pos:
            print(f"[恢复] 找到'私人城镇'按钮，位置: ({tavern_pos[0]}, {tavern_pos[1]})")
            _click_at(tavern_pos[0], tavern_pos[1], delay=0.5)
            break
        time.sleep(2)

    if not tavern_pos:
        print("[警告] 未找到'私人城镇'按钮，但游戏已成功重启")

    # 第9步：每 5 秒识别一次 War Table，识别到即代表游戏已加载进入私人城堡界面
    print("[恢复] 开始每 5 秒识别 War Table，识别到即继续…")
    war_table_timeout = 180  # 最长等 3 分钟兜底（避免异常情况下永久等待）
    war_table_found = False
    for _ in range(war_table_timeout // 5):
        if STOP_FLAG:
            print("[恢复] 收到停止信号，退出等待")
            return False
        hwnd = find_game_window()
        if hwnd:
            wt_match = detect_war_table(hwnd)
            if wt_match is not None:
                print(f"[恢复] 已识别到 War Table（置信度={wt_match[2]:.4f}），游戏加载完成，继续")
                war_table_found = True
                break
        time.sleep(5)
    if not war_table_found:
        print(f"[恢复] 等待 {war_table_timeout} 秒后仍未识别到 War Table，继续流程（兜底）")

    # 重置 REFRESH 缓存坐标（游戏重启后坐标可能变化）
    REFRESH_CLICK_POINT = None

    print("=" * 50)
    print("[恢复] 游戏恢复流程完成！")
    print("=" * 50)
    return True


def check_and_recover_if_frozen(freeze_monitor):
    """检查游戏是否卡死，如果卡死则执行恢复流程。
    恢复成功后返回 True，否则返回 False。"""
    if freeze_monitor.check():
        print("[卡死检测] 游戏判定卡死，开始恢复...")
        success = recover_game()
        freeze_monitor.reset()
        if success:
            print("[卡死检测] 游戏恢复成功，继续执行正常流程")
        else:
            print("[卡死检测] 游戏恢复失败，请手动处理")
        return success
    return False


# ========================= 窗口工具模块 =========================
# 负责游戏窗口的查找、聚焦、截图等基础操作

def find_game_window():
    """优先使用精确窗口句柄，找不到时再使用枚举法按标题回退。"""
    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
    if hwnd != 0:
        return hwnd

    found_hwnds = []

    def enum_windows_callback(current_hwnd, _):
        if not win32gui.IsWindowVisible(current_hwnd):
            return True
        title = win32gui.GetWindowText(current_hwnd)
        if CONFIG["game_title"] in title:
            found_hwnds.append(current_hwnd)
        return True

    win32gui.EnumWindows(enum_windows_callback, None)
    if found_hwnds:
        return found_hwnds[0]

    raise RuntimeError(
        f"未找到游戏窗口：class={CONFIG['game_class']} title={CONFIG['game_title']}"
    )


def focus_game_window(hwnd=None):
    """
    把游戏窗口切到前台，并默认移到屏幕左上角(0,0)，避免挡住 Trae/脚本输出窗口。
    不再对游戏窗口做永久顶层霸占，避免你点击浏览器或 VS Code 时被挡住。
    """
    if hwnd is None:
        hwnd = find_game_window()

    if hwnd == 0:
        raise RuntimeError("游戏窗口句柄无效")

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    # —— 每次聚焦后自动把窗口移到屏幕左上角，避免遮挡脚本输出
    # 注意：只移动位置，不改窗口大小（SWP_NOSIZE）。
    # 之前用 get_window_rect 返回的客户区尺寸去 SetWindowPos 设整窗口大小，
    # 会导致窗口越缩越小、客户区比例失调、游戏画面变扁。
    try:
        win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW)
    except Exception:
        pass

    try:
        win32gui.BringWindowToTop(hwnd)
    except Exception:
        pass

    try:
        ctypes.windll.user32.AllowSetForegroundWindow(
            ctypes.windll.kernel32.GetCurrentProcessId()
        )
    except Exception:
        pass

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass

    try:
        win32gui.SetActiveWindow(hwnd)
    except Exception:
        pass

    time.sleep(0.10)
    return hwnd


def get_window_rect(hwnd):
    """返回游戏窗口的屏幕矩形区域 (left, top, width, height)，物理像素，兼容 1K/2K 不同 DPI 缩放。
    使用 GetWindowRect 返回整窗口矩形（含标题栏/边框），与原来 2K 下能正常识别的行为保持一致。
    截图与点击坐标都基于此矩形，模板图也基于此截图裁剪。"""
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w = right - left
        h = bottom - top
        # 兜底：若窗口宽高异常偏小（DPI 虚拟化仍在生效），按当前显示器 DPI 缩放补齐
        if hwnd and (w < 1200 or h < 700):
            scale = get_monitor_dpi_from_window(hwnd)
            if scale > 1.01:
                left = int(left * scale)
                top = int(top * scale)
                w = int(w * scale)
                h = int(h * scale)
        return left, top, w, h
    except Exception:
        return 0, 0, 1920, 1080


def get_client_size(hwnd):
    """返回游戏窗口客户区尺寸（物理像素）。
    游戏内部渲染分辨率固定为 1600x900 时，客户区也应一致；否则使用实际值。"""
    try:
        rect = win32gui.GetClientRect(hwnd)
        cw = rect[2] - rect[0]
        ch = rect[3] - rect[1]
        if cw <= 0 or ch <= 0:
            return 1600, 900
        return cw, ch
    except Exception:
        return 1600, 900


def _capture_with_desktop_retry(capture_func):
    """桌面锁定导致 BitBlt 被拒绝时等待恢复，避免异常终止整个脚本。"""
    retry_started_at = None
    last_log_at = 0.0

    while not STOP_FLAG:
        try:
            image = capture_func()
            if retry_started_at is not None:
                waited = time.time() - retry_started_at
                print(f"[截图] 桌面截图已恢复，等待 {waited:.1f} 秒后继续原流程")
            return image
        except Exception as exc:
            error_text = str(exc).lower()
            desktop_unavailable = (
                "bitblt" in error_text
                or "拒绝访问" in error_text
                or "access is denied" in error_text
            )
            if not desktop_unavailable:
                raise

            now = time.time()
            if retry_started_at is None:
                retry_started_at = now
            if now - last_log_at >= 30.0:
                print(f"[WARN] 桌面可能已锁定，截图暂时不可用；每 5 秒重试，不会终止脚本：{exc}")
                last_log_at = now
            for _ in range(5):
                if STOP_FLAG:
                    break
                time.sleep(1.0)

    raise RuntimeError("收到停止信号，停止等待桌面截图恢复")


def capture_game_window(hwnd):
    """使用 mss 截取游戏窗口当前画面；锁屏时等待恢复后继续。"""
    def _grab():
        x, y, width, height = get_window_rect(hwnd)
        if width <= 0 or height <= 0:
            raise RuntimeError("游戏窗口尺寸无效")

        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": width, "height": height}
            img = np.array(sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    return _capture_with_desktop_retry(_grab)


def capture_client_region(hwnd, left, top, width, height):
    """截取客户区指定区域；锁屏时等待恢复，并确保每次尝试都释放 GDI 资源。"""
    def _grab():
        hdc_window = None
        hdc_mem = None
        hbmp = None
        old_bmp = None
        try:
            hdc_window = win32gui.GetDC(hwnd)
            hdc_mem = win32gui.CreateCompatibleDC(hdc_window)
            hbmp = win32gui.CreateCompatibleBitmap(hdc_window, width, height)
            old_bmp = win32gui.SelectObject(hdc_mem, hbmp)

            win32gui.BitBlt(
                hdc_mem, 0, 0, width, height,
                hdc_window, left, top, win32con.SRCCOPY
            )

            hbmp_obj = win32ui.CreateBitmapFromHandle(hbmp)
            bmp_str = hbmp_obj.GetBitmapBits(True)
            img = np.frombuffer(bmp_str, dtype=np.uint8).reshape((height, width, 4))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        finally:
            if hdc_mem and old_bmp:
                win32gui.SelectObject(hdc_mem, old_bmp)
            if hbmp:
                win32gui.DeleteObject(hbmp)
            if hdc_mem:
                win32gui.DeleteDC(hdc_mem)
            if hdc_window:
                win32gui.ReleaseDC(hwnd, hdc_window)

    return _capture_with_desktop_retry(_grab)


# ========================= 图像识别模块 =========================
# 模板加载（带缓存）、模板匹配、OCR 文字识别

def load_template(template_path):
    """
    加载模板图片，并做缓存，避免每帧重复读盘。
    这里优先走 Pillow，避免 OpenCV 在中文路径下的解码兼容性问题。
    """
    template_path = str(template_path)

    if template_path in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[template_path]

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板图片不存在：{template_path}")

    try:
        from PIL import Image
        img = np.array(Image.open(template_path).convert("RGB"))
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    except Exception as pil_exc:
        raise ValueError(f"模板图片读取失败：{template_path} | {pil_exc}") from pil_exc

    TEMPLATE_CACHE[template_path] = img
    return img


def find_template_center(frame_bgr, template_bgr, threshold=None):
    """
    在当前画面中寻找模板图片的位置，返回中心坐标（x, y），找不到返回 None。
    这里会做 cv2.matchTemplate 模板匹配。
    """
    result = find_template_rect(frame_bgr, template_bgr, threshold=threshold)
    if result is None:
        return None
    return result["center_x"], result["center_y"], result["max_val"]


def find_template_rect(frame_bgr, template_bgr, threshold=None):
    """返回模板匹配结果的矩形信息，便于后续 OCR 裁剪和点击定位。

    当单尺度匹配失败时，自动尝试多尺度匹配（0.5x~2.0x），
    以适应不同分辨率/DPI 缩放下的模板匹配。
    """
    if threshold is None:
        threshold = CONFIG["match_threshold"]

    fh, fw = frame_bgr.shape[:2]
    th, tw = template_bgr.shape[:2]

    # 先尝试 1.0x 原始尺度（最快，匹配成功直接返回）
    result = cv2.matchTemplate(frame_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        x0 = max_loc[0]
        y0 = max_loc[1]
        x1 = x0 + tw
        y1 = y0 + th
        return {
            "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "center_x": x0 + tw // 2,
            "center_y": y0 + th // 2,
            "max_val": max_val,
            "scale": 1.0,
        }

    # 单尺度匹配失败，尝试多尺度
    # 预计算可用的缩放比例（跳过原始尺度 1.0x，跳过会使模板大于帧的比例）
    scales = [s for s in [0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]
              if int(tw * s) <= fw and int(th * s) <= fh]

    best_score = max_val
    best_result = None

    for scale in scales:
        scaled = cv2.resize(template_bgr, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA)
        s_th, s_tw = scaled.shape[:2]
        result = cv2.matchTemplate(frame_bgr, scaled, cv2.TM_CCOEFF_NORMED)
        _, s_max_val, _, s_max_loc = cv2.minMaxLoc(result)

        if s_max_val > best_score:
            best_score = s_max_val
            x0 = s_max_loc[0]
            y0 = s_max_loc[1]
            x1 = x0 + s_tw
            y1 = y0 + s_th
            best_result = {
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "center_x": x0 + s_tw // 2,
                "center_y": y0 + s_th // 2,
                "max_val": s_max_val,
                "scale": scale,
            }

    if best_score >= threshold:
        if best_result is not None:
            return best_result
        # 原始尺度刚好达标
        return {
            "x0": max_loc[0], "y0": max_loc[1],
            "x1": max_loc[0] + tw, "y1": max_loc[1] + th,
            "center_x": max_loc[0] + tw // 2,
            "center_y": max_loc[1] + th // 2,
            "max_val": max_val,
            "scale": 1.0,
        }

    return None


# ========================= 走路控制模块（无光标模式） =========================
# 走路阶段游戏没有系统鼠标光标，使用 WASD 键控制移动和视角

def safe_press(key_name, duration=0.12):
    """安全按键：先保证游戏窗口在前台，再执行按键（按住时长加 ±30% 抖动）。"""
    hwnd = find_game_window()
    focus_game_window(hwnd)
    actual_duration = duration * random.uniform(0.7, 1.3)
    pyautogui.keyDown(key_name)
    time.sleep(actual_duration)
    pyautogui.keyUp(key_name)


def move_forward_once():
    """前进一步：无需系统鼠标光标，直接用 W 键走。"""
    safe_press("w", duration=CONFIG["forward_press_ms"] / 1000.0)
    time.sleep(CONFIG["step_wait_seconds"])


def rotate_view(direction, drag_px=160):
    """
    走路阶段不再使用鼠标右键拖拽视角。
    这里改为：只在目标偏左/偏右时做轻微 A/D 横移校正，主动作仍然是 W 慢走。
    """
    hwnd = find_game_window()
    focus_game_window(hwnd)

    if direction < 0:
        safe_press("a", duration=CONFIG["strafe_press_ms"] / 1000.0)
    else:
        safe_press("d", duration=CONFIG["strafe_press_ms"] / 1000.0)

    time.sleep(CONFIG["step_wait_seconds"])


def left_scan_once():
    rotate_view(-1, drag_px=160)


def right_scan_once():
    rotate_view(1, drag_px=160)


# ========================= 界面交互模块（有光标模式） =========================
# 弹窗阶段游戏有鼠标光标，使用鼠标点击和键盘交互

def press_e_interact():
    """
    当检测到 E 提示图时，按下 E 打开爬塔房间选择界面。
    这里属于“弹窗有光标点击模式”的交互阶段。
    """
    hwnd = find_game_window()
    focus_game_window(hwnd)

    # 人性化按 E（随机按住时长）
    humanized_press("e")
    print("[INFO] 已按下 E，尝试打开爬塔房间选择界面")


def click_screen_position(screen_x, screen_y, clicks=1):
    """利用当前屏幕坐标执行鼠标点击（已加入人性化鼠标移动）。"""
    hwnd = find_game_window()
    focus_game_window(hwnd)
    humanized_move_to(screen_x, screen_y)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.click(clicks=clicks)


def click_template_image(template_path, label=None, threshold=None, clicks=1):
    """在当前游戏窗口中根据模板图触发鼠标点击。"""
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(template_path)
    rect = find_template_rect(frame, template, threshold=threshold)
    if rect is None:
        if label:
            print(f"[WARN] 未找到 {label} 模板：{template_path}")
        return False

    left, top, width, height = get_window_rect(hwnd)
    screen_x = left + rect["center_x"]
    screen_y = top + rect["center_y"]
    click_screen_position(screen_x, screen_y, clicks=clicks)
    print(f"[INFO] 已点击 {label or template_path}")
    return True


def ocr_text_from_image(image_bgr, psm=7):
    """对 BGR 图像做 OCR 识别。"""
    try:
        from PIL import Image
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
        pil_image = Image.fromarray(binary)
        text = pytesseract.image_to_string(
            pil_image,
            config=f"--psm {psm} --oem 3",
        )
        return text.strip()
    except Exception as exc:
        print(f"[WARN] OCR 识别失败: {exc}")
        return ""


def ocr_word_boxes_from_image(image_bgr, psm=6):
    """返回 OCR 单词及坐标信息，后续用于解析房间列表中的 floor 数字。"""
    try:
        from PIL import Image
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
        pil_image = Image.fromarray(binary)
        data = pytesseract.image_to_data(
            pil_image,
            config=f"--psm {psm} --oem 3",
            output_type=Output.DICT,
        )
        return data
    except Exception as exc:
        print(f"[WARN] OCR 数据识别失败: {exc}")
        return {"text": [], "left": [], "top": [], "width": [], "height": [], "conf": []}


def _recognize_number_with_ddddocr(ocr, image_bgr, max_digits=3, min_digits=1):
    """对图像做多种预处理后用 ddddocr 识别数字，返回 int 或 None。
    max_digits: 最大位数（Floor=3, Score=2）
    min_digits: 最小位数（默认1）"""
    if image_bgr.size == 0:
        return None

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    preprocessed_images = [
        ("raw", image_bgr),
        ("gray", gray),
        ("binary120", cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)[1]),
        ("binary_inv120", cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)[1]),
        ("otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        ("otsu_inv", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]),
        ("binary150", cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]),
        ("binary_inv150", cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)[1]),
    ]

    for method, img in preprocessed_images:
        try:
            img_bytes = cv2.imencode('.png', img)[1].tobytes()
            text = ocr.classification(img_bytes)
            # 噪声过滤：如果原始文本包含大量非数字字母（纯字母串），直接跳过
            letter_count = sum(1 for c in text if c.isalpha())
            digit_count = sum(1 for c in text if c.isdigit())
            if letter_count > digit_count and digit_count < min_digits:
                # 大部分是字母，识别的不是数字，跳过（如'IoN5VSURVMA'这种噪声）
                continue
            clean = ''.join(c for c in text if c.isdigit())
            if min_digits <= len(clean) <= max_digits:
                num = int(clean)
                print(f"[DEBUG] ddddocr 识别成功: {method} text='{text}' num={num}")
                return num
        except Exception:
            continue

    return None


def _detect_row_boundaries(bgr_img):
    """通过红色通道检测行分割线，返回 [(y0, y1), ...] 每行的起止 Y 坐标。
    DD2 房间列表的 Floor 数字是亮红色，用 R-G 差值提取红色区域，
    从红色像素的 Y 坐标反推行边界，比灰度投影法准确得多。"""
    h, w = bgr_img.shape[:2]

    # 1. 提取红色区域（Floor数字是红色: R高, G/B低）
    b, g, r = cv2.split(bgr_img)
    red_mask = ((r.astype(np.int16) - g.astype(np.int16)) > 50) & \
               ((r.astype(np.int16) - b.astype(np.int16)) > 50) & \
               (r > 100)
    red_u8 = (red_mask.astype(np.uint8)) * 255

    # 2. 对红色掩码做水平投影，找到每行红色内容的 Y 范围
    red_proj = np.mean(red_u8, axis=1)

    # 3. 找红色像素密度>0的行区间（即Floor数字所在的行）
    row_threshold = 5  # 平均每个像素5以上有红色
    is_red = red_proj > row_threshold
    # 平滑
    kernel_size = 7
    smoothed = np.convolve(is_red.astype(float), np.ones(kernel_size)/kernel_size, mode='same')
    is_red_sm = smoothed > 0.4

    # 找红色行区间
    red_ranges = []
    in_range = False
    start = 0
    for y in range(h):
        if is_red_sm[y] and not in_range:
            start = y
            in_range = True
        elif not is_red_sm[y] and in_range:
            if y - start >= 15:  # Floor数字至少15px高
                red_ranges.append((start, y))
            in_range = False
    if in_range and h - start >= 15:
        red_ranges.append((start, h))

    print(f"[DEBUG] 红色通道检测到 {len(red_ranges)} 个Floor行, Y区间={red_ranges}")

    # 4. 根据红色行区间反推行边界
    #    每个红色行代表一行数据，行边界 = 红色区间 + 半个行距
    if len(red_ranges) >= 2:
        # 计算行距
        gaps = []
        for i in range(len(red_ranges) - 1):
            gap = red_ranges[i+1][0] - red_ranges[i][1]
            if gap > 0:
                gaps.append(gap)
        avg_gap = np.mean(gaps) if gaps else 20

        boundaries = []
        for i, (rs, re) in enumerate(red_ranges):
            # 上边界
            if i == 0:
                y0 = max(0, rs - int(avg_gap * 0.6))
            else:
                y0 = (red_ranges[i-1][1] + rs) // 2
            # 下边界
            if i == len(red_ranges) - 1:
                y1 = min(h, re + int(avg_gap * 0.6))
            else:
                y1 = (re + red_ranges[i+1][0]) // 2
            boundaries.append((y0, y1))

        print(f"[DEBUG] 行距={avg_gap:.0f}px, 行边界={boundaries}")
        return boundaries

    # 5. 红色通道没检测到，回退到灰度投影法
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    row_proj = np.mean(gray, axis=1)
    best_boundaries = []
    for threshold in (210, 200, 190, 180, 170, 160):
        is_content = row_proj < threshold
        smoothed = np.convolve(is_content.astype(float), np.ones(5)/5, mode='same')
        is_content_sm = smoothed > 0.3
        boundaries = []
        in_content = False
        start = 0
        for y in range(h):
            if is_content_sm[y] and not in_content:
                start = y; in_content = True
            elif not is_content_sm[y] and in_content:
                if y - start >= 8:
                    boundaries.append((start, y))
                in_content = False
        if in_content and h - start >= 8:
            boundaries.append((start, h))
        if len(boundaries) > len(best_boundaries):
            best_boundaries = boundaries
        if 4 <= len(best_boundaries) <= 7:
            break
    boundaries = best_boundaries
    if len(boundaries) < 3:
        row_count = 5
        row_h = h // row_count
        boundaries = [(i * row_h, (i + 1) * row_h) for i in range(row_count)]
    print(f"[DEBUG] 灰度回退检测: {len(boundaries)} 行, 区间={boundaries}")
    return boundaries


def ocr_room_list_numbers(image_bgr):
    """使用连通域 + ddddocr 识别房间列表的 Floor 数字和 Score 数字。

    参考 Tesseract 方案的核心思路：
    1. 跳过顶部 5% 区域（避开 "Floor" 表头，防止 "Floor" 中的 "l" 被识别成 1）
    2. 同行合并：间距<25px的独立数字拼接（如 "1"+"9"→"19"）
    3. 按 X 比例区分列：Floor列 55%-82%，Score列 82%-95%
    4. NONE 等字母被 ddddocr 数字模式忽略，自动过滤

    Returns:
        {"floors": [(value, left, top, width, height, conf), ...],
         "scores": [(value, top), ...]}
    """
    ocr = _get_ddddocr_instance()
    if ocr is None:
        return {"floors": [], "scores": []}

    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # ===== 1. 限制 Y 轴数据区 =====
    # Y:22%-80%（避开顶部 "Floor" 表头和底部空白区域）
    y_start = int(h * 0.22)
    y_end = int(h * 0.80)
    work_gray = gray[y_start:y_end, :]
    work_h = work_gray.shape[0]
    y_offset = y_start  # 记录偏移量用于还原坐标

    # ===== 2. 连通域分析找白色文字 =====
    _, binary = cv2.threshold(work_gray, 200, 255, cv2.THRESH_BINARY)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    components = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > 5:
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP] + y_offset  # 还原到原图坐标
            cw = stats[i, cv2.CC_STAT_WIDTH]
            ch = stats[i, cv2.CC_STAT_HEIGHT]
            components.append((x, y, cw, ch, area))

    if not components:
        print("[DEBUG] 连通域检测未找到任何白色文字")
        return {"floors": [], "scores": []}

    # ===== 3. 按行聚类 + 同行业合并 =====
    components.sort(key=lambda c: (c[1] // 15, c[0]))

    rows = []
    current_row = [components[0]]
    for comp in components[1:]:
        if abs(comp[1] - current_row[0][1]) < 25:
            current_row.append(comp)
        else:
            rows.append(current_row)
            current_row = [comp]
    rows.append(current_row)

    # 同一行内合并紧贴的连通域（间距<5px）
    merged_rows = []
    for row_comps in rows:
        row_comps.sort(key=lambda c: c[0])
        merged = []
        i = 0
        while i < len(row_comps):
            comp = list(row_comps[i])
            while i + 1 < len(row_comps):
                next_comp = row_comps[i + 1]
                gap = next_comp[0] - (comp[0] + comp[2])
                if gap <= 5:
                    new_x = min(comp[0], next_comp[0])
                    new_y = min(comp[1], next_comp[1])
                    new_x2 = max(comp[0] + comp[2], next_comp[0] + next_comp[2])
                    new_y2 = max(comp[1] + comp[3], next_comp[1] + next_comp[3])
                    comp = [new_x, new_y, new_x2 - new_x, new_y2 - new_y, comp[4] + next_comp[4]]
                    i += 1
                else:
                    break
            merged.append(tuple(comp))
            i += 1
        merged_rows.append(merged)

    print(f"[DEBUG] 连通域检测到 {len(components)} 个文字区域，分为 {len(merged_rows)} 行")

    # ===== 4. 逐区域 OCR：紧裁剪 + 放大5倍 + 多种预处理 =====
    ocr.set_ranges("0123456789")

    raw_digits = []
    for row_comps in merged_rows:
        for comp_x, comp_y, comp_w, comp_h, comp_area in row_comps:
            pad = 3
            cx0 = max(0, comp_x - pad)
            cy0 = max(0, comp_y - pad)
            cx1 = min(w, comp_x + comp_w + pad)
            cy1 = min(h, comp_y + comp_h + pad)
            digit_crop = gray[cy0:cy1, cx0:cx1]
            if digit_crop.size == 0:
                continue

            big = cv2.resize(digit_crop, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)

            digit_result = None
            pre_images = [
                cv2.threshold(big, 180, 255, cv2.THRESH_BINARY)[1],
                cv2.threshold(big, 150, 255, cv2.THRESH_BINARY)[1],
                cv2.threshold(big, 120, 255, cv2.THRESH_BINARY)[1],
                big,
            ]
            for pimg in pre_images:
                try:
                    buf = cv2.imencode('.png', pimg)[1].tobytes()
                    text = ocr.classification(buf)
                    if text and text.isdigit() and 1 <= len(text) <= 3:
                        digit_result = text
                        break
                except Exception:
                    pass

            if digit_result is not None:
                raw_digits.append({
                    "token": digit_result,
                    "left": comp_x,
                    "top": comp_y,
                    "width": comp_w,
                    "height": comp_h,
                    "conf": 1.0,
                })

    if not raw_digits:
        print("[DEBUG] 房间列表 ddddocr 未识别到任何 Floor 数字")
        return {"floors": [], "scores": []}

    # ===== 5. 同行相邻数字合并：如 "1"+"9"→"19" =====
    raw_digits.sort(key=lambda d: (d["top"], d["left"]))
    merged_digits = []
    for d in raw_digits:
        if merged_digits:
            prev = merged_digits[-1]
            same_row = abs(d["top"] - prev["top"]) < 15
            right_edge = prev["left"] + prev["width"]
            gap = d["left"] - right_edge
            adjacent = -5 <= gap <= 25
            if same_row and adjacent:
                combined = prev["token"] + d["token"]
                if len(combined) <= 4:
                    prev["token"] = combined
                    new_right = max(prev["left"] + prev["width"], d["left"] + d["width"])
                    prev["width"] = new_right - prev["left"]
                    prev["height"] = max(prev["height"], d["height"])
                    continue
        merged_digits.append(dict(d))

    # ===== 6. 过滤：1-3位数字，按 X 比例分列 =====
    floors = []
    scores = []

    for d in merged_digits:
        token = d["token"]
        if not token.isdigit() or not (1 <= len(token) <= 3):
            continue

        crop_w = w
        center_ratio = (d["left"] + d["width"] / 2) / crop_w if crop_w > 0 else 0

        # Floor 列：裁剪宽度的 70%-80%（左移5%）
        if 0.70 <= center_ratio <= 0.80:
            floors.append((
                int(token), d["left"], d["top"],
                d["width"], d["height"], d["conf"]
            ))
        # CHAMPION SCORE 列：裁剪宽度的 85%-92%（收窄）
        elif 0.85 < center_ratio <= 0.92:
            scores.append((int(token), d["top"]))

    if not floors:
        print("[DEBUG] 房间列表 ddddocr 未识别到任何 Floor 数字")
    else:
        print(f"[DEBUG] 房间列表 ddddocr 识别到 Floor: {[f[0] for f in floors]}")

    return {"floors": floors, "scores": scores}

def extract_selected_floor_number(hwnd, max_retries=5):
    """根据当前楼层区域模板直接识别区域内的三位数字。
    多次重试，每次尝试不同的二值化阈值和裁剪策略。"""
    for attempt in range(1, max_retries + 1):
        result = _try_extract_selected_floor(hwnd)
        if result is not None:
            print(f"[INFO] 第 {attempt} 次尝试成功，Selected Floor={result}")
            return result
        print(f"[INFO] 第 {attempt} 次尝试未识别到有效数字，重试...")
        if attempt < max_retries:
            time.sleep(1.5)

    print(f"[WARN] 经过 {max_retries} 次尝试仍未识别到 Selected Floor")
    return None


_DDDDOCR_INSTANCE = None  # ddddocr 全局单例，避免每次调用都重新加载模型


def _get_ddddocr_instance():
    """延迟初始化 ddddocr 单例，失败时返回 None。"""
    global _DDDDOCR_INSTANCE
    if _DDDDOCR_INSTANCE is not None:
        return _DDDDOCR_INSTANCE
    try:
        import ddddocr
        _DDDDOCR_INSTANCE = ddddocr.DdddOcr(show_ad=False, beta=True)
        print("[INFO] ddddocr 初始化成功")
    except ImportError:
        print("[WARN] ddddocr 未安装，数字识别将不可用 (pip install ddddocr)")
    except Exception as exc:
        print(f"[WARN] ddddocr 初始化失败: {exc}")
    return _DDDDOCR_INSTANCE


def _try_extract_selected_floor(hwnd):
    """单次尝试识别 Selected Floor 数字，返回 int 或 None。

    流程：
    1) 先尝试用 Selected Floor.png 模板定位（匹配成功则直接裁剪数字区域）
    2) 模板匹配失败时，回退到固定比例区域裁剪（X:10%-30%, Y:40%-60%）
    3) 在裁剪区域上用 ddddocr + 多种预处理方案识别三位数字
    """
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]

    debug_dir = SCRIPT_DIR / "_debug_selected_floor"
    debug_dir.mkdir(exist_ok=True)

    ocr = _get_ddddocr_instance()
    if ocr is None:
        return None

    # ===== 第1步：尝试模板匹配定位 =====
    crop_region = None  # (x0, y0, x1, y1) 数字区域在整帧中的坐标

    try:
        template = load_template(CONFIG["selected_floor_template"])
        # 多尺度匹配，提高不同分辨率下的匹配率
        best_match = None
        best_score = 0
        for scale in [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]:
            scaled = cv2.resize(template, None, fx=scale, fy=scale,
                               interpolation=cv2.INTER_AREA)
            sh, sw = scaled.shape[:2]
            if sw > w or sh > h:
                continue
            result = cv2.matchTemplate(frame, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = max_val
                best_match = (max_loc, sw, sh, scale)

        if best_match and best_score >= 0.50:
            loc, tw, th, scale = best_match
            # 模板中心附近是数字区域，裁掉左右箭头各 30%
            margin_x = int(tw * 0.30)
            margin_y = max(4, int(th * 0.10))
            cx0 = max(0, loc[0] + margin_x)
            cy0 = max(0, loc[1] + margin_y)
            cx1 = min(w, loc[0] + tw - margin_x)
            cy1 = min(h, loc[1] + th - margin_y)
            crop_region = (cx0, cy0, cx1, cy1)
            print(f"[DEBUG] 模板匹配成功 scale={scale} score={best_score:.3f} "
                  f"区域=({cx0},{cy0})-({cx1},{cy1})")
        else:
            print(f"[DEBUG] 模板匹配最高分={best_score:.3f}，低于阈值0.50，"
                  f"回退到固定比例区域")
    except FileNotFoundError:
        print("[DEBUG] Selected Floor.png 模板不存在，使用固定比例区域")
    except Exception as exc:
        print(f"[DEBUG] 模板匹配异常: {exc}，使用固定比例区域")

    # ===== 第2步：回退到固定比例区域 =====
    if crop_region is None:
        # 根据截图分析，Selected Floor 数字位于窗口左侧
        # X: 10%-30%, Y: 40%-60%
        rx0, rx1 = 0.10, 0.30
        ry0, ry1 = 0.40, 0.60
        cx0 = int(w * rx0)
        cy0 = int(h * ry0)
        cx1 = int(w * rx1)
        cy1 = int(h * ry1)
        crop_region = (cx0, cy0, cx1, cy1)
        print(f"[DEBUG] 使用固定比例区域 X:{rx0:.0%}-{rx1:.0%} Y:{ry0:.0%}-{ry1:.0%} "
              f"=({cx0},{cy0})-({cx1},{cy1})")

    # ===== 第3步：裁剪并识别 =====
    cx0, cy0, cx1, cy1 = crop_region
    crop = frame[cy0:cy1, cx0:cx1]

    # 保存裁剪区域供调试
    cv2.imwrite(str(debug_dir / "crop_region.png"), crop)
    ch, cw = crop.shape[:2]
    print(f"[DEBUG] 裁剪区域: {cw}x{ch}")

    # 在裁剪区域上尝试 OCR 识别
    result = _ocr_recognize_three_digits(ocr, crop)
    if result is not None:
        print(f"[INFO] Selected Floor 识别成功: {result}")
        cv2.imwrite(str(debug_dir / f"success_{result}.png"), crop)
        return result

    # 如果固定比例区域没识别到，尝试扩大搜索范围
    print("[DEBUG] 首次裁剪区域未识别到，尝试扩大范围...")
    for expand_x in [(0.08, 0.32), (0.05, 0.35)]:
        ex0 = int(w * expand_x[0])
        ex1 = int(w * expand_x[1])
        ey0 = cy0
        ey1 = cy1
        if ex1 - ex0 > 30:
            crop2 = frame[ey0:ey1, ex0:ex1]
            result = _ocr_recognize_three_digits(ocr, crop2)
            if result is not None:
                print(f"[INFO] Selected Floor 识别成功(扩大X范围): {result}")
                return result

    # 也尝试 Y 轴扩大
    for expand_y in [(0.35, 0.55), (0.38, 0.62), (0.42, 0.58)]:
        ey0 = int(h * expand_y[0])
        ey1 = int(h * expand_y[1])
        crop3 = frame[ey0:ey1, cx0:cx1]
        if crop3.size > 0:
            result = _ocr_recognize_three_digits(ocr, crop3)
            if result is not None:
                print(f"[INFO] Selected Floor 识别成功(扩大Y范围): {result}")
                return result

    # 最后：在整个客户区左半部分做滑动窗口扫描
    print("[DEBUG] 扩大范围仍未识别到，尝试滑动窗口扫描...")
    left_half = frame[int(h*0.15):int(h*0.65), int(w*0.05):int(w*0.40)]
    lh, lw = left_half.shape[:2]
    for win_w in [60, 80, 100, 120, 150]:
        for win_h in [25, 35, 45, 55]:
            for sx in range(0, lw - win_w, 15):
                for sy in range(0, lh - win_h, 10):
                    sub = left_half[sy:sy+win_h, sx:sx+win_w]
                    if sub.size == 0:
                        continue
                    result = _ocr_recognize_three_digits(ocr, sub)
                    if result is not None:
                        abs_x = sx + int(w * 0.05)
                        abs_y = sy + int(h * 0.15)
                        print(f"[INFO] Selected Floor 识别成功(滑动窗口): {result} "
                              f"位置=({abs_x},{abs_y})")
                        return result

    print("[DEBUG] 所有方法均未识别到有效三位数字")
    return None


def _ocr_recognize_three_digits(ocr, image_bgr):
    """对图像做多种预处理后用 ddddocr 识别，返回三位数字 int 或 None。"""
    if image_bgr.size == 0:
        return None

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # 多种预处理方案
    preprocessed_images = [
        ("raw", image_bgr),
        ("gray", gray),
        ("binary120", cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)[1]),
        ("binary_inv120", cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)[1]),
        ("otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        ("otsu_inv", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]),
        ("binary150", cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]),
        ("binary_inv150", cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)[1]),
    ]

    for method, img in preprocessed_images:
        try:
            img_bytes = cv2.imencode('.png', img)[1].tobytes()
            text = ocr.classification(img_bytes)
            clean = ''.join(c for c in text if c.isdigit())
            if len(clean) == 3:
                num = int(clean)
                if 100 <= num <= 999:
                    print(f"[DEBUG] ddddocr 识别成功: {method} text='{text}' num={num}")
                    return num
        except Exception:
            continue

    return None


def get_target_room_floor(hwnd, selected_floor):
    """扫描房间列表的 Floor 列和 CHAMPION SCORE 列，返回满足条件的目标房间。
    使用 ddddocr OCR + 行分割识别数字，避免 Tesseract 对游戏字体识别失败。
    房间列表有 4 列：NAME / Floor / CHAMPION SCORE / #
    合适房间条件：Floor >= selected_floor 且 CHAMPION SCORE == 0。"""
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]

    # 按游戏窗口比例裁剪右侧房间列表面板（X轴右半侧，包含 Floor / Score / # 三列）
    # 裁剪区域与测试脚本一致：X:30%-98%, Y:22%-80%
    x0 = int(w * 0.30)
    y0 = int(h * 0.22)
    x1 = int(w * 0.98)
    y1 = int(h * 0.80)
    crop = frame[y0:y1, x0:x1]

    # 保存裁剪区域供调试
    debug_dir = SCRIPT_DIR / "_debug_room_list"
    debug_dir.mkdir(exist_ok=True)
    cv2.imwrite(str(debug_dir / "room_list_crop.png"), crop)

    # 使用 ddddocr OCR（已改为行分割 + 单列识别）
    data = ocr_room_list_numbers(crop)

    floors = data.get("floors", [])   # [(value, top, height), ...]
    scores = data.get("scores", [])   # [(value, top), ...]

    if not floors:
        print("[WARN] 未从房间列表中识别到 floor 数字")
        return None, []

    # 按行匹配：每个 floor 找同一行（top 接近）的 CHAMPION SCORE
    # floors 中的 top 是裁剪区域内的 y 坐标，scores 中的 top 也是
    def find_score_for_row(floor_top, score_list, tolerance=20):
        for val, stop in score_list:
            if abs(stop - floor_top) <= tolerance:
                return val
        return None

    # 构建房间列表：(floor, champion_score, left, top, width, height, conf)
    # 注意：left/top/width/height 是裁剪区域内的坐标
    # 新 ocr_room_list_numbers 已返回 floor 数字的精确坐标，直接使用
    rooms = []
    for f_val, f_left, f_top, f_width, f_height, f_conf in floors:
        cs = find_score_for_row(f_top, scores)
        rooms.append((f_val, cs, f_left, f_top, f_width, f_height, f_conf))

    rooms.sort(key=lambda item: item[0], reverse=False)
    all_info = [(r[0], r[1]) for r in rooms]
    print(f"[INFO] 房间列表识别结果 (Floor, CHAMPION SCORE)：{all_info}，当前需要 Floor >= {selected_floor} 且 CHAMPION SCORE == 0")

    # 先筛选出所有"满足条件"的房间：Floor >= selected_floor 且 (CHAMPION SCORE is None or == 0)
    qualified_rooms = []
    for item in rooms:
        f_val, cs_val = item[0], item[1]
        if f_val >= selected_floor and (cs_val is None or cs_val == 0):
            qualified_rooms.append(item)

    if qualified_rooms:
        # 多个合适房间时选 FLOOR 最小的那个
        qualified_rooms.sort(key=lambda item: item[0], reverse=False)
        print(f"[INFO] 共 {len(qualified_rooms)} 个满足条件的房间 (Floor >= {selected_floor} 且 CHAMPION SCORE == 0)，FLOOR列表: {[r[0] for r in qualified_rooms]} → 选择最小FLOOR={qualified_rooms[0][0]}")
        room = qualified_rooms[0]
        print(f"[INFO] 目标房间：Floor={room[0]}，CHAMPION SCORE={room[1]}")
        # 返回格式：(floor, left, top, width, height, conf) — left/top/width/height 是裁剪区域内坐标
        return (room[0], room[2], room[3], room[4], room[5], room[6]), [r[0] for r in rooms]
    else:
        print(f"[INFO] 无满足条件的房间")
        return None, [r[0] for r in rooms]


def click_target_room_floor(hwnd, target_floor_info):
    """把鼠标移动到目标房间的 floor 数字处并双击进入。
    使用固定比例坐标计算点击位置，不依赖模板匹配。"""
    left, top, width, height = get_window_rect(hwnd)

    # 与 get_target_room_floor 使用相同的裁剪区域比例
    crop_x0 = int(width * 0.30)
    crop_y0 = int(height * 0.22)

    # target_floor_info: (floor_value, left, top, width, height, conf)
    floor_x = crop_x0 + target_floor_info[1] + target_floor_info[3] // 2
    floor_y = crop_y0 + target_floor_info[2] + target_floor_info[4] // 2
    screen_x = left + floor_x
    screen_y = top + floor_y

    click_screen_position(screen_x, screen_y, clicks=2)
    print(f"[INFO] 已双击目标房间 floor={target_floor_info[0]}")
    return True


def click_refresh_button():
    """点击 REFRESH 按钮，刷新房间列表。第一次通过模板找到并点击，
    鼠标停留在 REFRESH 上，后续直接左键点击即可，不再找图。"""
    global REFRESH_CLICK_POINT

    if not os.path.exists(CONFIG["refresh_template"]):
        print("[WARN] REFRESH 模板尚未补充，跳过刷新点击")
        return False

    # 已有缓存坐标，鼠标已经在 REFRESH 上，直接左键点击
    if REFRESH_CLICK_POINT is not None:
        hwnd = find_game_window()
        focus_game_window(hwnd)
        screen_x, screen_y = REFRESH_CLICK_POINT
        click_screen_position(screen_x, screen_y, clicks=1)
        print(f"[INFO] 鼠标已在 REFRESH 上，直接左键点击：({screen_x}, {screen_y})")
        return True

    # 第一次找 REFRESH：鼠标没有遮挡，直接模板匹配
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(CONFIG["refresh_template"])
    rect = find_template_rect(frame, template, threshold=CONFIG["match_threshold"])
    if rect is None:
        print("[WARN] 未找到 REFRESH 模板")
        return False

    left, top, _, _ = get_window_rect(hwnd)
    REFRESH_CLICK_POINT = (left + rect["center_x"], top + rect["center_y"])
    print(f"[INFO] 首次找到 REFRESH，缓存点击点：{REFRESH_CLICK_POINT}")

    # 点击 REFRESH，点击后鼠标自然停留在按钮上
    click_screen_position(REFRESH_CLICK_POINT[0], REFRESH_CLICK_POINT[1], clicks=1)
    return True


def detect_finish_game_and_click_to_tavern():
    """检测 finish game 结算画面，并点击 To Tavern 返回城堡。"""
    if not os.path.exists(CONFIG["finish_game_template"]):
        print("[WARN] finish game 模板尚未提供，等待人工确认")
        return False

    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(CONFIG["finish_game_template"])
    rect = find_template_rect(frame, template, threshold=0.62)
    if rect is None:
        return False

    if os.path.exists(CONFIG["to_tavern_template"]):
        click_template_image(CONFIG["to_tavern_template"], label="To Tavern", threshold=0.62)
        print("[INFO] 已检测到 finish game，点击 To Tavern 返回城堡")
        return True

    print("[INFO] 已检测到 finish game，但 To Tavern 模板尚未补充")
    return True


def detect_other_players_ready():
    """检测左侧玩家头像右下角是否有绿色对勾（其他玩家已准备）。
    返回 True 表示检测到有玩家准备了。同时更新 LAST_PLAYER_READY_TIME。"""
    global LAST_PLAYER_READY_TIME
    if not os.path.exists(CONFIG["ready_template"]):
        print("[WARN] ready 模板不存在，跳过检测")
        return False

    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    ready_template = load_template(CONFIG["ready_template"])

    # 在左侧玩家头像区域搜索（左侧约 0%-15% 宽度，10%-50% 高度）
    h, w = frame.shape[:2]
    x0, y0 = 0, int(h * 0.10)
    x1, y1 = int(w * 0.15), int(h * 0.50)
    search_region = frame[y0:y1, x0:x1]

    result = cv2.matchTemplate(search_region, ready_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)

    if max_val >= 0.6:
        print(f"[INFO] 检测到其他玩家已准备（置信度: {max_val:.2f}）")
        LAST_PLAYER_READY_TIME = time.time()
        return True
    return False


def detect_game_failed():
    """检测游戏失败画面（gamefailed.png），检测到后按 N 键继续。返回 True 表示检测到了失败。"""
    if not os.path.exists(CONFIG["game_failed_template"]):
        return False

    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]
    template = load_template(CONFIG["game_failed_template"])

    # 只在游戏下半边区域搜索
    half_frame = frame[h // 2:, :]
    rect = find_template_rect(half_frame, template, threshold=0.6)
    if rect is None:
        return False

    print("[INFO] 检测到游戏失败画面，按 N 键继续...")
    focus_game_window(hwnd)
    humanized_press("n")
    time.sleep(2)
    return True


def detect_room_full():
    """检测房间已满画面（roomfull.png），检测到后点击 OK 按钮。
    - 点完OK后若仍在 War Table 旁（能识别到 e-tip）：直接按E走 after_e_branch_main()（含楼层判断/chaos判断/换装等）
    - 否则走原流程：点击私人城镇按钮再重新寻路
    使用与 dd2_full.py 相同的固定参考尺寸 (1600, 900) 和客户区截取方式。"""
    if not os.path.exists(CONFIG["roomfull_template"]):
        return False

    hwnd = find_game_window()
    template = load_template(CONFIG["roomfull_template"])

    # 客户区尺寸：游戏内分辨率固定为 1600x900，这里动态获取以兼容 DPI/窗口模式差异
    cw, ch = get_client_size(hwnd)
    region = (0.25, 0.35, 0.75, 0.65)
    left = int(region[0] * cw)
    top = int(region[1] * ch)
    right = int(region[2] * cw)
    bottom = int(region[3] * ch)
    width = right - left
    height = bottom - top

    search_region = capture_client_region(hwnd, left, top, width, height)
    rect = find_template_rect(search_region, template, threshold=0.6)
    if rect is None:
        return False

    print("[INFO] 检测到房间已满，开始恢复流程...")
    focus_game_window(hwnd)

    if os.path.exists(CONFIG["kickok_template"]):
        print("[INFO] 查找并点击 OK 按钮...")
        ok_found = False
        for attempt in range(10):
            frame = capture_game_window(hwnd)
            ok_template = load_template(CONFIG["kickok_template"])
            ok_rect = find_template_rect(frame, ok_template, threshold=0.6)
            if ok_rect is not None:
                left, top, _, _ = get_window_rect(hwnd)
                screen_x = left + ok_rect["center_x"]
                screen_y = top + ok_rect["center_y"]
                click_screen_position(screen_x, screen_y, clicks=1)
                print(f"[INFO] 已点击 OK 按钮")
                time.sleep(2)
                ok_found = True
                break
            print(f"[INFO] 未找到 OK 按钮，重试 {attempt + 1}/10...")
            time.sleep(1)
        
        if not ok_found:
            print("[INFO] 多次尝试未找到 OK 按钮，可能是鼠标箭头遮挡，缓慢将鼠标移到提示文字区域左上角...")
            win_left, win_top, _, _ = get_window_rect(hwnd)
            text_top_left_x = win_left + left
            text_top_left_y = win_top + top
            pyautogui.moveTo(text_top_left_x, text_top_left_y, duration=0.5)
            time.sleep(0.5)
            
            for attempt in range(5):
                frame = capture_game_window(hwnd)
                ok_template = load_template(CONFIG["kickok_template"])
                ok_rect = find_template_rect(frame, ok_template, threshold=0.6)
                if ok_rect is not None:
                    left, top, _, _ = get_window_rect(hwnd)
                    screen_x = left + ok_rect["center_x"]
                    screen_y = top + ok_rect["center_y"]
                    click_screen_position(screen_x, screen_y, clicks=1)
                    print(f"[INFO] 已点击 OK 按钮")
                    time.sleep(2)
                    ok_found = True
                    break
                print(f"[INFO] 移开鼠标后仍未找到 OK 按钮，重试 {attempt + 1}/5...")
                time.sleep(1)
        
        if not ok_found:
            print("[WARN] 移开鼠标后仍未找到 OK 按钮，跳过点击")
            time.sleep(2)
    else:
        print("[WARN] kickok 模板不存在，跳过点击")
        time.sleep(2)

    # ========= 新增：点OK后检测是否还在 War Table 旁（能识别到 e-tip） =========
    e_tip_path = CONFIG.get("e_tip_template")
    e_tip_threshold = CONFIG.get("e_tip_threshold", 0.62)
    if e_tip_path and os.path.exists(e_tip_path):
        print("[INFO] roomfull点击OK后，检测是否还在 War Table 旁（e-tip识别）...")
        etip_found = False
        for _attempt in range(3):
            frame = capture_game_window(hwnd)
            etip_template = load_template(e_tip_path)
            etip_rect = find_template_rect(frame, etip_template, threshold=e_tip_threshold)
            if etip_rect is not None:
                etip_found = True
                break
            time.sleep(1.0)
        if etip_found:
            print("[INFO] 仍能识别到e-tip，说明已退回到War Table旁 → 直接按E进入后续流程（含楼层<300换装等判断）")
            humanized_press("e")
            time.sleep(1.5)
            # 直接走完整的按E后楼层分支总入口（包含300层判断、换装、chaos9判断、找房间等全套流程）
            after_e_branch_main()
            # after_e_branch_main() 会跑完一局后返回 True/False，处理完后这里直接 return True，
            # 让上层 run_room_progression_loop 退出，回到最外层 while 开始下一轮
            return True
        else:
            print("[INFO] 未识别到e-tip，走原流程：点击私人城镇按钮重新寻路")
    # ==========================================================================

    print("[INFO] 点击游戏画面中间，等待私人城镇按钮...")
    game_rect = win32gui.GetWindowRect(hwnd)
    center_x = (game_rect[0] + game_rect[2]) // 2
    center_y = (game_rect[1] + game_rect[3]) // 2

    if os.path.exists(CONFIG["private_tavern_template"]):
        tavern_template = load_template(CONFIG["private_tavern_template"])
        for attempt in range(20):
            click_screen_position(center_x, center_y, clicks=1)
            time.sleep(1.5)

            frame = capture_game_window(hwnd)
            tavern_rect = find_template_rect(frame, tavern_template, threshold=0.6)
            if tavern_rect is not None:
                left, top, _, _ = get_window_rect(hwnd)
                screen_x = left + tavern_rect["center_x"]
                screen_y = top + tavern_rect["center_y"]
                click_screen_position(screen_x, screen_y, clicks=1)
                print("[INFO] 已点击私人城镇按钮")
                time.sleep(2)
                return True
            print(f"[INFO] 未找到私人城镇按钮，重试 {attempt + 1}/20...")

        print("[WARN] 未找到私人城镇按钮，但已尝试恢复")
    else:
        print("[WARN] 私人城镇模板不存在，跳过点击")

    return True


def detect_roomfull_9001_and_handle():
    """检测 9001roomfull.png 或 9001roomfullv2.png（点击房间后瞬间弹出的房间满员提示）。
    检测到其中任意一个后按 Enter 确认，返回 True；未检测到返回 False。
    该函数在双击进入房间后 60 秒内每 10 秒调用一次。"""
    global ROOMFULL_9001_TRIGGERED

    # 同时支持两个模板：9001roomfull.png 和 9001roomfullv2.png
    template_paths = [
        CONFIG.get("roomfull_9001_template"),
        CONFIG.get("roomfull_9001_v2_template"),
    ]
    template_paths = [p for p in template_paths if p and os.path.exists(p)]
    if not template_paths:
        return False

    hwnd = find_game_window()
    if not hwnd:
        return False

    frame = capture_game_window(hwnd)
    matched_template = None
    matched_rect = None
    for tp in template_paths:
        template = load_template(tp)
        rect = find_template_rect(frame, template, threshold=0.85)
        if rect is not None:
            matched_template = os.path.basename(tp)
            matched_rect = rect
            break

    if matched_rect is None:
        return False

    print(f"[INFO] 检测到 {matched_template} 满员提示（置信度={matched_rect['max_val']:.4f}），按 Enter 确认后重新识别 e-tip")
    focus_game_window(hwnd)
    humanized_press("enter")
    time.sleep(1.5)
    ROOMFULL_9001_TRIGGERED = True
    return True


def detect_failure_retry():
    """检测失败重来画面（失败重来.png），检测到后按 N 键继续。
    返回 True 表示检测到了失败重来。
    使用与 dd2_full.py 相同的固定参考尺寸 (1600, 900) 和客户区截取方式。"""
    if not os.path.exists(CONFIG["failure_retry_template"]):
        return False

    hwnd = find_game_window()
    template = load_template(CONFIG["failure_retry_template"])

    # 客户区尺寸：游戏内分辨率固定为 1600x900，这里动态获取以兼容 DPI/窗口模式差异
    cw, ch = get_client_size(hwnd)
    region = (0.48, 0.77, 0.5, 0.8)
    left = int(region[0] * cw)
    top = int(region[1] * ch)
    right = int(region[2] * cw)
    bottom = int(region[3] * ch)
    width = right - left
    height = bottom - top

    search_region = capture_client_region(hwnd, left, top, width, height)

    rect = find_template_rect(search_region, template, threshold=0.8)
    if rect is None:
        return False

    print("[INFO] 检测到失败重来画面，按 N 键继续...")
    focus_game_window(hwnd)
    humanized_press("n")
    time.sleep(2)
    return True


def detect_kicked_and_recover():
    """检测被踢出房间画面（bekick.png / bekick2.png / bekick3.png），检测到后点击 kickok 按钮，
    然后点击私人城镇按钮，返回 True 表示处理了被踢情况。"""
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)

    # 第1步：检测 bekick.png / bekick2.png / bekick3.png（三种样式都视为被踢）
    rect = None
    if os.path.exists(CONFIG["bekick_template"]):
        template = load_template(CONFIG["bekick_template"])
        rect = find_template_rect(frame, template, threshold=0.6)
    if rect is None and os.path.exists(CONFIG["bekick2_template"]):
        template2 = load_template(CONFIG["bekick2_template"])
        rect = find_template_rect(frame, template2, threshold=0.6)
    if rect is None and os.path.exists(CONFIG["bekick3_template"]):
        template3 = load_template(CONFIG["bekick3_template"])
        rect = find_template_rect(frame, template3, threshold=0.6)
    if rect is None:
        return False

    print("[INFO] 检测到被踢出房间，开始恢复流程...")
    focus_game_window(hwnd)

    # 第1步：点击 kickok 按钮
    if os.path.exists(CONFIG["kickok_template"]):
        print("[INFO] 查找并点击 kickok 按钮...")
        for attempt in range(10):
            frame = capture_game_window(hwnd)
            ok_template = load_template(CONFIG["kickok_template"])
            ok_rect = find_template_rect(frame, ok_template, threshold=0.6)
            if ok_rect is not None:
                left, top, _, _ = get_window_rect(hwnd)
                screen_x = left + ok_rect["center_x"]
                screen_y = top + ok_rect["center_y"]
                click_screen_position(screen_x, screen_y, clicks=1)
                print(f"[INFO] 已点击 kickok 按钮")
                time.sleep(2)
                break
            print(f"[INFO] 未找到 kickok 按钮，重试 {attempt + 1}/10...")
            time.sleep(1)
    else:
        print("[WARN] kickok 模板不存在，跳过点击")
        time.sleep(2)

    # 第2步：点击游戏画面中间，等待私人城镇按钮出现
    print("[INFO] 点击游戏画面中间，等待私人城镇按钮...")
    game_rect = win32gui.GetWindowRect(hwnd)
    center_x = (game_rect[0] + game_rect[2]) // 2
    center_y = (game_rect[1] + game_rect[3]) // 2

    if os.path.exists(CONFIG["private_tavern_template"]):
        tavern_template = load_template(CONFIG["private_tavern_template"])
        for attempt in range(20):
            # 左键点击游戏画面中间
            click_screen_position(center_x, center_y, clicks=1)
            time.sleep(1.5)

            # 查找私人城镇按钮
            frame = capture_game_window(hwnd)
            tavern_rect = find_template_rect(frame, tavern_template, threshold=0.6)
            if tavern_rect is not None:
                left, top, _, _ = get_window_rect(hwnd)
                screen_x = left + tavern_rect["center_x"]
                screen_y = top + tavern_rect["center_y"]
                click_screen_position(screen_x, screen_y, clicks=1)
                print("[INFO] 已点击私人城镇按钮")
                time.sleep(2)
                return True
            print(f"[INFO] 未找到私人城镇按钮，重试 {attempt + 1}/20...")

        print("[WARN] 未找到私人城镇按钮，但已尝试恢复")
    else:
        print("[WARN] 私人城镇模板不存在，跳过点击")

    return True


def check_kicked_quick():
    """快速检测是否被踢，如果是则执行恢复流程并返回 True。"""
    if detect_kicked_and_recover():
        print("[INFO] 被踢恢复完成，等待 50 秒后重新开始")
        time.sleep(50)
        return True
    return False


# ========================= 异常检测与恢复模块 =========================
# 游戏失败检测（gamefailed.png → 按 N）
# 被踢出房间检测（bekick.png → kickok → 私人城镇）
# 房间循环主逻辑（按 2/0 + 随机方向键 + 检测结算）


def run_room_progression_loop():
    """进入目标房间后立即开始每 ~10 秒按一次 2 / 0 准备，
    每隔约30-60秒随机长按 W/S/A/D 之一 0.8~1.3 秒，
    检测 finish game 或 game failed，检测到后处理并返回。
    添加失败重来检测（失败重来.png）和定时按0逻辑（约4-5分钟随机间隔）。
    进入房间后15分钟内无玩家准备则视为卡死处理。
    运行全程：超过40分钟从未检测到队友准备绿色对钩 → 强制卡死重启。
    所有时序加入随机扰动，避免固定周期被反作弊检测。"""
    global STOP_FLAG, LAST_PLAYER_READY_TIME, ROOMFULL_9001_TRIGGERED

    print("[INFO] 已进入目标房间，开始按 2 / 0 准备（时序已随机化）")
    cycle_count = 0
    enter_time = time.time()
    last_auto_zero_time = enter_time
    next_auto_zero_interval = random.uniform(240, 300)
    last_move_time = enter_time
    next_move_interval = random.uniform(30, 60)
    player_ready_detected = False
    # 9001/roomfull 一般双击后约10秒才弹出；这里先在10秒时点首查，之后每分钟查一次（未检测到玩家准备才查）
    # last_roomfull_check_time 初值比 enter_time 少50秒 → now - last ≈ 50 + elapsed，所以 elapsed>=10 时会满足≥60秒的条件触发首次检查
    last_roomfull_check_time = enter_time - 50.0
    # 9001roomfull 并行检测：进房间后60秒内每轮循环都快速检测一次（不阻塞2/0按键）
    roomfull_9001_check_until = enter_time + 60.0
    # 网络连接中断并行检测：进房间后60秒内每轮循环都快速检测一次
    conn_fail_check_until = enter_time + 60.0
    # connectionfailed 模板定期检测：进房间后约10秒首次检查，之后每60秒检查一次（贯穿整局，不限前60秒）
    #   初值比 enter_time 少50秒 → now - last ≈ 50 + elapsed，elapsed>=10 时满足 ≥60秒，触发首次检查
    last_conn_fail_check_time = enter_time - 50.0
    # LAST_PLAYER_READY_TIME 为 None 时（游戏刚启动还没见过准备）用进入房间时间做兜底起点，避免 40 分钟检测误触发
    if LAST_PLAYER_READY_TIME is None:
        LAST_PLAYER_READY_TIME = enter_time

    while not STOP_FLAG:
        # 卡死检测
        if FREEZE_MONITOR and check_and_recover_if_frozen(FREEZE_MONITOR):
            print("[INFO] 游戏已从卡死恢复，中断当前房间循环")
            return False  # 恢复后需要重新走寻路流程

        now = time.time()

        # ===== 并行检测：进房间后60秒内快速检测 9001roomfull（不阻塞2/0按键）=====
        if now < roomfull_9001_check_until:
            if detect_roomfull_9001_and_handle():
                print("[INFO] 9001roomfull 满员提示已处理，返回重新走 e-tip 识别流程")
                ROOMFULL_9001_TRIGGERED = False
                return False

        # ===== 并行检测：进房间后60秒内快速检测网络连接中断（不阻塞2/0按键）=====
        if now < conn_fail_check_until:
            if check_connection_failed():
                print("[INFO] 进入房间后60秒内检测到网络连接中断，已执行恢复流程")
                return False

        # roomfull/9001检测：双击后约10秒首次检查；之后每60秒检查一次，且仅在未检测到玩家准备时检查
        if (not player_ready_detected) and (now - last_roomfull_check_time >= 60.0):
            last_roomfull_check_time = now
            if detect_room_full():
                print("[INFO] 定时扫描检测到房间已满/不存在，中断当前房间循环")
                return False

        # connectionfailed 网络连接中断定期检测：约10秒首次检查，之后每60秒检查一次（贯穿整局，不限前60秒）
        #   与主循环其他逻辑并行执行，检测到立即走卡死恢复流程（recover_game：关游戏→重开→回私人城镇）
        if now - last_conn_fail_check_time >= 60.0:
            last_conn_fail_check_time = now
            if check_connection_failed():
                print("[INFO] 定时扫描检测到网络连接中断（connectionfailed），已执行卡死恢复流程，中断当前房间循环")
                return False

        # ===== 全流程：超过40分钟从未检测到队友准备绿色对钩 → 强制卡死重启 =====
        if LAST_PLAYER_READY_TIME is not None:
            minutes_without_ready = (now - LAST_PLAYER_READY_TIME) / 60.0
            if minutes_without_ready >= NO_PLAYER_READY_TIMEOUT_MINUTES:
                print(f"[WARN] 超过 {minutes_without_ready:.1f} 分钟未检测到任何队友准备绿色对钩，执行卡死重启流程...")
                if FREEZE_MONITOR:
                    FREEZE_MONITOR.reset()
                success = recover_game()
                if success:
                    print("[INFO] 40分钟无准备卡死重启成功，中断当前房间循环")
                else:
                    print("[WARN] 40分钟无准备卡死重启失败，中断当前房间循环")
                return False

        # 快速检测断开连接（进入房间后可能直接断连）
        if check_disconnect_quick():
            print("[INFO] 进入房间后检测到断连，中断当前房间循环")
            return False

        # 进入房间后40分钟内无玩家准备 → 视为卡死（与全局40分钟阈值对齐）
        if not player_ready_detected:
            elapsed = now - enter_time
            print(f"[INFO] 进入房间后无玩家准备，已持续 {elapsed:.1f} 秒...")
            if elapsed >= 100:
                if check_disconnect_quick():
                    print("[INFO] 无玩家准备超100秒，检测到断开连接，中断当前房间循环")
                    return False
            if elapsed >= NO_PLAYER_READY_TIMEOUT_SECONDS:
                print("[WARN] 进入房间后40分钟内无玩家准备，视为卡死，开始恢复...")
                if FREEZE_MONITOR:
                    FREEZE_MONITOR.reset()
                success = recover_game()
                if success:
                    print("[INFO] 游戏恢复成功，中断当前房间循环")
                else:
                    print("[INFO] 游戏恢复失败，中断当前房间循环")
                return False

        hwnd = find_game_window()
        focus_game_window(hwnd)
        cycle_count += 1

        # 每 5~8 轮随机插入一次 2~5 秒的“发呆”停顿，模拟真人偶尔不动
        if cycle_count % random.randint(5, 8) == 0:
            idle_time = random.uniform(2.0, 5.0)
            print(f"[INFO] 模拟发呆，暂停 {idle_time:.1f} 秒...")
            time.sleep(idle_time)
            if STOP_FLAG:
                break

        # 按 2 准备（人性化按键，每次按住时间随机）
        humanized_press("2")

        # 每隔约30-60秒随机长按 W/S/A/D 之一 0.8~1.3 秒
        move_key = ""
        hold_time = 0
        if now - last_move_time >= next_move_interval:
            move_key = random.choice(["w", "s", "a", "d"])
            hold_time = random.uniform(0.8, 1.3)
            pyautogui.keyDown(move_key)
            time.sleep(hold_time)
            pyautogui.keyUp(move_key)
            last_move_time = now
            next_move_interval = random.uniform(110, 130)

        # 检测其他玩家是否已准备，有玩家准备才按 0
        pressed_zero = False
        if detect_other_players_ready():
            player_ready_detected = True
            humanized_press("0")
            pressed_zero = True
            if move_key:
                print(f"[INFO] 已按 2 + 0（检测到玩家准备）+ 长按 {move_key.upper()} {hold_time:.1f}秒，等待检测结算画面")
            else:
                print(f"[INFO] 已按 2 + 0（检测到玩家准备），等待检测结算画面")
        else:
            if move_key:
                print(f"[INFO] 已按 2（无玩家准备，跳过 0）+ 长按 {move_key.upper()} {hold_time:.1f}秒，等待检测结算画面")
            else:
                print(f"[INFO] 已按 2（无玩家准备，跳过 0），等待检测结算画面")

        # 定时按0：每隔约4-5分钟自动按一次0（独立于玩家准备检测）
        if now - last_auto_zero_time >= next_auto_zero_interval:
            humanized_press("0")
            print(f"[INFO] 定时按0（间隔 {next_auto_zero_interval:.1f} 秒）")
            last_auto_zero_time = now
            next_auto_zero_interval = random.uniform(240, 300)

        # 按完后等 ~0.9 秒（±30%），检测是否出现 finish game 或 game failed（检测频率加倍）
        humanized_sleep(0.9)

        # 按 2/0 后再做一次卡死检测
        if FREEZE_MONITOR and check_and_recover_if_frozen(FREEZE_MONITOR):
            print("[INFO] 按 2/0 后检测到卡死，中断当前房间循环")
            return False

        # 检测游戏失败
        if detect_game_failed():
            print("[INFO] 游戏失败已处理，继续检测结算画面")
            humanized_sleep(2.0)

        # 检测失败重来（失败重来.png）
        if detect_failure_retry():
            print("[INFO] 失败重来已处理，继续检测结算画面")
            humanized_sleep(2.0)

        # 检测被踢出房间
        kicked = detect_kicked_and_recover()
        if kicked:
            print("[INFO] 被踢出房间已处理，中断当前房间循环")
            return False

        if detect_finish_game_and_click_to_tavern():
            print("[INFO] 已检测到 finish game，点击 To Tavern 返回城堡，本局结束")
            return True

        # 未出现结算画面，随机等待 ~2.2 秒（±30%）后再按下一轮（检测频率加倍）
        humanized_sleep(2.2)

        # 等待后再做一次卡死检测
        if FREEZE_MONITOR and check_and_recover_if_frozen(FREEZE_MONITOR):
            print("[INFO] 等待后检测到卡死，中断当前房间循环")
            return False

    print("[INFO] 已停止房间循环")
    return False


# ========================= 卖装备模块 =========================
# 打开背包 → 点击背包1 → 识别所有10级装备并移到背包2 → 按Y卖出 → 关闭背包

def _find_template_in_window(hwnd, template_path, threshold=0.5,
                              x0_ratio=0.50, y0_ratio=0.15,
                              x1_ratio=0.95, y1_ratio=0.90):
    """在游戏窗口内的指定相对区域查找模板，返回 (screen_x, screen_y, conf) 或 None。
    使用窗口相对百分比坐标，兼容 1K/2K 不同显示器。
    支持多尺度匹配（0.5x-2.0x），适应不同分辨率/DPI 缩放。
    """
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]
    template = load_template(template_path)
    if template is None:
        return None

    x0, y0 = int(w * x0_ratio), int(h * y0_ratio)
    x1, y1 = int(w * x1_ratio), int(h * y1_ratio)
    search = frame[y0:y1, x0:x1]

    if search.size == 0:
        return None

    sh, sw = search.shape[:2]
    th, tw = template.shape[:2]

    # 先尝试 1.0x 原始尺度
    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        cx_in_window = x0 + max_loc[0] + tw // 2
        cy_in_window = y0 + max_loc[1] + th // 2
        win_left, win_top, _, _ = get_window_rect(hwnd)
        screen_x = win_left + cx_in_window
        screen_y = win_top + cy_in_window
        print(f"[查找模板] {template_path} 相似度={max_val:.4f} 窗口坐标=({cx_in_window},{cy_in_window})")
        return (screen_x, screen_y, max_val)

    # 多尺度匹配兜底
    scales = [s for s in [0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]
              if int(tw * s) <= sw and int(th * s) <= sh]

    best_score = max_val
    best_cx, best_cy = None, None

    for scale in scales:
        scaled = cv2.resize(template, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA)
        s_th, s_tw = scaled.shape[:2]
        result = cv2.matchTemplate(search, scaled, cv2.TM_CCOEFF_NORMED)
        _, s_max_val, _, s_max_loc = cv2.minMaxLoc(result)

        if s_max_val > best_score:
            best_score = s_max_val
            best_cx = x0 + s_max_loc[0] + s_tw // 2
            best_cy = y0 + s_max_loc[1] + s_th // 2

    if best_score >= threshold and best_cx is not None:
        win_left, win_top, _, _ = get_window_rect(hwnd)
        screen_x = win_left + best_cx
        screen_y = win_top + best_cy
        print(f"[查找模板] {template_path} 相似度={best_score:.4f}（多尺度） 窗口坐标=({best_cx},{best_cy})")
        return (screen_x, screen_y, best_score)

    print(f"[查找模板] {template_path} 最高相似度={best_score:.4f} < 阈值{threshold}")
    return None


def _find_in_backpack_region(hwnd, template_path, threshold=0.5, skip_positions=None):
    """在游戏窗口右半边背包区域内查找模板，返回帧坐标 (cx, cy, conf) 或 None。
    skip_positions 为已处理过的帧坐标列表，用于避免重复匹配同一件装备。
    支持多尺度匹配（0.5x-2.0x），适应不同分辨率/DPI 缩放。"""
    frame = capture_game_window(hwnd)
    h, w = frame.shape[:2]
    template = load_template(template_path)

    # 背包区域：画面右半边 50%~95% 宽，15%~90% 高
    x0, y0 = int(w * 0.50), int(h * 0.15)
    x1, y1 = int(w * 0.95), int(h * 0.90)
    search = frame[y0:y1, x0:x1]
    sh, sw = search.shape[:2]

    th, tw = template.shape[:2]

    # 先尝试 1.0x 原始尺度
    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)

    # 屏蔽已处理过的位置（半径 30 像素）
    if skip_positions:
        for (sx, sy) in skip_positions:
            local_x, local_y = sx - x0, sy - y0
            mx0 = max(0, local_x - 30)
            my0 = max(0, local_y - 30)
            mx1 = min(result.shape[1], local_x + 30)
            my1 = min(result.shape[0], local_y + 30)
            result[my0:my1, mx0:mx1] = -1.0

    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        cx = max_loc[0] + tw // 2 + x0
        cy = max_loc[1] + th // 2 + y0
        return cx, cy, max_val

    # 多尺度匹配兜底
    scales = [s for s in [0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]
              if int(tw * s) <= sw and int(th * s) <= sh]

    best_score = max_val
    best_cx, best_cy = None, None

    for scale in scales:
        scaled = cv2.resize(template, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA)
        s_th, s_tw = scaled.shape[:2]
        result = cv2.matchTemplate(search, scaled, cv2.TM_CCOEFF_NORMED)

        # 同样屏蔽已处理位置
        if skip_positions:
            for (sx, sy) in skip_positions:
                local_x, local_y = sx - x0, sy - y0
                mx0 = max(0, local_x - 30)
                my0 = max(0, local_y - 30)
                mx1 = min(result.shape[1], local_x + 30)
                my1 = min(result.shape[0], local_y + 30)
                result[my0:my1, mx0:mx1] = -1.0

        _, s_max_val, _, s_max_loc = cv2.minMaxLoc(result)

        if s_max_val > best_score:
            best_score = s_max_val
            best_cx = s_max_loc[0] + s_tw // 2 + x0
            best_cy = s_max_loc[1] + s_th // 2 + y0

    if best_score >= threshold and best_cx is not None:
        return best_cx, best_cy, best_score

    print(f"[卖装备-调试] {template_path} 最高相似度={best_score:.4f} < 阈值{threshold}，未识别")
    return None


def _find_level10_equipment(hwnd, skip_positions=None):
    """按住 Shift 后在背包区域查找 10 级装备，返回帧坐标或 None。"""
    pyautogui.keyDown("shift")
    time.sleep(1.0)
    result = _find_in_backpack_region(
        hwnd, CONFIG["level10_equipment_template"],
        threshold=0.6, skip_positions=skip_positions
    )
    if result is not None:
        print(f"[卖装备] 找到 10 级装备，帧坐标=({result[0]}, {result[1]})，置信度={result[2]:.4f}")
    else:
        print("[卖装备] 未找到 10 级装备（阈值0.6）")
    pyautogui.keyUp("shift")
    time.sleep(0.5)
    return result


def _move_equipment_to_backpack2(hwnd, equip_fx, equip_fy):
    """将一件 10 级装备从背包1 移到背包2：锁定 → 拿起 → 放入背包2。
    equip_fx, equip_fy 为帧坐标。
    """
    win_left, win_top, _, _ = get_window_rect(hwnd)

    # 1. 移动鼠标到装备位置（让鼠标离开背包2图标）
    eq_sx = win_left + equip_fx
    eq_sy = win_top + equip_fy
    humanized_move_to(eq_sx, eq_sy)
    time.sleep(random.uniform(0.8, 1.2))

    # 2. 按 L 锁定装备
    print("[卖装备] 按 L 锁定装备")
    humanized_press("l")
    time.sleep(random.uniform(0.8, 1.2))

    # 3. 左键点击拿起装备
    print("[卖装备] 左键点击装备（拿起）")
    pyautogui.click(button="left")
    time.sleep(random.uniform(1.2, 1.8))

    # 4. 查找背包2位置（使用窗口相对坐标，搜索区域接近全屏，阈值保持原值）
    bp2_result = _find_template_in_window(hwnd, CONFIG["backpack2_template"],
                                           threshold=0.7,
                                           x0_ratio=0.10, y0_ratio=0.10,
                                           x1_ratio=0.95, y1_ratio=0.95)
    if bp2_result is None:
        print("[卖装备] 等待 1 秒后重试查找背包2...")
        time.sleep(1.0)
        bp2_result = _find_template_in_window(hwnd, CONFIG["backpack2_template"],
                                               threshold=0.7,
                                               x0_ratio=0.10, y0_ratio=0.10,
                                               x1_ratio=0.95, y1_ratio=0.95)
    if bp2_result is None:
        print("[卖装备] 未找到背包2，移动失败")
        return False

    bp2_sx, bp2_sy = bp2_result[0], bp2_result[1]
    humanized_move_to(bp2_sx, bp2_sy)
    time.sleep(random.uniform(0.8, 1.2))

    # 5. 右键点击背包2放入装备
    print("[卖装备] 右键点击背包2（放入装备）")
    pyautogui.click(button="right")
    time.sleep(random.uniform(0.8, 1.2))

    # 6. 将鼠标移到安全位置，避免悬停影响下次检测
    safe_x = win_left + int(get_window_rect(hwnd)[2] * 0.25)
    safe_y = win_top + int(get_window_rect(hwnd)[3] * 0.25)
    humanized_move_to(safe_x, safe_y)
    time.sleep(random.uniform(0.8, 1.2))
    return True


def sell_equipment():
    """卖装备主流程：打开背包 → 背包1中找10级装备移到背包2 → 按Y卖出剩余 → 关闭背包。"""
    hwnd = find_game_window()
    focus_game_window(hwnd)
    print("[卖装备] 开始卖装备流程")

    # 1. 按 I 打开背包
    print("[卖装备] 按 I 打开背包...")
    humanized_press("i")
    time.sleep(3.0)

    # 2. 查找并点击背包1标签（使用窗口相对坐标，搜索区域接近全屏，阈值保持原值）
    bp1_result = _find_template_in_window(hwnd, CONFIG["backpack1_template"],
                                           threshold=0.7,
                                           x0_ratio=0.10, y0_ratio=0.10,
                                           x1_ratio=0.95, y1_ratio=0.95)
    if bp1_result is None:
        print("[卖装备] 未找到背包1，跳过卖装备")
        humanized_press("escape")
        time.sleep(1.0)
        return
    print(f"[卖装备] 找到背包1，位置=({bp1_result[0]}, {bp1_result[1]})")
    _click_at(bp1_result[0], bp1_result[1], delay=0.5)
    time.sleep(2.0)

    # 3. 循环查找 10 级装备并移到背包2（最多 20 轮）
    moved_count = 0
    skip_positions = []
    for round_idx in range(20):
        print(f"[卖装备] 第 {round_idx + 1} 轮检查 10 级装备...")
        equip_result = _find_level10_equipment(hwnd, skip_positions=skip_positions)
        if equip_result is None:
            print("[卖装备] 没有更多 10 级装备，进入出售流程")
            break
        eq_fx, eq_fy = equip_result[0], equip_result[1]
        if _move_equipment_to_backpack2(hwnd, eq_fx, eq_fy):
            moved_count += 1
            skip_positions.append((eq_fx, eq_fy))
            print(f"[卖装备] 已移动第 {moved_count} 件 10 级装备到背包2")
        else:
            print("[卖装备] 移动失败，跳过本轮")
        time.sleep(1.0)

    print(f"[卖装备] 共移动 {moved_count} 件 10 级装备到背包2")

    # 4. 按 Y 批量出售剩余装备
    print("[卖装备] 按 Y 批量出售装备...")
    humanized_press("y")
    time.sleep(2.0)
    print("[卖装备] 按 Enter 确认出售...")
    humanized_press("enter")
    time.sleep(2.0)

    # 5. 按 ESC 关闭背包
    print("[卖装备] 按 ESC 关闭背包")
    humanized_press("escape")
    time.sleep(2.0)

    print(f"[卖装备] 卖装备完成，共保护 {moved_count} 件 10 级装备")


# ========================= 辅助：缓慢分步移动鼠标 + 点击 =========================

def _slow_move_to(screen_x, screen_y):
    """从当前鼠标位置，分20步缓慢移动到目标坐标（防作弊）。"""
    try:
        current_x, current_y = win32api.GetCursorPos()
    except Exception:
        current_x, current_y = pyautogui.position()
    steps = 20
    step_delay = 0.005
    sx = (screen_x - current_x) / steps
    sy = (screen_y - current_y) / steps
    for i in range(steps):
        nx = int(current_x + sx * (i + 1))
        ny = int(current_y + sy * (i + 1))
        try:
            ctypes.windll.user32.SetCursorPos(nx, ny)
        except Exception:
            pyautogui.moveTo(nx, ny, duration=0)
        time.sleep(step_delay)


def _slow_click_at(screen_x, screen_y, clicks=1):
    """缓慢移动到指定屏幕坐标并点击。"""
    hwnd = find_game_window()
    focus_game_window(hwnd)
    _slow_move_to(screen_x, screen_y)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.click(clicks=clicks)
    time.sleep(random.uniform(0.1, 0.3))


def _slow_click_template(template_path, label=None, threshold=None, region=None, clicks=1):
    """通过模板找到图像后，缓慢移动鼠标并点击。region为游戏客户区比例(left,top,right,bottom)，仅在指定区域内搜索。"""
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    fh, fw = frame.shape[:2]
    search_frame = frame
    if region:
        lf, tf, rf, bf = region
        lf, tf, rf, bf = max(0, lf), max(0, tf), min(1, rf), min(1, bf)
        x0, y0 = int(lf * fw), int(tf * fh)
        x1, y1 = int(rf * fw), int(bf * fh)
        search_frame = frame[y0:y1, x0:x1]
    else:
        x0, y0 = 0, 0
    template = load_template(template_path)
    rect = find_template_rect(search_frame, template, threshold=threshold)
    if rect is None:
        if label:
            print(f"[WARN] 未找到 {label} 模板：{template_path}")
        return False
    cx = x0 + rect["center_x"]
    cy = y0 + rect["center_y"]
    left, top, _, _ = get_window_rect(hwnd)
    screen_x = left + cx
    screen_y = top + cy
    if label:
        print(f"[INFO] 找到 {label}，置信度={rect['max_val']:.3f}，屏幕坐标=({screen_x}, {screen_y})")
    _slow_click_at(screen_x, screen_y, clicks=clicks)
    return True


# ========================= 视角旋转模块（相对鼠标事件，用于>320层重置） =========================

def _rotate_view_left_for_reset(degrees=45, duration=1.0):
    """使用相对鼠标事件向左旋转视角（复用test_view_rotate的逻辑）。"""
    hwnd = find_game_window()
    if not hwnd:
        print("[ERROR] 未找到游戏窗口，无法旋转视角")
        return False
    focus_game_window(hwnd)
    humanized_sleep(0.5)
    game_rect = win32gui.GetWindowRect(hwnd)
    window_width = game_rect[2] - game_rect[0]
    # 系数：2.17 已由测试校准
    total_dx = -int(window_width * degrees * 2.17 / 180)
    steps = 50
    step_dx = int(total_dx / steps)
    step_delay = duration / steps
    for i in range(steps):
        if i == steps - 1:
            step_dx = total_dx - (steps - 1) * int(total_dx / steps)
        ctypes.windll.user32.mouse_event(0x0001, step_dx, 0, 0, 0)
        time.sleep(step_delay)
    time.sleep(0.2)
    return True


def _check_e_reset_present():
    """在全屏范围内检测e-reset模板是否出现（每次W后都会调一次）。"""
    template_path = CONFIG.get("e_reset_template")
    if not template_path or not os.path.exists(template_path):
        print(f"[ERROR] e-reset模板不存在: {template_path}")
        return False
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(template_path)
    rect = find_template_rect(frame, template, threshold=0.8)
    if rect:
        print(f"[INFO] 识别到 e-reset，相似度: {rect['max_val']:.4f} （模板路径: {template_path}）")
        return True
    return False


def perform_view_reset_and_restart():
    """
    楼层>320后执行：执行test_view_rotate中的整套操作，
    然后关闭游戏 → 重启 → 进入私人城堡 → 返回主流程。
    流程：左转43.65°(45°减3%)→ 盲按4次W（中间不识别e-reset）→ 盲按E → 等2秒 → 点击相对(0.65,0.75) → 识别resetconfirm.png点击（找不到/异常都回退Enter；3次全失败直接卡死）→ 等20秒 → 卡死关游戏重启
    """
    global NEED_RESET_AFTER_ROUND, LAST_COMPLETED_FLOOR, NEED_VIEW_RESET_BEFORE_NEXT_WAR
    print("[重置流程] 楼层>320，执行视角重置 + 重启游戏流程…")
    hwnd = find_game_window()
    if hwnd:
        # 1. 视角左转60°
        print("[重置流程] 1/7 视角左转60°…")
        try:
            _rotate_view_left_for_reset(60, duration=1.0)
        except Exception as e:
            print(f"[重置流程] 视角左转异常，跳过: {e}")
        # 2. 盲按 4 次 W（按 W 期间不再识别 e-reset，只走路），然后直接盲按 E
        print("[重置流程] 2/7 盲按 4 次 W（不识别e-reset），之后盲按 E…")
        for i in range(4):
            if STOP_FLAG:
                return
            print(f"[重置流程]  第 {i+1}/4 次盲按 W…")
            try:
                safe_press("w", duration=0.3)
            except Exception:
                pass
            time.sleep(1.0)
        # 4 次 W 走完后，直接盲按 E（不再检测 e-reset 图标）
        print("[重置流程]   4 次 W 完成，盲按 E…")
        try:
            humanized_press("e")
        except Exception:
            pass
        e_pressed = True
        # 3. 按 E 后等待2秒
        if e_pressed:
            print("[重置流程] 3/7 盲按 E 完成，等待 2 秒…")
            time.sleep(2.0)
        # 4. 点击相对(0.65, 0.75)
        print("[重置流程] 4/7 点击相对位置 (0.65, 0.75)…")
        try:
            game_rect = win32gui.GetWindowRect(hwnd)
            sx = game_rect[0] + int((game_rect[2] - game_rect[0]) * 0.65)
            sy = game_rect[1] + int((game_rect[3] - game_rect[1]) * 0.75)
            _slow_click_at(sx, sy)
        except Exception as e:
            print(f"[重置流程] 点击(0.65,0.75)异常，跳过: {e}")
        # 5. 识别 resetconfirm.png 并点击；任何异常/找不到时回退每秒1次Enter（共尝试3次）
        #    3次都没识别到/异常 → 跳过20秒等待，立即卡死重启
        print("[重置流程] 5/7 识别 resetconfirm.png 并点击（3次失败则直接卡死）…")
        confirm_template_path = CONFIG.get("resetconfirm_template")
        confirm_clicked = False
        resetconfirm_failed_critical = False
        try:
            g_left, g_top, g_right, g_bottom = win32gui.GetWindowRect(hwnd)
            for confirm_try in range(3):
                if STOP_FLAG:
                    return
                found_rect = None
                if confirm_template_path and os.path.exists(confirm_template_path):
                    try:
                        frame_cf = capture_game_window(hwnd)
                        tmpl_cf = load_template(confirm_template_path)
                        found_rect = find_template_rect(frame_cf, tmpl_cf, threshold=0.7)
                    except Exception as e:
                        print(f"[重置流程]   resetconfirm识别异常（尝试{confirm_try+1}/3），回退Enter: {e}")
                        found_rect = None
                if found_rect is not None:
                    # find_template_rect 返回键: x0, y0, x1, y1, center_x, center_y, max_val
                    # center_x/center_y 是截图相对坐标，需加上窗口左上角才能变屏幕坐标
                    tx = g_left + int(found_rect["center_x"])
                    ty = g_top + int(found_rect["center_y"])
                    print(f"[重置流程]   第 {confirm_try+1}/3 次识别到 resetconfirm，相似度={found_rect['max_val']:.4f}，点击屏幕坐标=({tx},{ty})")
                    try:
                        _slow_click_at(tx, ty)
                        confirm_clicked = True
                    except Exception as e:
                        print(f"[重置流程]   resetconfirm点击异常，回退Enter: {e}")
                        confirm_clicked = False
                    break
                else:
                    print(f"[重置流程]   第 {confirm_try+1}/3 次未识别到 resetconfirm，回退按 Enter")
                    try:
                        humanized_press("enter")
                    except Exception:
                        pass
                if confirm_try < 2:
                    time.sleep(1.0)
            if confirm_clicked:
                print("[重置流程]   resetconfirm 识别并点击完成")
            else:
                print("[重置流程]   3次均未识别到 resetconfirm（或异常），跳过等待，立即执行卡死重启")
                resetconfirm_failed_critical = True
        except Exception as e:
            # 最外层兜底：任何异常都尝试回退Enter 3次，然后标记 critical 直接卡死
            print(f"[重置流程]   resetconfirm步骤外层异常，强行回退3次Enter后直接卡死: {e}")
            for _q in range(3):
                try:
                    humanized_press("enter")
                except Exception:
                    pass
                if _q < 2:
                    time.sleep(1.0)
            resetconfirm_failed_critical = True
        # 6. resetconfirm 成功才等20秒；critical失败则跳过等待立即卡死
        if resetconfirm_failed_critical:
            print("[重置流程] 6/7 resetconfirm失败，跳过20秒等待 → 直接进入卡死重启")
        else:
            print("[重置流程] 6/7 重置确认后，等待 20 秒…")
            time.sleep(20.0)
    else:
        print("[WARN] 重置流程开始时未找到游戏窗口，跳过视角操作")
    # 7. 关闭游戏 → 重启（复用recover_game逻辑）
    print("[重置流程] 7/7 关闭游戏并重新启动…")
    try:
        time.sleep(1.0)
        success = recover_game()
    except Exception as e:
        print(f"[WARN] recover_game异常: {e}")
        success = False
    # 重置标记（视角专项已经执行过，下一次WarTable识别后不需要再执行）
    NEED_RESET_AFTER_ROUND = False
    NEED_VIEW_RESET_BEFORE_NEXT_WAR = False
    LAST_COMPLETED_FLOOR = None
    if success:
        print("[重置流程] 重启游戏成功，后续将按正常流程找War Table / 判断楼层")
    else:
        print("[WARN] 重置流程重启游戏失败，请手动处理")
    return success


# ========================= 换装流程模块（楼层<300时触发） =========================

def _find_and_click_auto_equip_gear():
    """在游戏左半侧区域寻找 autoequipgear.png，缓慢移动鼠标上去点击。"""
    template_path = CONFIG.get("auto_equip_gear_template")
    if not template_path or not os.path.exists(template_path):
        print(f"[ERROR] autoequipgear模板不存在: {template_path}")
        return False
    # region: 左半侧 (0,0)-(0.5,1)
    return _slow_click_template(template_path, label="AUTO EQUIP GEAR", threshold=0.8, region=(0.0, 0.0, 0.5, 1.0), clicks=1)


def perform_gear_switch_and_sell():
    """
    楼层<300时的换装+卖装备流程：
    1. 按ESC，1秒后：按I打开背包
    2. 游戏左半侧找autoequipgear → 缓慢移动上去 → 点击
    3. 执行原卖装备流程里的后续操作（找背包1/2保护10级、按Y卖、Enter、ESC关背包）
    """
    print("[换装流程] 楼层<300，开始换装+卖装备流程…")
    hwnd = find_game_window()
    focus_game_window(hwnd)
    # 1. 按ESC退出War Table界面（回到城堡）
    print("[换装流程] 1/5 按 ESC 退出 War Table 界面…")
    humanized_press("escape")
    time.sleep(1.0)
    # 2. 按 I 打开背包
    print("[换装流程] 2/5 按 I 打开背包…")
    humanized_press("i")
    time.sleep(1.5)
    # 3. 找左半侧 autoequipgear 并点击
    print("[换装流程] 3/5 查找 AUTO EQUIP GEAR 并点击…")
    ok = False
    for attempt in range(3):
        if STOP_FLAG:
            break
        if _find_and_click_auto_equip_gear():
            ok = True
            break
        print(f"[换装流程] 未找到 AUTO EQUIP GEAR，重试 {attempt+1}/3…")
        time.sleep(1.0)
    if not ok:
        print("[WARN] 换装流程中未找到 AUTO EQUIP GEAR，继续执行后续卖装备流程")
    time.sleep(1.5)
    # 4. 复用卖装备后续流程：找背包1、10级装备移到背包2、按Y卖、Enter
    print("[换装流程] 4/5 执行保护 10 级装备 + 卖装备操作…")
    moved_count = 0
    skip_positions = []
    bp1_result = _find_template_in_window(hwnd, CONFIG["backpack1_template"],
                                           threshold=0.7,
                                           x0_ratio=0.10, y0_ratio=0.10,
                                           x1_ratio=0.95, y1_ratio=0.95)
    if bp1_result is None:
        print("[换装流程] 未找到背包1，跳过10级装备保护步骤")
    else:
        print(f"[换装流程] 找到背包1，位置=({bp1_result[0]}, {bp1_result[1]})")
        # 先点击背包1标签，切换到背包1页面，否则Shift下找10级装备搜不到
        _click_at(bp1_result[0], bp1_result[1], delay=0.5)
        time.sleep(2.0)
        for round_idx in range(5):
            if STOP_FLAG:
                break
            print(f"[换装流程] 第 {round_idx + 1} 轮检查 10 级装备…")
            eq_result = _find_level10_equipment(hwnd, skip_positions=skip_positions)
            if eq_result is None:
                print("[换装流程] 没有更多 10 级装备，进入出售流程")
                break
            eq_fx, eq_fy, eq_conf = eq_result
            skip_positions.append((eq_fx, eq_fy))
            if _move_equipment_to_backpack2(hwnd, eq_fx, eq_fy):
                moved_count += 1
                print(f"[换装流程] 已移动第 {moved_count} 件 10 级装备到背包2")
            else:
                print("[换装流程] 移动失败，跳过本轮")
            time.sleep(1.0)
    print(f"[换装流程] 共移动 {moved_count} 件 10 级装备到背包2")
    # 按 Y 出售
    print("[换装流程] 按 Y 批量出售装备…")
    humanized_press("y")
    time.sleep(2.0)
    print("[换装流程] 按 Enter 确认出售…")
    humanized_press("enter")
    time.sleep(2.0)
    # 5. 按 ESC 关闭背包
    print("[换装流程] 5/5 按 ESC 关闭背包…")
    humanized_press("escape")
    time.sleep(2.0)
    print("[换装流程] 换装与卖装备完成")
    return True


def perform_sell_only_no_switch():
    """
    楼层≥300时的简化卖装备流程（不做autoequipgear换装）：
    1. 按ESC退出War Table界面，1秒后按I打开背包
    2. 直接找背包1点击 → 找10级装备移到背包2保护
    3. 按Y卖 → Enter确认 → ESC关闭背包
    """
    print("[卖装备流程] 楼层≥300，执行简化卖装备流程（不换装）…")
    hwnd = find_game_window()
    focus_game_window(hwnd)
    # 1. 按ESC退出War Table界面（回到城堡）
    print("[卖装备流程] 1/4 按 ESC 退出 War Table 界面…")
    humanized_press("escape")
    time.sleep(1.0)
    # 2. 按 I 打开背包
    print("[卖装备流程] 2/4 按 I 打开背包…")
    humanized_press("i")
    time.sleep(1.5)
    # 3. 找背包1 → 点击 → 保护10级装备 → 按Y卖 → Enter
    print("[卖装备流程] 3/4 执行保护 10 级装备 + 卖装备操作…")
    moved_count = 0
    skip_positions = []
    bp1_result = _find_template_in_window(hwnd, CONFIG["backpack1_template"],
                                           threshold=0.7,
                                           x0_ratio=0.10, y0_ratio=0.10,
                                           x1_ratio=0.95, y1_ratio=0.95)
    if bp1_result is None:
        print("[卖装备流程] 未找到背包1，跳过10级装备保护步骤")
    else:
        print(f"[卖装备流程] 找到背包1，位置=({bp1_result[0]}, {bp1_result[1]})")
        # 先点击背包1标签，切换到背包1页面，否则Shift下找10级装备搜不到
        _click_at(bp1_result[0], bp1_result[1], delay=0.5)
        time.sleep(2.0)
        for round_idx in range(5):
            if STOP_FLAG:
                break
            print(f"[卖装备流程] 第 {round_idx + 1} 轮检查 10 级装备…")
            eq_result = _find_level10_equipment(hwnd, skip_positions=skip_positions)
            if eq_result is None:
                print("[卖装备流程] 没有更多 10 级装备，进入出售流程")
                break
            eq_fx, eq_fy, eq_conf = eq_result
            skip_positions.append((eq_fx, eq_fy))
            if _move_equipment_to_backpack2(hwnd, eq_fx, eq_fy):
                moved_count += 1
                print(f"[卖装备流程] 已移动第 {moved_count} 件 10 级装备到背包2")
            else:
                print("[卖装备流程] 移动失败，跳过本轮")
            time.sleep(1.0)
    print(f"[卖装备流程] 共移动 {moved_count} 件 10 级装备到背包2")
    print("[卖装备流程] 按 Y 批量出售装备…")
    humanized_press("y")
    time.sleep(2.0)
    print("[卖装备流程] 按 Enter 确认出售…")
    humanized_press("enter")
    time.sleep(2.0)
    # 4. 按 ESC 关闭背包
    print("[卖装备流程] 4/4 按 ESC 关闭背包…")
    humanized_press("escape")
    time.sleep(2.0)
    print("[卖装备流程] 卖装备（不换装）完成")
    return True


# ========================= 分屏 defaults + chaos 判断模块 =========================

def _click_browse_anywhere():
    """找BROWSE按钮，优先游戏右侧(0.5-1.0, 0-1)，找不到就全屏搜索。"""
    template_path = CONFIG.get("browse_template")
    if not template_path or not os.path.exists(template_path):
        print(f"[ERROR] BROWSE模板不存在: {template_path}")
        return False
    # 先搜右侧
    if _slow_click_template(template_path, label="BROWSE(右侧)", threshold=CONFIG["match_threshold"], region=(0.5, 0.0, 1.0, 1.0), clicks=1):
        return True
    # 再搜全屏
    return _slow_click_template(template_path, label="BROWSE(全屏)", threshold=CONFIG["match_threshold"], region=None, clicks=1)


def _click_defaults_button():
    """点击 defaults.png 按钮（原地缓慢移动上去点击）。"""
    template_path = CONFIG.get("defaults_template")
    if not template_path or not os.path.exists(template_path):
        print(f"[ERROR] defaults模板不存在: {template_path}")
        return False
    return _slow_click_template(template_path, label="DEFAULTS", threshold=CONFIG["match_threshold"], clicks=1)


def _get_defaults_screen_center():
    """获取defaults按钮当前屏幕中心坐标（找不到返回None）。用于后续每10秒原地点击。"""
    template_path = CONFIG.get("defaults_template")
    if not template_path or not os.path.exists(template_path):
        return None
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    template = load_template(template_path)
    rect = find_template_rect(frame, template, threshold=CONFIG["match_threshold"])
    if rect is None:
        return None
    left, top, _, _ = get_window_rect(hwnd)
    return (left + rect["center_x"], top + rect["center_y"])


def _detect_chaos9_or_8():
    """
    点击defaults过2秒后，判断chaos9/chaos8情况。
    返回值：
      "chaos9"   → 找到了chaos9/chaos10/chaos11（gear分高，去右侧找房间）
      "chaos8"   → 找到了chaos8（gear分低）
      "none"     → 都没找到（gear分低）
    """
    chaos9_path = CONFIG.get("chaos9_template")
    chaos10_path = CONFIG.get("chaos10_template")
    chaos11_path = CONFIG.get("chaos11_template")
    chaos8_path = CONFIG.get("chaos8_template")
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)

    # 检测 chaos9（高阈值0.9，避免误识别）
    if chaos9_path and os.path.exists(chaos9_path):
        chaos9_rect = find_template_rect(frame, load_template(chaos9_path), threshold=0.9)
        if chaos9_rect:
            print(f"[分屏判断] 识别到 chaos9，相似度={chaos9_rect['max_val']:.4f}（阈值≥0.9），gear分高")
            return "chaos9"
        else:
            debug_rect = find_template_rect(frame, load_template(chaos9_path), threshold=CONFIG["match_threshold"])
            if debug_rect:
                print(f"[分屏判断] chaos9有疑似匹配相似度={debug_rect['max_val']:.4f} 但<0.9，继续检测chaos10/11")

    # 检测 chaos10（高阈值0.9，同chaos9规则）
    if chaos10_path and os.path.exists(chaos10_path):
        chaos10_rect = find_template_rect(frame, load_template(chaos10_path), threshold=0.9)
        if chaos10_rect:
            print(f"[分屏判断] 识别到 chaos10，相似度={chaos10_rect['max_val']:.4f}（阈值≥0.9），视为chaos9处理，gear分高")
            return "chaos9"
        else:
            debug_rect = find_template_rect(frame, load_template(chaos10_path), threshold=CONFIG["match_threshold"])
            if debug_rect:
                print(f"[分屏判断] chaos10有疑似匹配相似度={debug_rect['max_val']:.4f} 但<0.9，继续检测chaos11")

    # 检测 chaos11（高阈值0.9，同chaos9规则）
    if chaos11_path and os.path.exists(chaos11_path):
        chaos11_rect = find_template_rect(frame, load_template(chaos11_path), threshold=0.9)
        if chaos11_rect:
            print(f"[分屏判断] 识别到 chaos11，相似度={chaos11_rect['max_val']:.4f}（阈值≥0.9），视为chaos9处理，gear分高")
            return "chaos9"
        else:
            debug_rect = find_template_rect(frame, load_template(chaos11_path), threshold=CONFIG["match_threshold"])
            if debug_rect:
                print(f"[分屏判断] chaos11有疑似匹配相似度={debug_rect['max_val']:.4f} 但<0.9，继续检测chaos8")

    # 检测 chaos8
    if chaos8_path and os.path.exists(chaos8_path):
        chaos8_rect = find_template_rect(frame, load_template(chaos8_path), threshold=CONFIG["match_threshold"])
        if chaos8_rect:
            print(f"[分屏判断] 识别到 chaos8，相似度={chaos8_rect['max_val']:.4f}，gear分低")
            return "chaos8"

    print("[分屏判断] 未识别到 chaos9/10/11 或 chaos8，gear分低")
    return "none"


def enter_browse_defaults_and_judge_chaos():
    """
    换装卖装备后：
    1. 按 E 重新与 War Table 交互（此时已经回到城堡里的 War Table 前，如果没出现交互则走 detect_e_tip）
    2. 找 BROWSE 点击
    3. 点击 defaults
    4. 等2秒，判断chaos9/8
    返回: ("chaos9"|"gear_low", defaults_screen_center_or_None)
      gear_low 包含 chaos8 和 都没找到两种情况
    """
    global SKIP_FLOOR_CHECK_THIS_ROUND
    print("[分屏流程] 换装后重新按 E 打开 War Table 并判断 chaos…")
    hwnd = find_game_window()
    # 1. 按 E（先尝试找e_tip，找不到直接按）
    print("[分屏流程] 1/4 尝试按 E 与 War Table 交互…")
    for attempt in range(5):
        if STOP_FLAG:
            break
        e_pos = detect_e_tip(hwnd)
        if e_pos is not None:
            print("[分屏流程] 检测到 E 提示，按 E")
            press_e_interact()
            break
        else:
            print(f"[分屏流程] 未检测到 E 提示，直接按 E，重试 {attempt+1}/5…")
            humanized_press("e")
        time.sleep(1.0)
    time.sleep(1.5)
    # 2. 点击 BROWSE
    print("[分屏流程] 2/4 查找并点击 BROWSE…")
    ok = False
    for attempt in range(4):
        if STOP_FLAG:
            break
        if _click_browse_anywhere():
            ok = True
            break
        print(f"[分屏流程] 未找到 BROWSE，重试 {attempt+1}/4…")
        time.sleep(1.5)
    if not ok:
        print("[WARN] 未找到 BROWSE，将按 gear_low 走 Onslaught 流程")
        return ("gear_low", None)
    time.sleep(3.0)
    # 3. 点击 defaults
    print("[分屏流程] 3/4 点击 DEFAULTS…")
    ok = False
    for attempt in range(4):
        if STOP_FLAG:
            break
        if _click_defaults_button():
            ok = True
            break
        print(f"[分屏流程] 未找到 DEFAULTS，重试 {attempt+1}/4…")
        time.sleep(1.5)
    if not ok:
        print("[WARN] 未找到 DEFAULTS，将按 gear_low 走 Onslaught 流程")
        return ("gear_low", None)
    # 记录 defaults 屏幕中心，后续可能需要原地点击
    defaults_center = _get_defaults_screen_center()
    if defaults_center:
        print(f"[分屏流程] 记录 DEFAULTS 屏幕中心位置={defaults_center}")
    # 4. 等 2 秒，判断 chaos
    print("[分屏流程] 4/4 等待 2 秒后判断 chaos9 / chaos8…")
    time.sleep(2.0)
    judge = _detect_chaos9_or_8()
    if judge == "chaos9":
        # gear 分高 → 去右侧找房间
        SKIP_FLOOR_CHECK_THIS_ROUND = False
        return ("chaos9", defaults_center)
    else:
        # gear 分低（chaos8 或 未识别出chaos9都算）→ 重新走ONSLAUGHT找合适房间（不设跳过标记：打完回来仍要重新按楼层判断循环）
        SKIP_FLOOR_CHECK_THIS_ROUND = False
        print("[分屏流程] gear 分低（chaos8或未检测到chaos9），返回后重新按楼层判断，继续走ONSLAUGHT找合适房间刷分")
        return ("gear_low", defaults_center)


# ========================= 右侧房间进入模块（chaos9时触发） =========================

def _scan_right_panel_room_name():
    """
    chaos9/10/11后的右侧面板：在与 get_target_room_floor 完全相同的大裁剪区域
    （Frame X:30%-98%, Y:22%-80%）内搜索 chaos91011room.png 模板。
    找到即视为有房间（等同于识别到 Floor 列/Score列中有合适目标）。
    返回：(has_room, center_frame_or_None)
      - has_room=True 时 center_frame=(fx, fy, conf) 表示模板中心在游戏帧坐标
    """
    template_path = CONFIG.get("chaos91011_room_template")
    if not template_path or not os.path.exists(template_path):
        print(f"[右侧房间] chaos91011_room_template不存在: {template_path}")
        return (False, None)
    hwnd = find_game_window()
    frame = capture_game_window(hwnd)
    fh, fw = frame.shape[:2]

    # 与 get_target_room_floor 完全一致的整体裁剪区域：
    # Frame X:30%-98%, Y:22%-80%（不再缩小到 difficulty 子区域）
    crop_x0 = int(fw * 0.30)
    crop_y0 = int(fh * 0.22)
    crop_x1 = int(fw * 0.98)
    crop_y1 = int(fh * 0.80)
    search = frame[crop_y0:crop_y1, crop_x0:crop_x1]

    template = load_template(template_path)
    th, tw = template.shape[:2]
    if search.shape[0] < th or search.shape[1] < tw:
        print("[右侧房间] 房间列表裁剪区域比模板还小，无法匹配")
        return (False, None)
    try:
        res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
    except Exception as e:
        print(f"[右侧房间] 匹配chaos91011room失败: {e}")
        return (False, None)
    if max_val >= CONFIG["match_threshold"]:
        fx = max_loc[0] + tw // 2 + crop_x0
        fy = max_loc[1] + th // 2 + crop_y0
        print(f"[右侧房间] 在房间列表区域(X:30%-98%,Y:22%-80%)找到chaos91011room，置信度={max_val:.4f}，帧坐标=({fx}, {fy})")
        return (True, (fx, fy, max_val))
    print(f"[右侧房间] 房间列表区域未找到chaos91011room（最佳置信度={max_val:.4f}），当前无房间")
    return (False, None)


def _click_right_panel_any_room(center_frame=None):
    """
    右侧面板识别到chaos91011room模板后，在模板中心双击进入房间。
    若传入center_frame则直接用其帧坐标双击；否则尝试再扫描一次。
    """
    hwnd = find_game_window()
    left, top, _, _ = get_window_rect(hwnd)
    if center_frame is None:
        _, cf = _scan_right_panel_room_name()
        if cf is None:
            print("[右侧房间] 再次扫描右侧面板未找到数字")
            return False
        fx, fy, _ = cf
    else:
        fx, fy, _ = center_frame
    screen_x = left + fx
    screen_y = top + fy
    print(f"[右侧房间] 双击CHAMPION SCORE数字位置进入房间，屏幕坐标=({screen_x}, {screen_y})")
    _slow_click_at(screen_x, screen_y, clicks=2)
    return True


def enter_right_panel_room_and_run(defaults_center):
    """
    chaos9/10/11分支：不断扫描右侧面板是否存在CHAMPION SCORE数字。
      - 找到 → 双击数字位置进入 → 执行 run_room_progression_loop()
      - 没找到 → 每3秒点一次 DEFAULTS 刷新（优先用记录的坐标，否则重新识别DEFAULTS模板，再退而点击游戏画面中间）
      - 全流程检查：超过40分钟未检测到任何玩家准备绿色对钩 → 强制卡死重启
    """
    global LAST_PLAYER_READY_TIME
    print("[右侧房间] chaos9/10/11分支：进入右侧房间寻找流程…")
    while not STOP_FLAG:
        # 卡死检测
        if FREEZE_MONITOR and check_and_recover_if_frozen(FREEZE_MONITOR):
            print("[右侧房间] 卡死恢复，退出当前流程")
            return False
        # ===== 全流程：40 分钟未检测到任何玩家准备 → 强制卡死重启 =====
        _now_right = time.time()
        if LAST_PLAYER_READY_TIME is not None:
            _mins_right = (_now_right - LAST_PLAYER_READY_TIME) / 60.0
            if _mins_right >= NO_PLAYER_READY_TIMEOUT_MINUTES:
                print(f"[WARN] [右侧房间] 超过 {_mins_right:.1f} 分钟未检测到任何玩家准备绿色对钩，执行卡死重启流程...")
                if FREEZE_MONITOR:
                    FREEZE_MONITOR.reset()
                recover_game()
                LAST_PLAYER_READY_TIME = time.time()
                return False
        has_room, center_frame = _scan_right_panel_room_name()
        if has_room:
            print("[右侧房间] 找到CHAMPION SCORE数字，尝试双击进入…")
            if _click_right_panel_any_room(center_frame=center_frame):
                time.sleep(1.0)
                # 进入房间后的流程与onslaught相同（按0/2/WSAD等）
                run_room_progression_loop()
                return True
        # 没找到数字 → 每3秒点一次 DEFAULTS 刷新
        print("[右侧房间] 无房间数字，3秒后点击 DEFAULTS 刷新…")
        for _ in range(3):
            if STOP_FLAG:
                return False
            time.sleep(1.0)

        # --- 点击 DEFAULTS：先使用记录坐标，若不存在则重新识别模板，再不行点击游戏画面中间 ---
        if defaults_center is None:
            fresh_center = _get_defaults_screen_center()
            if fresh_center:
                defaults_center = fresh_center
                print(f"[右侧房间] 未记录 defaults 坐标，本轮重新识别成功：{defaults_center}")
            else:
                # 还是识别不到 → 点击游戏画面中间作为兜底
                hwnd = find_game_window()
                if hwnd:
                    left, top, right, bottom = get_window_rect(hwnd)
                    cx = (left + right) // 2
                    cy = (top + bottom) // 2
                    defaults_center = (cx, cy)
                    print(f"[右侧房间] DEFAULTS 模板识别失败，兜底点击游戏画面中间: {defaults_center}")
                else:
                    print("[右侧房间] 无 defaults 坐标且找不到游戏窗口，跳过 DEFAULTS 点击")
                    defaults_center = None

        if defaults_center:
            try:
                sx, sy = defaults_center
                ctypes.windll.user32.SetCursorPos(sx, sy)
                time.sleep(0.03)
                ctypes.windll.user32.mouse_event(0x0002, sx, sy, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(0x0004, sx, sy, 0, 0)
                print(f"[右侧房间] 已点击 DEFAULTS ({sx}, {sy})")
            except Exception as e:
                print(f"[右侧房间] 点击 DEFAULTS 失败: {e}，跳过此次刷新")

        # 点击后再给3秒观察窗口
        for _ in range(3):
            if STOP_FLAG:
                return False
            time.sleep(1.0)
    return False


# ========================= Onslaught 房间选择模块 =========================
# 进入 Onslaught → BROWSE → REFRESH → 读取楼层 → 扫描房间 → 双击进入


def _open_onslaught_and_read_floor():
    """
    进入Onslaught界面并读取Selected Floor：
      1) 点击ONSLAUGHT  2) 点击BROWSE  3) 点击REFRESH  4) 读取Selected Floor
    返回: selected_floor（int, 三位数）或 None
    """
    hwnd = find_game_window()
    focus_game_window(hwnd)
    if not os.path.exists(CONFIG["onslaught_template"]):
        print("[WARN] ONSLAUGHT 模板不存在，无法进入 Onslaught 流程")
        return None
    # 1) 点击 ONSLAUGHT
    time.sleep(1.2)
    if not click_template_image(CONFIG["onslaught_template"], label="ONSLAUGHT", threshold=CONFIG["match_threshold"]):
        print("[WARN] 未找到 ONSLAUGHT 按钮，终止后续流程")
        return None
    # 2) 点击 BROWSE（点击 ONSLAUGHT 后多等 3 秒再找 BROWSE）
    #  - 如果点击 ONSLAUGHT 之后直接就进入了房间列表页面，就不会有 BROWSE 按钮，此时若能找到 REFRESH 就跳过 BROWSE 继续
    time.sleep(4.5)
    browse_ok = click_template_image(CONFIG["browse_template"], label="BROWSE", threshold=CONFIG["match_threshold"])
    if not browse_ok:
        # 找不到 BROWSE，就查一下当前是不是已经直接到了 REFRESH 页面（部分场景点完ONSLAUGHT直接进房间列表）
        print("[INFO] 未找到 BROWSE，检查当前是否已直接进入房间列表页面（尝试识别 REFRESH）…")
        hwnd_local = find_game_window()
        focus_game_window(hwnd_local)
        frame_local = capture_game_window(hwnd_local)
        refresh_template = load_template(CONFIG["refresh_template"]) if os.path.exists(CONFIG["refresh_template"]) else None
        has_refresh = False
        if refresh_template is not None:
            refresh_rect = find_template_rect(frame_local, refresh_template, threshold=CONFIG["e_tip_threshold"])
            if refresh_rect is not None:
                print(f"[INFO] 已检测到 REFRESH（相似度={refresh_rect['max_val']:.3f}），说明已直接进入房间列表页面，跳过 BROWSE 继续")
                has_refresh = True
        if not has_refresh:
            print("[WARN] 未找到 BROWSE 且也未检测到 REFRESH，终止后续流程")
            return None
    # 3) 找到 REFRESH 并点击，让房间列表加载
    time.sleep(6.5)
    if not click_refresh_button():
        print("[WARN] 未找到 REFRESH 按钮，仍尝试读取楼层")
    # 等待 1-2 秒让房间列表刷新加载
    time.sleep(2)
    # 4) 读取 Selected Floor 当前楼层数字
    selected_floor = extract_selected_floor_number(hwnd)
    if selected_floor is None:
        print("[WARN] 无法读取 Selected Floor")
        return None
    return selected_floor


def _scan_rooms_and_run(selected_floor):
    """
    基于已读取的selected_floor，扫描房间列表找floor>=selected_floor的目标房间：
    找到后双击进入并执行房间流程。
    返回: True 表示打完一局成功返回；False 表示卡死/未找到
    全流程检查：超过40分钟未检测到任何玩家准备绿色对钩 → 强制卡死重启
    """
    global STOP_FLAG, LAST_COMPLETED_FLOOR, NEED_VIEW_RESET_BEFORE_NEXT_WAR, ROOMFULL_9001_TRIGGERED, LAST_PLAYER_READY_TIME
    while not STOP_FLAG:
        # ===== 全流程：40 分钟未检测到任何玩家准备 → 强制卡死重启 =====
        _now_scan = time.time()
        if LAST_PLAYER_READY_TIME is not None:
            _mins_scan = (_now_scan - LAST_PLAYER_READY_TIME) / 60.0
            if _mins_scan >= NO_PLAYER_READY_TIMEOUT_MINUTES:
                print(f"[WARN] [房间扫描] 超过 {_mins_scan:.1f} 分钟未检测到任何玩家准备绿色对钩，执行卡死重启流程...")
                if FREEZE_MONITOR:
                    FREEZE_MONITOR.reset()
                recover_game()
                LAST_PLAYER_READY_TIME = time.time()
                return False
        hwnd = find_game_window()
        focus_game_window(hwnd)
        target_room, all_floors = get_target_room_floor(hwnd, selected_floor)
        if target_room is not None:
            # 双击进入目标房间
            click_target_room_floor(hwnd, target_room)
            time.sleep(0.5)
            # 进入房间后的自动循环（打完返回True）
            # 9001roomfull 检测和断连检测都在 run_room_progression_loop 内部并行执行
            ok = run_room_progression_loop()
            if ok:
                LAST_COMPLETED_FLOOR = selected_floor
                if selected_floor > 320:
                    print(f"[INFO] 本轮楼层={selected_floor}>320，立即执行卡死重启 + 下一次识别到War Table后执行视角专项")
                    NEED_VIEW_RESET_BEFORE_NEXT_WAR = True
                    if FREEZE_MONITOR:
                        FREEZE_MONITOR.reset()
                    recover_game()
                    # recover_game 成功后游戏会重启，本函数返回 False 让外层重新走主循环检测 War Table
                    return False
            return ok
        # 无目标房间，点击 REFRESH 后每 4 秒检测一次
        print(f"[INFO] 当前房间列表无目标房间（识别到的 floor: {all_floors}，需要 >= {selected_floor}），点击 REFRESH 后每 4 秒检测")
        click_refresh_button()
        for i in range(5):
            time.sleep(4)
            if STOP_FLAG:
                return False
            if FREEZE_MONITOR and check_and_recover_if_frozen(FREEZE_MONITOR):
                print("[INFO] 房间扫描过程中游戏卡死并已恢复")
                return False
            hwnd = find_game_window()
            focus_game_window(hwnd)
            target_room, all_floors = get_target_room_floor(hwnd, selected_floor)
            if target_room is not None:
                click_target_room_floor(hwnd, target_room)
                time.sleep(0.5)
                # 9001roomfull 检测和断连检测都在 run_room_progression_loop 内部并行执行
                ok = run_room_progression_loop()
                if ok:
                    LAST_COMPLETED_FLOOR = selected_floor
                    if selected_floor > 320:
                        print(f"[INFO] 本轮楼层={selected_floor}>320，立即执行卡死重启 + 下一次识别到War Table后执行视角专项")
                        NEED_VIEW_RESET_BEFORE_NEXT_WAR = True
                        if FREEZE_MONITOR:
                            FREEZE_MONITOR.reset()
                        recover_game()
                        return False
                return ok
            print(f"[INFO] 第 {(i+1)*4} 秒检测，floor: {all_floors}，需要 >= {selected_floor}")
    return False


def enter_onslaught_and_select_room():
    """
    兼容旧逻辑的封装：进入Onslaught并找合适房间，直接调用拆分后的两个子函数。
    """
    selected_floor = _open_onslaught_and_read_floor()
    if selected_floor is None:
        return False
    return _scan_rooms_and_run(selected_floor)


# ========================= 按E后楼层分支总入口 =========================

def after_e_branch_main():
    """
    在 walk_to_war_table_and_press_e() 成功按E之后调用：
    1. 进入ONSLAUGHT → BROWSE → 读取Selected Floor
    2. 如果 SKIP_FLOOR_CHECK_THIS_ROUND=True → 直接扫描找合适房间进入（跳过楼层<300判断）
    3. 否则：
       - 楼层<300 → 换装卖装备 → 按E → BROWSE → defaults → chaos9/8判断
           * chaos9 → 去右侧面板找房间
           * gear_low → 再次ONSLAUGHT+BROWSE → 扫描找合适房间（本次SKIP楼层判断）
       - 楼层≥300 → 直接扫描找合适房间进入
    返回：打完房间成功返回True；中途失败/卡死返回False
    """
    global SKIP_FLOOR_CHECK_THIS_ROUND, LAST_COMPLETED_FLOOR, NEED_RESET_AFTER_ROUND, NEED_VIEW_RESET_BEFORE_NEXT_WAR
    # 重置本次标记：每次重新按E进入流程后，如果之前是gear_low过来的，会在最外层被设置为True，这里直接读取即可
    # 1. 进入 ONSLAUGHT 并读取楼层
    print("[分支入口] 进入 ONSLAUGHT 并读取 Selected Floor…")
    selected_floor = _open_onslaught_and_read_floor()
    if selected_floor is None:
        return False
    print(f"[分支入口] 当前 Selected Floor = {selected_floor}")

    # 2. 判断是否需要跳过楼层<300判断（来自gear_low的前序流程）
    if SKIP_FLOOR_CHECK_THIS_ROUND:
        print("[分支入口] SKIP_FLOOR_CHECK_THIS_ROUND=True，跳过楼层<300判断，直接找合适房间")
        SKIP_FLOOR_CHECK_THIS_ROUND = False
        ok = _scan_rooms_and_run(selected_floor)
        return ok

    # 3. 正常楼层判断分支
    if selected_floor < 300:
        print(f"[分支入口] 楼层 {selected_floor}<300，进入换装+卖装备流程…")
        # 3a. ESC → 按I → 找autoequipgear → 卖装备 → 关背包
        perform_gear_switch_and_sell()
        # 3b. 按E → 找BROWSE → 点击defaults → 等2秒 → 判断chaos9/8
        judge_result, defaults_center = enter_browse_defaults_and_judge_chaos()
        if judge_result == "chaos9":
            print("[分支入口] chaos9分支 → 进入右侧面板寻找房间…")
            ok = enter_right_panel_room_and_run(defaults_center)
            if ok:
                LAST_COMPLETED_FLOOR = selected_floor
                if selected_floor > 320:
                    print(f"[INFO] 本轮(chaos9右侧)楼层={selected_floor}>320，立即执行卡死重启 + 下一次识别到War Table后执行视角专项")
                    NEED_VIEW_RESET_BEFORE_NEXT_WAR = True
                    if FREEZE_MONITOR:
                        FREEZE_MONITOR.reset()
                    recover_game()
                    return False
            return ok
        else:
            # gear_low → 走楼层流程：切回 ONSLAUGHT 找合适房间刷分，
            # 打完后下一轮回来会重新换装备 + 检测 gear 分，直到能识别到 chaos9/10/11 才走右侧chaos房间路径
            print("[分支入口] gear_low分支 → 切回 ONSLAUGHT 找合适房间刷分（打完后再回来检测 gear 分）…")
            sf2 = _open_onslaught_and_read_floor()
            if sf2 is None:
                print("[WARN] gear_low后重试读取楼层失败，终止流程")
                return False
            if sf2 > 320:
                print(f"[分支入口] gear_low重入后读取 Selected Floor = {sf2}>320，立即执行卡死重启 + 下一次识别到War Table后执行视角专项")
                NEED_VIEW_RESET_BEFORE_NEXT_WAR = True
                LAST_COMPLETED_FLOOR = sf2
                if FREEZE_MONITOR:
                    FREEZE_MONITOR.reset()
                recover_game()
                return False
            print(f"[分支入口] gear_low重入后读取 Selected Floor = {sf2}")
            ok = _scan_rooms_and_run(sf2)
            return ok
    else:
        # 楼层 >= 300 分两种情况：
        #   300~320：还没到 Ancient Power 门槛，继续简化卖装备（不换装）→ 找合适楼层房间推进
        #   > 320：才走卡死重启 + 下一次识别到 War Table 后执行视角专项（reset）
        if selected_floor <= 320:
            print(f"[分支入口] 楼层 {selected_floor} 在 300~320 之间，继续简化卖装备（不换装）→ 找合适楼层房间推进")
            # 1. 简化卖装备（ESC→按I→找背包1点击→保护10级→按Y卖→ESC关背包）
            perform_sell_only_no_switch()
            # 2. 卖完装备后，当前还在城堡，按E回到War Table交互界面
            print("[分支入口] 卖装备完成，回到War Table旁识别e-tip并按E…")
            hwnd = find_game_window()
            etip_ok = False
            for _a in range(10):
                if STOP_FLAG:
                    break
                if detect_e_tip(hwnd) is not None:
                    humanized_press("e")
                    time.sleep(0.8)
                    etip_ok = True
                    break
                # 没识别到，按一下W微调位置
                humanized_press("w")
                time.sleep(0.3)
            if not etip_ok:
                print("[WARN] 卖装备后按E失败，尝试直接走ONSLAUGHT流程…")
            # 3. 重新走ONSLAUGHT→BROWSE→读Selected Floor，然后找合适房间
            sf_new = _open_onslaught_and_read_floor()
            if sf_new is None:
                print("[WARN] 卖装备后重新读取楼层失败，终止流程")
                return False
            if sf_new > 320:
                print(f"[分支入口] 卖装备后读取 Selected Floor = {sf_new}>320，立即执行卡死重启 + 下一次识别到War Table后执行视角专项")
                NEED_VIEW_RESET_BEFORE_NEXT_WAR = True
                LAST_COMPLETED_FLOOR = sf_new
                if FREEZE_MONITOR:
                    FREEZE_MONITOR.reset()
                recover_game()
                return False
            print(f"[分支入口] 卖装备后读取 Selected Floor = {sf_new}，开始找合适房间")
            ok = _scan_rooms_and_run(sf_new)
            return ok
        else:
            # 楼层 > 320，直接卡死重启 + 下一次识别到 War Table 后执行视角专项（reset）
            print(f"[分支入口] 楼层 {selected_floor}>320，直接执行卡死重启 + 视角专项（reset）流程")
            NEED_VIEW_RESET_BEFORE_NEXT_WAR = True
            LAST_COMPLETED_FLOOR = selected_floor
            if FREEZE_MONITOR:
                FREEZE_MONITOR.reset()
            recover_game()
            return False


# ========================= 自动寻路主逻辑 =========================
# War Table 识别 → 中心对齐 → 直走 → E 提示检测 → 按 E

def detect_war_table(hwnd):
    """
    在当前游戏窗口截图中识别 War Table 模板。
    这里支持多个角度模板：wartable1.png / wartable2.png / wartable3.png，
    取匹配度最高的那个作为当前的结果。
    """
    frame = capture_game_window(hwnd)
    best_match = None

    for template_path in CONFIG["war_table_templates"]:
        template = load_template(template_path)
        match = find_template_center(frame, template)
        if match is None:
            continue

        if best_match is None or match[2] > best_match[2]:
            best_match = match

    return best_match


def detect_e_tip(hwnd):
    """在当前游戏窗口截图中识别 E 提示模板（支持 e_tip、e_tip2、e_tip3 三张）。
    直接调用 find_template_rect（内部已含多尺度匹配），避免嵌套多尺度导致耗时过长。
    同时验证匹配位置：E 提示应在画面中下方（Y > 35%），过滤顶部的误匹配。"""
    frame = capture_game_window(hwnd)
    frame_h, frame_w = frame.shape[:2]
    threshold = CONFIG["e_tip_threshold"]
    # E 提示应出现在画面中下方，Y 坐标至少在画面 35% 以下
    min_valid_y = int(frame_h * 0.35)
    best = None            # (cx, cy, conf)
    best_scale_tag = "标准"
    overall_max_val = 0.0  # 记录所有尝试中的最高相似度，便于调试
    for key in ("e_tip_template", "e_tip2_template", "e_tip3_template"):
        path = CONFIG.get(key)
        if not path or not os.path.exists(path):
            continue
        template = load_template(path)
        # find_template_rect 内部已做多尺度匹配（0.5x-2.0x），这里直接调用即可
        rect = find_template_rect(frame, template, threshold=threshold)
        if rect is not None:
            cx = rect["center_x"]
            cy = rect["center_y"]
            conf = rect["max_val"]
            # 位置验证：E 提示应在画面中下方
            if cy < min_valid_y:
                # 匹配位置太靠上，很可能是误匹配，跳过
                continue
            if overall_max_val < conf:
                overall_max_val = conf
            if best is None or conf > best[2]:
                best = (cx, cy, conf)
                best_scale_tag = f"scale={rect['scale']}"
        else:
            # 记录标准尺度下的最高相似度（即使未过阈值）用于调试
            try:
                res = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
                _, mv, _, _ = cv2.minMaxLoc(res)
                if mv > overall_max_val:
                    overall_max_val = mv
            except Exception:
                pass
    if best is not None:
        print(f"[E提示] 识别到 E 提示，置信度={best[2]:.4f}（{best_scale_tag}），坐标=({best[0]}, {best[1]})")
    else:
        print(f"[E提示] 未识别到 E 提示，最高置信度={overall_max_val:.4f}（阈值={threshold}）")
    return best


def stop_now():
    """F12 热键触发的停止函数，立即终止脚本。"""
    global STOP_FLAG
    STOP_FLAG = True
    print("[INFO] 已收到 F12 停止信号，立即终止脚本...")
    import os
    os._exit(0)


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
        rotate_view(-1, drag_px=90)
        return "rotate_left"
    if dx > CONFIG["center_tolerance_x"]:
        rotate_view(1, drag_px=90)
        return "rotate_right"

    if abs(dy) > CONFIG["center_tolerance_y"]:
        move_forward_once()
        return "forward"

    return "approach"


def walk_to_war_table_and_press_e():
    """
    核心主逻辑：
    1) 若 NEED_VIEW_RESET_BEFORE_NEXT_WAR=True，先识别 War Table 并执行视角重置专项；
    2) 先朝前走 4 步接近 War Table，停顿 2 秒让画面稳定后识别 E 提示；
    3) 若未识别到 E，每走 1 步停顿一下再识别，直到识别出来为止；
    4) 识别到 E 后按 E 交互；
    5) F12 可立即中止所有键鼠动作。
    """
    global STOP_FLAG, NEED_VIEW_RESET_BEFORE_NEXT_WAR

    hwnd = find_game_window()

    print("[INFO] 1 秒后开始自动寻路…")
    time.sleep(1)

    # —— 视角重置专项入口：若标记为 True，先识别一次 War Table 并执行专项
    if NEED_VIEW_RESET_BEFORE_NEXT_WAR:
        hwnd_vr = find_game_window()
        table_pos = detect_war_table(hwnd_vr)
        if table_pos is not None:
            print("[INFO] NEED_VIEW_RESET_BEFORE_NEXT_WAR=True，识别到WarTable后立即执行视角重置专项+卡死重启…")
            NEED_VIEW_RESET_BEFORE_NEXT_WAR = False
            perform_view_reset_and_restart()
            # 专项执行完游戏会重启，返回 False 让外层重新走主循环寻路
            return False
        else:
            print("[INFO] NEED_VIEW_RESET_BEFORE_NEXT_WAR=True 但未识别到War Table，继续走前寻找")

    # 1) 先朝前走 4 步，接近 War Table（避免在出生点误匹配 E 提示）
    print("[INFO] 先朝前走 4 步，接近 War Table...")
    for _ in range(4):
        if STOP_FLAG:
            return False
        move_forward_once()
        time.sleep(0.4)

    # 2) 走完 4 步后停顿 0.5 秒，让画面稳定再识别 E（避免运动模糊导致误匹配）
    print("[INFO] 停顿 0.5 秒，等待画面稳定后识别 E 提示...")
    time.sleep(0.5)

    # 被踢检测
    if check_kicked_quick():
        return False  # 被踢恢复后重新开始寻路

    # 首次识别 E 提示
    hwnd = find_game_window()
    e_pos = detect_e_tip(hwnd)
    if e_pos is not None:
        print("[INFO] 检测到 E 提示，准备按 E 交互")
        press_e_interact()
        return True

    # 3) 未识别到 E，每走 1 步停顿一下再识别，直到识别出来为止
    print("[INFO] 未识别到 E 提示，开始每走 1 步停顿识别一次...")
    walk_step_count = 0
    max_walk_steps = 10  # 连续 10 次未识别到 E 提示，走卡死重启流程

    while not STOP_FLAG and walk_step_count < max_walk_steps:
        # 被踢检测
        if check_kicked_quick():
            return False  # 被踢恢复后重新开始寻路

        # 朝前走 1 步
        move_forward_once()
        walk_step_count += 1

        # 停顿一下，让画面稳定再识别 E
        time.sleep(0.5)

        # 识别 E 提示
        hwnd = find_game_window()
        e_pos = detect_e_tip(hwnd)
        if e_pos is not None:
            print(f"[INFO] 走 {walk_step_count} 步后检测到 E 提示，准备按 E 交互")
            press_e_interact()
            return True

    if walk_step_count >= max_walk_steps:
        print(f"[WARN] 连续 {max_walk_steps} 次未识别到 E 提示，执行卡死重启流程...")
        recover_game()
        return False
    else:
        print("[INFO] 脚本已停止")
    return False


# ========================= 主入口 =========================
# 完整流程循环：寻路 → 选房间 → 打怪 → 返回 → 循环
# 每轮开始前检测：被踢 > 卡死 > 正常流程

if __name__ == "__main__":
    register_stop_hotkey()
    enable_system_keep_awake()

    print("=" * 70)
    print("DD2 自动寻路到 War Table 并按 E 打开界面")
    print("=" * 70)
    print("说明：")
    print("- 走路阶段：无系统鼠标光标，主要使用 W 慢走，必要时轻微 A/D 横移校正")
    print("- 弹窗阶段：有鼠标光标，需要通过按 E 打开交互界面")
    print("- 后续流程：进入 Onslaught，读取 Selected Floor，扫描房间列表，双击目标房间")
    print("- 紧急停止：按 F12")
    print("- 卡死检测：自动监控游戏状态，卡死时自动关闭并重启游戏")
    print("- 全局启动：运行 hotkey_listener.py 后，在任意界面按 Ctrl+F11 可直接启动本脚本")
    print("- 模板路径：")
    print(f"  War Table = {CONFIG['war_table_templates']}")
    print(f"  E Tip     = {CONFIG['e_tip_template']}")
    print(f"  ONSLAUGHT = {CONFIG['onslaught_template']}")
    print(f"  BROWSE    = {CONFIG['browse_template']}")
    print(f"  Selected Floor = {CONFIG['selected_floor_template']}")
    print(f"  Room List = {CONFIG['room_list_template']}")
    print(f"  REFRESH   = {CONFIG['refresh_template']}")
    print("=" * 70)

    try:
        # 启动时检测游戏窗口是否存在
        print("[INFO] 正在查找游戏窗口...")
        hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])

        if hwnd:
            # 游戏窗口已打开，直接聚焦
            focus_game_window(hwnd)
            print(f"[INFO] 已找到并聚焦游戏窗口，句柄={hwnd}")
        else:
            # 游戏窗口未打开，通过 Steam 启动游戏
            print("[INFO] 游戏窗口未找到，通过 Steam 启动游戏...")

            launched = False
            for launch_attempt in range(3):
                print(f"[INFO] 第 {launch_attempt + 1} 次尝试启动游戏...")

                # 按 Win 键打开开始菜单
                _press_win_key()

                # 在屏幕左半边找 Steam 图标并点击
                screen_w = pyautogui.size()[0]
                left_region = (0, 0, screen_w // 2, pyautogui.size()[1])
                steam_pos = None
                for attempt in range(15):
                    steam_pos = _find_image_on_screen(TEMPLATE_STEAM, threshold=0.6, region=left_region)
                    if steam_pos:
                        print(f"[INFO] 找到Steam图标，位置: ({steam_pos[0]}, {steam_pos[1]})")
                        _click_at(steam_pos[0], steam_pos[1], delay=0.5)
                        break
                    print(f"[INFO] 未找到Steam图标，重试 {attempt + 1}/15...")
                    time.sleep(1)

                if not steam_pos:
                    print("[错误] 未找到Steam图标")
                    continue

                time.sleep(3)

                # 先找"取消"按钮（如果有），点击取消当前操作
                cancel_pos = None
                for attempt in range(5):
                    cancel_pos = _find_image_on_screen(TEMPLATE_CANCEL, threshold=FREEZE_MATCH_THRESHOLD)
                    if cancel_pos:
                        print(f"[INFO] 找到'取消'按钮，点击取消")
                        _click_at(cancel_pos[0], cancel_pos[1], delay=0.5)
                        time.sleep(2)
                        break
                    time.sleep(1)

                # 找"开始游戏"按钮并点击
                print("[INFO] 查找'开始游戏'按钮...")
                start_pos = None
                game_end_clicked = False
                for attempt in range(30):
                    start_pos = _find_image_on_screen(TEMPLATE_START_GAME, threshold=FREEZE_MATCH_THRESHOLD)
                    if start_pos:
                        print(f"[INFO] 找到'开始游戏'按钮，位置: ({start_pos[0]}, {start_pos[1]})")
                        _click_at(start_pos[0], start_pos[1], delay=0.5)
                        break
                    if attempt >= 9 and not game_end_clicked:
                        game_end_pos = _find_image_on_screen(TEMPLATE_GAME_END, threshold=FREEZE_MATCH_THRESHOLD)
                        if game_end_pos:
                            print(f"[INFO] 连续10次未找到'开始游戏'，检测到 gameend，点击位置: ({game_end_pos[0]}, {game_end_pos[1]})")
                            _click_at(game_end_pos[0], game_end_pos[1], delay=0.5)
                            game_end_clicked = True
                            time.sleep(2)
                            continue
                    print(f"[INFO] 未找到'开始游戏'按钮，重试 {attempt + 1}/30...")
                    time.sleep(2)

                if not start_pos:
                    print("[错误] 未找到'开始游戏'按钮")
                    continue

                # 等待游戏窗口出现
                print("[INFO] 等待游戏窗口出现...")
                for attempt in range(60):
                    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
                    if hwnd:
                        print(f"[INFO] DD2游戏窗口已出现，句柄: {hwnd}")
                        focus_game_window(hwnd)
                        time.sleep(3)
                        launched = True
                        break
                    print(f"[INFO] 等待游戏窗口... {attempt + 1}/60")
                    time.sleep(5)

                if launched:
                    break
                print("[INFO] 等待超时，重试 Steam 启动...")

            if not hwnd:
                print("[错误] 多次尝试后游戏窗口仍未出现，脚本退出")
                import sys
                sys.exit(1)

            # 游戏刚启动，点击画面中间查找私人城镇按钮
            print("[INFO] 游戏已启动，点击画面中间查找'私人城镇'按钮...")
            focus_game_window(hwnd)
            game_rect = win32gui.GetWindowRect(hwnd)
            center_x = (game_rect[0] + game_rect[2]) // 2
            center_y = (game_rect[1] + game_rect[3]) // 2
            tavern_template = load_template(TEMPLATE_PRIVATE_TAVERN)
            tavern_clicked = False
            for attempt in range(20):
                _click_at(center_x, center_y, delay=1.0)
                print(f"[INFO] 点击画面中间 ({center_x}, {center_y})，第 {attempt + 1} 次")
                frame = capture_game_window(hwnd)
                tavern_rect = find_template_rect(frame, tavern_template, threshold=0.6)
                if tavern_rect is not None:
                    left, top, _, _ = get_window_rect(hwnd)
                    screen_x = left + tavern_rect["center_x"]
                    screen_y = top + tavern_rect["center_y"]
                    _click_at(screen_x, screen_y, delay=0.5)
                    print("[INFO] 已点击私人城镇按钮")
                    tavern_clicked = True
                    break
                print(f"[INFO] 未找到私人城镇按钮，重试 {attempt + 1}/20...")
                time.sleep(1.5)
            if not tavern_clicked:
                print("[WARN] 未找到私人城镇按钮，但游戏已启动，等待 60 秒后继续")
                time.sleep(60)
            else:
                print("[INFO] 已点击私人城镇按钮，开始每隔10秒检测 War Table...")
                war_table_start_time = time.time()
                war_table_found = False
                for check_attempt in range(36):
                    elapsed = time.time() - war_table_start_time
                    frame = capture_game_window(hwnd)
                    war_table_rect = None
                    for template_path in CONFIG["war_table_templates"]:
                        war_table_template = load_template(template_path)
                        war_table_rect = find_template_rect(frame, war_table_template, threshold=0.78)
                        if war_table_rect is not None:
                            break
                    if war_table_rect is not None:
                        print("[INFO] 检测到 War Table，开始执行卖装备流程")
                        war_table_found = True
                        break
                    print(f"[INFO] 未检测到 War Table，已持续 {elapsed:.1f} 秒...")
                    # 未检测到 War Table 超过100秒，检测网络连接断开
                    if elapsed >= 100:
                        print("[INFO] 未检测到 War Table 超100秒，检测网络连接断开...")
                        if check_connection_failed():
                            print("[INFO] 网络连接断开检测触发恢复，重新开始")
                            hwnd = None
                            war_table_found = True
                            break
                    time.sleep(10)
                if not war_table_found:
                    print("[WARN] 6分钟内未检测到 War Table，视为卡死，开始恢复...")
                    success = recover_game()
                    if success:
                        print("[INFO] 游戏恢复成功，重新开始")
                        hwnd = None
                    else:
                        print("[INFO] 游戏恢复失败，请手动处理")

        time.sleep(1)

        FREEZE_MONITOR = GameFreezeMonitor()
        dpi_scale = get_system_dpi_scale()
        print(f"[INFO] 卡死检测已启用，将在运行过程中持续监控游戏状态（系统DPI缩放={dpi_scale}）")

        # 初始化 40 分钟无队友准备计时起点（游戏刚启动还没进房间，这里设当前时间）
        if LAST_PLAYER_READY_TIME is None:
            LAST_PLAYER_READY_TIME = time.time()
        last_disconnect_check_time = time.time()

        while not STOP_FLAG:
            # ===== 全流程：40 分钟未检测到任何队友准备绿色对钩 → 强制卡死重启（防止长时间停留在右侧面板/房间列表等流程时漏检）=====
            _now_out = time.time()
            if LAST_PLAYER_READY_TIME is not None:
                _mins = (_now_out - LAST_PLAYER_READY_TIME) / 60.0
                if _mins >= NO_PLAYER_READY_TIMEOUT_MINUTES:
                    print(f"[WARN] 主循环：超过 {_mins:.1f} 分钟未检测到任何队友准备绿色对钩，执行卡死重启流程...")
                    if FREEZE_MONITOR:
                        FREEZE_MONITOR.reset()
                    recover_game()
                    LAST_PLAYER_READY_TIME = time.time()
                    continue
            # 被踢检测（优先级最高，先于卡死检测）
            if check_kicked_quick():
                continue

            # 每10分钟检测一次网络连接断开
            now = time.time()
            if now - last_disconnect_check_time >= 600:
                print("[INFO] 定期检测网络连接断开...")
                if check_connection_failed():
                    print("[INFO] 网络连接断开检测触发恢复，等待 10 秒后重新开始")
                    time.sleep(10)
                    last_disconnect_check_time = time.time()
                    continue
                last_disconnect_check_time = now

            # 每轮循环开始前做一次卡死检测
            if check_and_recover_if_frozen(FREEZE_MONITOR):
                print("[INFO] 游戏已从卡死恢复，等待 10 秒后重新开始")
                time.sleep(10)
                continue

            # 不再在寻路前卖装备：改为 War Table 之后、读取 Selected Floor 之后按楼层判断再决定
            if walk_to_war_table_and_press_e():
                # 寻路完成后做一次卡死检测
                if check_and_recover_if_frozen(FREEZE_MONITOR):
                    print("[INFO] 游戏已从卡死恢复，等待 10 秒后重新开始")
                    time.sleep(10)
                    continue

                # 按E后走楼层分支入口（内部处理楼层<300换装、≥300直接onslaught、chaos9右面板、gear_low跳过等）
                after_e_branch_main()

                # 点击 To Tavern 返回城堡后，每隔10秒检测 War Table
                print("[INFO] 已返回城堡，开始每隔10秒检测 War Table...")
                hwnd = find_game_window()
                war_table_start_time = time.time()
                war_table_found = False
                for check_attempt in range(36):
                    elapsed = time.time() - war_table_start_time
                    frame = capture_game_window(hwnd)
                    war_table_rect = None
                    for template_path in CONFIG["war_table_templates"]:
                        war_table_template = load_template(template_path)
                        war_table_rect = find_template_rect(frame, war_table_template, threshold=0.78)
                        if war_table_rect is not None:
                            break
                    if war_table_rect is not None:
                        print("[INFO] 检测到 War Table，开始下一轮寻路")
                        war_table_found = True
                        break
                    print(f"[INFO] 未检测到 War Table，已持续 {elapsed:.1f} 秒...")
                    # 未检测到 War Table 超过100秒，检测网络连接断开
                    if elapsed >= 100:
                        print("[INFO] 未检测到 War Table 超100秒，检测网络连接断开...")
                        if check_connection_failed():
                            print("[INFO] 网络连接断开检测触发恢复，等待 10 秒后重新开始")
                            time.sleep(10)
                            war_table_found = True
                            break
                    time.sleep(10)
                if not war_table_found:
                    print("[WARN] 6分钟内未检测到 War Table，视为卡死，开始恢复...")
                    if FREEZE_MONITOR:
                        FREEZE_MONITOR.reset()
                    success = recover_game()
                    if success:
                        print("[INFO] 游戏恢复成功，等待 10 秒后重新开始")
                        time.sleep(10)
                    else:
                        print("[INFO] 游戏恢复失败，请手动处理")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[INFO] 用户中断退出")
    except FileNotFoundError as e:
        print(f"[ERROR] {e}\n请先把桌子模板与 E 提示模板放到: {CONFIG['template_dir']}")
    except RuntimeError as e:
        if "未找到游戏窗口" in str(e):
            print(f"[INFO] 游戏窗口消失，尝试通过 Steam 重启游戏...")
            # 游戏窗口消失，走 Steam 启动流程
            hwnd = None
            for launch_attempt in range(3):
                print(f"[INFO] 第 {launch_attempt + 1} 次尝试启动游戏...")
                _press_win_key()
                screen_w = pyautogui.size()[0]
                left_region = (0, 0, screen_w // 2, pyautogui.size()[1])
                steam_pos = None
                for attempt in range(15):
                    steam_pos = _find_image_on_screen(TEMPLATE_STEAM, threshold=0.6, region=left_region)
                    if steam_pos:
                        print(f"[INFO] 找到Steam图标，位置: ({steam_pos[0]}, {steam_pos[1]})")
                        _click_at(steam_pos[0], steam_pos[1], delay=0.5)
                        break
                    print(f"[INFO] 未找到Steam图标，重试 {attempt + 1}/15...")
                    time.sleep(1)
                if not steam_pos:
                    print("[错误] 未找到Steam图标")
                    continue
                time.sleep(3)
                cancel_pos = None
                for attempt in range(5):
                    cancel_pos = _find_image_on_screen(TEMPLATE_CANCEL, threshold=FREEZE_MATCH_THRESHOLD)
                    if cancel_pos:
                        print(f"[INFO] 找到'取消'按钮，点击取消")
                        _click_at(cancel_pos[0], cancel_pos[1], delay=0.5)
                        time.sleep(2)
                        break
                    time.sleep(1)
                print("[INFO] 查找'开始游戏'按钮...")
                start_pos = None
                game_end_clicked = False
                for attempt in range(30):
                    start_pos = _find_image_on_screen(TEMPLATE_START_GAME, threshold=FREEZE_MATCH_THRESHOLD)
                    if start_pos:
                        print(f"[INFO] 找到'开始游戏'按钮，位置: ({start_pos[0]}, {start_pos[1]})")
                        _click_at(start_pos[0], start_pos[1], delay=0.5)
                        break
                    if attempt >= 9 and not game_end_clicked:
                        game_end_pos = _find_image_on_screen(TEMPLATE_GAME_END, threshold=FREEZE_MATCH_THRESHOLD)
                        if game_end_pos:
                            print(f"[INFO] 连续10次未找到'开始游戏'，检测到 gameend，点击位置: ({game_end_pos[0]}, {game_end_pos[1]})")
                            _click_at(game_end_pos[0], game_end_pos[1], delay=0.5)
                            game_end_clicked = True
                            time.sleep(2)
                            continue
                    print(f"[INFO] 未找到'开始游戏'按钮，重试 {attempt + 1}/30...")
                    time.sleep(2)
                if not start_pos:
                    print("[错误] 未找到'开始游戏'按钮")
                    continue
                print("[INFO] 等待游戏窗口出现...")
                for attempt in range(60):
                    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
                    if hwnd:
                        print(f"[INFO] DD2游戏窗口已出现，句柄: {hwnd}")
                        focus_game_window(hwnd)
                        time.sleep(3)
                        break
                    print(f"[INFO] 等待游戏窗口... {attempt + 1}/60")
                    time.sleep(5)
                if hwnd:
                    break
                print("[INFO] 等待超时，重试 Steam 启动...")
            if not hwnd:
                print("[错误] 多次尝试后游戏窗口仍未出现，脚本退出")
                import sys
                sys.exit(1)
            # 游戏重启成功，先点击私人城镇按钮进入城堡
            print("[INFO] 游戏已重启，点击画面中间查找'私人城镇'按钮...")
            focus_game_window(hwnd)
            game_rect = win32gui.GetWindowRect(hwnd)
            center_x = (game_rect[0] + game_rect[2]) // 2
            center_y = (game_rect[1] + game_rect[3]) // 2
            tavern_template = load_template(TEMPLATE_PRIVATE_TAVERN)
            tavern_clicked = False
            for attempt in range(20):
                _click_at(center_x, center_y, delay=1.0)
                print(f"[INFO] 点击画面中间 ({center_x}, {center_y})，第 {attempt + 1} 次")
                frame = capture_game_window(hwnd)
                tavern_rect = find_template_rect(frame, tavern_template, threshold=0.6)
                if tavern_rect is not None:
                    left, top, _, _ = get_window_rect(hwnd)
                    screen_x = left + tavern_rect["center_x"]
                    screen_y = top + tavern_rect["center_y"]
                    _click_at(screen_x, screen_y, delay=0.5)
                    print("[INFO] 已点击私人城镇按钮")
                    tavern_clicked = True
                    break
                print(f"[INFO] 未找到私人城镇按钮，重试 {attempt + 1}/20...")
                time.sleep(1.5)
            if not tavern_clicked:
                print("[WARN] 未找到私人城镇按钮，但游戏已重启，等待 60 秒后继续")
                time.sleep(60)
            else:
                print("[INFO] 已点击私人城镇按钮，开始每隔10秒检测 War Table...")
                war_table_start_time = time.time()
                war_table_found = False
                for check_attempt in range(36):
                    elapsed = time.time() - war_table_start_time
                    frame = capture_game_window(hwnd)
                    war_table_rect = None
                    for template_path in CONFIG["war_table_templates"]:
                        war_table_template = load_template(template_path)
                        war_table_rect = find_template_rect(frame, war_table_template, threshold=0.78)
                        if war_table_rect is not None:
                            break
                    if war_table_rect is not None:
                        print("[INFO] 检测到 War Table，开始执行卖装备流程")
                        war_table_found = True
                        break
                    print(f"[INFO] 未检测到 War Table，已持续 {elapsed:.1f} 秒...")
                    # 未检测到 War Table 超过100秒，检测网络连接断开
                    if elapsed >= 100:
                        print("[INFO] 未检测到 War Table 超100秒，检测网络连接断开...")
                        if check_connection_failed():
                            print("[INFO] 网络连接断开检测触发恢复，重新开始")
                            war_table_found = True
                            break
                    time.sleep(10)
                if not war_table_found:
                    print("[WARN] 6分钟内未检测到 War Table，视为卡死，开始恢复...")
                    success = recover_game()
                    if success:
                        print("[INFO] 游戏恢复成功，重新开始")
                    else:
                        print("[INFO] 游戏恢复失败，请手动处理")
            # 进入主循环
            FREEZE_MONITOR = GameFreezeMonitor()
            while not STOP_FLAG:
                if check_kicked_quick():
                    continue
                if check_and_recover_if_frozen(FREEZE_MONITOR):
                    print("[INFO] 游戏已从卡死恢复，等待 10 秒后重新开始")
                    time.sleep(10)
                    continue

                # 不再在寻路前卖装备：改为按E后走楼层分支入口
                if walk_to_war_table_and_press_e():
                    if check_and_recover_if_frozen(FREEZE_MONITOR):
                        print("[INFO] 游戏已从卡死恢复，等待 10 秒后重新开始")
                        time.sleep(10)
                        continue
                    # 走楼层分支入口（内部处理换装、chaos判断、右侧面板/onslaught等）
                    after_e_branch_main()
                    # after_e_branch_main 内部已经处理了卡死+reset视角的流程，
                    # 返回后游戏已在城堡界面（recover_game 中 detect_war_table 已识别到），无需再等 60 秒
                    print("[INFO] 已返回城堡，立即开始下一轮寻路")
                time.sleep(1.0)
        else:
            print(f"[ERROR] 脚本异常: {e}")
    except Exception as e:
        if STOP_FLAG:
            print("[INFO] 已收到停止信号，脚本已停止")
        else:
            print(f"[ERROR] 脚本异常: {e}")
    finally:
        disable_system_keep_awake()
        print("[INFO] 已恢复 Windows 默认电源管理")
