from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from agents.analyst import analyst_node
from agents.bear import bear_node
from agents.bull import bull_node
from agents.debate import debate_node
from agents.news_hunter import news_hunter_node
from agents.portfolio_manager import portfolio_manager_node
from memory.store import build_store, save_memo
from state import AnalystFindings, DebateRound, InvestmentMemo, NewsFindings, ResearchState

# ---------------------------------------------------------------------------
# Planner node (inline — lightweight, for UI explainability only)
# ---------------------------------------------------------------------------

class _Plan(BaseModel):
    steps: list[str]


_PLANNER_SYSTEM = """You are a research coordinator at an investment firm.
Given a stock ticker, produce a concise research plan: 3 to 5 short bullet points
describing what specific aspects of this company to investigate and why they matter
for an investment decision. Be specific to the company and its sector — not generic.
Each step should be one clear sentence."""


def planner_node(state: ResearchState) -> dict:
    ticker = state["ticker"]
    model = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
    plan: _Plan = model.with_structured_output(_Plan).invoke(
        [
            SystemMessage(content=_PLANNER_SYSTEM),
            HumanMessage(content=f"Create a research plan for {ticker}."),
        ]
    )
    return {"plan": plan.steps}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"
_DB_PATH = _DATA_DIR / "checkpoints.db"
_MEM_PATH = _DATA_DIR / "memory.db"


def _make_archive_node(store):
    """Return a closure that saves the final memo to the long-term store."""
    @traceable(name="archive_node", run_type="tool")
    def archive_node(state: ResearchState) -> dict:
        memo = state.get("final_memo")
        if memo:
            save_memo(store, state["ticker"], memo)
        return {}
    return archive_node


def _make_node_with_store(fn, store):
    """Wrap a node function so the store is passed directly via closure."""
    def _node(state: ResearchState) -> dict:
        return fn(state, store=store)
    _node.__name__ = fn.__name__
    return _node


def build_graph(store=None):
    _DATA_DIR.mkdir(exist_ok=True)

    if store is None:
        store = build_store(_MEM_PATH)

    builder = StateGraph(ResearchState)

    # Nodes
    builder.add_node("planner", planner_node)
    builder.add_node("analyst", _make_node_with_store(analyst_node, store))
    builder.add_node("news_hunter", _make_node_with_store(news_hunter_node, store))
    builder.add_node("bull", bull_node)
    builder.add_node("bear", bear_node)
    builder.add_node("debate", debate_node)
    builder.add_node("portfolio_manager", _make_node_with_store(portfolio_manager_node, store))
    builder.add_node("archive", _make_archive_node(store))

    # Edges
    # START → planner
    builder.add_edge(START, "planner")
    # planner → analyst AND news_hunter  (parallel fan-out: two edges from one node)
    builder.add_edge("planner", "analyst")
    builder.add_edge("planner", "news_hunter")
    # analyst AND news_hunter → bull  (implicit fan-in: bull waits for both to finish)
    builder.add_edge("analyst", "bull")
    builder.add_edge("news_hunter", "bull")
    # Sequential chain
    builder.add_edge("bull", "bear")
    builder.add_edge("bear", "debate")
    builder.add_edge("debate", "portfolio_manager")
    builder.add_edge("portfolio_manager", "archive")
    builder.add_edge("archive", END)

    serde = JsonPlusSerializer().with_msgpack_allowlist(
        [AnalystFindings, NewsFindings, DebateRound, InvestmentMemo]
    )
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(conn, serde=serde)

    return builder.compile(checkpointer=checkpointer, store=store)


graph = build_graph()


# ---------------------------------------------------------------------------
# __main__ runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    thread_id = f"research-{ticker}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: ResearchState = {
        "ticker": ticker,
        "plan": [],
        "analyst_findings": None,
        "news_findings": None,
        "bull_case": "",
        "bear_case": "",
        "debate_rounds": [],
        "final_memo": None,
        "messages": [],
        "tools_used": {},
    }

    print(f"Research pipeline starting for {ticker}")
    print(f"Thread: {thread_id}\n")

    start = time.time()

    for chunk in graph.stream(initial_state, config=config):
        for node_name in chunk:
            elapsed = time.time() - start
            print(f"  [{elapsed:6.1f}s]  {node_name} done")

    elapsed = time.time() - start
    print(f"\nCompleted in {elapsed:.1f}s\n")

    memo = graph.get_state(config).values.get("final_memo")
    plan = graph.get_state(config).values.get("plan", [])

    if plan:
        print("Research Plan")
        print("-" * 40)
        for i, step in enumerate(plan, 1):
            print(f"  {i}. {step}")
        print()

    if memo:
        bar = "*" * memo.conviction + "-" * (5 - memo.conviction)
        print("=" * 70)
        print(f"INVESTMENT MEMO  --  {ticker}")
        print("=" * 70)
        print(f"Recommendation : {memo.recommendation}")
        print(f"Conviction     : {memo.conviction}/5  [{bar}]")
        print(f"Time Horizon   : {memo.time_horizon}")
        if memo.notion_url:
            print(f"Notion URL     : {memo.notion_url}")
        print(f"\nThesis\n{'-'*40}\n{memo.thesis}")
        print(f"\nCatalysts\n{'-'*40}")
        for c in memo.catalysts:
            print(f"  + {c}")
        print(f"\nKey Risks\n{'-'*40}")
        for r in memo.key_risks:
            print(f"  - {r}")
        print(f"\nNarrative\n{'-'*40}\n{memo.narrative}")
        print("=" * 70)
