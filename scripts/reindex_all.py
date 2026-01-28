"""
重新索引所有知识库文件（显示进度）
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lifee.memory import MemoryManager
from lifee.memory.embeddings import create_embedding_provider
from lifee.config.settings import settings


async def main():
    print("=" * 60)
    print("重新索引知识库")
    print("=" * 60)

    knowledge_dir = Path(__file__).parent.parent / "lifee" / "roles" / "krishnamurti" / "knowledge"
    db_path = Path(__file__).parent.parent / "lifee" / "roles" / "krishnamurti" / "knowledge.db"

    # 收集所有文件
    files = list(knowledge_dir.rglob("*.md")) + list(knowledge_dir.rglob("*.txt"))
    print(f"\n找到 {len(files)} 个文件")

    # 创建嵌入提供商
    print("\n初始化嵌入提供商...")
    embedding = create_embedding_provider(google_api_key=settings.google_api_key)

    # 创建管理器
    manager = MemoryManager(db_path, embedding)

    # 逐个索引文件
    print("\n开始索引...\n")
    total_chunks = 0

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {file_path.name}...", end=" ", flush=True)
        try:
            chunks = await manager.index_file(file_path, force=True)
            total_chunks += chunks
            print(f"{chunks} 个分块")
        except Exception as e:
            print(f"错误: {e}")

    print(f"\n完成！总共 {total_chunks} 个分块")

    # 验证
    stats = manager.get_stats()
    print(f"\n最终统计:")
    print(f"  文件数: {stats['file_count']}")
    print(f"  分块数: {stats['chunk_count']}")

    manager.close()


if __name__ == "__main__":
    asyncio.run(main())
