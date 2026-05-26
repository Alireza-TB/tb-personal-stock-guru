# ── TB Personal Stock Guru ─────────────────────────────────────────────────
# Base: python:3.12-slim + uv + Node.js (for Notion MCP server via npx)
# .env is NOT bundled — mount it at runtime via docker-compose env_file.
# ───────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System deps + Node.js ──────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Install uv (official installer) ───────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# ── Project setup ──────────────────────────────────────────────────────────
WORKDIR /app

# Copy lockfiles first so dependency layer is cached independently of source
COPY pyproject.toml uv.lock ./

# Sync dependencies into the project venv (frozen = exact lock, no dev deps)
RUN uv sync --frozen --no-dev

# Copy the rest of the source (excluding everything in .dockerignore)
COPY . .

# data/ is mounted at runtime; pre-create so the directory always exists
RUN mkdir -p /app/data

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "ui/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
