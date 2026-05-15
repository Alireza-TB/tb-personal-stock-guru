from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel

load_dotenv(override=True)


class NewsArticle(BaseModel):
    title: str
    source: str
    published_at: str
    url: str
    description: Optional[str] = None


class NewsResults(BaseModel):
    query: str
    total_results: int = 0
    articles: list[NewsArticle] = []
    error: Optional[str] = None


@tool
def search_news(query: str, days_back: int = 7) -> NewsResults:
    """Search recent news articles relevant to an investment research query using NewsAPI.

    Returns a ranked list of articles including title, source, publication date, URL,
    and a short description. Useful for gauging recent sentiment, earnings coverage,
    analyst upgrades/downgrades, regulatory news, or macroeconomic events affecting
    a company or sector.

    Args:
        query: Free-text search query (e.g. 'Apple earnings Q1 2025', 'TSLA recall').
               Supports NewsAPI boolean operators (AND, OR, NOT) and quoted phrases.
        days_back: How many calendar days back to search. Defaults to 7.
                   Maximum allowed by the free NewsAPI tier is 30.
    """
    try:
        api_key = os.environ["NEWSAPI_KEY"]
    except KeyError:
        return NewsResults(query=query, error="NEWSAPI_KEY environment variable not set")

    try:
        from_date = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        response = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_date,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 20,
                "apiKey": api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        articles = [
            NewsArticle(
                title=a.get("title") or "",
                source=a.get("source", {}).get("name") or "",
                published_at=a.get("publishedAt") or "",
                url=a.get("url") or "",
                description=a.get("description"),
            )
            for a in data.get("articles", [])
            if a.get("title") and a.get("url")
        ]

        return NewsResults(
            query=query,
            total_results=data.get("totalResults", len(articles)),
            articles=articles,
        )
    except httpx.HTTPStatusError as e:
        return NewsResults(
            query=query,
            error=f"NewsAPI HTTP {e.response.status_code}: {e.response.text[:200]}",
        )
    except httpx.RequestError as e:
        return NewsResults(query=query, error=f"NewsAPI request failed: {e}")
    except Exception as e:
        return NewsResults(query=query, error=f"search_news failed: {e}")
