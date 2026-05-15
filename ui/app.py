"""Streamlit entry-point for TB's Personal Stock Guru.

Run with:
    uv run streamlit run ui/app.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Resolve project root so imports work when launched from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import streamlit as st

st.set_page_config(
    page_title="Stock Guru",
    page_icon="📈",
    layout="wide",
)

from agents.graph import build_graph
from memory.store import build_store
from ui.components import (
    render_analyst_findings,
    render_archive_page,
    render_debate,
    render_investment_memo,
    render_news_findings,
    render_portfolio_page,
    render_research_plan,
    render_settings_page,
)
from ui.streaming import run_research

# ---------------------------------------------------------------------------
# Shared graph + store  (cached: survives reruns, shared across browser tabs)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent / "data"
_MEM_PATH = _DATA_DIR / "memory.db"


@st.cache_resource
def _get_graph_and_store():
    """Build (once) the LangGraph graph and the long-term SqliteStore."""
    _DATA_DIR.mkdir(exist_ok=True)
    store = build_store(_MEM_PATH)
    g = build_graph(store=store)
    return g, store


# ---------------------------------------------------------------------------
# Session-state defaults
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    defaults: dict = {
        "research_running": False,   # True while graph.stream() is running
        "research_done":    False,   # True after a run completes
        "last_ticker":      "",      # Ticker of the most recent run
        "thread_id":        "",      # LangGraph checkpoint thread id
        "rs":               {},      # Accumulated ResearchState output fields
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------

_init_session_state()
graph, store = _get_graph_and_store()

tab_research, tab_portfolio, tab_archive, tab_settings = st.tabs(
    ["🔬 Research", "💼 Portfolio", "📂 Archive", "⚙️ Settings"]
)

# ── Research tab ─────────────────────────────────────────────────────────────
with tab_research:
    st.header("Stock Research")

    # Input row
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        ticker_input = st.text_input(
            "Ticker symbol",
            placeholder="e.g. NVDA",
            label_visibility="collapsed",
            disabled=st.session_state.research_running,
        )
    with col_btn:
        run_clicked = st.button(
            "▶ Run Research",
            use_container_width=True,
            type="primary",
            disabled=st.session_state.research_running,
        )

    st.divider()

    # ── Kick off a new run ────────────────────────────────────────────────
    if run_clicked and ticker_input.strip():
        ticker = ticker_input.strip().upper()
        st.session_state.research_running = True
        st.session_state.research_done    = False
        st.session_state.last_ticker      = ticker
        st.session_state.rs               = {}
        st.session_state.thread_id = (
            f"ui-{ticker}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        st.rerun()

    # ── Active run — drive the stream ─────────────────────────────────────
    if st.session_state.research_running:
        ticker    = st.session_state.last_ticker
        config    = {"configurable": {"thread_id": st.session_state.thread_id}}
        st.info(f"🔄 Running research on **{ticker}** — this takes a minute or two …")
        run_research(ticker, graph, config)
        st.rerun()  # clean render from session state

    # ── Completed run — render all sections from session state ────────────
    elif st.session_state.research_done:
        rs     = st.session_state.rs
        ticker = st.session_state.last_ticker

        st.success(f"✅ Research complete for **{ticker}**")

        if rs.get("plan"):
            render_research_plan(rs["plan"])

        if rs.get("analyst_findings"):
            render_analyst_findings(rs["analyst_findings"])

        if rs.get("news_findings"):
            render_news_findings(rs["news_findings"])

        if rs.get("bull_case") or rs.get("bear_case") or rs.get("debate_rounds"):
            render_debate(
                rs.get("bull_case", ""),
                rs.get("bear_case", ""),
                rs.get("debate_rounds", []),
            )

        if rs.get("final_memo"):
            render_investment_memo(rs["final_memo"])

    # ── Idle state ────────────────────────────────────────────────────────
    else:
        st.markdown(
            "_Enter a ticker above and click **▶ Run Research** to start a new analysis._"
        )

# ── Portfolio tab ─────────────────────────────────────────────────────────────
with tab_portfolio:
    render_portfolio_page(store)

# ── Archive tab ───────────────────────────────────────────────────────────────
with tab_archive:
    render_archive_page(store)

# ── Settings tab ─────────────────────────────────────────────────────────────
with tab_settings:
    render_settings_page(store)
