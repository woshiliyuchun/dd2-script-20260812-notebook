"""Send periodic keyboard and mouse input to DD2 in the background."""

import ctypes
import time
from ctypes import wintypes


GAME_WINDOW_CLASS = "LaunchUnrealUWindowsClient"
GAME_WINDOW_TITLE = "Dungeon Defenders 2"
ZERO_INTERVAL_SECONDS = 3.0
THREE_INTERVAL_SECONDS = 6.0
THREE_TO_CLICK_DELAY_SECONDS = 2.0
KEY_HOLD_SECONDS = 0.05
HOTKEY_POLL_SECONDS = 0.05

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
VK_0 = 0x30
VK_3 = 0x33
VK_F12 = 0x7B
MAPVK_VK_TO_VSC = 0

user32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.LPARAM,
)

user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.EnumWindows.argtypes = (
    WNDENUMPROC,
    wintypes.LPARAM,
)
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
)
user32.GetWindowTextW.restype = ctypes.c_int
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.PostMessageW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostMessageW.restype = wintypes.BOOL
user32.GetClientRect.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.RECT),
)
user32.GetClientRect.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short


def find_dd2_window():
    """Find DD2 by exact class/title, then fall back to a title search."""
    hwnd = user32.FindWindowW(GAME_WINDOW_CLASS, GAME_WINDOW_TITLE)
    if hwnd:
        return hwnd

    matches = []

    @WNDENUMPROC
    def enum_callback(current_hwnd, _):
        if not user32.IsWindowVisible(current_hwnd):
            return True
        text_length = user32.GetWindowTextLengthW(current_hwnd)
        if text_length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(text_length + 1)
        user32.GetWindowTextW(current_hwnd, title_buffer, len(title_buffer))
        if GAME_WINDOW_TITLE.lower() in title_buffer.value.lower():
            matches.append(current_hwnd)
            return False
        return True

    user32.EnumWindows(enum_callback, 0)
    return matches[0] if matches else None


def send_key_to_window(hwnd, virtual_key):
    """Post one key press directly to the target window."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    scan_code = user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
    key_down_lparam = 1 | (scan_code << 16)
    key_up_lparam = key_down_lparam | (1 << 30) | (1 << 31)

    ctypes.set_last_error(0)
    if not user32.PostMessageW(hwnd, WM_KEYDOWN, virtual_key, key_down_lparam):
        return False
    time.sleep(KEY_HOLD_SECONDS)
    if not user32.PostMessageW(hwnd, WM_KEYUP, virtual_key, key_up_lparam):
        return False
    return True


def send_left_click_to_window(hwnd):
    """Post one left click at the center of the target window's client area."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    client_rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
        return False
    width = client_rect.right - client_rect.left
    height = client_rect.bottom - client_rect.top
    if width <= 0 or height <= 0:
        return False

    x = width // 2
    y = height // 2
    mouse_lparam = (y << 16) | x

    ctypes.set_last_error(0)
    if not user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, mouse_lparam):
        return False
    if not user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, mouse_lparam):
        return False
    time.sleep(KEY_HOLD_SECONDS)
    if not user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, mouse_lparam):
        return False
    return True


def is_f12_down():
    """Return True while the global F12 key is physically held down."""
    return bool(user32.GetAsyncKeyState(VK_F12) & 0x8000)


def main():
    print("[后台按键] 每3秒向DD2发送一次主键盘数字0")
    print("[后台按键] 每6秒发送一次数字3，并在每次数字3后2秒发送一次左键")
    print("[后台按键] 按 F12 停止脚本")

    current_hwnd = None
    zero_count = 0
    three_count = 0
    left_click_count = 0
    waiting_logged = False
    now = time.monotonic()
    next_zero_at = now
    next_three_at = now + THREE_INTERVAL_SECONDS
    next_left_click_at = None

    try:
        while True:
            if is_f12_down():
                print("[后台按键] 检测到 F12，脚本已停止")
                break

            now = time.monotonic()
            action_deadlines = [
                ("zero", next_zero_at),
                ("three", next_three_at),
            ]
            if next_left_click_at is not None:
                action_deadlines.append(("left_click", next_left_click_at))
            action, next_action_at = min(
                action_deadlines,
                key=lambda item: item[1],
            )
            if now < next_action_at:
                time.sleep(min(HOTKEY_POLL_SECONDS, next_action_at - now))
                continue

            if action == "zero":
                next_zero_at = now + ZERO_INTERVAL_SECONDS
            elif action == "three":
                next_three_at = now + THREE_INTERVAL_SECONDS
            else:
                next_left_click_at = None

            if not current_hwnd or not user32.IsWindow(current_hwnd):
                current_hwnd = find_dd2_window()
                if not current_hwnd:
                    if not waiting_logged:
                        print("[后台按键] 未找到DD2窗口，持续等待...")
                        waiting_logged = True
                    continue
                print(f"[后台按键] 已找到DD2窗口，句柄={current_hwnd}")
                waiting_logged = False

            send_failed = False
            if action == "zero":
                if send_key_to_window(current_hwnd, VK_0):
                    zero_count += 1
                    if zero_count == 1 or zero_count % 20 == 0:
                        print(f"[后台按键] 已发送 {zero_count} 次数字0")
                else:
                    send_failed = True

            elif action == "three":
                if send_key_to_window(current_hwnd, VK_3):
                    three_count += 1
                    next_left_click_at = (
                        time.monotonic() + THREE_TO_CLICK_DELAY_SECONDS
                    )
                    if three_count == 1 or three_count % 10 == 0:
                        print(f"[后台按键] 已发送 {three_count} 次数字3")
                else:
                    send_failed = True

            else:
                if send_left_click_to_window(current_hwnd):
                    left_click_count += 1
                    if left_click_count == 1 or left_click_count % 10 == 0:
                        print(
                            f"[后台按键] 已在数字3后2秒发送 "
                            f"{left_click_count} 次左键"
                        )
                else:
                    send_failed = True

            if send_failed:
                error_code = ctypes.get_last_error()
                print(
                    f"[后台按键] 发送失败（Windows错误码={error_code}），"
                    "重新查找游戏窗口"
                )
                current_hwnd = None
    except KeyboardInterrupt:
        print("\n[后台按键] 已停止")


if __name__ == "__main__":
    main()
