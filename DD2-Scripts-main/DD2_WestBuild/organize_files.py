import os
import shutil

# 源目录
source_dir = r"F:\DD2脚本\DD2_WestBuild"
root_dir = r"F:\DD2脚本"

# 目标目录
target_dir = os.path.join(root_dir, "DD2西方世界挂机脚本")

# 创建目标目录
os.makedirs(target_dir, exist_ok=True)

# 需要移动的文件
files_to_move = [
    # 主脚本
    "dd2_full.py",
    # 测试脚本
    "test_click_replay.py",
    "test_extra_reward.py",
    "test_failure_replay.py",
    "test_screenshot_region.py",
    "test_sell_equipment.py",
    # 模板图片
    "replay.bmp",
    "失败重来.bmp", 
    "额外奖励.bmp",
    # 配置检查
    "check_hwnd.py"
]

# 从 DD2_WestBuild 移动文件
for filename in files_to_move:
    src = os.path.join(source_dir, filename)
    if os.path.exists(src):
        dst = os.path.join(target_dir, filename)
        shutil.copy2(src, dst)
        print(f"✅ 复制: {filename}")
    else:
        print(f"⚠️ 不存在: {filename}")

# 从根目录移动 PNG 模板图片
png_files = ["replay.png", "失败重来.png", "额外奖励.png"]
for filename in png_files:
    src = os.path.join(root_dir, filename)
    if os.path.exists(src):
        dst = os.path.join(target_dir, filename)
        shutil.copy2(src, dst)
        print(f"✅ 复制: {filename}")

print(f"\n🎉 完成！所有文件已复制到: {target_dir}")