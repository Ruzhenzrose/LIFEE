"""
修复原文目录中文件名过长的文件
"""

from pathlib import Path
import shutil

source_dir = Path(r"C:\Users\12916\Desktop\项目\LIFEE\lifee\roles\krishnamurti\原文")

# 需要重命名的文件映射
rename_map = {
    "活出自在": "活出自在.pdf",
    "人生中不可不想的事": "人生中不可不想的事.pdf",
}

print("扫描目录中的文件...\n")

for file in source_dir.iterdir():
    name = file.name
    for key, new_name in rename_map.items():
        if key in name:
            new_path = source_dir / new_name
            print(f"发现: {name[:60]}...")
            print(f"重命名为: {new_name}")
            try:
                file.rename(new_path)
                print("[OK] 成功\n")
            except Exception as e:
                print(f"[FAIL] 失败: {e}\n")
            break

print("\n完成！当前目录文件：")
for f in sorted(source_dir.iterdir()):
    print(f"  {f.name}")
