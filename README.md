# TB's Personal Stock Guru

A multi-agent investment research desk powered by [LangGraph](https://github.com/langchain-ai/langgraph) and Claude.

## Project layout

```
.
├── agents/     # LangGraph agent definitions
├── tools/      # Custom tools (market data, SEC filings, web search, …)
├── state/      # Shared graph state schemas (Pydantic)
├── ui/         # Streamlit front-end
├── data/       # Local data downloads (git-ignored)
└── tests/      # Pytest test suite
```

## Quickstart

```bash
# 1. Copy and fill in your API keys
cp .env.example .env

# 2. Install dependencies (uv resolves & syncs automatically)
uv sync

# 3. Run the Streamlit app
uv run streamlit run ui/app.py
```

## Required API keys

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |
| `TAVILY_API_KEY` | https://tavily.com |
| `FINNHUB_API_KEY` | https://finnhub.io |
| `NEWSAPI_KEY` | https://newsapi.org |
