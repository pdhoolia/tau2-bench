# The tau2-bench MCP servers as an image: the unified server on :8000, the airline,
# retail, telecom and legal domains at /mcp/<domain>, one world per MCP session
# (src/tau2/mcp/worlds.py). Built by Strata's `tau2` compose profile; runs on its own:
#
#   docker build -t tau2-mcp . && docker run -p 8000:8000 tau2-mcp
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Dependencies first, so a source change does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra mcp --no-install-project

COPY src ./src
# The data directory is found next to the source tree (tau2.utils.utils.DATA_DIR);
# only the four served domains are copied.
COPY data/tau2/domains/airline ./data/tau2/domains/airline
COPY data/tau2/domains/retail ./data/tau2/domains/retail
COPY data/tau2/domains/telecom ./data/tau2/domains/telecom
COPY data/tau2/domains/legal ./data/tau2/domains/legal
RUN uv sync --frozen --no-dev --extra mcp

ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8000
CMD ["python", "-m", "tau2.mcp.unified_server", "--host", "0.0.0.0", "--port", "8000"]
