"""
性能基准测试
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lifee.config.settings import settings
from lifee.roles import RoleManager
from lifee.providers import GeminiProvider, Message, MessageRole
from lifee.memory import format_search_results


async def main():
    print("性能基准测试")
    print("=" * 50)

    role_manager = RoleManager()
    question = "什么是冥想？"

    # 1. 加载知识库（首次）
    t0 = time.time()
    knowledge_manager = await role_manager.get_knowledge_manager(
        "krishnamurti",
        google_api_key=settings.google_api_key,
    )
    t1 = time.time()
    print(f"加载知识库: {(t1-t0)*1000:.0f} ms")

    # 2. RAG 搜索
    t0 = time.time()
    results = await knowledge_manager.search(question, max_results=3)
    t1 = time.time()
    print(f"RAG 搜索:    {(t1-t0)*1000:.0f} ms")

    # 3. LLM 首 token
    provider = GeminiProvider(
        api_key=settings.google_api_key,
        model="gemini-2.0-flash",
    )

    role_prompt = role_manager.load_role("krishnamurti")
    context = format_search_results(results) if results else ""
    system = role_prompt + "\n\n## 相关知识\n" + context

    messages = [Message(role=MessageRole.USER, content=question)]

    t0 = time.time()
    first_token_time = None
    response = ""

    async for chunk in provider.stream(messages=messages, system=system):
        if first_token_time is None:
            first_token_time = time.time()
        response += chunk

    t1 = time.time()

    print(f"首 token:    {(first_token_time-t0)*1000:.0f} ms")
    print(f"完整响应:    {(t1-t0)*1000:.0f} ms ({len(response)} 字符)")

    print("\n" + "=" * 50)
    total = (first_token_time - t0) * 1000 if first_token_time else 0
    # 假设搜索和首token是串行的
    print(f"用户感知延迟 (搜索+首token): ~{(t1-t0)*1000 + 500:.0f} ms")

    knowledge_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
