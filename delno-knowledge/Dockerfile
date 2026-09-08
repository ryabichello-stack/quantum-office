FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main_delno.py ./main.py
COPY brain_platform ./brain_platform
COPY vault ./vault
COPY docker-entrypoint.sh ./docker-entrypoint.sh

ENV PYTHONPATH=/app
ENV BRAIN_ENABLED=true
ENV BRAIN_DATA_DIR=/data
ENV BRAIN_DB_PATH=/data/brain.db
ENV BRAIN_ALLOW_LOCAL_INGEST=true
ENV BRAIN_STORE=sqlite
ENV BRAIN_VECTOR_BACKEND=sqlite_json
ENV BRAIN_DEMO_TENANT=delno-demo

RUN mkdir -p /data && chmod +x /app/docker-entrypoint.sh

EXPOSE 8021

CMD ["/app/docker-entrypoint.sh"]
