# -*- coding: utf-8 -*-
"""
测试 _scan_right_panel_room_name() 修改后的 difficulty 区域识别逻辑

测试策略：
1. 合成一张"模拟游戏画面"（默认 2560x1440，模拟 2K 游戏窗口）
2. 把真实的 chaos91011room.png 模板贴到画面对应的 difficulty 区域位置
   （模板中心位置在 frame 中 X: 30%+55%*(98%-30%) 到 30%+82%*(98%-30%) 范围内，
    即 frame X 约 67.4%-85.76%）
3. 通过 monkey-patch 替换主脚本里的 find_game_window / capture_game_window，
   让 _scan_right_panel_room_name 使用合成画面
4. 调用 _scan_right_panel_room_name，看能否匹配成功，并打印诊断信息

用法：
    python test_difficulty_region_match.py
    python test_difficulty_region_match.py --w 1920 --h 1080     # 模拟 1K
    python test_difficulty_region_match.py --real-shot "D:/xxx/gameshot.png"
                                                                # 用真实游戏截图代替合成画面
    python test_difficulty_region_match.py --save-debug          # 额外保存合成画面+裁剪区域到磁盘
"""

import os
import sys
import argparse
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(r"d:\DD2脚本\dd2onslaught")
sys.path.insert(0, str(SCRIPT_DIR))

import dd2_war_table_walk as main_mod
from dd2_war_table_walk import CONFIG, load_template

TEMPLATE_PATH = CONFIG["chaos91011_room_template"]


# ====================================================================
# 模拟画面的合成
# ====================================================================

def _calc_difficulty_region_in_frame(w, h):
    """根据主脚本的计算公式，返回 difficulty 搜索区域在 frame 中的绝对坐标范围。
    与 _scan_right_panel_room_name 中的公式完全一致。
    """
    crop_x0 = int(w * 0.30)
    crop_y0 = int(h * 0.22)
    crop_x1 = int(w * 0.98)
    crop_y1 = int(h * 0.80)
    crop_w = crop_x1 - crop_x0
    diff_x0_in_crop = int(crop_w * 0.55)
    diff_x1_in_crop = int(crop_w * 0.82)
    diff_x0 = crop_x0 + diff_x0_in_crop
    diff_x1 = crop_x0 + diff_x1_in_crop
    return {
        "crop": (crop_x0, crop_y0, crop_x1, crop_y1),
        "diff_in_frame": (diff_x0, crop_y0, diff_x1, crop_y1),
        "diff_in_crop": (diff_x0_in_crop, 0, diff_x1_in_crop, crop_y1 - crop_y0),
    }


def build_synthetic_frame(w, h, template_bgr, save_debug=False, debug_dir=None):
    """合成一张 w x h 的"游戏画面"，把 template 贴到 difficulty 区域中央。
    返回合成画面 (h, w, 3) BGR。
    """
    regions = _calc_difficulty_region_in_frame(w, h)
    diff_x0, diff_y0, diff_x1, diff_y1 = regions["diff_in_frame"]
    diff_w = diff_x1 - diff_x0
    diff_h = diff_y1 - diff_y0

    th, tw = template_bgr.shape[:2]
    if diff_w < tw or diff_h < th:
        raise ValueError(
            f"difficulty 区域 ({diff_w}x{diff_h}) 比模板 ({tw}x{th}) 小，无法贴入"
        )

    # 创建灰色背景（避免纯黑导致 matchTemplate 分母为 0）
    frame = np.full((h, w, 3), 40, dtype=np.uint8)

    # 在 difficulty 区域中央贴模板
    paste_x = diff_x0 + (diff_w - tw) // 2
    paste_y = diff_y0 + (diff_h - th) // 2
    frame[paste_y:paste_y + th, paste_x:paste_x + tw] = template_bgr

    # 画 difficulty 区域边框（方便人眼查看）
    cv2.rectangle(frame, (diff_x0, diff_y0), (diff_x1, diff_y1), (0, 255, 0), 2)
    cv2.putText(frame, "difficulty region", (diff_x0 + 5, diff_y0 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

    # 画整体裁剪区域边框
    cx0, cy0, cx1, cy1 = regions["crop"]
    cv2.rectangle(frame, (cx0, cy0), (cx1, cy1), (255, 255, 0), 1)
    cv2.putText(frame, "crop region", (cx0 + 5, cy0 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)

    # 画模板贴入位置（红色框）
    cv2.rectangle(frame, (paste_x, paste_y), (paste_x + tw, paste_y + th), (0, 0, 255), 2)
    cv2.putText(frame, "template", (paste_x, paste_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    print(f"[合成] 画面尺寸: {w}x{h}")
    print(f"[合成] 整体裁剪区域 (X:30%-98%, Y:22%-80%): "
          f"({cx0},{cy0})-({cx1},{cy1}) size={cx1-cx0}x{cy1-cy0}")
    print(f"[合成] difficulty 区域 (裁剪区域内 X:55%-82%): "
          f"({diff_x0},{diff_y0})-({diff_x1},{diff_y1}) size={diff_w}x{diff_h}")
    print(f"[合成] 模板尺寸: {tw}x{th}")
    print(f"[合成] 模板贴入位置: ({paste_x},{paste_y})，中心=({paste_x+tw//2},{paste_y+th//2})")

    if save_debug and debug_dir:
        debug_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(debug_dir / "synthetic_frame.png"), frame)
        # 也保存只裁剪到 difficulty 区域的图
        cv2.imwrite(str(debug_dir / "difficulty_crop.png"),
                    frame[diff_y0:diff_y1, diff_x0:diff_x1])
        print(f"[调试] 已保存合成画面到 {debug_dir / 'synthetic_frame.png'}")
        print(f"[调试] 已保存 difficulty 区域裁剪到 {debug_dir / 'difficulty_crop.png'}")

    return frame


# ====================================================================
# monkey-patch 主脚本函数
# ====================================================================

def patch_capture_with_frame(frame):
    """把主脚本的 find_game_window / capture_game_window 替换为返回合成画面的版本"""
    fake_hwnd = 0xDEAD

    def fake_find_game_window():
        return fake_hwnd

    def fake_capture_game_window(hwnd):
        return frame.copy()

    main_mod.find_game_window = fake_find_game_window
    main_mod.capture_game_window = fake_capture_game_window
    print(f"[Patch] find_game_window / capture_game_window 已替换为合成画面版本")


# ====================================================================
# 主流程
# ====================================================================

def run_test(frame, save_debug=False, debug_dir=None):
    """对给定 frame 运行 _scan_right_panel_room_name，打印结果"""
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

        # 验证坐标是否在 difficulty 区域内
        h, w = frame.shape[:2]
        regions = _calc_difficulty_region_in_frame(w, h)
        dx0, dy0, dx1, dy1 = regions["diff_in_frame"]
        in_region = (dx0 <= fx <= dx1) and (dy0 <= fy <= dy1)
        print(f"       difficulty 区域 = ({dx0},{dy0})-({dx1},{dy1})")
        print(f"       匹配点在 difficulty 区域内？ {in_region}")
        if not in_region:
            print(f"       ⚠️  匹配点不在 difficulty 区域内，逻辑有误！")
    else:
        print(f"[结果] ❌ 未匹配到 chaos91011room")
        print(f"       请检查 difficulty 区域参数 / 模板 / 合成画面")

    if save_debug and debug_dir:
        # 保存主脚本内部的 crop 区域（模拟 _scan_right_panel_room_name 的裁剪）
        h, w = frame.shape[:2]
        crop_x0 = int(w * 0.30)
        crop_y0 = int(h * 0.22)
        crop_x1 = int(w * 0.98)
        crop_y1 = int(h * 0.80)
        crop = frame[crop_y0:crop_y1, crop_x0:crop_x1]
        crop_w = crop.shape[1]
        diff_x0 = int(crop_w * 0.55)
        diff_x1 = int(crop_w * 0.82)
        search = crop[:, diff_x0:diff_x1]
        cv2.imwrite(str(debug_dir / "main_script_search_region.png"), search)
        print(f"[调试] 已保存主脚本搜索区域到 {debug_dir / 'main_script_search_region.png'}")


def main():
    parser = argparse.ArgumentParser(description="测试 difficulty 区域识别逻辑")
    parser.add_argument("--w", type=int, default=2560, help="合成画面宽度（默认 2560，2K）")
    parser.add_argument("--h", type=int, default=1440, help="合成画面高度（默认 1440，2K）")
    parser.add_argument("--real-shot", type=str, default=None,
                        help="使用真实游戏截图代替合成画面（路径）")
    parser.add_argument("--save-debug", action="store_true",
                        help="保存合成画面+裁剪区域到磁盘")
    args = parser.parse_args()

    debug_dir = Path(r"d:\DD2脚本\_debug_difficulty_test")

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
