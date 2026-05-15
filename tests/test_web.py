"""Integration tests for tools/web.py — hits live Tavily and the open web."""
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from tools.web import SearchResults, WebPage, fetch_url, web_search

_PUBLIC_URL = "https://en.wikipedia.org/wiki/Apple_Inc."


class TestWebSearch:
    def test_returns_search_results_model(self):
        result = web_search.invoke({"query": "Apple AAPL stock analysis"})
        assert isinstance(result, SearchResults)

    def test_query_echoed(self):
        result = web_search.invoke({"query": "Apple AAPL stock analysis"})
        assert result.query == "Apple AAPL stock analysis"

    def test_results_list_present(self):
        result = web_search.invoke({"query": "Apple AAPL stock analysis"})
        assert isinstance(result.results, list)
        assert len(result.results) > 0

    def test_results_have_url(self):
        result = web_search.invoke({"query": "Apple AAPL stock analysis"})
        for r in result.results:
            assert r.url.startswith("http")

    def test_results_have_title_and_snippet(self):
        result = web_search.invoke({"query": "Apple AAPL stock analysis"})
        for r in result.results:
            assert r.title is not None
            assert r.snippet is not None

    def test_max_results_respected(self):
        result = web_search.invoke({"query": "Apple stock", "max_results": 3})
        assert len(result.results) <= 3

    def test_no_error_on_valid_query(self):
        result = web_search.invoke({"query": "Apple AAPL stock analysis"})
        assert result.error is None


class TestFetchUrl:
    def test_returns_web_page_model(self):
        result = fetch_url.invoke({"url": _PUBLIC_URL})
        assert isinstance(result, WebPage)

    def test_url_echoed(self):
        result = fetch_url.invoke({"url": _PUBLIC_URL})
        assert result.url == _PUBLIC_URL

    def test_cleaned_text_non_empty(self):
        result = fetch_url.invoke({"url": _PUBLIC_URL})
        assert len(result.cleaned_text) > 0

    def test_cleaned_text_truncated(self):
        result = fetch_url.invoke({"url": _PUBLIC_URL})
        assert len(result.cleaned_text) <= 8000

    def test_contains_expected_content(self):
        result = fetch_url.invoke({"url": _PUBLIC_URL})
        assert "Apple" in result.cleaned_text

    def test_no_error_on_valid_url(self):
        result = fetch_url.invoke({"url": _PUBLIC_URL})
        assert result.error is None


class TestErrorHandling:
    def test_http_error_returns_valid_object(self, monkeypatch):
        import httpx
        import tools.web as web_mod

        def _bad_get(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "403",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(403),
            )

        monkeypatch.setattr(web_mod.httpx, "get", _bad_get)
        result = fetch_url.invoke({"url": "https://example.com/blocked"})
        assert isinstance(result, WebPage)
        assert result.error is not None
        assert result.cleaned_text == ""

    def test_network_error_fetch_url_returns_valid_object(self, monkeypatch):
        import httpx
        import tools.web as web_mod

        def _bad_get(*args, **kwargs):
            raise httpx.RequestError("connection refused")

        monkeypatch.setattr(web_mod.httpx, "get", _bad_get)
        result = fetch_url.invoke({"url": "https://example.com"})
        assert isinstance(result, WebPage)
        assert result.error is not None

    def test_web_search_client_failure_returns_valid_object(self, monkeypatch):
        import tools.web as web_mod

        class _BadClient:
            def __init__(self, **kwargs):
                pass

            def search(self, *args, **kwargs):
                raise Exception("Tavily unavailable")

        monkeypatch.setattr(web_mod, "TavilyClient", _BadClient)
        result = web_search.invoke({"query": "Apple"})
        assert isinstance(result, SearchResults)
        assert result.error is not None
        assert result.results == []

    def test_missing_tavily_key_returns_valid_object(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = web_search.invoke({"query": "Apple"})
        assert isinstance(result, SearchResults)
        assert result.error is not None
