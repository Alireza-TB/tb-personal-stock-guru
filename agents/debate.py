from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from state import DebateRound, ResearchState

# Configurable number of rebuttal rounds beyond the opening statements.
# Opening statements (bull_case / bear_case) are round 0; rebuttals start at round 1.
NUM_REBUTTAL_ROUNDS = 2

_BULL_REBUTTAL_SYSTEM = """You are a disciplined long-side investor making a rebuttal in a structured investment debate.
You are opinionated, confident, and grounded in evidence.

You are in a REBUTTAL round — not an opening statement. Rules:
- Read your opponent's argument carefully. Identify either their strongest claim and dismantle it,
  or their weakest claim and expose it. Do not do both — pick one and go deep.
- Quote or closely paraphrase the specific point you are attacking so it is clear what you are refuting.
- Do not restate your opening case. Every sentence should be a direct response to what they just said.
- Stay grounded: only use facts present in the analyst and news findings provided.
- Write approximately 150 words. Tight, punchy prose — no bullet points."""

_BEAR_REBUTTAL_SYSTEM = """You are a skeptical short-side investor making a rebuttal in a structured investment debate.
You are methodically skeptical, precise, and look for what others are glossing over.

You are in a REBUTTAL round — not an opening statement. Rules:
- Read your opponent's argument carefully. Identify either their strongest claim and dismantle it,
  or their weakest claim and expose it. Do not do both — pick one and go deep.
- Quote or closely paraphrase the specific point you are attacking so it is clear what you are refuting.
- Do not restate your opening case. Every sentence should be a direct response to what they just said.
- Stay grounded: only use facts present in the analyst and news findings provided.
- Write approximately 150 words. Tight, punchy prose — no bullet points."""


def _findings_context(state: ResearchState) -> str:
    analyst = state["analyst_findings"]
    news = state["news_findings"]
    return (
        f"ANALYST FINDINGS:\n"
        f"{analyst.model_dump_json(indent=2) if analyst else 'Not available.'}\n\n"
        f"NEWS FINDINGS:\n"
        f"{news.model_dump_json(indent=2) if news else 'Not available.'}"
    )


def _rebuttal(
    persona_system: str,
    opponent_argument: str,
    findings: str,
    ticker: str,
    model: ChatAnthropic,
) -> str:
    response = model.invoke(
        [
            SystemMessage(content=persona_system),
            HumanMessage(
                content=(
                    f"Ticker: {ticker}\n\n"
                    f"Your opponent just argued:\n\"\"\"\n{opponent_argument}\n\"\"\"\n\n"
                    f"Reference data (use only these facts):\n{findings}\n\n"
                    f"Write your rebuttal (~150 words)."
                )
            ),
        ]
    )
    return response.content


def debate_node(state: ResearchState) -> dict:
    """Run NUM_REBUTTAL_ROUNDS rebuttal rounds and return the full debate_rounds list.

    Returns the complete list (not just new rounds) so LangGraph's default overwrite
    reducer sets state["debate_rounds"] cleanly. Callers should not rely on additive
    merging here.
    """
    ticker = state["ticker"]
    findings = _findings_context(state)
    model = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.4)

    rounds: list[DebateRound] = []

    # Seed: the opening statements from bull_node / bear_node
    last_bull = state["bull_case"]
    last_bear = state["bear_case"]

    for round_num in range(1, NUM_REBUTTAL_ROUNDS + 1):
        # Bull rebuts the bear's most recent argument
        bull_rebuttal = _rebuttal(_BULL_REBUTTAL_SYSTEM, last_bear, findings, ticker, model)
        # Bear rebuts the bull's fresh rebuttal
        bear_rebuttal = _rebuttal(_BEAR_REBUTTAL_SYSTEM, bull_rebuttal, findings, ticker, model)

        rounds.append(
            DebateRound(
                round_number=round_num,
                bull_argument=bull_rebuttal,
                bear_argument=bear_rebuttal,
            )
        )

        last_bull = bull_rebuttal
        last_bear = bear_rebuttal

    return {"debate_rounds": rounds}


if __name__ == "__main__":
    from agents.analyst import analyst_node
    from agents.bear import bear_node
    from agents.bull import bull_node
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

    print(f"[1/5] Analyst node ({ticker})...")
    state.update(analyst_node(state))
    print("[2/5] News hunter node...")
    state.update(news_hunter_node(state))
    print("[3/5] Bull node...")
    state.update(bull_node(state))
    print("[4/5] Bear node...")
    state.update(bear_node(state))
    print(f"[5/5] Debate node ({NUM_REBUTTAL_ROUNDS} rebuttal rounds)...\n")
    state.update(debate_node(state))

    print("=" * 70)
    print("OPENING STATEMENTS")
    print("=" * 70)
    print("\n--- BULL (opening) ---")
    print(state["bull_case"])
    print("\n--- BEAR (opening) ---")
    print(state["bear_case"])

    for rd in state["debate_rounds"]:
        print("\n" + "=" * 70)
        print(f"REBUTTAL ROUND {rd.round_number}")
        print("=" * 70)
        print(f"\n--- BULL (round {rd.round_number}) ---")
        print(rd.bull_argument)
        print(f"\n--- BEAR (round {rd.round_number}) ---")
        print(rd.bear_argument)
