"""
简单测试嵌入 API
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lifee.memory.embeddings import create_embedding_provider
from lifee.config.settings import settings


async def main():
    print("测试嵌入 API...")
    print(f"Google API Key: {'已配置' if settings.google_api_key else '未配置'}")

    if not settings.google_api_key:
        print("\n错误: 未配置 GOOGLE_API_KEY")
        print("请在 .env 文件中添加 GOOGLE_API_KEY")
        return

    try:
        provider = create_embedding_provider(
            google_api_key=settings.google_api_key,
        )
        print(f"嵌入提供商: {type(provider).__name__}")
        print(f"模型: {getattr(provider, 'model', 'unknown')}")

        # 测试嵌入
        print("\n正在测试嵌入...")
        embedding = await provider.embed("这是一个测试")
        print(f"嵌入维度: {len(embedding)}")
        print(f"前 5 个值: {embedding[:5]}")
        print("\n嵌入 API 正常！")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
