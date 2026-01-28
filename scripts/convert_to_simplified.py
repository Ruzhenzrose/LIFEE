"""
将繁体中文书籍转换为简体中文
"""

from pathlib import Path
from opencc import OpenCC

# 繁体转简体
cc = OpenCC('t2s')

books_dir = Path(r"C:\Users\12916\Desktop\项目\LIFEE\lifee\roles\krishnamurti\knowledge\books")

# 需要转换的繁体书籍
traditional_books = [
    "《般若之旅》.txt",
    "《心靈自由之路》.txt",
    "《重新認識你自己》.txt",
    "謀生之道.txt",
    "心智大師的對話.txt",
    "智慧的覺醒.txt",
    "轉變的緊迫性.txt",
    "最後的演講.txt",
]

print("开始繁简转换...\n")

for filename in traditional_books:
    file_path = books_dir / filename
    if not file_path.exists():
        print(f"跳过: {filename} (不存在)")
        continue

    print(f"处理: {filename}")

    # 读取内容
    content = file_path.read_text(encoding='utf-8')

    # 转换内容
    simplified_content = cc.convert(content)

    # 转换文件名
    simplified_name = cc.convert(filename)
    new_path = books_dir / simplified_name

    # 写入新文件
    new_path.write_text(simplified_content, encoding='utf-8')

    # 删除旧文件（如果文件名不同）
    if filename != simplified_name:
        file_path.unlink()
        print(f"  -> {simplified_name}")
    else:
        print(f"  -> 内容已转换")

print("\n完成！当前文件：")
for f in sorted(books_dir.iterdir()):
    print(f"  {f.name}")
