# -*- coding: utf-8 -*-
"""
测试 _scan_right_panel_room_name() 修改后的「房间列表大裁剪区」识别逻辑

新逻辑：
  不再在裁剪内的 difficulty 子区域搜索，而是直接使用整个大裁剪区
  Frame X:30%-98%, Y:22%-80%（与 get_target_room_floor 的整体裁剪完全一致）。

测试策略：
1. 合成一张"模拟游戏画面"（默认 2560x1440，模拟 2K 游戏窗口）
2. 把真实的 chaos91011room.png 模板贴到大裁剪区内的随机位置
3. 通过 monkey-patch 替换主脚本里的 find_game_window / capture_game_window，
   让 _scan_right_panel_room_name 使用合成画面
4. 调用 _scan_right_panel_room_name，看能否匹配成功，并打印诊断信息

用法：
    python test_right_panel_region_match.py
    python test_right_panel_region_match.py --w 1920 --h 1080
    python test_right_panel_region_match.py --real-shot "D:/path/to/gameshot.png"
    python test_right_panel_region_match.py --save-debug
"""

import os
import sys
import random
import argparse
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(r"d:\DD2脚本\dd2onslaught")
sys.path.insert(0, str(SCRIPT_DIR))

import dd2_war_table_walk as main_mod
from dd2_war_table_walk import CONFIG, load_template

TEMPLATE_PATH = CONFIG["chaos91011_room_template"]


def _calc_search_region_in_frame(w, h):
    """根据主脚本新公式，返回搜索区域（即整体裁剪，不再有 difficulty 子区域）。
    与 _scan_right_panel_room_name 保持完全一致：
      crop = frame[22%-80% Y, 30%-98% X]
    """
    crop_x0 = int(w * 0.30)
    crop_y0 = int(h * 0.22)
    crop_x1 = int(w * 0.98)
    crop_y1 = int(h * 0.80)
    return {
        "search": (crop_x0, crop_y0, crop_x1, crop_y1),
    }


def build_synthetic_frame(w, h, template_bgr, paste_pos=None, save_debug=False, debug_dir=None):
    """合成一张 w x h 的"游戏画面"，把模板贴到大裁剪搜索区内的指定位置（不指定则在搜索区随机）。"""
    regions = _calc_search_region_in_frame(w, h)
    sx0, sy0, sx1, sy1 = regions["search"]
    search_w = sx1 - sx0
    search_h = sy1 - sy0

    th, tw = template_bgr.shape[:2]
    if search_w < tw or search_h < th:
        raise ValueError(
            f"搜索区 ({search_w}x{search_h}) 比模板 ({tw}x{th}) 小，无法贴入"
        )

    frame = np.full((h, w, 3), 40, dtype=np.uint8)

    if paste_pos:
        paste_x, paste_y = paste_pos
    else:
        paste_x = random.randint(sx0, sx1 - tw)
        paste_y = random.randint(sy0, sy1 - th)

    frame[paste_y:paste_y + th, paste_x:paste_x + tw] = template_bgr

    # 画搜索区边框（绿框）
    cv2.rectangle(frame, (sx0, sy0), (sx1, sy1), (0, 255, 0), 2)
    cv2.putText(frame, "search region (X30%-98%, Y22%-80%)",
                (sx0 + 5, sy0 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)

    # 画模板贴入位置（红框）
    cv2.rectangle(frame, (paste_x, paste_y), (paste_x + tw, paste_y + th), (0, 0, 255), 2)
    cv2.putText(frame, "template", (paste_x, paste_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    print(f"[合成] 画面尺寸: {w}x{h}")
    print(f"[合成] 搜索区 (Frame X:30%-98%, Y:22%-80%): "
          f"({sx0},{sy0})-({sx1},{sy1}) size={search_w}x{search_h}")
    print(f"[合成] 模板尺寸: {tw}x{th}")
    print(f"[合成] 模板贴入位置: ({paste_x},{paste_y})，中心=({paste_x+tw//2},{paste_y+th//2})")

    if save_debug and debug_dir:
        debug_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(debug_dir / "synthetic_frame.png"), frame)
        cv2.imwrite(str(debug_dir / "search_region.png"),
                    frame[sy0:sy1, sx0:sx1])
        print(f"[调试] 已保存合成画面到 {debug_dir / 'synthetic_frame.png'}")
        print(f"[调试] 已保存搜索区裁剪到 {debug_dir / 'search_region.png'}")

    return frame


def patch_capture_with_frame(frame):
    fake_hwnd = 0xDEAD

    def fake_find_game_window():
        return fake_hwnd

    def fake_capture_game_window(hwnd):
        return frame.copy()

    main_mod.find_game_window = fake_find_game_window
    main_mod.capture_game_window = fake_capture_game_window
    print(f"[Patch] find_game_window / capture_game_window 已替换为合成画面版本")


def run_test(frame, save_debug=False, debug_dir=None):
    patch_capture_with_frame(frame)

    print("\n" + "=" * 60)
    print("调用主脚本 _scan_right_panel_room_name()")
    print("=" * 60)
    print(f"主脚本阈值 match_threshold = {CONFIG['match_threshold']}")
    print(f"模板路径 = {TEMPLATE_PATH}")
    print("-" * 60)

    has_room, center_frame = main_mod._scan_right_panel_room_name()

    print("-" * 60)
    if has_room:
        fx, fy, conf = center_frame
        print(f"[结果] ✅ 匹配成功！")
        print(f"       帧坐标中心 = ({fx}, {fy})")
        print(f"       置信度     = {conf:.4f}")
        print(f"       置信度 >= 阈值 {CONFIG['match_threshold']}？ {conf >= CONFIG['match_threshold']}")

        h, w = frame.shape[:2]
        regions = _calc_search_region_in_frame(w, h)
        sx0, sy0, sx1, sy1 = regions["search"]
        in_region = (sx0 <= fx <= sx1) and (sy0 <= fy <= sy1)
        print(f"       搜索区 = ({sx0},{sy0})-({sx1},{sy1})")
        print(f"       匹配点在搜索区内？ {in_region}")
    else:
        print(f"[结果] ❌ 未匹配到 chaos91011room")

    if save_debug and debug_dir:
        h, w = frame.shape[:2]
        regions = _calc_search_region_in_frame(w, h)
        sx0, sy0, sx1, sy1 = regions["search"]
        search = frame[sy0:sy1, sx0:sx1]
        cv2.imwrite(str(debug_dir / "main_script_search_region.png"), search)
        print(f"[调试] 主脚本搜索区域已保存到 {debug_dir / 'main_script_search_region.png'}（与合成搜索区应完全一致）")


def main():
    parser = argparse.ArgumentParser(description="测试右侧面板大裁剪区识别逻辑")
    parser.add_argument("--w", type=int, default=2560, help="合成画面宽度（默认 2560）")
    parser.add_argument("--h", type=int, default=1440, help="合成画面高度（默认 1440）")
    parser.add_argument("--real-shot", type=str, default=None, help="使用真实游戏截图代替合成画面")
    parser.add_argument("--save-debug", action="store_true", help="保存调试图片")
    args = parser.parse_args()

    debug_dir = Path(r"d:\DD2脚本\_debug_right_panel_test")

    if not os.path.exists(TEMPLATE_PATH):
        print(f"[错误] 模板不存在: {TEMPLATE_PATH}")
        sys.exit(1)

    template_bgr = load_template(TEMPLATE_PATH)
    print(f"[加载] 模板加载成功: {TEMPLATE_PATH} shape={template_bgr.shape}")

    if args.real_shot:
        if not os.path.exists(args.real_shot):
            print(f"[错误] 真实截图不存在: {args.real_shot}")
            sys.exit(1)
        print(f"[加载] 使用真实游戏截图: {args.real_shot}")
        frame = cv2.imdecode(np.fromfile(args.real_shot, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            print(f"[错误] 截图读取失败")
            sys.exit(1)
        print(f"[加载] 截图尺寸: {frame.shape[1]}x{frame.shape[0]}")
    else:
        print(f"\n[合成] 开始合成 {args.w}x{args.h} 模拟游戏画面...")
        frame = build_synthetic_frame(args.w, args.h, template_bgr,
                                       save_debug=args.save_debug, debug_dir=debug_dir)

    run_test(frame, save_debug=args.save_debug, debug_dir=debug_dir)


if __name__ == "__main__":
    main()
