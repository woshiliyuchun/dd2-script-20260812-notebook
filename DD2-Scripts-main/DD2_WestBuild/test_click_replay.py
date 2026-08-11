import time
import win32gui
import pyautogui

GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"

REPLAY_REGION = (0.6, 0.88, 0.68, 0.91)


def main():
    print("=" * 60)
    print("  DD2 replay按钮点击测试")
    print("=" * 60)
    print()

    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd == 0:
        print("❌ 找不到游戏窗口")
        return

    print(f"✅ 找到游戏窗口: {hwnd}")
    
    rect = win32gui.GetWindowRect(hwnd)
    l, t, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
    
    client_rect = win32gui.GetClientRect(hwnd)
    cw, ch = client_rect[2], client_rect[3]
    
    print(f"窗口位置: ({l}, {t}), 尺寸: {w}x{h}")
    print(f"客户区尺寸: {cw}x{ch}")
    print()

    rel_x = (REPLAY_REGION[0] + REPLAY_REGION[2]) / 2
    rel_y = (REPLAY_REGION[1] + REPLAY_REGION[3]) / 2
    
    client_x = int(rel_x * cw)
    client_y = int(rel_y * ch)
    
    screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    
    print(f"replay区域: {REPLAY_REGION}")
    print(f"区域中心相对坐标: ({rel_x:.3f}, {rel_y:.3f})")
    print(f"客户区坐标: ({client_x}, {client_y})")
    print(f"屏幕坐标: ({screen_x}, {screen_y})")
    print()

    print("倒计时 3 秒，请确保游戏窗口在前台...")
    for i in range(3, 0, -1):
        print(f"   {i}...")
        time.sleep(1)

    print()
    print("移动鼠标并点击...")
    pyautogui.moveTo(screen_x, screen_y)
    time.sleep(1.0)
    pyautogui.click()
    
    print()
    print("✅ 测试完成")


if __name__ == "__main__":
    main()