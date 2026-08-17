FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DEMO_READ_ONLY=true \
    LLM_PROVIDER=mock

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/instance

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "evalbench:create_app()"]
