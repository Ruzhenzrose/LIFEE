"""
公司名/股票代码 → yfinance ticker 解析

支持：
1. 正则匹配 ticker 格式：AAPL、0700.HK、600519.SS/SZ
2. 静态字典匹配：中英文公司名 → ticker
3. yfinance 在线搜索兜底（覆盖所有上市公司）
"""

import asyncio
import re

from .tickers import TICKER_MAP

# 美股 ticker: 1-5 大写字母（独立单词）
_US_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")

# 港股 ticker: 4位数字.HK（用非 ASCII 字母数字边界，兼容中文）
_HK_TICKER_RE = re.compile(r"(?<!\d)(\d{4}\.HK)(?![a-zA-Z0-9])", re.IGNORECASE)

# A股 ticker: 6位数字.SS 或 .SZ
_CN_TICKER_RE = re.compile(r"(?<!\d)(\d{6}\.(?:SS|SZ))(?![a-zA-Z0-9])", re.IGNORECASE)


# 预构建反向索引：ticker → 是否合法（用于验证正则匹配的美股 ticker）
_KNOWN_US_TICKERS = {v for v in TICKER_MAP.values() if "." not in v}

# 在线搜索时限制的交易所（美股、港股、A股）
_ALLOWED_EXCHANGES = {"NMS", "NYQ", "NGM", "PCX", "BTS", "NCM",  # 美股 NASDAQ/NYSE
                      "HKG",  # 港股
                      "SHH", "SHZ"}  # A股



def _search_yfinance(query: str) -> list[str]:
    """用 yfinance Search 在线搜索 ticker（同步，供 to_thread 调用）

    策略：先搜完整 query，没结果则逐词搜索
    """
    from yfinance import Search

    def _extract(results) -> list[str]:
        tickers = []
        for q in results.quotes:
            if q.get("quoteType") != "EQUITY":
                continue
            exchange = q.get("exchange", "")
            if exchange in _ALLOWED_EXCHANGES:
                tickers.append(q["symbol"])
            if len(tickers) >= 3:
                break
        return tickers

    # 1. 先用完整 query 搜索
    results = Search(query, max_results=5)
    tickers = _extract(results)
    if tickers:
        return tickers

    # 2. 拆词逐个搜索：只搜大写开头或全大写的词（专有名词/ticker）
    words = [w for w in query.split() if len(w) >= 2 and (w[0].isupper() or w.isupper())]
    for word in words:
        results = Search(word, max_results=3)
        tickers = _extract(results)
        if tickers:
            return tickers[:1]  # 单词搜索只取最佳匹配

    return []


class TickerResolver:
    """从用户输入中解析股票 ticker"""

    @staticmethod
    def resolve_from_input(text: str) -> list[str]:
        """
        从用户输入中提取 ticker 列表（静态匹配，无网络调用）

        Returns:
            去重后的 ticker 列表，最多 3 个
        """
        found: list[str] = []
        seen: set[str] = set()

        def _add(ticker: str) -> None:
            t = ticker.upper() if "." not in ticker else ticker.split(".")[0].upper() + "." + ticker.split(".")[1].upper()
            if t not in seen:
                seen.add(t)
                found.append(t)

        # 1. 正则匹配明确的 ticker 格式
        for m in _HK_TICKER_RE.finditer(text):
            _add(m.group(1))
        for m in _CN_TICKER_RE.finditer(text):
            _add(m.group(1))
        # 美股 ticker 需要在已知列表中才算（避免 "I" "A" 等误匹配）
        for m in _US_TICKER_RE.finditer(text):
            ticker = m.group(1)
            if ticker in _KNOWN_US_TICKERS:
                _add(ticker)

        # 2. 字典匹配公司名
        text_lower = text.lower()
        for name, ticker in TICKER_MAP.items():
            if name in text_lower:
                _add(ticker)

        return found[:3]

    @staticmethod
    async def search_online(query: str) -> list[str]:
        """
        用 yfinance 在线搜索 ticker（字典没命中时的兜底）

        Args:
            query: 搜索关键词（英文效果最佳）

        Returns:
            ticker 列表，最多 3 个
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_search_yfinance, query),
                timeout=10,
            )
        except Exception:
            return []
