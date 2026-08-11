import time
import ctypes
import win32gui
import win32api
import win32con

GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"
KEY_W = 0x57
SCAN_CODE_W = 0x11

MAPVK_VK_TO_VSC = 0


def get_scan_code(vk_code):
    return ctypes.windll.user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC)


def make_lparam_keydown(vk_code, repeat=1, scan_code=None, is_extended=False):
    if scan_code is None:
        scan_code = get_scan_code(vk_code)
    lparam = repeat & 0xFFFF
    lparam |= (scan_code & 0xFF) << 16
    if is_extended:
        lparam |= 1 << 24
    lparam |= 0 << 29
    lparam |= 0 << 30
    lparam |= 0 << 31
    return lparam


def make_lparam_keyup(vk_code, repeat=1, scan_code=None, is_extended=False):
    if scan_code is None:
        scan_code = get_scan_code(vk_code)
    lparam = repeat & 0xFFFF
    lparam |= (scan_code & 0xFF) << 16
    if is_extended:
        lparam |= 1 << 24
    lparam |= 1 << 29
    lparam |= 1 << 30
    lparam |= 1 << 31
    return lparam


def bring_window_to_front(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.1)


def send_key_down(hwnd, vk_code, use_post=True):
    lparam = make_lparam_keydown(vk_code)
    if use_post:
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparam)
    else:
        win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lparam)


def send_key_up(hwnd, vk_code, use_post=True):
    lparam = make_lparam_keyup(vk_code)
    if use_post:
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lparam)
    else:
        win32api.SendMessage(hwnd, win32con.WM_KEYUP, vk_code, lparam)


if __name__ == "__main__":
    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd == 0:
        print("❌ 找不到游戏窗口，请确认游戏已打开、窗口标题正确！")
        exit(1)

    print(f"✅ 窗口绑定成功，句柄：{hwnd}")
    print(f"   类名：{win32gui.GetClassName(hwnd)}")
    print(f"   标题：{repr(win32gui.GetWindowText(hwnd))}")

    is_foreground = (win32gui.GetForegroundWindow() == hwnd)
    print(f"   是否为前台窗口：{'是' if is_foreground else '否'}")

    if not is_foreground:
        print("⚠️  窗口不在前台，尝试激活窗口...")
        try:
            bring_window_to_front(hwnd)
            is_foreground = (win32gui.GetForegroundWindow() == hwnd)
            print(f"   激活后是否前台：{'是' if is_foreground else '否'}")
        except Exception as e:
            print(f"   激活失败：{e}")

    print("\n🎮 测试方案1：PostMessage + 标准 lParam")
    print("开始按住W向前行走5秒...")

    send_key_down(hwnd, KEY_W, use_post=True)

    for i in range(5, 0, -1):
        print(f"  行走中... 剩余 {i} 秒")
        time.sleep(1)

    send_key_up(hwnd, KEY_W, use_post=True)
    print("✅ 5秒行走完成，松开W键")