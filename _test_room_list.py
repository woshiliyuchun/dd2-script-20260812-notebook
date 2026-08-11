# -*- coding: utf-8 -*-
"""
测试脚本：检测当前 DD2 游戏画面房间列表中的 Floor 数字有几个。
运行方法：
  1. 先手动把游戏打开到房间列表界面（Onslaught Session Browser，能看到 Floor 列数字）
  2. 运行本脚本，会自动聚焦游戏窗口并截图识别
  3. 测试图全部输出到 D:\\DD2脚本\\_test_output\\ 文件夹

核心思路：
- 裁剪区域与参考脚本一致：X:30%-98%, Y:18%-72%（保留标题，ocr_room_list_numbers 内部跳过 Y:5% 标题区）
- 直接调用主脚本的 ocr_room_list_numbers 函数，确保逻辑完全一致
"""
import sys
import os
import time
import shutil
import win32gui

# 确保能导入主脚本
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dd2onslaught"))

from dd2onslaught.dd2_war_table_walk import (
    CONFIG,
    capture_game_window,
    focus_game_window,
    ocr_room_list_numbers,
)
import cv2
import numpy as np

OUTPUT_DIR = r"D:\DD2脚本\_test_output"


def clean_output_dir():
    for attempt in range(5):
        try:
            if os.path.exists(OUTPUT_DIR):
                shutil.rmtree(OUTPUT_DIR)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            print(f"[INFO] 测试输出目录已清空: {OUTPUT_DIR}")
            return
        except PermissionError:
            print(f"[WARN] 文件被占用，重试 {attempt+1}/5...")
            time.sleep(1)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_img(name, img):
    p = os.path.join(OUTPUT_DIR, name)
    ext = os.path.splitext(name)[1] or ".png"
    try:
        ok, buf = cv2.imencode(ext, img)
        if ok:
            with open(p, "wb") as f:
                f.write(buf.tobytes())
            return True
    except Exception as e:
        print(f"   保存失败 {name}: {e}")
    return False


def main():
    print("=" * 70)
    print("[TEST] 房间列表 Floor 数字检测测试（主脚本ocr_room_list_numbers）")
    print("=" * 70)

    clean_output_dir()

    # ===== 1. 找游戏窗口 =====
    print("[INFO] 正在查找游戏窗口...")
    hwnd = win32gui.FindWindow(CONFIG["game_class"], CONFIG["game_title"])
    if not hwnd:
        print("[ERROR] 未找到 DD2 游戏窗口，请先启动游戏并进入房间列表界面")
        return 1
    print(f"[INFO] 找到游戏窗口，句柄={hwnd}")

    # ===== 2. 聚焦游戏窗口 =====
    print("[INFO] 聚焦游戏窗口并等待 3 秒让画面稳定...")
    try:
        focus_game_window(hwnd)
        print(f"[INFO] 已聚焦游戏窗口，句柄={hwnd}")
    except Exception as e:
        print(f"[WARN] focus_game_window 异常: {e}")
    time.sleep(3)

    # ===== 3. 截图 =====
    frame = capture_game_window(hwnd)
    if frame is None or frame.size == 0:
        print("[ERROR] 截图失败")
        return 1
    h, w = frame.shape[:2]
    print(f"[INFO] 截图尺寸: {w}x{h}")
    save_img("01_full_frame.png", frame)

    # ===== 4. 与参考脚本相同的裁剪区域 =====
    # 参考脚本：X:30%-98%, Y:22%-80%
    x0 = int(w * 0.30)
    y0 = int(h * 0.22)
    x1 = int(w * 0.98)
    y1 = int(h * 0.80)
    crop = frame[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    print(f"[INFO] 裁剪区域: 帧内X[{x0},{x1}] Y[{y0},{y1}] → {cw}x{ch}")
    save_img("02_room_list_crop.png", crop)

    # 画列参考线（Floor 70%-80%，Score 85%-92%）
    vis = crop.copy()
    fl_x0, fl_x1 = int(cw * 0.70), int(cw * 0.80)
    sc_x0, sc_x1 = int(cw * 0.85), int(cw * 0.92)
    cv2.rectangle(vis, (fl_x0, 0), (fl_x1, ch), (0, 0, 255), 2)
    cv2.rectangle(vis, (sc_x0, 0), (sc_x1, ch), (0, 255, 0), 2)
    cv2.putText(vis, "FLOOR (70%-80%)", (fl_x0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    cv2.putText(vis, "SCORE (85%-92%)", (sc_x0, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    # Y 轴数据区：22%-80%
    y_top = int(ch * 0.22)
    y_bot = int(ch * 0.80)
    cv2.line(vis, (0, y_top), (cw, y_top), (255, 0, 0), 2)
    cv2.putText(vis, "Y=22% START", (5, y_top + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
    cv2.line(vis, (0, y_bot), (cw, y_bot), (255, 0, 0), 2)
    cv2.putText(vis, "Y=80% END", (5, y_bot - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
    save_img("03_columns_overlay.png", vis)

    # ===== 5. 直接调用主脚本的 OCR 函数 =====
    print("-" * 60)
    print("[INFO] 调用 ocr_room_list_numbers(crop)...")
    result = ocr_room_list_numbers(crop)

    floors = result.get("floors", [])
    scores = result.get("scores", [])

    # ===== 6. 可视化：在裁剪图上标注识别到的 Floor =====
    vis2 = crop.copy()
    for f_val, f_left, f_top, f_width, f_height, f_conf in floors:
        cv2.rectangle(vis2, (f_left, f_top), (f_left + f_width, f_top + f_height), (0, 0, 255), 2)
        cv2.putText(vis2, str(f_val), (f_left, f_top - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
    for s_val, s_top in scores:
        # Score 列位置（85%-92%）
        sc_x0_v = int(cw * 0.85)
        cv2.putText(vis2, str(s_val), (sc_x0_v, s_top + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    save_img("04_floors_overlay.png", vis2)

    # ===== 7. 最终结果 =====
    print("=" * 70)
    print(f"[FINAL] 识别到 Floor 数量: {len(floors)}")
    print(f"[FINAL] Floor 值列表: {[f[0] for f in floors]}")
    print(f"[FINAL] Score 值列表: {[s[0] for s in scores]}")
    print(f"[INFO] 所有测试图片已保存到: {OUTPUT_DIR}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
