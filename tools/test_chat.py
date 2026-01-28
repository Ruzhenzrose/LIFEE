"""
测试完整对话流程（含 RAG）
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lifee.config.settings import settings
from lifee.roles import RoleManager
from lifee.providers import GeminiProvider, Message, MessageRole
from lifee.memory import format_search_results


async def main():
    print("=" * 60)
    print("LIFEE 对话测试（克里希那穆提角色 + RAG）")
    print("=" * 60)

    # 初始化
    role_manager = RoleManager()

    # 加载角色
    print("\n1. 加载角色...")
    role_prompt = role_manager.load_role("krishnamurti")
    if role_prompt:
        print(f"   角色提示词: {len(role_prompt)} 字符")
    else:
        print("   错误: 无法加载角色")
        return

    # 加载知识库
    print("\n2. 加载知识库...")
    knowledge_manager = await role_manager.get_knowledge_manager(
        "krishnamurti",
        google_api_key=settings.google_api_key,
    )
    if knowledge_manager:
        stats = knowledge_manager.get_stats()
        print(f"   文件数: {stats['file_count']}")
        print(f"   分块数: {stats['chunk_count']}")
    else:
        print("   错误: 无法加载知识库")
        return

    # 创建 Provider
    print("\n3. 创建 LLM Provider...")
    provider = GeminiProvider(
        api_key=settings.google_api_key,
        model="gemini-2.0-flash",
    )
    print(f"   Provider: {provider.name}")
    print(f"   Model: {provider.model}")

    # 测试问题
    test_question = "什么是冥想？冥想的本质是什么？"

    print(f"\n4. 搜索相关知识...")
    print(f"   问题: {test_question}")

    search_results = await knowledge_manager.search(
        test_question,
        max_results=3,
        min_score=0.35,
    )

    if search_results:
        print(f"   找到 {len(search_results)} 条相关内容:")
        for i, r in enumerate(search_results, 1):
            filename = Path(r.path).name
            print(f"   [{i}] {filename} (分数: {r.score:.2f})")

        knowledge_context = format_search_results(search_results)
    else:
        print("   没有找到相关内容")
        knowledge_context = ""

    # 构建系统提示词
    system_prompt = role_prompt
    if knowledge_context:
        system_prompt += "\n\n---\n\n## 相关知识（供参考）\n\n" + knowledge_context

    # 调用 LLM
    print(f"\n5. 调用 LLM 生成回答...")
    print("-" * 60)

    messages = [Message(role=MessageRole.USER, content=test_question)]

    response = ""
    async for chunk in provider.stream(
        messages=messages,
        system=system_prompt,
        temperature=0.7,
    ):
        print(chunk, end="", flush=True)
        response += chunk

    print("\n" + "-" * 60)
    print(f"\n回答长度: {len(response)} 字符")

    # 清理
    knowledge_manager.close()
    print("\n测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
