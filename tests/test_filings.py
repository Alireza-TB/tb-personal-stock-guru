"""Integration tests for tools/filings.py — hits live SEC EDGAR API."""
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from tools.filings import FilingsResult, get_recent_filings

TICKER = "AAPL"
BAD_TICKER = "ZZZZZZZ"


class TestGetRecentFilings:
    def test_returns_filings_result_model(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        assert isinstance(result, FilingsResult)

    def test_ticker_uppercased(self):
        result = get_recent_filings.invoke({"ticker": "aapl"})
        assert result.ticker == "AAPL"

    def test_cik_is_non_empty_string(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        assert result.cik
        assert result.cik.isdigit()

    def test_returns_filings_list(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        assert isinstance(result.filings, list)
        assert len(result.filings) > 0

    def test_limit_respected(self):
        result = get_recent_filings.invoke({"ticker": TICKER, "limit": 2})
        assert len(result.filings) <= 2

    def test_form_type_matches_request(self):
        result = get_recent_filings.invoke({"ticker": TICKER, "form_type": "10-K"})
        for filing in result.filings:
            assert filing.form_type == "10-K"

    def test_filing_dates_present(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        for filing in result.filings:
            assert filing.filing_date
            assert len(filing.filing_date) == 10  # YYYY-MM-DD

    def test_accession_number_format(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        for filing in result.filings:
            assert filing.accession_number
            assert "-" in filing.accession_number

    def test_primary_doc_url_is_sec_url(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        for filing in result.filings:
            if filing.primary_doc_url:
                assert "sec.gov" in filing.primary_doc_url

    def test_10q_form_type(self):
        result = get_recent_filings.invoke({"ticker": TICKER, "form_type": "10-Q", "limit": 3})
        assert isinstance(result, FilingsResult)
        for filing in result.filings:
            assert filing.form_type == "10-Q"

    def test_no_error_on_valid_ticker(self):
        result = get_recent_filings.invoke({"ticker": TICKER})
        assert result.error is None


class TestErrorHandling:
    def test_bad_ticker_returns_valid_object(self):
        result = get_recent_filings.invoke({"ticker": BAD_TICKER})
        assert isinstance(result, FilingsResult)
        assert result.error is not None
        assert result.filings == []
        assert result.ticker == BAD_TICKER.upper()

    def test_sec_network_error_returns_valid_object(self, monkeypatch):
        import httpx
        import tools.filings as filings_mod

        # Clear the lru_cache so our patched get is actually called
        filings_mod._load_ticker_cik_map.cache_clear()

        def _bad_get(*args, **kwargs):
            raise httpx.RequestError("simulated SEC outage")

        monkeypatch.setattr(filings_mod.httpx, "get", _bad_get)
        result = get_recent_filings.invoke({"ticker": TICKER})
        assert isinstance(result, FilingsResult)
        assert result.error is not None
        assert result.filings == []

        # Restore cache for subsequent tests
        filings_mod._load_ticker_cik_map.cache_clear()
