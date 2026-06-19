FROM python:3.11-slim-bookworm

LABEL maintainer=""
LABEL description="RAG Telegram Bot (aiogram3)"
LABEL version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

RUN mkdir -p /app/data/embeddings /app/logs /app/.cache && \
    chown -R appuser:appuser /app

USER appuser

VOLUME ["/app/data", "/app/logs"]

EXPOSE 8080

CMD ["python", "main.py"]
