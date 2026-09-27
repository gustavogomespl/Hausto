# Imagem da API do agente de fatura (FastAPI + LangChain create_agent). Pronta para Cloud Run:
# escuta em $PORT (padrão 8080), roda sem root e não carrega segredo nenhum (tudo via ambiente).

FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim AS deps
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Web app (React + Vite): só o build estático vai para a imagem final.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-trixie
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FONTE_DADOS=mock \
    LOG_FORMATO=json
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin agente
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY main.py ./
COPY app ./app
COPY data ./data
COPY --from=web /web/dist ./web/dist
USER 10001:10001
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
