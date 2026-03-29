"""
yfinance 异步封装 + StockData 数据类 + 内存 TTL 缓存
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StockData:
    """股票数据"""
    ticker: str
    name: str = ""
    currency: str = "USD"
    exchange: str = ""

    # 业务背景
    sector: str = ""
    industry: str = ""
    employees: Optional[int] = None
    beta: Optional[float] = None

    # 价格
    price: Optional[float] = None
    change_pct: Optional[float] = None
    week52_low: Optional[float] = None
    week52_high: Optional[float] = None
    market_cap: Optional[float] = None

    # 估值
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    dividend_yield: Optional[float] = None

    # 财务
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    free_cash_flow: Optional[float] = None
    operating_cash_flow: Optional[float] = None

    # 增长
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None

    # 利润率
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None

    # 债务健康
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    total_cash: Optional[float] = None
    total_debt: Optional[float] = None

    # 分析师
    target_price: Optional[float] = None
    recommendation: Optional[str] = None
    analyst_count: Optional[int] = None

    error: Optional[str] = None


def _fetch_sync(ticker: str) -> StockData:
    """同步获取（将被 asyncio.to_thread 调用）"""
    import yfinance as yf

    data = StockData(ticker=ticker)
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or info.get("regularMarketPrice") is None:
            data.error = f"无法获取 {ticker} 的数据"
            return data

        # 基本信息
        data.name = info.get("shortName", info.get("longName", ""))
        data.currency = info.get("currency", "USD")
        data.exchange = info.get("exchange", "")

        # 业务背景
        data.sector = info.get("sector", "")
        data.industry = info.get("industry", "")
        data.employees = info.get("fullTimeEmployees")
        data.beta = info.get("beta")

        # 价格
        data.price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev_close = info.get("regularMarketPreviousClose")
        if data.price and prev_close and prev_close > 0:
            data.change_pct = (data.price - prev_close) / prev_close * 100
        data.week52_low = info.get("fiftyTwoWeekLow")
        data.week52_high = info.get("fiftyTwoWeekHigh")
        data.market_cap = info.get("marketCap")

        # 估值
        data.pe_ratio = info.get("trailingPE")
        data.forward_pe = info.get("forwardPE")
        data.pb_ratio = info.get("priceToBook")
        data.ps_ratio = info.get("priceToSalesTrailing12Months")
        data.peg_ratio = info.get("trailingPegRatio")
        data.ev_to_ebitda = info.get("enterpriseToEbitda")
        data.dividend_yield = info.get("dividendYield")
        # yfinance dividendYield 已是百分比形式（0.39 = 0.39%），无需 *100

        # 财务
        data.revenue = info.get("totalRevenue")
        data.net_income = info.get("netIncomeToCommon")
        data.ebitda = info.get("ebitda")
        data.free_cash_flow = info.get("freeCashflow")
        data.operating_cash_flow = info.get("operatingCashflow")

        # 增长（ratio → 百分比）
        data.revenue_growth = info.get("revenueGrowth")
        if data.revenue_growth is not None:
            data.revenue_growth *= 100
        data.earnings_growth = info.get("earningsGrowth")
        if data.earnings_growth is not None:
            data.earnings_growth *= 100

        # 利润率（ratio → 百分比）
        data.gross_margin = info.get("grossMargins")
        if data.gross_margin is not None:
            data.gross_margin *= 100
        data.operating_margin = info.get("operatingMargins")
        if data.operating_margin is not None:
            data.operating_margin *= 100
        data.profit_margin = info.get("profitMargins")
        if data.profit_margin is not None:
            data.profit_margin *= 100
        data.roe = info.get("returnOnEquity")
        if data.roe is not None:
            data.roe *= 100
        data.roa = info.get("returnOnAssets")
        if data.roa is not None:
            data.roa *= 100

        # 债务健康
        data.debt_to_equity = info.get("debtToEquity")
        data.current_ratio = info.get("currentRatio")
        data.total_cash = info.get("totalCash")
        data.total_debt = info.get("totalDebt")

        # 分析师
        data.target_price = info.get("targetMeanPrice")
        data.recommendation = info.get("recommendationKey")
        data.analyst_count = info.get("numberOfAnalystOpinions")

    except Exception as e:
        data.error = str(e)

    return data


# TTL 缓存条目
@dataclass
class _CacheEntry:
    data: StockData
    timestamp: float


class StockFetcher:
    """异步股票数据获取器，带内存 TTL 缓存"""

    def __init__(self, ttl: int = 300):
        self._cache: dict[str, _CacheEntry] = {}
        self._ttl = ttl  # 缓存有效期（秒），默认 5 分钟

    def _get_cached(self, ticker: str) -> Optional[StockData]:
        entry = self._cache.get(ticker)
        if entry and (time.monotonic() - entry.timestamp) < self._ttl:
            return entry.data
        return None

    def _set_cache(self, ticker: str, data: StockData) -> None:
        self._cache[ticker] = _CacheEntry(data=data, timestamp=time.monotonic())

    async def fetch(self, ticker: str) -> StockData:
        """获取单只股票数据"""
        cached = self._get_cached(ticker)
        if cached:
            return cached

        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(_fetch_sync, ticker),
                timeout=30,
            )
        except asyncio.TimeoutError:
            data = StockData(ticker=ticker, error="获取超时")
        except Exception as e:
            data = StockData(ticker=ticker, error=str(e))

        if not data.error:
            self._set_cache(ticker, data)
        return data

    async def fetch_batch(self, tickers: list[str]) -> dict[str, StockData]:
        """并发获取多只股票数据"""
        tasks = [self.fetch(t) for t in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, StockData] = {}
        for ticker, result in zip(tickers, results):
            if isinstance(result, Exception):
                output[ticker] = StockData(ticker=ticker, error=str(result))
            else:
                output[ticker] = result
        return output
