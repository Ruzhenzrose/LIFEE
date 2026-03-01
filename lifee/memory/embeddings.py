"""
嵌入提供者模块

支持 Gemini（默认）和 OpenAI 嵌入 API
参考 clawdbot embeddings-gemini.js / embeddings-openai.js
"""

import asyncio
import re
import time
from abc import ABC, abstractmethod
from typing import Optional

from google import genai


def _contains_non_english(text: str) -> bool:
    """检测文本是否包含非英文字符（CJK、日文假名、韩文等）"""
    return bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))


class EmbeddingProvider(ABC):
    """嵌入提供者抽象基类"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称"""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """向量维度"""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """生成单个文本的嵌入向量"""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量（默认逐个处理）"""
        results = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)
        return results


class GeminiEmbedding(EmbeddingProvider):
    """
    Gemini 嵌入提供者

    使用 gemini-embedding-001 模型（免费）
    维度：768
    """

    DEFAULT_MODEL = "gemini-embedding-001"
    DIMENSIONS = 3072

    def __init__(self, api_key: str, model: str = None):
        self._api_key = api_key
        self._model = model or self.DEFAULT_MODEL
        self._client = genai.Client(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS

    async def embed(self, text: str) -> list[float]:
        """生成文本嵌入"""
        result = await self._client.aio.models.embed_content(
            model=self._model,
            contents=text,
        )
        return list(result.embeddings[0].values)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入（使用 Gemini 原生批量 API）"""
        if not texts:
            return []
        batch_size = 100  # Gemini 单次请求最多约 100 个文本
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            result = await self._client.aio.models.embed_content(
                model=self._model,
                contents=batch,
            )
            all_embeddings.extend(list(e.values) for e in result.embeddings)
            if start + batch_size < len(texts):
                await asyncio.sleep(0.5)  # 批次间暂停避免限流
        return all_embeddings

    # 翻译缓存：(text, target_lang) → (result, timestamp)，避免同一轮多个参与者重复翻译
    _translate_cache: dict[tuple[str, str], tuple[str, float]] = {}
    _TRANSLATE_CACHE_TTL = 60.0  # 缓存 60 秒

    async def translate_to_keywords(self, text: str, target_lang: str = "English") -> str:
        """将文本翻译为目标语言的搜索关键词，用于跨语言 BM25 搜索"""
        cache_key = (text, target_lang)
        cached = self._translate_cache.get(cache_key)
        if cached:
            result, ts = cached
            if time.time() - ts < self._TRANSLATE_CACHE_TTL:
                return result

        try:
            response = await self._client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=(
                    f"Translate the following text into {target_lang} search keywords. "
                    f"Rules: output ONLY {target_lang} words, separated by spaces. "
                    "No articles, no prepositions, no punctuation. "
                    "Include synonyms for key concepts.\n"
                    f"Input: {text}"
                ),
            )
            result = response.text.strip()
            self._translate_cache[cache_key] = (result, time.time())
            return result
        except Exception:
            return text  # 翻译失败时回退到原文


class OpenAIEmbedding(EmbeddingProvider):
    """
    OpenAI 嵌入提供者

    使用 text-embedding-3-small 模型
    维度：1536
    """

    DEFAULT_MODEL = "text-embedding-3-small"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DIMENSIONS = 1536

    def __init__(
        self,
        api_key: str,
        model: str = None,
        base_url: str = None,
    ):
        self._api_key = api_key
        self._model = model or self.DEFAULT_MODEL
        self._base_url = base_url or self.DEFAULT_BASE_URL

        # 延迟导入 openai
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._base_url,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS

    async def embed(self, text: str) -> list[float]:
        """生成文本嵌入"""
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入（OpenAI 原生支持批量）"""
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]


def create_embedding_provider(
    google_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
) -> EmbeddingProvider:
    """
    创建嵌入提供者

    优先级：Gemini > OpenAI

    Args:
        google_api_key: Google API Key（用于 Gemini）
        openai_api_key: OpenAI API Key

    Returns:
        嵌入提供者实例

    Raises:
        ValueError: 如果没有可用的 API Key
    """
    # 优先使用 Gemini（免费）
    if google_api_key:
        return GeminiEmbedding(api_key=google_api_key)

    # 备选 OpenAI
    if openai_api_key:
        return OpenAIEmbedding(api_key=openai_api_key)

    raise ValueError(
        "没有可用的嵌入 API Key。"
        "请设置 GOOGLE_API_KEY（推荐）或 OPENAI_API_KEY。"
    )
