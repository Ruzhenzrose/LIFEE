"""
验证索引完整性
"""

import sqlite3
from pathlib import Path

# 知识库目录
knowledge_dir = Path(r"C:\Users\12916\Desktop\项目\LIFEE\lifee\roles\krishnamurti\knowledge")
db_path = Path(r"C:\Users\12916\Desktop\项目\LIFEE\lifee\roles\krishnamurti\knowledge.db")

print("=" * 60)
print("索引完整性验证")
print("=" * 60)

# 统计文件系统中的文件
print("\n【文件系统】")
fs_files = {}
for pattern in ["*.md", "*.txt"]:
    for f in knowledge_dir.rglob(pattern):
        content = f.read_text(encoding="utf-8", errors="ignore")
        fs_files[str(f)] = {
            "name": f.name,
            "chars": len(content),
            "lines": content.count("\n"),
        }

print(f"文件总数: {len(fs_files)}")
total_chars = sum(f["chars"] for f in fs_files.values())
print(f"总字符数: {total_chars:,}")

# 统计数据库中的内容
print("\n【数据库】")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查 files 表
cursor.execute("SELECT COUNT(*) FROM files")
db_file_count = cursor.fetchone()[0]
print(f"已索引文件数: {db_file_count}")

# 检查 chunks 表
cursor.execute("SELECT COUNT(*), SUM(LENGTH(text)) FROM chunks")
chunk_count, db_chars = cursor.fetchone()
print(f"分块数: {chunk_count}")
print(f"总字符数: {db_chars:,}")

# 检查哪些文件已索引
cursor.execute("SELECT path FROM files")
indexed_paths = set(row[0] for row in cursor.fetchall())

# 对比
print("\n【对比结果】")
missing = []
for path, info in fs_files.items():
    if path not in indexed_paths:
        missing.append(info["name"])

if missing:
    print(f"未索引的文件 ({len(missing)}):")
    for name in missing:
        print(f"  - {name}")
else:
    print("所有文件都已索引 ✓")

# 覆盖率
coverage = (db_chars / total_chars * 100) if total_chars > 0 else 0
print(f"\n字符覆盖率: {coverage:.1f}%")
print(f"  (因为分块有重叠，所以可能 > 100%)")

conn.close()
