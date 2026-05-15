from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from langsmith import traceable
from langgraph.store.base import BaseStore
from langgraph.store.sqlite import SqliteStore
from pydantic import BaseModel

if TYPE_CHECKING:
    from state import InvestmentMemo

_USER_NS = ("user", "profile")
_PROFILE_KEY = "profile"


class UserProfile(BaseModel):
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = "moderate"
    sectors_of_interest: list[str] = []
    holdings: list[str] = []
    notes: str = ""


def build_store(db_path: str | Path) -> SqliteStore:
    """Create (or open) a persistent SqliteStore at db_path."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
    store = SqliteStore(conn)
    store.setup()
    return store


# ---------------------------------------------------------------------------
# Memo helpers
# ---------------------------------------------------------------------------

@traceable(name="save_memo", run_type="tool")
def save_memo(store: BaseStore, ticker: str, memo: "InvestmentMemo") -> None:
    """Persist an InvestmentMemo under ("memos", ticker) keyed by UTC timestamp."""
    key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    store.put(("memos", ticker.upper()), key, memo.model_dump())


def get_memo_history(store: BaseStore, ticker: str, limit: int = 5) -> list["InvestmentMemo"]:
    """Return the most recent N memos for a ticker, newest first."""
    from state import InvestmentMemo

    items = store.search(("memos", ticker.upper()), limit=100)
    items_sorted = sorted(items, key=lambda x: x.key, reverse=True)[:limit]
    memos = []
    for item in items_sorted:
        try:
            memos.append(InvestmentMemo(**item.value))
        except Exception:
            pass
    return memos


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def get_user_profile(store: BaseStore) -> UserProfile:
    """Return the stored UserProfile, or a default if none exists."""
    item = store.get(_USER_NS, _PROFILE_KEY)
    if item is None:
        return UserProfile()
    try:
        return UserProfile(**item.value)
    except Exception:
        return UserProfile()


def update_user_profile(store: BaseStore, **fields) -> UserProfile:
    """Update the given fields on the stored profile, preserving the rest."""
    current = get_user_profile(store)
    updated = current.model_copy(update={k: v for k, v in fields.items() if v is not None})
    store.put(_USER_NS, _PROFILE_KEY, updated.model_dump())
    return updated


# ---------------------------------------------------------------------------
# Prompt context builder (used by agent nodes)
# ---------------------------------------------------------------------------

def list_all_tickers(store: BaseStore) -> list[str]:
    """Return a sorted list of all distinct tickers that have at least one memo."""
    tickers: set[str] = set()
    try:
        namespaces = store.list_namespaces(prefix=("memos",))
        for ns in namespaces:
            if isinstance(ns, (list, tuple)) and len(ns) >= 2 and ns[0] == "memos":
                tickers.add(str(ns[1]))
    except Exception:
        pass
    return sorted(tickers)


def build_memory_context(store: Optional[BaseStore], ticker: str) -> str:
    """Return a short (≤3 line) context string for injection into agent prompts.

    Returns an empty string if the store is None, profile is default, and no
    prior memos exist — so callers can safely skip injection.
    """
    if store is None:
        return ""
    try:
        profile = get_user_profile(store)
        memos = get_memo_history(store, ticker, limit=3)

        lines: list[str] = []

        profile_parts: list[str] = []
        if profile.risk_tolerance != "moderate":
            profile_parts.append(f"risk tolerance: {profile.risk_tolerance}")
        if profile.sectors_of_interest:
            profile_parts.append(f"sectors of interest: {', '.join(profile.sectors_of_interest)}")
        if profile.holdings:
            ticker_flag = f" (holds {ticker})" if ticker.upper() in [h.upper() for h in profile.holdings] else ""
            profile_parts.append(f"current holdings: {', '.join(profile.holdings)}{ticker_flag}")
        if profile.notes:
            profile_parts.append(f"user notes: {profile.notes}")
        if profile_parts:
            lines.append("User context — " + " | ".join(profile_parts))

        if memos:
            latest = memos[0]
            lines.append(
                f"Prior research on {ticker.upper()} ({len(memos)} run(s)) — "
                f"most recent: {latest.recommendation}, conviction {latest.conviction}/5. "
                f"Thesis: {latest.thesis}"
            )

        return "\n".join(lines)
    except Exception:
        return ""
