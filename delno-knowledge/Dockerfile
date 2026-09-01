FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY brain_platform ./brain_platform

ENV PYTHONPATH=/app
ENV BRAIN_ENABLED=true
ENV BRAIN_DATA_DIR=/data
ENV BRAIN_DB_PATH=/data/brain.db
ENV BRAIN_ALLOW_LOCAL_INGEST=true
ENV BRAIN_STORE=sqlite
ENV BRAIN_VECTOR_BACKEND=sqlite_json

RUN mkdir -p /data /app/vault

EXPOSE 8021

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8021"]
