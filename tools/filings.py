from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel

load_dotenv(override=True)

_SEC_HEADERS = {
    "User-Agent": "StockGuru/1.0 research@stockguru.local",
    "Accept-Encoding": "gzip, deflate",
}

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{doc}"


class Filing(BaseModel):
    form_type: str
    filing_date: str
    accession_number: str
    primary_doc_url: str


class FilingsResult(BaseModel):
    ticker: str
    cik: str = ""
    filings: list[Filing] = []
    error: Optional[str] = None


@lru_cache(maxsize=1)
def _load_ticker_cik_map() -> dict[str, str]:
    """Fetch and cache the SEC company_tickers.json map once per process."""
    response = httpx.get(_TICKERS_URL, headers=_SEC_HEADERS, timeout=15)
    response.raise_for_status()
    data = response.json()
    return {v["ticker"].upper(): str(v["cik_str"]) for v in data.values()}


def _ticker_to_cik(ticker: str) -> str:
    mapping = _load_ticker_cik_map()
    cik = mapping.get(ticker.upper())
    if cik is None:
        raise ValueError(f"Ticker '{ticker}' not found in SEC company_tickers.json")
    return cik


@tool
def get_recent_filings(ticker: str, form_type: str = "10-K", limit: int = 3) -> FilingsResult:
    """Retrieve recent SEC EDGAR filings for a company directly from the SEC's EDGAR API.

    Returns the filing date, accession number, and a direct URL to the primary document
    for each matching filing. Useful for accessing 10-K annual reports, 10-Q quarterly
    reports, 8-K current reports, DEF 14A proxy statements, and other regulatory filings.

    No files are downloaded to disk — all data is fetched via the EDGAR JSON API.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL', 'MSFT', 'TSLA').
        form_type: SEC form type to filter by. Common values: '10-K', '10-Q', '8-K',
                   'DEF 14A', 'S-1'. Defaults to '10-K'.
        limit: Maximum number of filings to return. Defaults to 3.
    """
    try:
        cik = _ticker_to_cik(ticker)
    except ValueError as e:
        return FilingsResult(ticker=ticker.upper(), error=str(e))
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        return FilingsResult(ticker=ticker.upper(), error=f"SEC ticker map fetch failed: {e}")

    try:
        padded_cik = cik.zfill(10)

        response = httpx.get(
            _SUBMISSIONS_URL.format(cik=padded_cik),
            headers=_SEC_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        filings: list[Filing] = []
        for form, date, accession, doc in zip(forms, dates, accessions, primary_docs):
            if form != form_type:
                continue

            folder = accession.replace("-", "")
            url = _FILING_BASE_URL.format(cik=cik, folder=folder, doc=doc) if doc else ""

            filings.append(
                Filing(
                    form_type=form,
                    filing_date=date,
                    accession_number=accession,
                    primary_doc_url=url,
                )
            )

            if len(filings) >= limit:
                break

        return FilingsResult(ticker=ticker.upper(), cik=cik, filings=filings)
    except httpx.HTTPStatusError as e:
        return FilingsResult(
            ticker=ticker.upper(),
            cik=cik,
            error=f"SEC EDGAR HTTP {e.response.status_code} for '{ticker}'",
        )
    except httpx.RequestError as e:
        return FilingsResult(
            ticker=ticker.upper(),
            cik=cik,
            error=f"SEC EDGAR request failed for '{ticker}': {e}",
        )
    except Exception as e:
        return FilingsResult(
            ticker=ticker.upper(),
            cik=cik,
            error=f"get_recent_filings failed for '{ticker}': {e}",
        )
