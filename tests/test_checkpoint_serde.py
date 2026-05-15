"""Fast round-trip test for checkpoint serialization of our Pydantic models.

Exercises the serde layer directly — no agents, no API calls, runs in <1s.
Verifies that after serialize → deserialize, each model comes back as the
correct Pydantic type (not a plain dict), which is what the LangGraph
'Deserializing unregistered type' warning indicates is broken.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from state import AnalystFindings, DebateRound, InvestmentMemo, NewsFindings

_SERDE = JsonPlusSerializer().with_msgpack_allowlist(
    [AnalystFindings, NewsFindings, DebateRound, InvestmentMemo]
)

_ANALYST = AnalystFindings(
    summary="Strong fundamentals with premium valuation.",
    key_metrics={"pe_ratio": 36.1, "market_cap": 4.38e12},
    strengths=["Best-in-class margins", "Services flywheel"],
    weaknesses=["Elevated P/E", "China exposure"],
    valuation_assessment="Premium but defensible given growth trajectory.",
)

_NEWS = NewsFindings(
    summary="Positive sentiment on earnings beat and AI positioning.",
    top_headlines=["Apple hits all-time high"],
    themes=["AI strategy", "Record earnings"],
    sentiment="positive",
    key_catalysts=["WWDC 2026", "iPhone 18 launch"],
)

_DEBATE = DebateRound(
    round_number=1,
    bull_argument="Services at $31B/quarter deserves a software multiple.",
    bear_argument="The Q2 print is a peak, not a trajectory.",
)

_MEMO = InvestmentMemo(
    thesis="Re-accelerating flywheel with multiple growth levers.",
    conviction=4,
    time_horizon="medium",
    recommendation="Buy",
    key_risks=["CEO transition timing", "Valuation at 52-week high"],
    catalysts=["WWDC AI reveal", "iPhone 18 cycle"],
    narrative="Bull case won the structural debate; bear's transition risk earns a 4 not a 5.",
)


def _round_trip(obj):
    serialized = _SERDE.dumps_typed(obj)
    return _SERDE.loads_typed(serialized)


class TestCheckpointSerde:
    def test_analyst_findings_round_trips_as_correct_type(self):
        result = _round_trip(_ANALYST)
        assert isinstance(result, AnalystFindings), f"Expected AnalystFindings, got {type(result)}"

    def test_analyst_findings_data_intact(self):
        result = _round_trip(_ANALYST)
        assert result.summary == _ANALYST.summary
        assert result.key_metrics == _ANALYST.key_metrics
        assert result.strengths == _ANALYST.strengths

    def test_news_findings_round_trips_as_correct_type(self):
        result = _round_trip(_NEWS)
        assert isinstance(result, NewsFindings), f"Expected NewsFindings, got {type(result)}"

    def test_news_findings_data_intact(self):
        result = _round_trip(_NEWS)
        assert result.sentiment == "positive"
        assert result.top_headlines == _NEWS.top_headlines
        assert result.themes == _NEWS.themes

    def test_debate_round_round_trips_as_correct_type(self):
        result = _round_trip(_DEBATE)
        assert isinstance(result, DebateRound), f"Expected DebateRound, got {type(result)}"

    def test_debate_round_data_intact(self):
        result = _round_trip(_DEBATE)
        assert result.round_number == 1
        assert result.bull_argument == _DEBATE.bull_argument

    def test_investment_memo_round_trips_as_correct_type(self):
        result = _round_trip(_MEMO)
        assert isinstance(result, InvestmentMemo), f"Expected InvestmentMemo, got {type(result)}"

    def test_investment_memo_data_intact(self):
        result = _round_trip(_MEMO)
        assert result.conviction == 4
        assert result.recommendation == "Buy"
        assert result.time_horizon == "medium"

    def test_investment_memo_conviction_validates(self):
        result = _round_trip(_MEMO)
        assert 1 <= result.conviction <= 5

    def test_no_deserialization_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            # If any "Deserializing unregistered type" warning fires, this will raise
            for obj in [_ANALYST, _NEWS, _DEBATE, _MEMO]:
                _round_trip(obj)
