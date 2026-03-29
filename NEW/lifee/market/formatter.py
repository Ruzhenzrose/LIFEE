"""
StockData → 简洁文本（适合注入 system prompt）

数字格式化规则：
- USD: B (billion) / T (trillion)
- CNY/HKD: 亿 / 万亿
"""

from typing import Optional

from .fetcher import StockData


def _fmt_number(value: Optional[float], currency: str) -> str:
    """格式化大数字"""
    if value is None:
        return ""
    sign = "-" if value < 0 else ""
    abs_val = abs(value)
    if currency in ("CNY", "HKD"):
        if abs_val >= 1e12:
            return f"{sign}{abs_val / 1e12:.2f}万亿"
        if abs_val >= 1e8:
            return f"{sign}{abs_val / 1e8:.0f}亿"
        if abs_val >= 1e4:
            return f"{sign}{abs_val / 1e4:.0f}万"
        return f"{sign}{abs_val:.0f}"
    else:
        if abs_val >= 1e12:
            return f"{sign}${abs_val / 1e12:.2f}T"
        if abs_val >= 1e9:
            return f"{sign}${abs_val / 1e9:.0f}B"
        if abs_val >= 1e6:
            return f"{sign}${abs_val / 1e6:.0f}M"
        return f"{sign}${abs_val:,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    """格式化百分比"""
    if value is None:
        return ""
    return f"{value:.1f}%"


def _market_label(ticker: str) -> str:
    """根据 ticker 判断市场"""
    if ticker.endswith(".HK"):
        return "港股"
    elif ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return "A股"
    return "美股"


def _currency_symbol(currency: str) -> str:
    if currency == "CNY":
        return "¥"
    if currency == "HKD":
        return "HK$"
    return "$"


def format_stock_data(data: StockData) -> str:
    """将单只 StockData 格式化为简洁文本"""
    if data.error:
        return f"【{data.ticker}】数据获取失败: {data.error}"

    market = _market_label(data.ticker)
    cs = _currency_symbol(data.currency)
    lines = []

    # 标题行：名称 + ticker + 市场 + 行业
    name_part = f"{data.name} " if data.name else ""
    industry_part = f" | {data.industry}" if data.industry else ""
    lines.append(f"【{name_part}{data.ticker}】{market}{industry_part}")

    # 价格行
    price_parts = []
    if data.price is not None:
        change = f" ({'+' if (data.change_pct or 0) >= 0 else ''}{_fmt_pct(data.change_pct)})" if data.change_pct is not None else ""
        price_parts.append(f"价格: {cs}{data.price:,.2f}{change}")
    if data.week52_low is not None and data.week52_high is not None:
        price_parts.append(f"52周: {cs}{data.week52_low:,.2f}-{cs}{data.week52_high:,.2f}")
    if data.market_cap is not None:
        price_parts.append(f"市值: {_fmt_number(data.market_cap, data.currency)}")
    if price_parts:
        lines.append(" | ".join(price_parts))

    # 估值行
    val_parts = []
    if data.pe_ratio is not None:
        val_parts.append(f"PE {data.pe_ratio:.1f}")
    if data.forward_pe is not None:
        val_parts.append(f"Forward PE {data.forward_pe:.1f}")
    if data.pb_ratio is not None:
        val_parts.append(f"PB {data.pb_ratio:.1f}")
    if data.ps_ratio is not None:
        val_parts.append(f"PS {data.ps_ratio:.1f}")
    if data.peg_ratio is not None:
        val_parts.append(f"PEG {data.peg_ratio:.2f}")
    if data.ev_to_ebitda is not None:
        val_parts.append(f"EV/EBITDA {data.ev_to_ebitda:.1f}")
    if data.dividend_yield is not None:
        val_parts.append(f"股息率 {_fmt_pct(data.dividend_yield)}")
    if val_parts:
        lines.append("估值: " + " | ".join(val_parts))

    # 财务行
    fin_parts = []
    if data.revenue is not None:
        fin_parts.append(f"营收 {_fmt_number(data.revenue, data.currency)}")
    if data.net_income is not None:
        fin_parts.append(f"净利 {_fmt_number(data.net_income, data.currency)}")
    if data.ebitda is not None:
        fin_parts.append(f"EBITDA {_fmt_number(data.ebitda, data.currency)}")
    if data.operating_cash_flow is not None:
        fin_parts.append(f"经营现金流 {_fmt_number(data.operating_cash_flow, data.currency)}")
    if data.free_cash_flow is not None:
        fin_parts.append(f"自由现金流 {_fmt_number(data.free_cash_flow, data.currency)}")
    if fin_parts:
        lines.append("财务: " + " | ".join(fin_parts))

    # 增长行
    growth_parts = []
    if data.revenue_growth is not None:
        lines_sign = "+" if data.revenue_growth >= 0 else ""
        growth_parts.append(f"营收增速 {lines_sign}{_fmt_pct(data.revenue_growth)}")
    if data.earnings_growth is not None:
        lines_sign = "+" if data.earnings_growth >= 0 else ""
        growth_parts.append(f"利润增速 {lines_sign}{_fmt_pct(data.earnings_growth)}")
    if growth_parts:
        lines.append("增长: " + " | ".join(growth_parts))

    # 利润率行
    margin_parts = []
    if data.gross_margin is not None:
        margin_parts.append(f"毛利 {_fmt_pct(data.gross_margin)}")
    if data.operating_margin is not None:
        margin_parts.append(f"营业 {_fmt_pct(data.operating_margin)}")
    if data.profit_margin is not None:
        margin_parts.append(f"净利率 {_fmt_pct(data.profit_margin)}")
    if data.roe is not None:
        margin_parts.append(f"ROE {_fmt_pct(data.roe)}")
    if data.roa is not None:
        margin_parts.append(f"ROA {_fmt_pct(data.roa)}")
    if margin_parts:
        lines.append("利润率: " + " | ".join(margin_parts))

    # 债务健康行
    debt_parts = []
    if data.debt_to_equity is not None:
        debt_parts.append(f"负债率 {data.debt_to_equity:.1f}%")
    if data.current_ratio is not None:
        debt_parts.append(f"流动比率 {data.current_ratio:.2f}")
    if data.total_cash is not None:
        debt_parts.append(f"现金 {_fmt_number(data.total_cash, data.currency)}")
    if data.total_debt is not None:
        debt_parts.append(f"负债 {_fmt_number(data.total_debt, data.currency)}")
    if debt_parts:
        lines.append("债务: " + " | ".join(debt_parts))

    # 分析师行
    analyst_parts = []
    if data.target_price is not None:
        rec = f" ({data.recommendation})" if data.recommendation else ""
        analyst_parts.append(f"目标价 {cs}{data.target_price:,.2f}{rec}")
    if data.analyst_count is not None:
        analyst_parts.append(f"{data.analyst_count}人覆盖")
    if data.beta is not None:
        analyst_parts.append(f"Beta {data.beta:.2f}")
    if analyst_parts:
        lines.append("分析师: " + " | ".join(analyst_parts))

    return "\n".join(lines)


def format_batch(results: dict[str, StockData]) -> str:
    """格式化多只股票数据"""
    if not results:
        return ""

    parts = []
    for data in results.values():
        formatted = format_stock_data(data)
        if formatted:
            parts.append(formatted)

    if not parts:
        return ""

    return "📊 实时市场数据\n\n" + "\n\n".join(parts)
