"""Fast tests for the memory layer — no agents, no API calls, runs in <1s."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from langgraph.store.sqlite import SqliteStore

from memory.store import (
    UserProfile,
    build_memory_context,
    get_memo_history,
    get_user_profile,
    save_memo,
    update_user_profile,
)
from state import InvestmentMemo


def _make_store() -> SqliteStore:
    conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    store = SqliteStore(conn)
    store.setup()
    return store


def _make_memo(**overrides) -> InvestmentMemo:
    defaults = dict(
        thesis="Strong services flywheel justifies premium.",
        conviction=4,
        time_horizon="medium",
        recommendation="Buy",
        key_risks=["CEO transition timing"],
        catalysts=["WWDC 2026", "iPhone 18 launch"],
        narrative="Bull case won the structural debate.",
    )
    return InvestmentMemo(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Memo persistence
# ---------------------------------------------------------------------------

class TestMemo:
    def test_save_and_retrieve_single_memo(self):
        store = _make_store()
        memo = _make_memo()
        save_memo(store, "AAPL", memo)
        history = get_memo_history(store, "AAPL")
        assert len(history) == 1
        assert isinstance(history[0], InvestmentMemo)

    def test_retrieved_memo_data_intact(self):
        store = _make_store()
        memo = _make_memo(conviction=3, recommendation="Hold")
        save_memo(store, "AAPL", memo)
        result = get_memo_history(store, "AAPL")[0]
        assert result.conviction == 3
        assert result.recommendation == "Hold"
        assert result.thesis == memo.thesis

    def test_ticker_is_case_insensitive(self):
        store = _make_store()
        save_memo(store, "aapl", _make_memo())
        assert len(get_memo_history(store, "AAPL")) == 1
        assert len(get_memo_history(store, "aapl")) == 1

    def test_limit_respected(self):
        store = _make_store()
        for conviction in range(1, 6):
            save_memo(store, "AAPL", _make_memo(conviction=conviction))
        history = get_memo_history(store, "AAPL", limit=3)
        assert len(history) <= 3

    def test_different_tickers_isolated(self):
        store = _make_store()
        save_memo(store, "AAPL", _make_memo(recommendation="Buy"))
        save_memo(store, "TSLA", _make_memo(recommendation="Avoid"))
        assert get_memo_history(store, "AAPL")[0].recommendation == "Buy"
        assert get_memo_history(store, "TSLA")[0].recommendation == "Avoid"

    def test_empty_history_returns_empty_list(self):
        store = _make_store()
        assert get_memo_history(store, "NVDA") == []


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

class TestUserProfile:
    def test_default_profile_returned_when_none_stored(self):
        store = _make_store()
        profile = get_user_profile(store)
        assert isinstance(profile, UserProfile)
        assert profile.risk_tolerance == "moderate"
        assert profile.sectors_of_interest == []
        assert profile.holdings == []

    def test_update_risk_tolerance(self):
        store = _make_store()
        update_user_profile(store, risk_tolerance="aggressive")
        assert get_user_profile(store).risk_tolerance == "aggressive"

    def test_update_sectors(self):
        store = _make_store()
        update_user_profile(store, sectors_of_interest=["tech", "energy"])
        assert get_user_profile(store).sectors_of_interest == ["tech", "energy"]

    def test_update_preserves_other_fields(self):
        store = _make_store()
        update_user_profile(store, risk_tolerance="conservative", holdings=["AAPL"])
        update_user_profile(store, sectors_of_interest=["tech"])
        profile = get_user_profile(store)
        assert profile.risk_tolerance == "conservative"
        assert profile.holdings == ["AAPL"]
        assert profile.sectors_of_interest == ["tech"]

    def test_update_notes(self):
        store = _make_store()
        update_user_profile(store, notes="prefer long-term holds")
        assert get_user_profile(store).notes == "prefer long-term holds"

    def test_update_returns_updated_profile(self):
        store = _make_store()
        result = update_user_profile(store, risk_tolerance="aggressive")
        assert isinstance(result, UserProfile)
        assert result.risk_tolerance == "aggressive"


# ---------------------------------------------------------------------------
# Memory context builder
# ---------------------------------------------------------------------------

class TestBuildMemoryContext:
    def test_returns_empty_string_for_none_store(self):
        assert build_memory_context(None, "AAPL") == ""

    def test_returns_empty_string_for_default_profile_and_no_memos(self):
        store = _make_store()
        ctx = build_memory_context(store, "AAPL")
        assert ctx == ""

    def test_includes_non_default_risk_tolerance(self):
        store = _make_store()
        update_user_profile(store, risk_tolerance="aggressive")
        ctx = build_memory_context(store, "AAPL")
        assert "aggressive" in ctx

    def test_includes_prior_memo_summary(self):
        store = _make_store()
        save_memo(store, "AAPL", _make_memo())
        ctx = build_memory_context(store, "AAPL")
        assert "AAPL" in ctx
        assert "Buy" in ctx

    def test_context_is_short(self):
        store = _make_store()
        update_user_profile(store, risk_tolerance="conservative", sectors_of_interest=["tech"])
        save_memo(store, "AAPL", _make_memo())
        ctx = build_memory_context(store, "AAPL")
        # Should be 1-2 lines, not a wall of text
        assert len(ctx.splitlines()) <= 3
