FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DEMO_READ_ONLY=true \
    LLM_PROVIDER=mock \
    MAX_RUN_COST_USD=0 \
    PORT=8000 \
    WEB_CONCURRENCY=2

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --system --uid 10001 --no-create-home evalbench \
    && mkdir -p /app/instance \
    && chown evalbench:evalbench /app/instance
USER evalbench

EXPOSE 8000

# The demo database lives on the ephemeral filesystem and is rebuilt idempotently on every start.
CMD ["sh", "-c", "python -m evalbench.cli demo-seed && exec gunicorn --bind 0.0.0.0:${PORT} --threads 4 --timeout 120 --access-logfile - 'evalbench:create_app()'"]
