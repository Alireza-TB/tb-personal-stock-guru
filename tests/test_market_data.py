"""Integration tests for tools/market_data.py — hits live Yahoo Finance."""
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from tools.market_data import Fundamentals, PriceHistory, get_fundamentals, get_price_history

TICKER = "AAPL"
BAD_TICKER = "ZZZZZZZ"


class TestGetPriceHistory:
    def test_returns_price_history_model(self):
        result = get_price_history.invoke({"ticker": TICKER})
        assert isinstance(result, PriceHistory)

    def test_ticker_is_uppercased(self):
        result = get_price_history.invoke({"ticker": "aapl"})
        assert result.ticker == "AAPL"

    def test_has_data_points(self):
        result = get_price_history.invoke({"ticker": TICKER})
        assert len(result.data_points) > 0

    def test_current_price_positive(self):
        result = get_price_history.invoke({"ticker": TICKER})
        assert result.current_price > 0

    def test_period_high_gte_low(self):
        result = get_price_history.invoke({"ticker": TICKER})
        assert result.period_high >= result.period_low

    def test_date_range_present(self):
        result = get_price_history.invoke({"ticker": TICKER})
        assert result.start_date
        assert result.end_date
        assert result.start_date <= result.end_date

    def test_custom_period(self):
        result = get_price_history.invoke({"ticker": TICKER, "period": "3mo"})
        assert result.period == "3mo"
        assert len(result.data_points) > 0

    def test_data_point_shape(self):
        result = get_price_history.invoke({"ticker": TICKER})
        pt = result.data_points[0]
        assert pt.date
        assert pt.close > 0

    def test_no_error_on_valid_ticker(self):
        result = get_price_history.invoke({"ticker": TICKER})
        assert result.error is None


class TestGetFundamentals:
    def test_returns_fundamentals_model(self):
        result = get_fundamentals.invoke({"ticker": TICKER})
        assert isinstance(result, Fundamentals)

    def test_ticker_is_uppercased(self):
        result = get_fundamentals.invoke({"ticker": "aapl"})
        assert result.ticker == "AAPL"

    def test_market_cap_positive(self):
        result = get_fundamentals.invoke({"ticker": TICKER})
        assert result.market_cap is not None
        assert result.market_cap > 0

    def test_revenue_positive(self):
        result = get_fundamentals.invoke({"ticker": TICKER})
        assert result.revenue_ttm is not None
        assert result.revenue_ttm > 0

    def test_sector_and_industry_present(self):
        result = get_fundamentals.invoke({"ticker": TICKER})
        assert result.sector
        assert result.industry

    def test_beta_is_float_or_none(self):
        result = get_fundamentals.invoke({"ticker": TICKER})
        assert result.beta is None or isinstance(result.beta, float)

    def test_no_error_on_valid_ticker(self):
        result = get_fundamentals.invoke({"ticker": TICKER})
        assert result.error is None


class TestErrorHandling:
    def test_bad_ticker_price_history_returns_valid_object(self):
        result = get_price_history.invoke({"ticker": BAD_TICKER})
        assert isinstance(result, PriceHistory)
        assert result.error is not None
        assert result.data_points == []
        assert result.current_price == 0.0

    def test_bad_ticker_fundamentals_returns_valid_object(self):
        result = get_fundamentals.invoke({"ticker": BAD_TICKER})
        assert isinstance(result, Fundamentals)
        assert result.error is not None
        assert result.market_cap is None
        assert result.sector is None
