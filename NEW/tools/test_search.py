"""
测试搜索功能（不重新索引）
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lifee.memory import MemoryManager
from lifee.memory.embeddings import create_embedding_provider
from lifee.config.settings import settings


async def main():
    print("=" * 50)
    print("知识库搜索测试")
    print("=" * 50)

    # 创建嵌入提供商
    embedding = create_embedding_provider(
        google_api_key=settings.google_api_key,
    )

    # 打开已有的数据库
    db_path = Path(__file__).parent.parent / "lifee" / "roles" / "krishnamurti" / "knowledge.db"
    print(f"\n数据库: {db_path}")
    print(f"大小: {db_path.stat().st_size / 1024 / 1024:.1f} MB")

    manager = MemoryManager(db_path, embedding)

    # 显示统计
    stats = manager.get_stats()
    print(f"\n知识库统计:")
    print(f"  文件数: {stats['file_count']}")
    print(f"  分块数: {stats['chunk_count']}")

    if stats['chunk_count'] == 0:
        print("\n知识库为空，需要先索引")
        manager.close()
        return

    # 测试搜索
    test_queries = [
        "什么是冥想？",
        "如何面对恐惧？",
        "爱是什么？",
    ]

    print("\n" + "=" * 50)
    print("搜索测试")
    print("=" * 50)

    for query in test_queries:
        print(f"\n查询: {query}")
        print("-" * 40)

        results = await manager.search(query, max_results=2, min_score=0.3)

        if not results:
            print("  没有找到相关内容")
        else:
            for i, r in enumerate(results, 1):
                filename = Path(r.path).name
                # 处理特殊字符
                preview = r.text[:120].replace("\n", " ").replace("\xa0", " ")
                try:
                    print(f"  [{i}] {filename} (分数: {r.score:.2f})")
                    print(f"      {preview}...")
                except UnicodeEncodeError:
                    print(f"  [{i}] {filename} (分数: {r.score:.2f})")
                    print(f"      [内容包含特殊字符]")

    manager.close()
    print("\n测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
