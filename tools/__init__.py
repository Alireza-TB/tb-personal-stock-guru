from tools.filings import get_recent_filings
from tools.market_data import get_fundamentals, get_price_history
from tools.news import search_news
from tools.web import fetch_url, web_search

ALL_TOOLS = [
    get_price_history,
    get_fundamentals,
    search_news,
    web_search,
    fetch_url,
    get_recent_filings,
]
