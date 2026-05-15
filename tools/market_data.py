from __future__ import annotations

import os
from typing import Optional

import yfinance as yf
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel

load_dotenv(override=True)


class PricePoint(BaseModel):
    date: str
    close: float


class PriceHistory(BaseModel):
    ticker: str
    period: str
    start_date: str = ""
    end_date: str = ""
    current_price: float = 0.0
    period_high: float = 0.0
    period_low: float = 0.0
    data_points: list[PricePoint] = []
    error: Optional[str] = None


class Fundamentals(BaseModel):
    ticker: str
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    revenue_ttm: Optional[float] = None
    profit_margin: Optional[float] = None
    beta: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    error: Optional[str] = None


@tool
def get_price_history(ticker: str, period: str = "1y") -> PriceHistory:
    """Fetch OHLCV price history for a stock ticker using Yahoo Finance.

    Returns the date range covered, the current (most recent close) price,
    the period high and low, and a list of daily (date, close) data points
    ordered oldest-first.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'MSFT', 'TSLA').
        period: Lookback window. Valid values: '1d', '5d', '1mo', '3mo',
                '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'. Defaults to '1y'.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        if hist.empty:
            return PriceHistory(
                ticker=ticker.upper(),
                period=period,
                error=f"No price history found for ticker '{ticker}'",
            )

        hist.index = hist.index.tz_localize(None) if hist.index.tzinfo else hist.index
        data_points = [
            PricePoint(date=str(idx.date()), close=round(float(row["Close"]), 4))
            for idx, row in hist.iterrows()
        ]

        return PriceHistory(
            ticker=ticker.upper(),
            period=period,
            start_date=str(hist.index[0].date()),
            end_date=str(hist.index[-1].date()),
            current_price=round(float(hist["Close"].iloc[-1]), 4),
            period_high=round(float(hist["High"].max()), 4),
            period_low=round(float(hist["Low"].min()), 4),
            data_points=data_points,
        )
    except Exception as e:
        return PriceHistory(
            ticker=ticker.upper(),
            period=period,
            error=f"Failed to fetch price history for '{ticker}': {e}",
        )


def _safe_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@tool
def get_fundamentals(ticker: str) -> Fundamentals:
    """Fetch key fundamental metrics for a stock ticker using Yahoo Finance.

    Returns valuation, profitability, and descriptive data including market cap,
    P/E ratios, EPS, dividend yield, trailing twelve-month revenue, profit margin,
    beta, sector, and industry classification.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'MSFT', 'TSLA').
    """
    try:
        info = yf.Ticker(ticker).info

        if not info or (
            info.get("regularMarketPrice") is None
            and info.get("currentPrice") is None
            and "symbol" not in info
        ):
            return Fundamentals(
                ticker=ticker.upper(),
                error=f"No fundamental data found for ticker '{ticker}'",
            )

        return Fundamentals(
            ticker=ticker.upper(),
            market_cap=_safe_float(info.get("marketCap")),
            pe_ratio=_safe_float(info.get("trailingPE")),
            forward_pe=_safe_float(info.get("forwardPE")),
            eps=_safe_float(info.get("trailingEps")),
            dividend_yield=_safe_float(info.get("dividendYield")),
            revenue_ttm=_safe_float(info.get("totalRevenue")),
            profit_margin=_safe_float(info.get("profitMargins")),
            beta=_safe_float(info.get("beta")),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )
    except Exception as e:
        return Fundamentals(
            ticker=ticker.upper(),
            error=f"Failed to fetch fundamentals for '{ticker}': {e}",
        )
