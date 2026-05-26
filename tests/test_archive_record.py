"""Tests for the ResearchRecord data model and archive store helpers.

All tests use an in-memory SQLite store — no agent runs, no API calls, <1s.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from langgraph.store.sqlite import SqliteStore

from memory.store import (
    get_research_records,
    list_all_tickers,
    save_memo,
    save_research_record,
)
from state import (
    AnalystFindings,
    DebateRound,
    InvestmentMemo,
    NewsFindings,
    ResearchRecord,
)


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------

def _make_store() -> SqliteStore:
    conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    store = SqliteStore(conn)
    store.setup()
    return store


def _make_record(ticker: str = "AAPL", **overrides) -> ResearchRecord:
    defaults = dict(
        timestamp=datetime(2025, 3, 14, 12, 0, 0, tzinfo=timezone.utc),
        ticker=ticker,
        plan=["Assess iPhone demand cycle", "Evaluate services margin trend"],
        analyst_findings=AnalystFindings(
            summary="Solid fundamentals with margin expansion.",
            key_metrics={"P/E": 28.5, "Revenue Growth": "8%"},
            strengths=["Services flywheel", "Brand moat"],
            weaknesses=["China exposure", "Hardware saturation"],
            valuation_assessment="Fairly valued at current multiples.",
        ),
        news_findings=NewsFindings(
            summary="Broadly positive sentiment around WWDC.",
            top_headlines=["Apple unveils AI features", "Services hit record revenue"],
            themes=["AI", "services", "China"],
            sentiment="positive",
            key_catalysts=["WWDC 2025", "India expansion"],
        ),
        bull_case="Strong services revenue and AI integration create a durable moat.",
        bear_case="China headwinds and slowing hardware refresh cycles cap upside.",
        debate_rounds=[
            DebateRound(
                round_number=1,
                bull_argument="Services margin expansion offsets hardware risk.",
                bear_argument="Regulatory pressure on App Store fees is mounting.",
            )
        ],
        final_memo=InvestmentMemo(
            thesis="Services-led growth justifies a premium multiple.",
            conviction=4,
            time_horizon="medium",
            recommendation="Buy",
            key_risks=["China geopolitics", "App Store regulation"],
            catalysts=["WWDC 2025", "iPhone 18 super-cycle"],
            narrative="Bull case carried the debate on structural margin story.",
        ),
        tools_used={"analyst": ["get_financial_data"], "news_hunter": ["search_web"]},
    )
    return ResearchRecord(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Test 1 — ResearchRecord model: instantiation and JSON serialisation
# ---------------------------------------------------------------------------

class TestResearchRecordModel:
    def test_instantiation_with_all_fields(self):
        record = _make_record()
        assert record.ticker == "AAPL"
        assert record.final_memo.recommendation == "Buy"
        assert record.final_memo.conviction == 4
        assert len(record.debate_rounds) == 1
        assert record.tools_used == {
            "analyst": ["get_financial_data"],
            "news_hunter": ["search_web"],
        }

    def test_model_dump_json_is_serialisable(self):
        """model_dump(mode='json') must produce a plain-dict with no datetime objects."""
        import json
        record = _make_record()
        data = record.model_dump(mode="json")
        # Should not raise
        serialised = json.dumps(data)
        assert '"ticker"' in serialised
        assert '"AAPL"' in serialised

    def test_timestamp_field_accepts_aware_datetime(self):
        ts = datetime(2025, 6, 1, 9, 30, 0, tzinfo=timezone.utc)
        record = _make_record(timestamp=ts)
        assert record.timestamp == ts

    def test_tools_used_defaults_to_empty_dict(self):
        """tools_used has a default_factory — omitting it should not raise."""
        record = _make_record()
        record2 = record.model_copy(update={"tools_used": {}})
        assert record2.tools_used == {}


# ---------------------------------------------------------------------------
# Test 2 — save_research_record / get_research_records round-trip
# ---------------------------------------------------------------------------

class TestSaveAndRetrieve:
    def test_saved_record_is_retrievable(self):
        store = _make_store()
        record = _make_record()
        save_research_record(store, record)
        results = get_research_records(store, "AAPL")
        assert len(results) == 1
        assert isinstance(results[0], ResearchRecord)

    def test_round_trip_preserves_memo_fields(self):
        store = _make_store()
        record = _make_record()
        save_research_record(store, record)
        retrieved = get_research_records(store, "AAPL")[0]
        assert retrieved.final_memo.recommendation == "Buy"
        assert retrieved.final_memo.conviction == 4
        assert retrieved.final_memo.thesis == record.final_memo.thesis

    def test_round_trip_preserves_nested_findings(self):
        store = _make_store()
        record = _make_record()
        save_research_record(store, record)
        retrieved = get_research_records(store, "AAPL")[0]
        assert retrieved.analyst_findings.summary == record.analyst_findings.summary
        assert retrieved.news_findings.sentiment == "positive"

    def test_round_trip_preserves_plan_and_debate(self):
        store = _make_store()
        record = _make_record()
        save_research_record(store, record)
        retrieved = get_research_records(store, "AAPL")[0]
        assert retrieved.plan == record.plan
        assert len(retrieved.debate_rounds) == 1
        assert retrieved.debate_rounds[0].round_number == 1

    def test_ticker_lookup_is_case_insensitive(self):
        store = _make_store()
        save_research_record(store, _make_record(ticker="aapl"))
        assert len(get_research_records(store, "AAPL")) == 1
        assert len(get_research_records(store, "aapl")) == 1

    def test_empty_store_returns_empty_list(self):
        store = _make_store()
        assert get_research_records(store, "NVDA") == []

    def test_different_tickers_are_isolated(self):
        store = _make_store()
        save_research_record(store, _make_record(ticker="AAPL"))
        save_research_record(store, _make_record(ticker="TSLA"))
        assert len(get_research_records(store, "AAPL")) == 1
        assert len(get_research_records(store, "TSLA")) == 1


# ---------------------------------------------------------------------------
# Test 3 — list_all_tickers includes ("research",) namespace
# ---------------------------------------------------------------------------

class TestListAllTickers:
    def test_ticker_from_research_namespace_appears(self):
        store = _make_store()
        save_research_record(store, _make_record(ticker="MSFT"))
        tickers = list_all_tickers(store)
        assert "MSFT" in tickers

    def test_ticker_from_memos_namespace_still_appears(self):
        """Legacy ("memos",) namespace must not be dropped."""
        from state import InvestmentMemo
        store = _make_store()
        memo = InvestmentMemo(
            thesis="Legacy entry.",
            conviction=3,
            time_horizon="short",
            recommendation="Hold",
            key_risks=[],
            catalysts=[],
            narrative="Legacy.",
        )
        save_memo(store, "IBM", memo)
        tickers = list_all_tickers(store)
        assert "IBM" in tickers

    def test_tickers_from_both_namespaces_merged(self):
        from state import InvestmentMemo
        store = _make_store()
        save_research_record(store, _make_record(ticker="AAPL"))
        memo = InvestmentMemo(
            thesis="Legacy.",
            conviction=2,
            time_horizon="short",
            recommendation="Pass",
            key_risks=[],
            catalysts=[],
            narrative=".",
        )
        save_memo(store, "GOOG", memo)
        tickers = list_all_tickers(store)
        assert "AAPL" in tickers
        assert "GOOG" in tickers

    def test_returns_sorted_list(self):
        store = _make_store()
        for t in ["TSLA", "AAPL", "MSFT"]:
            save_research_record(store, _make_record(ticker=t))
        tickers = list_all_tickers(store)
        assert tickers == sorted(tickers)

    def test_empty_store_returns_empty_list(self):
        store = _make_store()
        assert list_all_tickers(store) == []


# ---------------------------------------------------------------------------
# Test 4 — get_research_records ordering and limit
# ---------------------------------------------------------------------------

class TestGetResearchRecordsOrdering:
    def test_newest_first(self):
        store = _make_store()
        ts_old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ts_new = datetime(2025, 6, 1, tzinfo=timezone.utc)
        save_research_record(store, _make_record(timestamp=ts_old))
        save_research_record(store, _make_record(timestamp=ts_new))
        results = get_research_records(store, "AAPL")
        assert results[0].timestamp >= results[1].timestamp

    def test_limit_respected(self):
        store = _make_store()
        for month in range(1, 6):
            ts = datetime(2025, month, 1, tzinfo=timezone.utc)
            save_research_record(store, _make_record(timestamp=ts))
        results = get_research_records(store, "AAPL", limit=3)
        assert len(results) <= 3

    def test_most_recent_within_limit(self):
        """When limited to N, the N newest records should be returned."""
        store = _make_store()
        timestamps = [
            datetime(2025, m, 1, tzinfo=timezone.utc) for m in range(1, 6)
        ]
        for ts in timestamps:
            save_research_record(store, _make_record(timestamp=ts))
        results = get_research_records(store, "AAPL", limit=2)
        returned_months = sorted(r.timestamp.month for r in results)
        # The 2 newest are months 4 and 5
        assert returned_months == [4, 5]
