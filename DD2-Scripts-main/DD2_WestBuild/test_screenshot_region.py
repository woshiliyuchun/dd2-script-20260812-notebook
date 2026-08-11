import time
import win32gui
import win32api
import win32con
import win32ui
import numpy as np
import cv2

GAME_CLASS = "LaunchUnrealUWindowsClient"
GAME_TITLE = "Dungeon Defenders 2"

REGION = (0.6, 0.88, 0.68, 0.91)
TEMPLATE_PATH = r"F:\DD2脚本\replay.png"


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


def load_image(image_path):
    try:
        from PIL import Image
        img = Image.open(image_path).convert('RGB')
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"❌ 加载图片失败: {e}")
        return None


def main():
    print("=" * 60)
    print("  DD2 图像识别测试 (BitBlt版)")
    print("=" * 60)
    print()

    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd == 0:
        print("❌ 找不到游戏窗口")
        return

    print(f"✅ 找到游戏窗口: {hwnd}")
    l, t, w, h = get_window_rect(hwnd)
    cw, ch = get_client_rect(hwnd)
    print(f"窗口位置: ({l}, {t}), 尺寸: {w}x{h}")
    print(f"客户区尺寸: {cw}x{ch}")
    print()

    left = int(REGION[0] * cw)
    top = int(REGION[1] * ch)
    right = int(REGION[2] * cw)
    bottom = int(REGION[3] * ch)
    width = right - left
    height = bottom - top

    print(f"识别区域 (相对): ({REGION[0]:.3f}, {REGION[1]:.3f}) - ({REGION[2]:.3f}, {REGION[3]:.3f})")
    print(f"识别区域 (客户区): ({left}, {top}) - ({right}, {bottom})")
    print(f"识别区域大小: {width}x{height}")
    print()

    template = load_image(TEMPLATE_PATH)
    if template is None:
        print("❌ 无法加载模板图片")
        return
    print(f"模板图片尺寸: {template.shape[1]}x{template.shape[0]}")
    print()

    print("📸 使用BitBlt截取游戏区域...")
    img_bgr = capture_client_region(hwnd, left, top, width, height)

    from PIL import Image
    output_path = r"F:\DD2脚本\region_screenshot.png"
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    Image.fromarray(img_rgb).save(output_path)
    print(f"✅ 截图已保存到: {output_path}")
    print(f"截图尺寸: {img_bgr.shape[1]}x{img_bgr.shape[0]}")
    print()

    print("🔍 开始图像识别...")
    
    if img_bgr.shape[0] < template.shape[0] or img_bgr.shape[1] < template.shape[1]:
        print(f"❌ 截图尺寸小于模板尺寸！")
        print(f"   截图: {img_bgr.shape[1]}x{img_bgr.shape[0]}")
        print(f"   模板: {template.shape[1]}x{template.shape[0]}")
        return

    result = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    print(f"相似度: {max_val:.4f}")
    print(f"阈值: 0.8")

    if max_val >= 0.8:
        th, tw = template.shape[:2]
        center_x = left + max_loc[0] + tw // 2
        center_y = top + max_loc[1] + th // 2
        print(f"✅ 找到匹配！位置: ({center_x}, {center_y})")
    else:
        print("❌ 未找到匹配")
        print("")
        print("💡 建议：将当前截图保存为模板图片")
        print(f"   复制 {output_path} 覆盖 {r'F:\DD2脚本\replay.png'}")
        print("   这样模板和截图颜色一致，就能识别成功！")

    print()
    print("测试完成")


if __name__ == "__main__":
    main()