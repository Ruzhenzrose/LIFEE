"""
实时股票数据模块

唯一公开入口：resolve_and_fetch(user_input) -> str
"""

from .resolver import TickerResolver
from .fetcher import StockFetcher
from .formatter import format_batch

# 模块级单例，复用缓存
_fetcher = StockFetcher(ttl=300)


async def resolve_and_fetch(user_input: str, translated_input: str = "") -> str:
    """
    从用户输入中识别公司名/代码，获取实时数据，返回格式化文本

    Args:
        user_input: 用户原始输入（中文或英文）
        translated_input: 已翻译的英文关键词（用于在线搜索兜底）

    失败时返回空字符串，不影响对话流程
    """
    try:
        # 1. 静态匹配（正则 + 字典，无网络调用）
        tickers = TickerResolver.resolve_from_input(user_input)

        # 也对翻译后的英文做一次字典匹配（如 "apple" → AAPL）
        if not tickers and translated_input:
            tickers = TickerResolver.resolve_from_input(translated_input)

        # 2. 字典没命中 → yfinance 在线搜索兜底
        if not tickers:
            search_query = translated_input.strip() if translated_input else user_input
            if search_query:
                tickers = await TickerResolver.search_online(search_query)

        if not tickers:
            return ""

        results = await _fetcher.fetch_batch(tickers)

        # 过滤掉完全失败的结果
        valid = {k: v for k, v in results.items() if not v.error}
        if not valid:
            return ""

        return format_batch(valid)
    except Exception:
        return ""
