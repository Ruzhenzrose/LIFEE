"""
Market 模块单元测试：resolver、formatter、cache
"""

import asyncio
import time
from unittest.mock import patch, MagicMock

from lifee.market.resolver import TickerResolver
from lifee.market.fetcher import StockData, StockFetcher
from lifee.market.formatter import format_stock_data, format_batch


# ============ Resolver 测试 ============

class TestTickerResolver:
    def test_chinese_company_name(self):
        result = TickerResolver.resolve_from_input("分析一下苹果公司")
        assert "AAPL" in result

    def test_english_company_name(self):
        result = TickerResolver.resolve_from_input("what about tesla?")
        assert "TSLA" in result

    def test_hk_ticker_format(self):
        result = TickerResolver.resolve_from_input("看看0700.HK的走势")
        assert "0700.HK" in result

    def test_a_share_ticker_format(self):
        result = TickerResolver.resolve_from_input("600519.SS 最近怎么样")
        assert "600519.SS" in result

    def test_sz_ticker_format(self):
        result = TickerResolver.resolve_from_input("看看300750.SZ")
        assert "300750.SZ" in result

    def test_multiple_companies(self):
        result = TickerResolver.resolve_from_input("比较苹果和腾讯")
        assert "AAPL" in result
        assert "0700.HK" in result

    def test_max_three_tickers(self):
        result = TickerResolver.resolve_from_input("苹果微软谷歌亚马逊特斯拉")
        assert len(result) <= 3

    def test_no_match(self):
        result = TickerResolver.resolve_from_input("今天天气怎么样")
        assert result == []

    def test_dedup(self):
        result = TickerResolver.resolve_from_input("AAPL apple 苹果")
        assert result.count("AAPL") == 1

    def test_case_insensitive_dict(self):
        result = TickerResolver.resolve_from_input("Tesla is great")
        assert "TSLA" in result

    def test_us_ticker_regex_rejects_common_words(self):
        """不应该把 I, A, THE 等常见单词当作 ticker"""
        result = TickerResolver.resolve_from_input("I think A is THE best")
        assert result == []


# ============ Formatter 测试 ============

class TestFormatter:
    def test_format_basic(self):
        data = StockData(
            ticker="AAPL", name="Apple", currency="USD",
            price=198.50, change_pct=1.2, market_cap=3e12,
        )
        text = format_stock_data(data)
        assert "AAPL" in text
        assert "Apple" in text
        assert "198.50" in text
        assert "+1.2%" in text

    def test_format_error(self):
        data = StockData(ticker="INVALID", error="无法获取")
        text = format_stock_data(data)
        assert "失败" in text

    def test_format_hkd_numbers(self):
        data = StockData(
            ticker="0700.HK", currency="HKD",
            market_cap=3.6e12, revenue=554.5e9,
        )
        text = format_stock_data(data)
        assert "万亿" in text
        assert "亿" in text

    def test_format_usd_numbers(self):
        data = StockData(
            ticker="AAPL", currency="USD",
            revenue=383e9, market_cap=3.05e12,
        )
        text = format_stock_data(data)
        assert "B" in text
        assert "T" in text

    def test_format_skip_none_fields(self):
        data = StockData(ticker="TEST", currency="USD", price=100.0)
        text = format_stock_data(data)
        assert "估值" not in text
        assert "财务" not in text

    def test_format_batch_empty(self):
        assert format_batch({}) == ""

    def test_format_batch_header(self):
        data = StockData(ticker="AAPL", currency="USD", price=198.0)
        text = format_batch({"AAPL": data})
        assert "实时市场数据" in text

    def test_format_negative_change(self):
        data = StockData(ticker="TEST", currency="USD", price=100.0, change_pct=-2.5)
        text = format_stock_data(data)
        assert "-2.5%" in text


# ============ Cache 测试 ============

class TestStockFetcherCache:
    def test_cache_hit(self):
        fetcher = StockFetcher(ttl=300)
        mock_data = StockData(ticker="AAPL", price=198.0)
        fetcher._set_cache("AAPL", mock_data)

        result = fetcher._get_cached("AAPL")
        assert result is not None
        assert result.price == 198.0

    async def test_cache_expiry(self):
        fetcher = StockFetcher(ttl=1)  # 1秒过期
        mock_data = StockData(ticker="AAPL", price=198.0)
        fetcher._set_cache("AAPL", mock_data)

        # 立即应该命中
        assert fetcher._get_cached("AAPL") is not None

        # 等待过期
        await asyncio.sleep(1.1)
        assert fetcher._get_cached("AAPL") is None

    async def test_cache_miss(self):
        fetcher = StockFetcher(ttl=300)
        assert fetcher._get_cached("UNKNOWN") is None


# ============ resolve_and_fetch 集成测试 ============

class TestResolveAndFetch:
    async def test_no_match_returns_empty(self):
        from lifee.market import resolve_and_fetch
        result = await resolve_and_fetch("今天天气怎么样")
        assert result == ""

    async def test_exception_returns_empty(self):
        """即使出错也应该返回空字符串"""
        from lifee.market import resolve_and_fetch
        with patch("lifee.market.TickerResolver.resolve_from_input", side_effect=RuntimeError("boom")):
            result = await resolve_and_fetch("苹果")
            assert result == ""
