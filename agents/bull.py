from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from state import ResearchState

_SYSTEM_PROMPT = """You are a disciplined long-side investor at a value-oriented hedge fund.
You have studied the analyst and news findings provided and must now make the strongest
honest bull case for owning this stock.

Your style:
- Opinionated and confident, but grounded — you build conviction from evidence, not hype.
- Reframe weaknesses as temporary, cyclical, or already priced in.
- Surface underappreciated strengths: durable competitive advantages, optionality the market
  is ignoring, margin expansion potential, or a catalyst that changes the narrative.
- Articulate a clear path to upside: what has to be true, and why it's more likely than not.
- Write 200–350 words. Paragraph prose, not bullet points.

Hard constraints:
- Never invent facts, figures, or events not present in the findings you were given.
- Do not make a buy recommendation by name — argue the case, let the PM decide.
- No weasel words ("might", "could potentially") — write with conviction."""


def bull_node(state: ResearchState) -> dict:
    ticker = state["ticker"]
    analyst = state["analyst_findings"]
    news = state["news_findings"]

    findings_block = f"""ANALYST FINDINGS:
{analyst.model_dump_json(indent=2) if analyst else "Not available."}

NEWS FINDINGS:
{news.model_dump_json(indent=2) if news else "Not available."}"""

    model = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.3)
    response = model.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Build the bull case for {ticker} based on these findings:\n\n{findings_block}"
            ),
        ]
    )

    return {"bull_case": response.content}


if __name__ == "__main__":
    from agents.analyst import analyst_node
    from agents.news_hunter import news_hunter_node

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    state: ResearchState = {
        "ticker": ticker,
        "plan": [],
        "analyst_findings": None,
        "news_findings": None,
        "bull_case": "",
        "bear_case": "",
        "debate_rounds": [],
        "final_memo": None,
        "messages": [],
    }

    print(f"[1/3] Running analyst node for {ticker}...")
    state.update(analyst_node(state))
    print("[2/3] Running news hunter node...")
    state.update(news_hunter_node(state))
    print("[3/3] Running bull node...\n")
    state.update(bull_node(state))

    print("=== ANALYST FINDINGS ===")
    import json
    print(json.dumps(state["analyst_findings"].model_dump(), indent=2))
    print("\n=== NEWS FINDINGS ===")
    print(json.dumps(state["news_findings"].model_dump(), indent=2))
    print("\n=== BULL CASE ===")
    print(state["bull_case"])
