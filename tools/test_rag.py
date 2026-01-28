"""
测试 RAG 知识库功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from lifee.roles import RoleManager
from lifee.config.settings import settings


async def main():
    print("=" * 50)
    print("RAG 知识库测试")
    print("=" * 50)

    role_manager = RoleManager()

    # 检查角色信息
    info = role_manager.get_role_info("krishnamurti")
    print(f"\n角色: krishnamurti")
    print(f"显示名: {info.get('display_name')}")
    print(f"有知识库: {info.get('has_knowledge')}")

    # 初始化知识库
    print("\n正在初始化知识库（首次需要生成嵌入向量，可能需要 1-2 分钟）...")

    try:
        manager = await role_manager.get_knowledge_manager(
            "krishnamurti",
            google_api_key=settings.google_api_key,
            openai_api_key=getattr(settings, 'openai_api_key', None),
        )
    except Exception as e:
        print(f"\n错误: {e}")
        print("\n请确保已配置 GOOGLE_API_KEY（用于生成嵌入向量）")
        return

    if not manager:
        print("\n错误: 无法初始化知识库")
        print("请确保已配置 GOOGLE_API_KEY")
        return

    # 显示统计
    stats = manager.get_stats()
    print(f"\n知识库统计:")
    print(f"  文件数: {stats['file_count']}")
    print(f"  分块数: {stats['chunk_count']}")
    print(f"  嵌入模型: {stats['embedding_provider']}/{stats['embedding_model']}")

    # 测试搜索
    test_queries = [
        "什么是冥想？",
        "如何面对恐惧？",
        "爱是什么？",
        "思想的本质",
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
                preview = r.text[:150].replace("\n", " ")
                print(f"  [{i}] {filename} (分数: {r.score:.2f})")
                print(f"      {preview}...")

    manager.close()
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
