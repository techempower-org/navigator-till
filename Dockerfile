# Navigator Till: one container, one port. Builds on amd64 and arm64 (python:3.12-slim has both).
# Runtime env (all optional in mock mode): MOCK=1|0, PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_WEBHOOK_ID,
# NT_DB (default /data/navigator-till.db here; bind-mount /data), NT_DB_RETENTION_DAYS, NT_DESK_TOKEN,
# ANTHROPIC_API_KEY + NT_MODEL (offline parser/templates without them), NT_ORG, NT_ORG_EMAIL, NT_PRICING.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    NT_DB=/data/navigator-till.db MOCK=1 PORT=8077
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY navigator_till ./navigator_till
RUN pip install --no-cache-dir ".[ai]" && mkdir -p /data && chown 65534:65534 /data
USER 65534:65534
VOLUME ["/data"]
EXPOSE 8077
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8077/healthz', timeout=4).status==200 else 1)"
CMD ["sh", "-c", "uvicorn navigator_till.app:app --host 0.0.0.0 --port ${PORT}"]
