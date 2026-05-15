"""Drive graph.stream() and progressively render results into Streamlit placeholders.

run_research() is called during the "research_running" phase.  It:
  1. Creates one st.status() per node (all start as "running" / spinner).
  2. Creates st.empty() placeholders for each result section.
  3. Iterates graph.stream() — for each completed node it marks the status
     complete and updates the relevant placeholder.
  4. Merges every node output into st.session_state.rs (skipping "messages").
  5. Sets research_running=False / research_done=True when the stream ends.
     The caller should call st.rerun() immediately after to get the clean render.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from ui.components import (
    render_analyst_findings,
    render_debate,
    render_investment_memo,
    render_news_findings,
    render_research_plan,
)

# ---------------------------------------------------------------------------
# Node metadata
# ---------------------------------------------------------------------------

NODE_ORDER = [
    "planner",
    "analyst",
    "news_hunter",
    "bull",
    "bear",
    "debate",
    "portfolio_manager",
    "archive",
]

NODE_LABELS: dict[str, str] = {
    "planner":           "📋 Research Plan",
    "analyst":           "🔬 Fundamental Analyst",
    "news_hunter":       "📰 News Hunter",
    "bull":              "🐂 Bull Case",
    "bear":              "🐻 Bear Case",
    "debate":            "⚔️ Analyst Debate",
    "portfolio_manager": "📊 Portfolio Manager",
    "archive":           "💾 Saving to Archive",
}


# ---------------------------------------------------------------------------
# Main streaming driver
# ---------------------------------------------------------------------------

def run_research(ticker: str, graph, config: dict) -> None:  # noqa: ANN001
    """Stream the research graph and progressively update the UI.

    Modifies ``st.session_state.rs`` in-place as results arrive.
    Sets ``st.session_state.research_running = False`` and
    ``st.session_state.research_done = True`` before returning.
    """
    initial_state = {
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

    # ── Status indicators — one per node, all start as running ─────────────
    statuses: dict[str, st.delta_generator.DeltaGenerator] = {}  # type: ignore[name-defined]
    for node in NODE_ORDER:
        statuses[node] = st.status(
            f"⏳ {NODE_LABELS[node]} …",
            state="running",
            expanded=False,
        )

    # ── Progressive-render placeholders ────────────────────────────────────
    plan_ph    = st.empty()
    analyst_ph = st.empty()
    news_ph    = st.empty()
    debate_ph  = st.empty()
    memo_ph    = st.empty()

    # ── Stream loop (wrapped in @traceable for LangSmith observability) ─────
    rs: dict = st.session_state.rs  # mutable alias — mutations are reflected

    @traceable(name=f"stock-guru/{ticker}", run_type="chain")
    def _stream_and_render() -> None:
        """Run graph.stream() inside a LangSmith trace context.

        Being inside @traceable means:
        - langchain-core's LangChainTracer detects get_current_run_tree() and
          nests all LangGraph node spans as children of this root run.
        - We can call get_current_run_tree().get_url() at the end to surface
          the trace link in the UI.
        """
        try:
            for chunk in graph.stream(initial_state, config=config):
                # Guard: LangGraph occasionally emits None or non-dict chunks
                if not isinstance(chunk, dict):
                    continue

                for node_name, output in chunk.items():
                    # Guard: some node outputs can be None (e.g. archive → {})
                    if not isinstance(output, dict):
                        continue

                    # Mark the node status complete
                    label = NODE_LABELS.get(node_name, node_name)
                    if node_name in statuses:
                        statuses[node_name].update(
                            label=f"✅ {label}",
                            state="complete",
                            expanded=False,
                        )

                    # Merge output into shared session-state dict
                    # (skip "messages" — add_messages reducer, not rendered)
                    for k, v in output.items():
                        if k != "messages":
                            rs[k] = v

                    # ── Progressive rendering ────────────────────────────
                    if node_name == "planner" and rs.get("plan"):
                        with plan_ph.container():
                            render_research_plan(rs["plan"])

                    elif node_name == "analyst" and rs.get("analyst_findings"):
                        with analyst_ph.container():
                            render_analyst_findings(rs["analyst_findings"])

                    elif node_name == "news_hunter" and rs.get("news_findings"):
                        with news_ph.container():
                            render_news_findings(rs["news_findings"])

                    elif node_name == "bear":
                        # Both bull_case and bear_case now available
                        with debate_ph.container():
                            render_debate(
                                rs.get("bull_case", ""),
                                rs.get("bear_case", ""),
                                [],  # rounds come after debate node
                            )

                    elif node_name == "debate":
                        with debate_ph.container():
                            render_debate(
                                rs.get("bull_case", ""),
                                rs.get("bear_case", ""),
                                rs.get("debate_rounds", []),
                            )

                    elif node_name == "portfolio_manager" and rs.get("final_memo"):
                        with memo_ph.container():
                            render_investment_memo(rs["final_memo"])

        except Exception as exc:  # noqa: BLE001
            # Surface the error as a readable banner rather than a raw traceback
            st.error(f"⚠️ Research pipeline error: {exc}")
            for status_obj in statuses.values():
                try:
                    status_obj.update(state="error", expanded=False)
                except Exception:
                    pass
            return  # exit _stream_and_render; finally block still runs

        # ── Capture LangSmith trace URL while still inside @traceable ────
        try:
            run_tree = get_current_run_tree()
            if run_tree is not None:
                rs["trace_url"] = run_tree.get_url()
        except Exception:
            pass  # silently skip — never fail the run over a missing link

    try:
        _stream_and_render()
    finally:
        # Always clear the running flag so the UI never stays locked
        st.session_state.research_running = False
        st.session_state.research_done    = True
