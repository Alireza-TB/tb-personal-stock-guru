"""Reusable Streamlit render functions for each data model.

All functions are pure renderers: they take data objects and call st.X() calls.
They do not read or write session state.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Markdown / LaTeX escape helper
# ---------------------------------------------------------------------------

def escape_streamlit(text: str) -> str:
    """Escape characters that Streamlit's markdown renderer misinterprets in prose.

    Covers:
    * ``$`` → ``\\$``   prevents LaTeX math-mode (e.g. "$875.1 billion")
    * ``_`` between word chars → ``\\_``  prevents accidental italics in
      identifiers / ticker symbols (e.g. "NET_INCOME")
    * ``*`` adjacent to a digit → ``\\*``  prevents italic/bold in numeric
      expressions (e.g. "2*revenue" or "5x*")
    """
    if not text:
        return text
    # Dollar signs — highest priority, always escape
    text = text.replace("$", r"\$")
    # Underscores flanked by word characters (e.g. TICKER_SYMBOL)
    text = re.sub(r'(?<=\w)_(?=\w)', r'\\_', text)
    # Asterisks directly adjacent to digits (numeric multipliers / footnotes)
    text = re.sub(r'(?<=\d)\*|\*(?=\d)', r'\\*', text)
    return text


# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------

_REC_COLORS = {
    "Buy":   "#1a7f4b",
    "Hold":  "#b07000",
    "Avoid": "#a82020",
    "Pass":  "#555555",
}
_SENTIMENT_COLORS = {
    "positive": "#1a7f4b",
    "neutral":  "#555555",
    "negative": "#a82020",
    "mixed":    "#b07000",
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _badge(text: str, color: str) -> str:
    """Return an HTML inline badge span."""
    return (
        f'<span style="background:{color};color:#fff;padding:3px 11px;'
        f'border-radius:4px;font-weight:700;font-size:0.92em">'
        f'{html.escape(text)}</span>'
    )


def _tinted_box(text: str, side: str) -> None:
    """Render a block of text in a lightly tinted left-bordered box.

    side: 'bull' → green tint  |  'bear' → red tint
    """
    if side == "bull":
        bg, border = "#f0fff4", "#48bb78"
    else:
        bg, border = "#fff5f5", "#fc8181"

    escaped = html.escape(text).replace("\n\n", "</p><p style='margin:0.4em 0'>").replace("\n", "<br>")
    st.markdown(
        f'<div style="background:{bg};border-left:4px solid {border};'
        f'padding:12px 14px;border-radius:4px;font-size:0.875em;line-height:1.6;'
        f'color:#1a1a1a;width:100%;box-sizing:border-box">'
        f'<p style="margin:0">{escaped}</p></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Research tab — individual finding renderers
# ---------------------------------------------------------------------------

def render_research_plan(plan: list[str]) -> None:
    with st.expander("Research Plan", expanded=False):
        for i, step in enumerate(plan, 1):
            st.markdown(f"**{i}.** {step}")


def render_analyst_findings(findings) -> None:
    st.subheader("Analyst Findings")
    st.markdown(escape_streamlit(findings.summary))

    col_s, col_w = st.columns(2)
    with col_s:
        st.markdown("**Strengths**")
        for s in findings.strengths:
            st.markdown(f"+ {escape_streamlit(s)}")
    with col_w:
        st.markdown("**Weaknesses**")
        for w in findings.weaknesses:
            st.markdown(f"- {escape_streamlit(w)}")

    if findings.key_metrics:
        import pandas as pd
        rows = [
            {"Metric": k, "Value": str(v) if v is not None else "—"}
            for k, v in findings.key_metrics.items()
        ]
        st.dataframe(
            pd.DataFrame(rows).set_index("Metric"),
            use_container_width=True,
            hide_index=False,
        )

    with st.expander("Valuation Assessment", expanded=False):
        st.markdown(escape_streamlit(findings.valuation_assessment))


def render_news_findings(findings) -> None:
    st.subheader("News Findings")

    color = _SENTIMENT_COLORS.get(findings.sentiment, "#555")
    st.markdown(
        f'Sentiment: {_badge(findings.sentiment.upper(), color)}',
        unsafe_allow_html=True,
    )
    st.caption(escape_streamlit(findings.summary))
    st.markdown("")

    col_h, col_t = st.columns(2)
    with col_h:
        st.markdown("**Top Headlines**")
        for headline in findings.top_headlines:
            st.markdown(f"- {escape_streamlit(headline)}")
        if findings.key_catalysts:
            st.markdown("**Key Catalysts**")
            for c in findings.key_catalysts:
                st.markdown(f"+ {escape_streamlit(c)}")
    with col_t:
        st.markdown("**Themes**")
        tags_html = " ".join(
            f'<span style="background:#eef;border:1px solid #bbd;padding:2px 9px;'
            f'border-radius:12px;font-size:0.82em;display:inline-block;margin:2px;'
            f'color:#1a1a1a">'
            f'{html.escape(t)}</span>'
            for t in findings.themes
        )
        st.markdown(tags_html, unsafe_allow_html=True)


def render_debate(bull_case: str, bear_case: str, rounds: list) -> None:
    st.subheader("Analyst Debate")

    # Opening cases
    bc, br = st.columns(2)
    with bc:
        st.markdown("#### 🐂 Bull Opening")
        _tinted_box(bull_case or "*Not yet available.*", "bull")
    with br:
        st.markdown("#### 🐻 Bear Opening")
        _tinted_box(bear_case or "*Not yet available.*", "bear")

    # Rebuttal rounds
    for rd in rounds:
        st.markdown(f"---\n**Rebuttal Round {rd.round_number}**")
        rc1, rc2 = st.columns(2)
        with rc1:
            _tinted_box(rd.bull_argument, "bull")
        with rc2:
            _tinted_box(rd.bear_argument, "bear")


def render_investment_memo(memo) -> None:
    st.subheader("Investment Memo")

    rec_color = _REC_COLORS.get(memo.recommendation, "#555")
    dots = "●" * memo.conviction + "○" * (5 - memo.conviction)

    st.markdown(
        f'{_badge(memo.recommendation, rec_color)}'
        f'&nbsp;&nbsp;<span style="font-size:1.15em;letter-spacing:2px;color:#333">{dots}</span>'
        f'&nbsp;&nbsp;<span style="color:#777;font-size:0.9em">conviction {memo.conviction}/5'
        f' &nbsp;·&nbsp; {memo.time_horizon.capitalize()} horizon</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.markdown(f"**Thesis:** {escape_streamlit(memo.thesis)}")
    st.markdown("")

    col_c, col_r = st.columns(2)
    with col_c:
        st.markdown("**Catalysts**")
        for c in memo.catalysts:
            st.markdown(f"+ {escape_streamlit(c)}")
    with col_r:
        st.markdown("**Key Risks**")
        for r in memo.key_risks:
            st.markdown(f"- {escape_streamlit(r)}")

    with st.expander("Full Narrative", expanded=False):
        st.markdown(escape_streamlit(memo.narrative))

    # Action links row — Notion save and/or LangSmith trace
    notion_url = getattr(memo, "notion_url", None)
    trace_url  = st.session_state.get("rs", {}).get("trace_url")
    if notion_url or trace_url:
        link_cols = st.columns(len([u for u in (notion_url, trace_url) if u]))
        col_idx = 0
        if notion_url:
            with link_cols[col_idx]:
                st.link_button("📝 Open in Notion", notion_url)
            col_idx += 1
        if trace_url:
            with link_cols[col_idx]:
                st.link_button("🔍 View LangSmith trace", trace_url)


# ---------------------------------------------------------------------------
# Portfolio tab
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _fetch_price_data(ticker: str) -> tuple[float | None, float | None, list[float]]:
    """Cached yfinance fetch.  Returns (current_price, pct_change_today, closes)."""
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if hist.empty:
            return None, None, []
        if hist.index.tzinfo:
            hist.index = hist.index.tz_localize(None)
        closes = [round(float(v), 2) for v in hist["Close"].tolist()]
        current = closes[-1]
        prev    = closes[-2] if len(closes) > 1 else current
        pct     = round((current - prev) / prev * 100, 2) if prev else 0.0
        return current, pct, closes
    except Exception:
        return None, None, []


def _sparkline(prices: list[float], positive: bool) -> go.Figure:
    color      = "#1a7f4b" if positive else "#a82020"
    fill_color = "rgba(26,127,75,0.12)" if positive else "rgba(168,32,32,0.12)"
    fig = go.Figure(
        go.Scatter(
            y=prices, mode="lines",
            line=dict(color=color, width=1.5),
            fill="tozeroy", fillcolor=fill_color,
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False),
        height=70, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_portfolio_page(store) -> None:
    from memory.store import get_user_profile

    st.header("Portfolio")
    profile  = get_user_profile(store)
    holdings = profile.holdings

    if not holdings:
        st.info("No holdings configured. Add tickers in the **Settings** tab.")
        return

    cols_per_row = 3
    for row_start in range(0, len(holdings), cols_per_row):
        row_tickers = holdings[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, ticker in zip(cols, row_tickers):
            with col:
                price, pct, closes = _fetch_price_data(ticker)
                if price is None:
                    st.warning(f"**{ticker}** — data unavailable")
                    continue
                arrow = "▲" if (pct or 0) >= 0 else "▼"
                pct_color = "#1a7f4b" if (pct or 0) >= 0 else "#a82020"
                st.markdown(f"**{ticker}**")
                st.markdown(
                    f"<span style='font-size:1.25em'>${price:,.2f}</span>"
                    f"&nbsp;<span style='color:{pct_color};font-size:0.9em'>"
                    f"{arrow} {abs(pct or 0):.2f}%</span>",
                    unsafe_allow_html=True,
                )
                if closes:
                    fig = _sparkline(closes, (pct or 0) >= 0)
                    st.plotly_chart(
                        fig, use_container_width=True,
                        config={"displayModeBar": False},
                    )
                st.markdown("---")


# ---------------------------------------------------------------------------
# Archive tab
# ---------------------------------------------------------------------------

def render_archive_page(store) -> None:
    from memory.store import get_memo_history, list_all_tickers

    st.header("Research Archive")
    tickers = list_all_tickers(store)

    if not tickers:
        st.info("No research history yet. Run research on a ticker to see it here.")
        return

    # Filters
    f1, f2 = st.columns(2)
    with f1:
        filter_ticker = st.selectbox("Filter by ticker", ["All"] + tickers, key="arc_ticker")
    with f2:
        filter_rec = st.selectbox(
            "Filter by recommendation", ["All", "Buy", "Hold", "Avoid", "Pass"],
            key="arc_rec",
        )

    # Collect
    search_tickers = tickers if filter_ticker == "All" else [filter_ticker]
    rows: list[tuple[str, object]] = []
    for t in search_tickers:
        for memo in get_memo_history(store, t, limit=20):
            rows.append((t, memo))

    if filter_rec != "All":
        rows = [(t, m) for t, m in rows if m.recommendation == filter_rec]

    if not rows:
        st.info("No memos match the current filters.")
        return

    st.caption(f"{len(rows)} memo(s)")

    for ticker, memo in rows:
        rec_color = _REC_COLORS.get(memo.recommendation, "#555")
        dots = "●" * memo.conviction + "○" * (5 - memo.conviction)
        label = f"{ticker}  ·  {memo.recommendation}  ·  {dots}  ·  {memo.time_horizon}"
        with st.expander(label, expanded=False):
            render_investment_memo(memo)


# ---------------------------------------------------------------------------
# Settings tab
# ---------------------------------------------------------------------------

def render_settings_page(store) -> None:
    from memory.store import get_user_profile, update_user_profile

    st.header("Settings")
    profile = get_user_profile(store)

    _KNOWN_SECTORS = [
        "tech", "energy", "healthcare", "finance", "consumer",
        "industrials", "utilities", "real estate", "materials",
    ]
    all_sectors = sorted(set(_KNOWN_SECTORS) | set(profile.sectors_of_interest))

    with st.form("user_profile_form"):
        risk = st.selectbox(
            "Risk tolerance",
            ["conservative", "moderate", "aggressive"],
            index=["conservative", "moderate", "aggressive"].index(profile.risk_tolerance),
        )
        sectors = st.multiselect(
            "Sectors of interest",
            options=all_sectors,
            default=[s for s in profile.sectors_of_interest if s in all_sectors],
        )
        holdings_str = st.text_input(
            "Holdings (comma-separated tickers)",
            value=", ".join(profile.holdings),
            help="e.g.  AAPL, MSFT, NVDA",
        )
        notes = st.text_area(
            "Investment notes / preferences",
            value=profile.notes,
            height=110,
        )

        if st.form_submit_button("Save Profile", use_container_width=True):
            holdings_list = [
                h.strip().upper() for h in holdings_str.split(",") if h.strip()
            ]
            update_user_profile(
                store,
                risk_tolerance=risk,
                sectors_of_interest=sectors,
                holdings=holdings_list,
                notes=notes,
            )
            st.success("Profile saved!")
            st.rerun()
