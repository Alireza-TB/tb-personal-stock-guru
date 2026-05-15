from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langgraph.store.base import BaseStore

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from memory.store import build_memory_context
from state import AnalystFindings, ResearchState
from tools.filings import get_recent_filings
from tools.market_data import get_fundamentals, get_price_history

_SYSTEM_PROMPT = """You are a senior equity analyst at a top-tier investment firm.
Your job is to perform rigorous fundamental and technical analysis on a given stock.

Follow this process:
1. Call get_fundamentals to retrieve valuation metrics, margins, and sector context.
2. Call get_price_history to understand recent price action, trend, and volatility.
3. If the company has meaningful recent developments, call get_recent_filings to review
   the latest 10-K or 10-Q for management commentary, risk factors, and financial health.
4. Synthesise all gathered data into a balanced, evidence-based assessment.

Important constraints:
- Do NOT make buy, sell, or hold recommendations. That is the portfolio manager's job.
- Stick to facts and analysis: what the numbers say, what the trend shows, what the
  filings reveal. Label each observation as a strength or weakness where appropriate.
- Be concise but specific — cite actual figures (e.g. "P/E of 28x", "revenue up 12% YoY")."""

_GROUNDING_SYSTEM = """You are extracting structured data from financial tool results.
Produce an AnalystFindings object strictly from the tool results provided below.

Rules:
- Every figure cited in summary, strengths, weaknesses, and valuation_assessment MUST
  come directly from the tool results below. Do not introduce any metrics, ratios, dates,
  or claims from outside the tool results.
- key_metrics must be populated only with values explicitly present in the tool results.
- If a metric is not available in the tool results, omit it from key_metrics rather than
  inventing a value.
{memory_suffix}
Tool results:
{grounding_block}"""

_TOOLS = [get_price_history, get_fundamentals, get_recent_filings]


def _extract_grounding_block(messages: list) -> str:
    parts = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            parts.append(content)
    return "\n\n---\n\n".join(parts)


def analyst_node(
    state: ResearchState,
    *,
    store: Optional[BaseStore] = None,
) -> dict:
    ticker = state["ticker"]

    memory_ctx = build_memory_context(store, ticker)
    system_prompt = _SYSTEM_PROMPT
    if memory_ctx:
        system_prompt = f"[Context]\n{memory_ctx}\n\n{_SYSTEM_PROMPT}"

    base_model = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
    react_agent = create_react_agent(base_model, _TOOLS, prompt=system_prompt)

    agent_result = react_agent.invoke(
        {"messages": [HumanMessage(content=f"Analyze {ticker}. Produce structured findings.")]}
    )

    # Collect every tool that was actually called (ToolMessage.name = function name).
    tool_names: list[str] = [
        msg.name
        for msg in agent_result["messages"]
        if isinstance(msg, ToolMessage) and msg.name
    ]

    grounding_block = _extract_grounding_block(agent_result["messages"])
    memory_suffix = f"\n[User context for relevance weighting]\n{memory_ctx}\n" if memory_ctx else ""

    structured_model = base_model.with_structured_output(AnalystFindings)
    findings: AnalystFindings = structured_model.invoke(
        [
            SystemMessage(content=_GROUNDING_SYSTEM.format(
                grounding_block=grounding_block,
                memory_suffix=memory_suffix,
            )),
            HumanMessage(content=f"Extract AnalystFindings for {ticker} from the tool results above."),
        ]
    )

    return {"analyst_findings": findings, "tools_used": {"analyst": tool_names}}


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

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
    }

    print(f"Running analyst node for {ticker}...\n")
    result = analyst_node(initial_state)
    findings = result["analyst_findings"]
    print(json.dumps(findings.model_dump(), indent=2))
