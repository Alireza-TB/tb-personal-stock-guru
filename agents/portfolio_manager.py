from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from memory.store import build_memory_context
from state import InvestmentMemo, ResearchState
from tools.mcp_loader import notion_session

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior portfolio manager at a long/short equity fund.
You have just reviewed a full research packet on a stock: analyst data, news findings,
opening bull and bear cases, and a multi-round rebuttal debate.

Your job is to synthesise this material into a signed investment memo.

How to reason:
- Read both sides as steelman arguments, not as positions to dismiss.
- Decide where the truth lives: which side made claims the other could not rebut?
  Which claims rested on evidence, and which on extrapolation?
- Your recommendation must follow from that assessment. It must be defensible from
  the evidence in the packet. "It could go either way" is not a recommendation.

How to set conviction (1–5):
- 5: The bear arguments were structurally weak or factually wrong. Strong asymmetry.
- 4: The bull case is clearly stronger, bear raised real but manageable concerns.
- 3: Both sides made credible points. A lean, not a strong view.
- 2: Meaningful uncertainty. The bear's strongest points were not fully answered.
- 1: The evidence is genuinely mixed or the risks are severe enough to stay out.

What to put in each field:
- thesis: One crisp sentence — the core reason the investment makes sense (or doesn't).
- key_risks: The bear's STRONGEST points from the debate, not generic risks like
  "macro uncertainty." If the bear made a compelling unrefuted claim, it goes here.
- catalysts: The bull's strongest evidence-backed points plus specific upcoming events
  from the news findings. Do not include speculative catalysts.
- narrative (~300 words): Explain the call. Name the single strongest counter-argument
  explicitly. Explain why you are overriding it or deferring to it.
  Do not hedge with "on the other hand" without ultimately landing somewhere.

Hard rules:
- No invented facts. Every claim must trace to the research packet.
- Do not recommend Buy and then list five bear risks that undermine it — own the call.
- time_horizon reflects how long the thesis needs to play out, not a hedge."""

# Expected Notion database property names and their types.
# Used to validate the schema at node startup before attempting a write.
_EXPECTED_PROPERTIES = {
    "Ticker": "title",
    "Recommendation": "multi_select",
    "Conviction": "number",
    "Time Horizon": "multi_select",
    "Date": "date",
    "Thesis": "rich_text",
}

# Tools the PM uses for the Notion side-effect (not in the main reasoning call).
_NOTION_TOOLS = ["API-post-page", "API-retrieve-a-database", "API-retrieve-a-data-source"]


def _build_memo_packet(state: ResearchState, memory_ctx: str = "") -> str:
    analyst = state["analyst_findings"]
    news = state["news_findings"]
    bull = state["bull_case"]
    bear = state["bear_case"]
    rounds = state["debate_rounds"]

    sections: list[str] = []

    sections.append(f"TICKER: {state['ticker']}")

    if memory_ctx:
        sections.append(f"── PRIOR RESEARCH CONTEXT ──\n{memory_ctx}")

    sections.append(
        "── ANALYST FINDINGS ──\n"
        + (analyst.model_dump_json(indent=2) if analyst else "Not available.")
    )

    sections.append(
        "── NEWS FINDINGS ──\n"
        + (news.model_dump_json(indent=2) if news else "Not available.")
    )

    sections.append(f"── BULL OPENING CASE ──\n{bull or 'Not available.'}")
    sections.append(f"── BEAR OPENING CASE ──\n{bear or 'Not available.'}")

    if rounds:
        debate_text = ""
        for rd in rounds:
            debate_text += (
                f"\n--- Rebuttal Round {rd.round_number} ---\n"
                f"BULL:\n{rd.bull_argument}\n\n"
                f"BEAR:\n{rd.bear_argument}\n"
            )
        sections.append(f"── DEBATE REBUTTALS ──{debate_text}")
    else:
        sections.append("── DEBATE REBUTTALS ──\nNone recorded.")

    return "\n\n".join(sections)


def _parse_mcp_response(result) -> dict:
    """Extract and parse the JSON payload from an MCP tool response."""
    if isinstance(result, list) and result:
        text = result[0].get("text", "")
    elif isinstance(result, str):
        text = result
    else:
        text = str(result)
    return json.loads(text)


async def _save_memo_to_notion_async(
    ticker: str,
    memo: InvestmentMemo,
    database_id: str,
) -> str:
    """Open a single Notion MCP session, validate the schema, then create the page."""
    async with notion_session(allowlist=_NOTION_TOOLS) as tools:
        # ── Step 1: preflight — verify DB is accessible and find the data source ──
        db_tool = tools.get("API-retrieve-a-database")
        data_source_id: str | None = None
        if db_tool:
            db_data = _parse_mcp_response(
                await db_tool.ainvoke({"database_id": database_id})
            )
            if db_data.get("object") != "database":
                raise ValueError(
                    f"Notion database lookup returned unexpected object type: "
                    f"{db_data.get('object')!r}. Check NOTION_DATABASE_ID."
                )
            sources = db_data.get("data_sources", [])
            if sources:
                data_source_id = sources[0]["id"].replace("-", "")

        # ── Step 2: validate property schema via data source ──
        ds_tool = tools.get("API-retrieve-a-data-source")
        if ds_tool and data_source_id:
            ds_data = _parse_mcp_response(
                await ds_tool.ainvoke({"data_source_id": data_source_id})
            )
            actual = {
                name: prop.get("type")
                for name, prop in ds_data.get("properties", {}).items()
            }
            missing = [k for k in _EXPECTED_PROPERTIES if k not in actual]
            if missing:
                raise ValueError(
                    f"Notion database is missing expected properties: {missing}. "
                    f"Found: {list(actual.keys())}"
                )
            wrong_type = [
                f"{k} (expected {v!r}, got {actual[k]!r})"
                for k, v in _EXPECTED_PROPERTIES.items()
                if k in actual and actual[k] != v
            ]
            if wrong_type:
                raise ValueError(
                    f"Notion property type mismatch: {wrong_type}"
                )

        # ── Step 3: create the database row ──
        page_tool = tools.get("API-post-page")
        if not page_tool:
            raise RuntimeError("API-post-page tool not available from Notion MCP server")

        properties = {
            "Ticker": {
                "title": [{"type": "text", "text": {"content": ticker.upper()}}]
            },
            "Recommendation": {
                "multi_select": [{"name": memo.recommendation}]
            },
            "Conviction": {
                "number": memo.conviction
            },
            "Time Horizon": {
                # Notion options are Title-cased; memo stores lowercase
                "multi_select": [{"name": memo.time_horizon.capitalize()}]
            },
            "Date": {
                "date": {"start": date.today().isoformat()}
            },
            "Thesis": {
                # Notion rich_text blocks max 2000 chars each
                "rich_text": [{"type": "text", "text": {"content": memo.thesis[:2000]}}]
            },
        }

        page_data = _parse_mcp_response(
            await page_tool.ainvoke({
                "parent": {"type": "database_id", "database_id": database_id},
                "properties": properties,
            })
        )

        url = page_data.get("url", "")
        if not url:
            raise ValueError(f"Notion page created but URL missing in response: {page_data}")
        return url


def _save_memo_to_notion(ticker: str, memo: InvestmentMemo) -> str | None:
    """Synchronous wrapper around the async Notion save. Never raises."""
    database_id = os.environ.get("NOTION_DATABASE_ID", "").strip()
    if not database_id:
        logger.warning("[Notion] NOTION_DATABASE_ID not set — skipping save")
        return None

    coro = _save_memo_to_notion_async(ticker, memo, database_id)
    try:
        # graph.stream() is synchronous — no running event loop here.
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "event loop" in str(exc).lower():
            # Fallback: run in a fresh thread that owns its own event loop.
            import concurrent.futures
            coro2 = _save_memo_to_notion_async(ticker, memo, database_id)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    return pool.submit(asyncio.run, coro2).result(timeout=90)
                except Exception as inner:
                    logger.warning("[Notion] Save failed (thread fallback): %s", inner)
                    return None
        logger.warning("[Notion] Save failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("[Notion] Save failed: %s", exc)
        return None


def portfolio_manager_node(
    state: ResearchState,
    *,
    store: Optional[BaseStore] = None,
) -> dict:
    ticker = state["ticker"]
    memory_ctx = build_memory_context(store, ticker)
    memo_packet = _build_memo_packet(state, memory_ctx)

    # ── Synthesis: Opus reasons over the full research packet ──
    model = ChatAnthropic(model="claude-opus-4-7")
    structured_model = model.with_structured_output(InvestmentMemo)

    memo: InvestmentMemo = structured_model.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Write the investment memo for {ticker}.\n\n"
                    f"{memo_packet}"
                )
            ),
        ]
    )

    # ── Side-effect: save to Notion (never crashes the graph) ──
    notion_url = _save_memo_to_notion(ticker, memo)
    if notion_url:
        print(f"[Notion] Memo saved: {notion_url}", file=sys.stderr)
        memo = memo.model_copy(update={"notion_url": notion_url})
    else:
        print("[Notion] Save skipped or failed — see warnings above", file=sys.stderr)

    return {"final_memo": memo}


if __name__ == "__main__":
    from agents.analyst import analyst_node
    from agents.bear import bear_node
    from agents.bull import bull_node
    from agents.debate import debate_node
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

    print(f"[1/6] Analyst node ({ticker})...")
    state.update(analyst_node(state))
    print("[2/6] News hunter node...")
    state.update(news_hunter_node(state))
    print("[3/6] Bull node...")
    state.update(bull_node(state))
    print("[4/6] Bear node...")
    state.update(bear_node(state))
    print("[5/6] Debate node...")
    state.update(debate_node(state))
    print("[6/6] Portfolio manager node...\n")
    state.update(portfolio_manager_node(state))

    memo = state["final_memo"]

    stars = "*" * memo.conviction + "-" * (5 - memo.conviction)
    print("=" * 70)
    print(f"INVESTMENT MEMO — {ticker}")
    print("=" * 70)
    print(f"Recommendation : {memo.recommendation}")
    print(f"Conviction     : {memo.conviction}/5  {stars}")
    print(f"Time Horizon   : {memo.time_horizon}")
    if memo.notion_url:
        print(f"Notion URL     : {memo.notion_url}")
    print(f"\nThesis\n{'-' * 40}\n{memo.thesis}")
    print(f"\nCatalysts\n{'-' * 40}")
    for c in memo.catalysts:
        print(f"  + {c}")
    print(f"\nKey Risks\n{'-' * 40}")
    for r in memo.key_risks:
        print(f"  - {r}")
    print(f"\nNarrative\n{'-' * 40}\n{memo.narrative}")
    print("=" * 70)
