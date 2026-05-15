from __future__ import annotations

import os
from typing import Optional

import httpx
import trafilatura
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel
from tavily import TavilyClient

load_dotenv(override=True)

_MAX_CLEANED_TEXT_CHARS = 8000


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class SearchResults(BaseModel):
    query: str
    results: list[SearchResult] = []
    error: Optional[str] = None


class WebPage(BaseModel):
    title: Optional[str] = None
    url: str
    cleaned_text: str = ""
    error: Optional[str] = None


@tool
def web_search(query: str, max_results: int = 5) -> SearchResults:
    """Search the live web for current information using Tavily's AI-optimized search.

    Returns a list of relevant web results with title, URL, and a short content snippet.
    Use this to find recent analyst reports, financial news, earnings call summaries,
    SEC filing commentary, industry trends, or any time-sensitive information about a
    company or market that may not be in the LLM's training data.

    Args:
        query: Natural-language or keyword search query.
               Be specific: prefer 'Apple Q1 2025 earnings beat' over 'Apple news'.
        max_results: Maximum number of results to return. Defaults to 5, max 10.
    """
    try:
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        response = client.search(query, max_results=min(max_results, 10))

        results = [
            SearchResult(
                title=r.get("title") or "",
                url=r.get("url") or "",
                snippet=r.get("content") or "",
            )
            for r in response.get("results", [])
            if r.get("url")
        ]

        return SearchResults(query=query, results=results)
    except KeyError:
        return SearchResults(query=query, error="TAVILY_API_KEY environment variable not set")
    except Exception as e:
        return SearchResults(query=query, error=f"web_search failed: {e}")


@tool
def fetch_url(url: str) -> WebPage:
    """Fetch a web page and extract its clean readable text, stripping HTML, ads, and navigation.

    Use this to read the full text of a news article, analyst report, press release,
    or SEC filing HTML page after finding its URL via web_search. The returned text is
    truncated to 8000 characters to keep context manageable.

    Args:
        url: Full URL of the page to fetch (must start with http:// or https://).
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    try:
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        return WebPage(url=url, error=f"HTTP {e.response.status_code} fetching {url}")
    except httpx.RequestError as e:
        return WebPage(url=url, error=f"Request failed fetching {url}: {e}")

    raw_html = response.text
    cleaned = trafilatura.extract(raw_html, include_comments=False, include_tables=True)

    if not cleaned:
        cleaned = ""

    metadata = trafilatura.extract_metadata(raw_html)
    title = metadata.title if metadata and metadata.title else None

    return WebPage(
        title=title,
        url=url,
        cleaned_text=cleaned[:_MAX_CLEANED_TEXT_CHARS],
    )
