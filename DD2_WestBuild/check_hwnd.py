import win32gui


def enum_callback(hwnd, windows_list):
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    if "Dungeon Defenders" in title:
        windows_list.append((hwnd, cls, title))


windows = []
win32gui.EnumWindows(enum_callback, windows)
for item in windows:
    print(f"句柄:{item[0]} | 类名:{item[1]} | 窗口标题:{repr(item[2])}")
