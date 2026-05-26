from datetime import datetime
from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


def _merge_tools_used(
    left: dict[str, list[str]],
    right: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge tools_used dicts from parallel nodes (analyst + news_hunter).

    Each node contributes one key (e.g. "analyst", "news_hunter") so a simple
    dict merge is safe — there are no collisions under normal operation.
    """
    return {**left, **right}


class AnalystFindings(BaseModel):
    summary: str
    key_metrics: dict[str, float | str | None]
    strengths: list[str]
    weaknesses: list[str]
    valuation_assessment: str


class NewsFindings(BaseModel):
    summary: str
    top_headlines: list[str]
    themes: list[str]
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    key_catalysts: list[str]


class DebateRound(BaseModel):
    round_number: int
    bull_argument: str
    bear_argument: str


class InvestmentMemo(BaseModel):
    thesis: str
    conviction: Annotated[int, Field(ge=1, le=5)]
    time_horizon: Literal["short", "medium", "long"]
    recommendation: Literal["Buy", "Hold", "Avoid", "Pass"]
    key_risks: list[str]
    catalysts: list[str]
    narrative: str
    notion_url: Optional[str] = None


class ResearchRecord(BaseModel):
    """A complete snapshot of one research run, stored in the archive."""

    timestamp: datetime
    ticker: str
    plan: list[str]
    analyst_findings: AnalystFindings
    news_findings: NewsFindings
    bull_case: str
    bear_case: str
    debate_rounds: list[DebateRound]
    final_memo: InvestmentMemo
    tools_used: dict[str, list[str]] = Field(default_factory=dict)


class ResearchState(TypedDict):
    ticker: str
    plan: list[str]
    analyst_findings: AnalystFindings | None
    news_findings: NewsFindings | None
    bull_case: str
    bear_case: str
    debate_rounds: list[DebateRound]
    final_memo: InvestmentMemo | None
    messages: Annotated[list, add_messages]
    # Which tools each agent actually called during this run.
    # Key = node name ("analyst", "news_hunter"), value = list of tool fn names.
    # Uses a merge reducer so parallel nodes each write their own key without
    # clobbering the other.
    tools_used: Annotated[dict[str, list[str]], _merge_tools_used]
