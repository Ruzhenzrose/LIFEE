"""
展示分块详情
"""

import sqlite3
from pathlib import Path

db_path = Path(r"C:\Users\12916\Desktop\项目\LIFEE\lifee\roles\krishnamurti\knowledge.db")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 统计每个文件的分块数
print("=" * 60)
print("各文件分块统计")
print("=" * 60)

cursor.execute("""
    SELECT path, COUNT(*) as chunk_count
    FROM chunks
    GROUP BY path
    ORDER BY chunk_count DESC
""")

for path, count in cursor.fetchall():
    filename = Path(path).name
    print(f"  {filename}: {count} 个分块")

# 展示一个分块示例
print("\n" + "=" * 60)
print("分块示例（来自《重新认识你自己》）")
print("=" * 60)

cursor.execute("""
    SELECT text, start_line, end_line
    FROM chunks
    WHERE path LIKE '%重新认识你自己%'
    LIMIT 3
""")

for i, (text, start, end) in enumerate(cursor.fetchall(), 1):
    print(f"\n[分块 {i}] 行 {start}-{end}")
    print("-" * 40)
    # 只显示前 200 字符
    preview = text[:300].replace("\n", "\n  ")
    print(f"  {preview}...")

conn.close()
