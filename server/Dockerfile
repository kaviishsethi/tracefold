# Tracefold engine. Runs on a private network; every request needs a client token.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.9.25 && apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 tracefold
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY tracefold ./tracefold
RUN uv sync --frozen --no-dev && mkdir -p /data && chown tracefold /data
USER tracefold
ENV TRACEFOLD_DATA=/data TRACEFOLD_HOST=0.0.0.0 TRACEFOLD_PORT=8787 PATH="/app/.venv/bin:$PATH"
VOLUME ["/data"]
EXPOSE 8787
# Keys (EXA_API_KEY / TAVILY_API_KEY, AWS remediation) come from the environment or /data/.env.
ENV TRACEFOLD_ENV_FILE=/data/.env
CMD ["tracefold", "serve"]
