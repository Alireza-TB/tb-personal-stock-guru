from __future__ import annotations

import logging
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
from state import NewsFindings, ResearchState
from tools.news import search_news
from tools.web import fetch_url, web_search

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a financial news analyst at a leading investment research firm.
Your job is to gather and synthesize recent news, media coverage, and web sentiment about a company.

Follow this process:
1. Call search_news to find recent news articles about the company (use a 14-day lookback).
   Search using both the company name and ticker symbol for broader coverage.
2. Optionally call web_search to capture broader context: analyst reactions, industry news,
   competitor developments, regulatory updates, or macro trends affecting the company.
3. Optionally call fetch_url on one or two particularly important articles to read their
   full content — prioritise earnings coverage, major strategic announcements, or regulatory filings.
4. Identify the dominant themes across all sources.
5. Assess the overall sentiment tone of recent coverage.
6. Identify specific catalysts — upcoming events or recent developments that could move the stock.

Important constraints:
- Do NOT make buy, sell, or hold recommendations. Your role is information synthesis, not judgement.
- Be specific: reference actual headlines, name actual sources, cite specific data points from tools.
- Distinguish between factual news and speculative commentary."""

_GROUNDING_SYSTEM = """You are extracting structured data from tool results.
Produce a NewsFindings object strictly from the tool results provided below.

Rules:
- top_headlines MUST contain only headline strings that appear verbatim in the tool results.
  Do not paraphrase, summarize, or invent headlines. If fewer than 5 real headlines are
  available in the results, return fewer — do not pad with invented ones.
- themes, sentiment, and key_catalysts must be synthesized solely from the tool results.
  Do not introduce any facts, names, figures, or events not present in the results below.

Tool results:
{grounding_block}"""

_TOOLS = [search_news, web_search, fetch_url]


def _extract_grounding_block(messages: list) -> str:
    """Concatenate all ToolMessage contents from the agent's message history."""
    parts = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            parts.append(content)
    return "\n\n---\n\n".join(parts)


def _filter_headlines(findings: NewsFindings, grounding_block: str) -> NewsFindings:
    """Drop any headline not present as a substring in the grounding block."""
    grounding_lower = grounding_block.lower()
    kept = []
    dropped = []
    for headline in findings.top_headlines:
        if headline.lower() in grounding_lower:
            kept.append(headline)
        else:
            dropped.append(headline)
    if dropped:
        logger.warning(
            "Dropped %d headline(s) not found in tool results: %s",
            len(dropped),
            dropped,
        )
        print(f"[news_hunter] WARNING: dropped {len(dropped)} ungrounded headline(s): {dropped}",
              file=sys.stderr)
    return findings.model_copy(update={"top_headlines": kept})


def news_hunter_node(
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
        {"messages": [HumanMessage(content=f"Research recent news and sentiment for {ticker}. Produce structured findings.")]}
    )

    # Collect every tool that was actually called (ToolMessage.name = function name).
    tool_names: list[str] = [
        msg.name
        for msg in agent_result["messages"]
        if isinstance(msg, ToolMessage) and msg.name
    ]

    grounding_block = _extract_grounding_block(agent_result["messages"])

    structured_model = base_model.with_structured_output(NewsFindings)
    findings: NewsFindings = structured_model.invoke(
        [
            SystemMessage(content=_GROUNDING_SYSTEM.format(grounding_block=grounding_block)),
            HumanMessage(content=f"Extract NewsFindings for {ticker} from the tool results above."),
        ]
    )

    findings = _filter_headlines(findings, grounding_block)
    return {"news_findings": findings, "tools_used": {"news_hunter": tool_names}}


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.WARNING)
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

    print(f"Running news hunter node for {ticker}...\n")
    result = news_hunter_node(initial_state)
    findings = result["news_findings"]
    print(json.dumps(findings.model_dump(), indent=2))
