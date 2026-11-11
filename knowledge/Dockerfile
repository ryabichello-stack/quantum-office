FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py store.py __init__.py ./
COPY brain_platform ./brain_platform
COPY scripts ./scripts
COPY vault ./vault
COPY content ./content
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
 && mkdir -p /data \
 && PYTHONPATH=/app python3 -c "from pathlib import Path; from brain_platform.publish.export_monolith import export_monolith; print(export_monolith(vault=Path('vault/quantum-brain'), out_path=Path('content/quantum_labs.md')))"
ENV KNOWLEDGE_CONTENT_DIR=/app/content \
    BRAIN_VAULT_PATH=/app/vault/quantum-brain \
    BRAIN_DATA_DIR=/data \
    BRAIN_DB_PATH=/data/brain.db \
    BRAIN_AUTO_INGEST=true \
    KNOWLEDGE_READ_MODE=legacy
EXPOSE 8017
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8017"]
