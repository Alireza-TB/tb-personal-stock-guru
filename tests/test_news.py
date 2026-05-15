"""Integration tests for tools/news.py — hits live NewsAPI."""
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from tools.news import NewsResults, search_news


class TestSearchNews:
    def test_returns_news_results_model(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        assert isinstance(result, NewsResults)

    def test_query_echoed(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        assert result.query == "Apple AAPL stock"

    def test_articles_list_present(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        assert isinstance(result.articles, list)

    def test_articles_have_title_and_url(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        for article in result.articles:
            assert article.title
            assert article.url.startswith("http")

    def test_articles_have_source(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        for article in result.articles:
            assert article.source is not None

    def test_total_results_non_negative(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        assert result.total_results >= 0

    def test_custom_days_back(self):
        result = search_news.invoke({"query": "Apple AAPL", "days_back": 3})
        assert isinstance(result, NewsResults)

    def test_no_error_on_valid_query(self):
        result = search_news.invoke({"query": "Apple AAPL stock"})
        assert result.error is None


class TestErrorHandling:
    def test_missing_api_key_returns_valid_object(self, monkeypatch):
        monkeypatch.delenv("NEWSAPI_KEY", raising=False)
        result = search_news.invoke({"query": "Apple"})
        assert isinstance(result, NewsResults)
        assert result.error is not None
        assert result.articles == []
        assert result.total_results == 0

    def test_network_error_returns_valid_object(self, monkeypatch):
        import httpx
        import tools.news as news_mod

        def _bad_get(*args, **kwargs):
            raise httpx.RequestError("simulated network failure")

        monkeypatch.setattr(news_mod.httpx, "get", _bad_get)
        result = search_news.invoke({"query": "Apple"})
        assert isinstance(result, NewsResults)
        assert result.error is not None
        assert result.articles == []
