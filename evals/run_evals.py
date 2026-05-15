"""Evaluation harness for TB's Personal Stock Guru.

Runs a held-out set of tickers end-to-end through the full research graph and
scores each result on four dimensions:

  1. Tool coverage   — did the ReAct agents actually call the expected tools?
  2. Memo completeness — are all required fields non-trivially populated?
  3. Debate quality  — are the bull and bear cases making genuinely different
                       arguments? (Haiku judge)
  4. Defensibility   — does the PM narrative explicitly name and address the
                       strongest bear point? (Haiku judge)

Usage:
    uv run python evals/run_evals.py            # full 5-ticker eval
    uv run python evals/run_evals.py AMD        # single ticker (for smoke-testing)

The script prints an estimated cost and asks for confirmation before running
the full suite. Single-ticker runs skip the prompt.

Output: evals/results/<timestamp>.md
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from agents.graph import build_graph
from memory.store import build_store
from state import InvestmentMemo, ResearchState

# ---------------------------------------------------------------------------
# Eval configuration
# ---------------------------------------------------------------------------

TICKERS = ["AAPL", "NVDA", "F", "PLTR", "AMD"]

# Rough per-run cost in USD (based on MSFT trace: ~71k tokens, Haiku+Sonnet+Opus mix).
# Judge calls add ~$0.04 for the full 5-ticker run.
COST_PER_RUN_USD  = 0.38
COST_JUDGES_TOTAL = 0.04

_DATA_DIR    = Path(__file__).parent.parent / "data"
_RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Scoring dimension 1: tool coverage
# ---------------------------------------------------------------------------

def score_tool_coverage(state: dict) -> dict[str, bool]:
    """Read state['tools_used'] (populated by analyst + news_hunter nodes)."""
    tools_used   = state.get("tools_used", {})
    analyst_tools = set(tools_used.get("analyst", []))
    news_tools    = set(tools_used.get("news_hunter", []))

    return {
        # At least one of the two core market-data tools was called
        "analyst_market_data": bool(analyst_tools & {"get_price_history", "get_fundamentals"}),
        # SEC filings tool (optional — agent may skip for some tickers)
        "analyst_filings": "get_recent_filings" in analyst_tools,
        # Primary news tool
        "news_search": "search_news" in news_tools,
    }


# ---------------------------------------------------------------------------
# Scoring dimension 2: memo completeness
# ---------------------------------------------------------------------------

def score_completeness(memo: InvestmentMemo) -> dict[str, bool]:
    return {
        "thesis_nonempty":     bool(memo.thesis.strip()),
        "catalysts_ge2":       len(memo.catalysts) >= 2,
        "risks_ge2":           len(memo.key_risks) >= 2,
        "narrative_ge150w":    len(memo.narrative.split()) >= 150,
    }


# ---------------------------------------------------------------------------
# Scoring dimension 3: debate quality (Haiku judge)
# ---------------------------------------------------------------------------

class DebateJudgment(BaseModel):
    verdict: Literal["DIFFERENT", "SAME"]
    reason: str  # one sentence


_DEBATE_JUDGE_SYSTEM = """\
You evaluate whether two investment arguments are substantively different.

DIFFERENT means the two sides are making genuinely distinct economic claims —
different causal mechanisms, different facts they weight most heavily, or
different predictions about what will happen.

SAME means they are making the same structural argument with opposite framing
(e.g. both anchor on "growth" but one calls it sustainable, the other calls it
priced-in). This is a common failure mode — be strict."""


def judge_debate_quality(bull_case: str, bear_case: str) -> DebateJudgment:
    """Call Haiku to determine whether the bull and bear cases are distinct."""
    prompt = (
        f"Bull case (first 600 chars):\n{bull_case[:600]}\n\n"
        f"Bear case (first 600 chars):\n{bear_case[:600]}\n\n"
        "Are these making genuinely DIFFERENT economic arguments, or essentially "
        "the SAME argument with opposite framing?"
    )
    model = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
    return model.with_structured_output(DebateJudgment).invoke(
        [
            SystemMessage(content=_DEBATE_JUDGE_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )


# ---------------------------------------------------------------------------
# Scoring dimension 4: recommendation defensibility (Haiku judge)
# ---------------------------------------------------------------------------

class DefensibilityJudgment(BaseModel):
    names_specific_bear_point: bool  # cites a concrete claim, not vague hedging
    explains_override: bool          # says why proceeding despite that concern
    reason: str                      # one sentence


_DEFENSIBILITY_JUDGE_SYSTEM = """\
You evaluate investment research memos for analytical rigour.

names_specific_bear_point: true only if the narrative explicitly cites a concrete
bear argument (a specific risk, figure, or mechanism) — not generic phrases like
"risks exist" or "the bears argue generally."

explains_override: true only if the narrative then states a specific reason the
author is proceeding (or not proceeding) despite that concern — not just
acknowledging it and moving on."""


def judge_defensibility(narrative: str) -> DefensibilityJudgment:
    """Call Haiku to check whether the PM narrative names and addresses the bear."""
    prompt = (
        f"Investment memo narrative (first 900 chars):\n{narrative[:900]}\n\n"
        "Does this narrative: "
        "(1) name a specific bear argument, and "
        "(2) explain why the author is proceeding despite it?"
    )
    model = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
    return model.with_structured_output(DefensibilityJudgment).invoke(
        [
            SystemMessage(content=_DEFENSIBILITY_JUDGE_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )


# ---------------------------------------------------------------------------
# Single-ticker eval runner
# ---------------------------------------------------------------------------

def _bool_icon(b: bool) -> str:
    return "YES" if b else "no"


def run_one(ticker: str, graph, config: dict) -> dict:
    """Run the full graph on one ticker and return a scores dict."""
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

    print(f"\n  >> {ticker}: running graph ...", end="", flush=True)
    t0 = time.time()

    for _ in graph.stream(initial_state, config=config):
        pass  # stream to completion; state accumulated in checkpointer

    elapsed = time.time() - t0
    print(f" done in {elapsed:.0f}s")

    final = graph.get_state(config).values
    memo: InvestmentMemo | None = final.get("final_memo")

    result: dict = {
        "ticker":         ticker,
        "elapsed_s":      round(elapsed),
        "recommendation": memo.recommendation if memo else "—",
        "conviction":     memo.conviction if memo else 0,
    }

    # 1. Tool coverage
    cov = score_tool_coverage(final)
    result["tool_market_data"] = cov["analyst_market_data"]
    result["tool_filings"]     = cov["analyst_filings"]
    result["tool_news"]        = cov["news_search"]

    # 2. Memo completeness
    if memo:
        comp = score_completeness(memo)
        result["complete_thesis"]    = comp["thesis_nonempty"]
        result["complete_catalysts"] = comp["catalysts_ge2"]
        result["complete_risks"]     = comp["risks_ge2"]
        result["complete_narrative"] = comp["narrative_ge150w"]
    else:
        result.update({
            "complete_thesis": False, "complete_catalysts": False,
            "complete_risks": False,  "complete_narrative": False,
        })

    # 3. Debate quality (Haiku judge)
    bull = final.get("bull_case", "")
    bear = final.get("bear_case", "")
    if bull and bear:
        print(f"  -- {ticker}: running debate judge ...", end="", flush=True)
        dj = judge_debate_quality(bull, bear)
        result["debate_verdict"] = dj.verdict
        result["debate_reason"]  = dj.reason
        print(" done")
    else:
        result["debate_verdict"] = "NO_DATA"
        result["debate_reason"]  = "Bull or bear case missing."

    # 4. Defensibility (Haiku judge)
    if memo and memo.narrative:
        print(f"  -- {ticker}: running defensibility judge ...", end="", flush=True)
        dv = judge_defensibility(memo.narrative)
        result["defense_names"]    = dv.names_specific_bear_point
        result["defense_explains"] = dv.explains_override
        result["defense_reason"]   = dv.reason
        print(" done")
    else:
        result["defense_names"]    = False
        result["defense_explains"] = False
        result["defense_reason"]   = "No narrative available."

    return result


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------

def _completeness_cell(r: dict) -> str:
    checks = [
        r["complete_thesis"],
        r["complete_catalysts"],
        r["complete_risks"],
        r["complete_narrative"],
    ]
    score = sum(checks)
    icons = "".join(_bool_icon(c) for c in checks)
    return f"{score}/4 {icons}"


def _tool_cell(r: dict) -> str:
    return (
        f"mkt:{_bool_icon(r['tool_market_data'])} "
        f"10K:{_bool_icon(r['tool_filings'])} "
        f"news:{_bool_icon(r['tool_news'])}"
    )


def build_report(results: list[dict], tickers_run: list[str]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        f"# Eval Report — {ts}",
        "",
        f"Tickers: {', '.join(tickers_run)}",
        "",
        "## Results",
        "",
        "| Ticker | Rec (conv) | Tool coverage | Completeness | Debate | Defense (name/explain) | Time |",
        "|--------|-----------|---------------|--------------|--------|------------------------|------|",
    ]

    for r in results:
        debate_cell = (
            f"{_bool_icon(r['debate_verdict'] == 'DIFFERENT')} {r['debate_verdict']}"
        )
        defense_cell = (
            f"{_bool_icon(r['defense_names'])}/{_bool_icon(r['defense_explains'])}"
        )
        lines.append(
            f"| {r['ticker']} "
            f"| {r['recommendation']} ({r['conviction']}) "
            f"| {_tool_cell(r)} "
            f"| {_completeness_cell(r)} "
            f"| {debate_cell} "
            f"| {defense_cell} "
            f"| {r['elapsed_s']}s |"
        )

    lines += [
        "",
        "## Debate judge notes",
        "",
    ]
    for r in results:
        lines.append(f"**{r['ticker']}:** {r['debate_reason']}")
    lines.append("")

    lines += ["## Defensibility judge notes", ""]
    for r in results:
        lines.append(f"**{r['ticker']}:** {r['defense_reason']}")
    lines.append("")

    lines += [
        "## Legend",
        "",
        "- **Tool coverage** - `mkt`: market data (price/fundamentals), `10K`: SEC filings, `news`: NewsAPI",
        "- **Completeness** - thesis / >=2 catalysts / >=2 risks / narrative >=150 words",
        "- **Debate** - YES/DIFFERENT means the Haiku judge found genuinely distinct economic arguments",
        "- **Defense** - name: PM cited a specific bear point | explain: PM said why proceeding despite it",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # On Windows the default console encoding (cp1252) can't handle Unicode symbols
    # in the markdown report. Reconfigure stdout to UTF-8 if possible; fall back
    # silently so the file write (which always uses UTF-8) still works.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Single-ticker override from CLI arg
    if len(sys.argv) > 1:
        tickers_to_run = [sys.argv[1].upper()]
        skip_confirm   = True
    else:
        tickers_to_run = TICKERS
        skip_confirm   = False

    n = len(tickers_to_run)
    est_cost = round(n * COST_PER_RUN_USD + (COST_JUDGES_TOTAL if not skip_confirm else 0.008 * n), 2)

    print("=" * 60)
    print("Stock Guru — Eval Harness")
    print("=" * 60)
    print(f"Tickers   : {', '.join(tickers_to_run)}")
    print(f"Est. cost : ~${est_cost:.2f}  ({n} run(s) + judge calls)")
    print()

    if not skip_confirm:
        ans = input("Proceed? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    _DATA_DIR.mkdir(exist_ok=True)
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    store = build_store(_DATA_DIR / "memory.db")
    graph = build_graph(store=store)

    results: list[dict] = []
    for ticker in tickers_to_run:
        thread_id = f"eval-{ticker}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        config    = {"configurable": {"thread_id": thread_id}}
        try:
            r = run_one(ticker, graph, config)
        except Exception as exc:
            print(f"\n  FAILED {ticker}: {exc}")
            r = {
                "ticker": ticker, "elapsed_s": 0,
                "recommendation": "ERROR", "conviction": 0,
                "tool_market_data": False, "tool_filings": False, "tool_news": False,
                "complete_thesis": False, "complete_catalysts": False,
                "complete_risks": False, "complete_narrative": False,
                "debate_verdict": "ERROR", "debate_reason": str(exc),
                "defense_names": False, "defense_explains": False, "defense_reason": str(exc),
            }
        results.append(r)

    report = build_report(results, tickers_to_run)

    ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _RESULTS_DIR / f"{ts_file}.md"
    out_path.write_text(report, encoding="utf-8")

    print()
    print(report)
    print()
    print(f"Report saved → {out_path}")


if __name__ == "__main__":
    main()
